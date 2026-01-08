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


class BlockchainAPIError(Exception):
    """Base exception for blockchain API errors."""
    pass


class TransientError(BlockchainAPIError):
    """Retryable error (timeout, rate limit, 5xx)."""
    pass


class FatalError(BlockchainAPIError):
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
        httpx.HTTPStatusError,   # HTTP 4xx/5xx errors
        ssl.SSLError,            # SSL/TLS errors (may not be wrapped by httpx)
        TransientError
    )
) -> Callable:
    """
    Decorator for retrying tool calls with exponential backoff.

    Only retries transient errors; fatal errors propagate immediately.
    Uses whitelist approach - only known transient errors are retried.
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
                        wait_time = backoff_base ** attempt
                        logger.warning(
                            f"{func.__name__} attempt {attempt + 1} failed: {e}. "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(f"{func.__name__} failed after {max_retries + 1} attempts")
                        raise TransientError(f"Max retries exceeded: {e}") from e
                except FatalError:
                    raise

            raise last_error or TransientError("Unknown error")

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
        """Handle HTTP response, raising appropriate exceptions."""
        if response.status_code == 400:
            # Bad request (invalid params, symbol not found) - don't retry
            raise FatalError(f"Bad request: {response.url}")
        if response.status_code == 404:
            raise FatalError(f"Resource not found: {response.url}")
        if response.status_code == 429:
            # Track rate limits and stop if too many
            record_rate_limit(self.SOURCE_NAME)

            # Check for Retry-After header (standard HTTP)
            retry_after = response.headers.get('retry-after') or response.headers.get('Retry-After')
            if retry_after:
                try:
                    wait_seconds = float(retry_after)
                    # Cap at 5 minutes to avoid hanging
                    wait_seconds = min(wait_seconds, 300)
                    logger.warning(
                        f"{self.SOURCE_NAME} rate limited - API suggests retry after {wait_seconds}s"
                    )
                    time.sleep(wait_seconds)
                    raise TransientError(f"Rate limit (waited {wait_seconds:.1f}s as suggested by API)")
                except (ValueError, TypeError):
                    # Retry-After might be HTTP-date format, ignore for now
                    pass

            raise TransientError("Rate limit exceeded")
        if response.status_code >= 500:
            raise TransientError(f"Server error: {response.status_code}")
        response.raise_for_status()
        return response.json()

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
