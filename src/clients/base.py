"""
Base classes and utilities for blockchain tools.
"""

import time
import logging
import json
import hashlib
import ssl
from pathlib import Path
from typing import Any, Callable, TypeVar, Optional, Dict
from functools import wraps

import httpx

import config

logger = logging.getLogger(__name__)

# File cache settings
CACHE_DIR = Path(".cache/api")
CACHE_ENABLED = True  # Set to False to disable caching


def cached(source: str = "default", model: type = None):
    """
    Decorator for caching function results to local files.

    Automatically generates cache key from function name and all arguments.
    Works with both regular functions and methods.
    Supports Pydantic models via the `model` parameter.

    Args:
        source: Cache namespace (e.g., "electrs-doge", "binance")
        model: Optional Pydantic model class for deserializing cached data

    Usage:
        @cached("my-api")
        def fetch_data(id: str) -> dict:
            return {"result": ...}

        @cached("my-api", model=MyModel)
        def fetch_model(id: str) -> MyModel:
            return MyModel(...)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            if not CACHE_ENABLED:
                return func(*args, **kwargs)

            # Build cache key from function name and all arguments
            # Skip 'self' for methods
            cache_args = args[1:] if args and hasattr(args[0], '__class__') else args
            key_parts = [func.__name__]
            key_parts.extend(str(a) for a in cache_args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)

            # Generate file path
            key_hash = hashlib.md5(cache_key.encode()).hexdigest()
            cache_dir = CACHE_DIR / source
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / f"{key_hash}.json"

            # Try read from cache
            if cache_path.exists():
                try:
                    with open(cache_path, "r") as f:
                        data = json.load(f)
                        logger.debug(f"Cache hit: {source}/{func.__name__}")
                        # Deserialize to model if specified
                        if model is not None:
                            return model(**data)
                        return data
                except (json.JSONDecodeError, IOError):
                    pass

            # Call function and cache result
            result = func(*args, **kwargs)

            # Don't cache empty results (empty list, empty dict, None)
            if result is None or result == [] or result == {}:
                logger.debug(f"Cache skip (empty result): {source}/{func.__name__}")
                return result

            # Serialize for caching
            try:
                # Handle Pydantic models
                if hasattr(result, 'model_dump'):
                    cache_data = result.model_dump()
                else:
                    cache_data = result

                with open(cache_path, "w") as f:
                    json.dump(cache_data, f)
                logger.debug(f"Cache write: {source}/{func.__name__}")
            except (IOError, TypeError) as e:
                logger.debug(f"Cache skip (not serializable): {e}")

            return result
        return wrapper
    return decorator


T = TypeVar("T")

# Global rate limit tracker - for statistics and debugging
_rate_limit_tracker: Dict[str, int] = {}


def calculate_backoff_time(
    attempt: int,
    base: float = config.TOOL_RETRY_BACKOFF_BASE,
    max_wait: float = 60.0
) -> float:
    """
    Calculate exponential backoff wait time.

    Args:
        attempt: Current attempt number (0-indexed)
        base: Backoff base (default from config.TOOL_RETRY_BACKOFF_BASE)
        max_wait: Maximum wait time in seconds (default 60s)

    Returns:
        Wait time in seconds: min(base^attempt, max_wait)

    Example:
        - attempt=0, base=2: 1s   (2^0)
        - attempt=1, base=2: 2s   (2^1)
        - attempt=2, base=2: 4s   (2^2)
        - attempt=3, base=2: 8s   (2^3)
        - attempt=4, base=5: 25s  (5^2, with base=5 from LLM)
        - attempt=5, base=5: 60s  (capped at max_wait)
    """
    return min(base ** attempt, max_wait)


def extract_retry_after_header(headers: Dict[str, str]) -> Optional[float]:
    """
    Extract Retry-After wait time from HTTP headers (RFC 7231).

    Supports:
    - Retry-After: 120 (seconds as integer)
    - Retry-After: 33.5 (seconds as float)
    - x-ratelimit-reset-tokens: 33.519s (OpenAI custom format)

    Args:
        headers: HTTP response headers dict

    Returns:
        Wait time in seconds if found, None otherwise

    Example:
        >>> extract_retry_after_header({'retry-after': '60'})
        60.0
        >>> extract_retry_after_header({'Retry-After': '33.5'})
        33.5
        >>> extract_retry_after_header({'x-ratelimit-reset-tokens': '33.519s'})
        33.519
        >>> extract_retry_after_header({})
        None
    """
    # Standard HTTP Retry-After header (case-insensitive)
    retry_after = headers.get('retry-after') or headers.get('Retry-After')
    if retry_after:
        try:
            return float(retry_after)
        except (ValueError, TypeError):
            # Retry-After might be HTTP-date format, not supported yet
            pass

    # OpenAI custom header: x-ratelimit-reset-tokens (e.g., "33.519s")
    reset_tokens = headers.get('x-ratelimit-reset-tokens', '')
    if reset_tokens.endswith('s'):
        try:
            return float(reset_tokens.rstrip('s'))
        except (ValueError, TypeError):
            pass

    return None


class TransientError(Exception):
    """
    Retryable error (timeout, rate limit, 5xx).

    Attributes:
        retry_after: Optional suggested wait time in seconds (from Retry-After header)
    """
    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class FatalError(Exception):
    """Non-retryable error (tx not found, invalid hash)."""
    pass


class QuotaExhaustedError(FatalError):
    """Fatal error when API quota is exhausted (e.g., daily/monthly limit reached)."""
    pass


def record_rate_limit(source: str) -> None:
    """
    Record a rate limit hit from a source for statistics.

    This only logs the occurrence for debugging purposes and does not stop execution.
    Individual retry logic (via with_retry decorator) handles transient rate limits.
    """
    _rate_limit_tracker[source] = _rate_limit_tracker.get(source, 0) + 1
    count = _rate_limit_tracker[source]
    logger.warning(f"Rate limit hit from {source} (total: {count} in this session)")


def clear_rate_limits() -> None:
    """Clear rate limit tracker (call when starting new session)."""
    _rate_limit_tracker.clear()


def with_retry(
    max_retries: int = config.TOOL_MAX_RETRIES,
    backoff_base: float = config.TOOL_RETRY_BACKOFF_BASE,
    transient_exceptions: tuple = (
        httpx.TimeoutException,
        httpx.ConnectError,      # Connection errors (DNS, refused, etc.)
        ssl.SSLError,            # SSL/TLS errors (may not be wrapped by httpx)
        TransientError           # Our custom transient errors (429, 5xx) from _handle_response
    )
) -> Callable:
    """
    Decorator for retrying tool calls with exponential backoff.

    Only retries transient errors; fatal errors propagate immediately.
    Uses whitelist approach - only known transient errors are retried.

    Note: httpx.HTTPStatusError is NOT in the whitelist because:
    - Most 4xx errors are fatal (400, 401, 403, 404)
    - API clients should use _handle_response() to classify HTTP errors into
      TransientError (429, 5xx) or FatalError (4xx) properly
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error: Optional[Exception] = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except transient_exceptions as e:
                    last_error = e
                    if attempt < max_retries:
                        # Check if TransientError has server-suggested retry_after
                        if isinstance(e, TransientError) and e.retry_after:
                            # Respect server's suggestion but cap to avoid hanging
                            wait_time = min(e.retry_after, config.RETRY_AFTER_MAX_WAIT)
                            logger.info(f"Using server-suggested Retry-After: {wait_time}s")
                        else:
                            # Use exponential backoff
                            wait_time = calculate_backoff_time(attempt, backoff_base)

                        logger.warning(
                            f"{func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                            f"Retrying in {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(f"{func.__name__} failed after {max_retries + 1} attempts")
                        raise TransientError(f"Max retries exceeded: {e}") from e
                except FatalError:
                    # Fatal errors should not be retried
                    raise

            # This should never be reached (all paths return or raise)
            # But keep as safety net - if we get here, last_error must exist
            raise TransientError(f"Retry loop exhausted: {last_error}") from last_error

        return wrapper
    return decorator


class LoggingHTTPClient:
    """Wrapper around httpx.Client that logs all requests."""

    def __init__(self, client: httpx.Client, source_name: str = "api"):
        self._client = client
        self._source = source_name

    def _build_full_url(self, url: str, params: Optional[Dict] = None) -> str:
        """Build full URL with query params for logging."""
        if not params:
            return url
        from urllib.parse import urlencode
        return f"{url}?{urlencode(params)}"

    def get(self, url: str, **kwargs) -> httpx.Response:
        full_url = self._build_full_url(url, kwargs.get("params"))
        logger.info(f"HTTP Request: GET {full_url}")
        return self._client.get(url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        full_url = self._build_full_url(url, kwargs.get("params"))
        logger.info(f"HTTP Request: POST {full_url}")
        return self._client.post(url, **kwargs)

    def __getattr__(self, name):
        # Delegate other methods to underlying client
        return getattr(self._client, name)


class BaseAPIClient:
    """Base class for blockchain API clients."""

    # Override in subclasses to identify the API source
    SOURCE_NAME = "unknown"

    def __init__(self, timeout: int = config.TOOL_TIMEOUT):
        # Add User-Agent to avoid API rejections (some services require it)
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; BlockchainClient/1.0)"
        }
        self._raw_client = httpx.Client(
            timeout=timeout,
            headers=headers,
            follow_redirects=True
        )
        self.client = LoggingHTTPClient(self._raw_client, self.SOURCE_NAME)

    def _handle_response(self, response: httpx.Response) -> dict:
        """
        Handle HTTP response, classifying errors we need to handle specially.

        Responsibility: Error classification ONLY. Does not perform retry or sleep.
        Retry logic is handled by @with_retry decorator.

        Classification strategy:
        - 429: Wrap as TransientError with retry_after metadata
        - 5xx: Wrap as TransientError (server errors are retryable)
        - Other 4xx: Let httpx.HTTPStatusError propagate (will NOT be retried)
        - Unknown: Let raise_for_status() handle it

        Raises:
            TransientError: Retryable errors (429 rate limit, 5xx server errors)
            httpx.HTTPStatusError: Client errors (4xx) - NOT retried
        """
        # 429 rate limit (transient - should retry with server-suggested wait time)
        if response.status_code == 429:
            record_rate_limit(self.SOURCE_NAME)
            # Extract Retry-After and attach to exception for @with_retry to use
            retry_after = extract_retry_after_header(response.headers)
            if retry_after:
                logger.debug(f"{self.SOURCE_NAME} rate limited - server suggests {retry_after}s")
            raise TransientError("Rate limit exceeded", retry_after=retry_after)

        # 5xx server errors (transient - should retry)
        if response.status_code >= 500:
            raise TransientError(f"Server error: {response.status_code}")

        # Success or other errors (4xx) - let httpx handle it
        # This will raise httpx.HTTPStatusError for 4xx, which is NOT in transient_exceptions
        response.raise_for_status()
        return response.json()

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
