"""
API client infrastructure for BlockchainMAS.

Provides base classes, retry/cache decorators, and error handling for HTTP API clients.
"""

from .base import (
    # Base classes
    BaseAPIClient,
    LoggingHTTPClient,

    # Exceptions
    TransientError,
    FatalError,
    QuotaExhaustedError,

    # Decorators
    with_retry,
    cached,

    # Utilities
    calculate_backoff_time,
    extract_retry_after_header,
    record_rate_limit,
    clear_rate_limits,
)

__all__ = [
    # Base classes
    "BaseAPIClient",
    "LoggingHTTPClient",

    # Exceptions
    "TransientError",
    "FatalError",
    "QuotaExhaustedError",

    # Decorators
    "with_retry",
    "cached",

    # Utilities
    "calculate_backoff_time",
    "extract_retry_after_header",
    "record_rate_limit",
    "clear_rate_limits",
]
