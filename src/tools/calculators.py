"""
Calculator functions for time and amount window computations.

These functions are decorated with @tool to be usable by LLM agents,
while also being callable as regular Python functions.
"""

from typing import List, Dict, Any
from langchain_core.tools import tool


@tool
def calculate_search_time_window(dst_block_time: int, search_time_span: int) -> Dict[str, int]:
    """Calculate backward search time window: [dst_block_time - search_time_span, dst_block_time].

    Use in Step 2 for price fetch window."""
    return {
        "start": dst_block_time - search_time_span,
        "end": dst_block_time
    }


@tool
def calculate_search_amount_window(
    dst_amount: float,
    dst_asset: str,
    src_asset: str,
    price_min: float,
    price_max: float,
    price_coin: str,
    price_quote: str
) -> Dict[str, Any]:
    """Convert dst amount to src amount using price range. Handles price direction automatically.

    Just provide the price you got (any direction), this tool handles inversion if needed."""
    # Validate price inputs
    if price_min <= 0 or price_max <= 0:
        raise ValueError(
            f"Invalid prices ({price_min}, {price_max}). "
            f"Fetch {price_coin}_in_{price_quote} price first before calling this calculator."
        )

    if dst_amount <= 0:
        raise ValueError(f"Invalid dst_amount: {dst_amount}. Amount must be positive.")

    # Check if price direction matches our need (dst_asset in src_asset)
    if price_coin.upper() == dst_asset.upper() and price_quote.upper() == src_asset.upper():
        # Direct match: dst_asset_in_src_asset
        # price tells us: 1 dst_asset = price src_asset
        final_price_min = price_min
        final_price_max = price_max
    elif price_coin.upper() == src_asset.upper() and price_quote.upper() == dst_asset.upper():
        # Inverted match: src_asset_in_dst_asset
        # price tells us: 1 src_asset = price dst_asset
        # We need: 1 dst_asset = ? src_asset
        # So invert: 1 dst_asset = (1/price) src_asset
        # When inverting: min becomes 1/max, max becomes 1/min
        final_price_min = 1.0 / price_max
        final_price_max = 1.0 / price_min
    else:
        raise ValueError(
            f"Price direction mismatch: need {dst_asset}->{src_asset} conversion, "
            f"but got price {price_coin}_in_{price_quote}"
        )

    # Safety check: ensure min < max
    if final_price_min > final_price_max:
        final_price_min, final_price_max = final_price_max, final_price_min

    return {
        "min": dst_amount * final_price_min,
        "max": dst_amount * final_price_max,
        "asset": src_asset
    }


@tool
def calculate_check_time_windows(block_times: List[int], check_time_span: int) -> List[Dict[str, int]]:
    """Calculate symmetric check windows: [T - span, T + span] for each candidate time T.

    Use in Step 4 for batch price fetching."""
    unique_times = sorted(set(block_times))
    windows = []
    for t in unique_times:
        windows.append({
            "center": t,
            "start": t - check_time_span,
            "end": t + check_time_span
        })
    return windows
