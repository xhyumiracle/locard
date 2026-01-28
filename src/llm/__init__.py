"""
LLM service layer.

Provides LLM clients with retry logic and provider-specific implementations.
Supports multiple providers with automatic selection based on model name.
"""

import logging
from langchain_core.language_models import BaseChatModel

from .openai import (
    ChatOpenAIWithRetry,
    create_chat_openai_with_retry,
)
from .anthropic import (
    ChatAnthropicWithRetry,
    create_chat_anthropic_with_retry,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ChatOpenAIWithRetry",
    "create_chat_openai_with_retry",
    "ChatAnthropicWithRetry",
    "create_chat_anthropic_with_retry",
    "create_chat_model",
]


def create_chat_model(
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    **kwargs
) -> BaseChatModel:
    """
    Create chat model with automatic provider selection based on model name.

    Provider selection rules (industry standard pattern):
    - "gpt-*" → OpenAI (gpt-4, gpt-4o, gpt-3.5-turbo, etc.)
    - "claude-*" → Anthropic (claude-3-5-sonnet-20241022, etc.)
    - Other → Default to OpenAI

    Args:
        model: Model name (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
        temperature: Temperature setting
        max_tokens: Maximum tokens
        **kwargs: Additional provider-specific parameters

    Returns:
        BaseChatModel instance with retry logic configured

    Examples:
        >>> # OpenAI
        >>> llm = create_chat_model(model="gpt-4o")
        >>> # Anthropic
        >>> llm = create_chat_model(model="claude-3-5-sonnet-20241022")

    Note:
        All clients include automatic retry logic for transient errors
        (rate limits, server errors, connection issues).
    """
    if not model:
        # If no model specified, use default (OpenAI)
        logger.debug("No model specified, using OpenAI as default provider")
        return create_chat_openai_with_retry(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    # Auto-detect provider from model name
    model_lower = model.lower()

    if model_lower.startswith("claude-"):
        logger.debug(f"Detected Anthropic model: {model}")
        return create_chat_anthropic_with_retry(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    elif model_lower.startswith("gpt-"):
        logger.debug(f"Detected OpenAI model: {model}")
        return create_chat_openai_with_retry(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    else:
        # Default to OpenAI for unknown model names
        logger.warning(f"Unknown model prefix: {model}, defaulting to OpenAI provider")
        return create_chat_openai_with_retry(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
