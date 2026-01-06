"""
LLM utilities with unified retry and rate limit handling.

Provides helper functions for creating LLM instances with intelligent retry logic.
"""

import logging
import time
from functools import wraps
from typing import Any
from langchain_openai import ChatOpenAI
from openai import RateLimitError, APIError

import config

logger = logging.getLogger(__name__)


class ChatOpenAIWithRetry(ChatOpenAI):
    """ChatOpenAI subclass with enhanced retry logic for persistent rate limits."""

    def invoke(self, *args, **kwargs) -> Any:
        """
        Invoke with two-tier retry strategy:
        1. SDK built-in retry (max_retries=2): Handles short transient errors
        2. Outer retry loop: Handles persistent rate limits with longer waits

        Distinguishes between retryable and non-retryable rate limit errors:
        - Retryable: TPM/RPM rate limits (wait and retry)
        - Non-retryable: Request too large, quota exceeded (raise immediately)
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
                if attempt == max_outer_attempts - 1:
                    logger.error(f"Rate limit exceeded after {max_outer_attempts} attempts")
                    raise

                # Try to extract Retry-After from exception or response
                wait_time = None
                if hasattr(e, 'response') and e.response:
                    # Check for Retry-After header
                    retry_after = e.response.headers.get('retry-after')
                    if retry_after:
                        try:
                            wait_time = float(retry_after)
                            logger.info(f"Using Retry-After header: {wait_time}s")
                        except ValueError:
                            pass

                    # Fallback: parse x-ratelimit-reset-tokens (e.g., "33.519s")
                    if not wait_time:
                        reset_tokens = e.response.headers.get('x-ratelimit-reset-tokens', '')
                        if reset_tokens.endswith('s'):
                            try:
                                wait_time = float(reset_tokens.rstrip('s'))
                                logger.info(f"Using x-ratelimit-reset-tokens: {wait_time}s")
                            except ValueError:
                                pass

                # Fallback to exponential backoff if no header info
                if not wait_time:
                    wait_time = min(5 * (2 ** attempt), 60)
                    logger.info(f"No Retry-After header, using exponential backoff: {wait_time}s")

                # Cap at 2 minutes to avoid excessive waits
                wait_time = min(wait_time, 120)

                logger.warning(
                    f"Rate limited (attempt {attempt + 1}/{max_outer_attempts}), "
                    f"waiting {wait_time:.1f}s before retry. Error: {error_str}"
                )
                time.sleep(wait_time)
            except APIError as e:
                error_str = str(e)
                status_code = getattr(e, 'status_code', None)

                # Whitelist: Only retry transient 5xx server errors
                # 500: Internal Server Error
                # 502: Bad Gateway
                # 503: Service Unavailable
                # 504: Gateway Timeout
                if status_code in (500, 502, 503, 504):
                    if attempt == max_outer_attempts - 1:
                        logger.error(f"Server error after {max_outer_attempts} attempts")
                        raise

                    wait_time = min(5 * (2 ** attempt), 60)
                    logger.warning(
                        f"Server error {status_code} (attempt {attempt + 1}/{max_outer_attempts}), "
                        f"waiting {wait_time}s before retry. Error: {error_str}"
                    )
                    time.sleep(wait_time)
                else:
                    # Non-retryable errors (4xx client errors, auth, schema validation, etc.)
                    # 400: Bad Request (schema errors, invalid params)
                    # 401: Unauthorized (auth errors)
                    # 403: Forbidden
                    # 404: Not Found
                    logger.error(f"Non-retryable API error (status {status_code}): {error_str}")
                    raise


def create_chat_openai_with_retry(
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    **kwargs
) -> ChatOpenAI:
    """
    Create ChatOpenAI instance with automatic retry for rate limits.

    Two-tier retry strategy:
    1. SDK built-in retry (max_retries=2): Handles short transient errors (0.8s → 1.6s)
    2. Outer retry wrapper: Handles persistent rate limits with longer waits (5s → 10s → 20s → 40s → 60s)

    Retries on:
    - RateLimitError: Rate limit exceeded (429)
    - APIError: Transient API errors (5xx)

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
    return ChatOpenAIWithRetry(
        model=model or config.LLM_MODEL,
        temperature=temperature if temperature is not None else config.LLM_TEMPERATURE,
        max_tokens=max_tokens or config.LLM_MAX_TOKENS,
        max_retries=2,  # SDK handles short retries (0.8s → 1.6s)
        timeout=config.LLM_TIMEOUT,
        **kwargs
    )
