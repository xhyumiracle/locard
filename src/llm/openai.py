"""
OpenAI LLM client with unified retry and rate limit handling.

Provides ChatOpenAI wrapper with intelligent retry logic for transient errors.
"""

import logging
import time
from functools import wraps
from typing import Any
from langchain_openai import ChatOpenAI
from openai import RateLimitError, APIError, APIConnectionError, APITimeoutError
import httpx

import config
from src.clients.base import retry_with_backoff, extract_retry_after_header

logger = logging.getLogger(__name__)


class ChatOpenAIWithRetry(ChatOpenAI):
    """ChatOpenAI subclass with enhanced retry logic for transient errors."""

    def invoke(self, *args, **kwargs) -> Any:
        """
        Invoke with two-tier retry strategy:
        1. SDK built-in retry (max_retries=2): Handles short transient errors
        2. Outer retry loop: Handles persistent errors with longer waits

        Retryable errors:
        - RateLimitError: TPM/RPM rate limits (wait and retry)
        - APIError: Transient server errors (5xx)
        - APIConnectionError: Network connection issues
        - APITimeoutError: Request timeout

        Non-retryable errors:
        - Request too large, quota exceeded (raise immediately)
        - Client errors (4xx): Bad request, auth, etc.
        """
        max_outer_attempts = config.LLM_MAX_RETRIES

        for attempt in range(max_outer_attempts):
            try:
                return super().invoke(*args, **kwargs)
            except RateLimitError as e:
                error_str = str(e)

                # Check if this is a non-retryable rate limit error
                # "Request too large" - input/output tokens exceed model limit
                if "Request too large" in error_str or "must be reduced" in error_str:
                    logger.error(f"Request too large for model: {error_str}")
                    raise ValueError(f"Request exceeds token limit: {error_str}") from e

                # "insufficient_quota" - account has no credits
                if "insufficient_quota" in error_str:
                    logger.error(f"Insufficient quota: {error_str}")
                    raise ValueError(f"API quota exceeded: {error_str}") from e

                # Unknown 429 error type - raise for investigation
                if "rate_limit_exceeded" not in error_str:
                    logger.error(f"Unknown 429 error: {error_str}")
                    raise ValueError(f"Unknown rate limit error: {error_str}") from e

                # Standard rate limit (TPM/RPM) - retry with backoff
                # Try to extract Retry-After from server response
                wait_time = None
                if hasattr(e, 'response') and e.response:
                    wait_time = extract_retry_after_header(e.response.headers)
                    if wait_time:
                        logger.info(f"Using Retry-After header: {wait_time}s")

                retry_with_backoff("Rate limit", error_str, attempt, max_outer_attempts, wait_time)
            except (APIConnectionError, APITimeoutError) as e:
                # Connection and timeout errors are transient - retry with backoff
                # IMPORTANT: Must catch these BEFORE APIError since they may inherit from it
                error_type = type(e).__name__
                error_str = str(e)
                retry_with_backoff(error_type, error_str, attempt, max_outer_attempts)
            except APIError as e:
                error_str = str(e)
                status_code = getattr(e, 'status_code', None)

                # Whitelist: Only retry transient 5xx server errors
                # 500: Internal Server Error, 502: Bad Gateway
                # 503: Service Unavailable, 504: Gateway Timeout
                if status_code in (500, 502, 503, 504):
                    retry_with_backoff(f"Server error {status_code}", error_str, attempt, max_outer_attempts)
                else:
                    # Non-retryable errors (4xx client errors, auth, schema validation, etc.)
                    # 400: Bad Request, 401: Unauthorized, 403: Forbidden, 404: Not Found
                    logger.error(f"Non-retryable API error (status {status_code}): {error_str}")
                    raise


def create_chat_openai_with_retry(
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    **kwargs
) -> ChatOpenAI:
    """
    Create ChatOpenAI instance with automatic retry for transient errors.

    Two-tier retry strategy:
    1. SDK built-in retry (max_retries=2): Handles short transient errors (0.8s → 1.6s)
    2. Outer retry wrapper: Handles persistent errors with longer waits (5s → 10s → 20s → 40s → 60s)

    Retries on:
    - RateLimitError: Rate limit exceeded (429)
    - APIError: Transient server errors (5xx)
    - APIConnectionError: Network connection issues
    - APITimeoutError: Request timeout

    Timeout configuration:
    - Uses httpx.Timeout for explicit timeout control
    - connect: 30s (time to establish connection)
    - read/write/pool: config.LLM_TIMEOUT (default 120s)

    Args:
        model: Model name (default: config.LLM_MODEL)
        temperature: Temperature (default: config.LLM_TEMPERATURE)
        max_tokens: Max tokens (default: config.LLM_MAX_TOKENS)
        **kwargs: Additional ChatOpenAI parameters

    Returns:
        ChatOpenAI instance with retry configured

    Example:
        llm = create_chat_openai_with_retry(temperature=0)
        llm_with_structured = llm.with_structured_output(MySchema)
    """
    # Create explicit timeout object with separate connect timeout
    # connect: 30s - time to establish connection (shorter, fails fast if unreachable)
    # read/write/pool: config.LLM_TIMEOUT - time for data transfer (longer, handles slow responses)
    timeout = httpx.Timeout(
        timeout=config.LLM_TIMEOUT,  # Default for read/write/pool
        connect=30.0  # Shorter connect timeout to fail fast
    )

    return ChatOpenAIWithRetry(
        model=model or config.LLM_MODEL,
        temperature=temperature if temperature is not None else config.LLM_TEMPERATURE,
        max_tokens=max_tokens or config.LLM_MAX_TOKENS,
        max_retries=2,  # SDK handles short retries (0.8s → 1.6s)
        timeout=timeout,
        **kwargs
    )
