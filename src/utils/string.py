"""String utility functions."""


def is_numeric_like(s: str) -> bool:
    """Check if string is numeric-like (number, float, or long hex).

    Numeric-like values are considered critical identifiers for distinguishing
    tool calls (timestamps, amounts, tx hashes, etc.)

    Args:
        s: String to check

    Returns:
        True if s is: integer, float, scientific notation, or long hex (>16 chars)

    Examples:
        >>> is_numeric_like("1752610998")
        True
        >>> is_numeric_like("0.13629613")
        True
        >>> is_numeric_like("1.5e10")
        True
        >>> is_numeric_like("abc123def456789012345678")  # long hex
        True
        >>> is_numeric_like("BTC")
        False
        >>> is_numeric_like("out")
        False
    """
    s = str(s).strip()
    if not s:
        return False

    # Try parsing as number
    try:
        float(s)
        return True
    except ValueError:
        pass

    # Check if it's a long hex string (likely a txid/hash)
    if len(s) > 16 and all(c in '0123456789abcdefABCDEF' for c in s):
        return True

    return False
