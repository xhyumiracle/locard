
def ensure_ts_seconds(ts: int) -> int:
    """Ensure timestamp is in seconds."""
    if ts > 1_000_000_000_000: # is ms
        return ts // 1000
    else:
        return ts # is sec