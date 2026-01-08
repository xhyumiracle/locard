"""
Anthropic Claude LLM client with unified retry and rate limit handling.

Provides ChatAnthropic wrapper with intelligent retry logic for transient errors.
"""

import logging
import time
from typing import Any
from langchain_anthropic import ChatAnthropic
from anthropic import RateLimitError, APIError, APIConnectionError, APITimeoutError

import config
from src.clients.base import retry_with_backoff, extract_retry_after_header

logger = logging.getLogger(__name__)


class ChatAnthropicWithRetry(ChatAnthropic):
    """ChatAnthropic subclass with enhanced retry logic for transient errors."""

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
                # Anthropic uses similar error codes to OpenAI
                if "overloaded" in error_str.lower():
                    # 529 overloaded_error - server is overloaded, retry with backoff
                    wait_time = None
                    if hasattr(e, 'response') and e.response:
                        wait_time = extract_retry_after_header(e.response.headers)
                        if wait_time:
                            logger.info(f"Using Retry-After header: {wait_time}s")
                    retry_with_backoff("Server overloaded", error_str, attempt, max_outer_attempts, wait_time)
                else:
                    # Standard rate limit (tokens/requests per minute) - retry with backoff
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
                # 503: Service Unavailable, 529: Overloaded
                if status_code in (500, 502, 503, 529):
                    retry_with_backoff(f"Server error {status_code}", error_str, attempt, max_outer_attempts)
                else:
                    # Non-retryable errors (4xx client errors, auth, schema validation, etc.)
                    # 400: Bad Request, 401: Unauthorized, 403: Forbidden, 404: Not Found
                    logger.error(f"Non-retryable API error (status {status_code}): {error_str}")
                    raise


def create_chat_anthropic_with_retry(
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    **kwargs
) -> ChatAnthropic:
    """
    Create ChatAnthropic instance with automatic retry for transient errors.

    Two-tier retry strategy:
    1. SDK built-in retry (max_retries=2): Handles short transient errors
    2. Outer retry wrapper: Handles persistent errors with longer waits (5s → 10s → 20s → 40s → 60s)

    Retries on:
    - RateLimitError: Rate limit exceeded (429)
    - APIError: Transient server errors (5xx, 529)
    - APIConnectionError: Network connection issues
    - APITimeoutError: Request timeout

    Timeout configuration:
    - Uses simple float timeout (in seconds)
    - Default: config.LLM_TIMEOUT (120s)

    Args:
        model: Model name (e.g., "claude-3-5-sonnet-20241022")
        temperature: Temperature (default: config.LLM_TEMPERATURE)
        max_tokens: Max tokens (default: config.LLM_MAX_TOKENS)
        **kwargs: Additional ChatAnthropic parameters

    Returns:
        ChatAnthropic instance with retry configured

    Example:
        llm = create_chat_anthropic_with_retry(model="claude-3-5-sonnet-20241022", temperature=0)
        llm_with_structured = llm.with_structured_output(MySchema)
    """
    return ChatAnthropicWithRetry(
        model=model,  # Required for Anthropic
        temperature=temperature if temperature is not None else config.LLM_TEMPERATURE,
        max_tokens=max_tokens or config.LLM_MAX_TOKENS,
        max_retries=2,  # SDK handles short retries
        timeout=config.LLM_TIMEOUT,  # Simple float timeout in seconds
        **kwargs
    )
