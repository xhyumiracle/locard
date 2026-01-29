"""
Calculator functions for time and amount window computations.

These functions are decorated with @tool to be usable by LLM agents,
while also being callable as regular Python functions.
"""

import logging
from typing import List, Dict, Any
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Approximate value ordering (higher = more valuable per unit)
# Used as fallback when price_coin/price_quote are not provided
ASSET_VALUE_ORDER = {
    # Tier 1: Most valuable
    "BTC": 100,
    "WBTC": 100,

    # Tier 2: Mid-high value
    "ETH": 50,
    "WETH": 50,
    "BNB": 40,

    # Tier 3: Mid value
    "LTC": 18,
    "SOL": 20,
    "MATIC": 10,
    "AVAX": 15,

    # Tier 4: Lower value
    "DOGE": 1,
    "SHIB": 0.01,

    # Default for unknown assets
    "DEFAULT": 5
}


@tool
def calculate_search_time_window(
    dst_block_time: int,
    search_time_span: int,
    search_time_offset: int = None
) -> Dict[str, int]:
    """Calculate backward search time window: [dst_block_time - search_time_span, dst_block_time - search_time_offset].

    Use in Step 2 for price fetch window. Leave search_time_offset empty unless explicitly specified in params."""

    end_time = dst_block_time if search_time_offset is None else dst_block_time - search_time_offset

    return {
        "start": end_time - search_time_span,
        "end": end_time
    }


def _infer_price_direction(dst_asset: str, src_asset: str, price_min: float, price_max: float) -> tuple[str, str]:
    """Infer price direction based on asset value ordering and price range magnitude.

    Returns: (price_coin, price_quote)
    """
    dst_value = ASSET_VALUE_ORDER.get(dst_asset.upper(), ASSET_VALUE_ORDER["DEFAULT"])
    src_value = ASSET_VALUE_ORDER.get(src_asset.upper(), ASSET_VALUE_ORDER["DEFAULT"])

    # If prices are > 1, it likely means "coin_in_quote" where coin is more valuable
    # If prices are < 1, it likely means "coin_in_quote" where quote is more valuable
    avg_price = (price_min + price_max) / 2

    if dst_value > src_value:
        # dst is more valuable (e.g., BTC > ETH), so price is likely dst_in_src (BTC_in_ETH = 30+)
        if avg_price > 1:
            logger.info(f"Inferred price direction: {dst_asset}_in_{src_asset} (dst more valuable, price > 1)")
            return dst_asset, src_asset
        else:
            # Price < 1 but dst more valuable, so it must be src_in_dst
            logger.info(f"Inferred price direction: {src_asset}_in_{dst_asset} (dst more valuable, price < 1)")
            return src_asset, dst_asset
    else:
        # src is more valuable (e.g., ETH > DOGE), so price is likely src_in_dst (ETH_in_DOGE = large)
        if avg_price > 1:
            logger.info(f"Inferred price direction: {src_asset}_in_{dst_asset} (src more valuable, price > 1)")
            return src_asset, dst_asset
        else:
            # Price < 1 but src more valuable, so it must be dst_in_src
            logger.info(f"Inferred price direction: {dst_asset}_in_{src_asset} (src more valuable, price < 1)")
            return dst_asset, src_asset


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
            f"Price must be positive before calling this calculator."
        )

    if dst_amount <= 0:
        raise ValueError(f"Invalid dst_amount: {dst_amount}. Amount must be positive.")

    # Loose equality: case-insensitive match, or one side empty (can infer)
    def loose_equal(a: str, b: str) -> bool:
        if not a and not b:
            return False  # Both empty = not equal (cannot determine)
        if not a or not b:
            return True   # One empty = equal (can infer)
        return a.upper() == b.upper()  # Both present = case-insensitive compare

    # Match price direction with dst/src using loose equality
    # Check inference first (priority fix: empty strings should trigger inference, not loose matching)
    if not price_coin and not price_quote:
        # Both price_coin and price_quote missing: use value-based inference
        price_coin, price_quote = _infer_price_direction(dst_asset, src_asset, price_min, price_max)
        logger.info(f"Price direction inferred from asset values: {price_coin}_in_{price_quote}")
        # Apply inferred direction
        if price_coin.upper() == dst_asset.upper():
            final_price_min = price_min
            final_price_max = price_max
        else:
            final_price_min = 1.0 / price_max
            final_price_max = 1.0 / price_min
    elif loose_equal(dst_asset, price_coin) and loose_equal(src_asset, price_quote):
        # Direct match: dst_in_src (e.g., BTC_in_ETH)
        final_price_min = price_min
        final_price_max = price_max
        logger.info(f"Price direction: direct match {dst_asset}_in_{src_asset}")
    elif loose_equal(dst_asset, price_quote) and loose_equal(src_asset, price_coin):
        # Inverted match: src_in_dst (e.g., ETH_in_BTC, need to invert)
        final_price_min = 1.0 / price_max
        final_price_max = 1.0 / price_min
        logger.info(f"Price direction: inverted match {src_asset}_in_{dst_asset}, inverting prices")
    else:
        raise ValueError(
            f"Price direction mismatch: cannot match {dst_asset}/{src_asset} with {price_coin}/{price_quote}"
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
