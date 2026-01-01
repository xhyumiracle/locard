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
        """
        max_outer_attempts = config.LLM_MAX_RETRIES

        for attempt in range(max_outer_attempts):
            try:
                return super().invoke(*args, **kwargs)
            except RateLimitError as e:
                if attempt == max_outer_attempts - 1:
                    # Last attempt failed, re-raise
                    logger.error(f"Rate limit exceeded after {max_outer_attempts} attempts")
                    raise

                # Exponential backoff: 5s → 10s → 20s → 40s → capped at 60s
                wait_time = min(5 * (2 ** attempt), 60)
                logger.warning(
                    f"Rate limited (attempt {attempt + 1}/{max_outer_attempts}), "
                    f"waiting {wait_time}s before retry. Error: {str(e)}"
                )
                time.sleep(wait_time)
            except APIError as e:
                # For 5xx errors, also retry with backoff
                if attempt == max_outer_attempts - 1:
                    logger.error(f"API error after {max_outer_attempts} attempts")
                    raise

                wait_time = min(5 * (2 ** attempt), 60)
                logger.warning(
                    f"API error (attempt {attempt + 1}/{max_outer_attempts}), "
                    f"waiting {wait_time}s before retry. Error: {str(e)}"
                )
                time.sleep(wait_time)


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
