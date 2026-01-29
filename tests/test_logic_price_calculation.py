"""
Test calculator's price direction inference when price_coin/price_quote are missing.

This tests the fallback logic that infers price direction based on:
1. Asset value ordering (BTC > ETH > DOGE etc.)
2. Price magnitude (>1 or <1)
"""

from src.tools.calculators import calculate_search_amount_window


def test_btc_to_eth_inference():
    """Test BTC->ETH conversion with missing price_coin/price_quote.

    Price: BTC_in_ETH = 33-37 (BTC more valuable, price > 1)
    Should correctly infer and convert 0.27586129 BTC to ETH.
    """
    result = calculate_search_amount_window(
        dst_amount=0.27586129,
        dst_asset="BTC",
        src_asset="ETH",
        price_min=33.6640680369,
        price_max=37.459864431,
        # price_coin and price_quote are intentionally omitted
    )

    print("Test 1: BTC->ETH (price missing)")
    print(f"  Input: 0.27586129 BTC, price [33.66, 37.46]")
    print(f"  Output: {result}")
    print(f"  Expected: ~9.29 to ~10.33 ETH")

    assert result["asset"] == "ETH"
    assert 9.0 < result["min"] < 10.0
    assert 10.0 < result["max"] < 11.0
    print("  ✅ PASS\n")


def test_eth_to_doge_inference():
    """Test ETH->DOGE conversion with missing price_coin/price_quote.

    Price: ETH_in_DOGE = large number (ETH more valuable, price > 1)
    Should correctly infer and convert ETH to DOGE.
    """
    result = calculate_search_amount_window(
        dst_amount=10.0,
        dst_asset="ETH",
        src_asset="DOGE",
        price_min=10000.0,
        price_max=12000.0,
    )

    print("Test 2: ETH->DOGE (price missing)")
    print(f"  Input: 10.0 ETH, price [10000, 12000]")
    print(f"  Output: {result}")
    print(f"  Expected: ~100000 to ~120000 DOGE")

    assert result["asset"] == "DOGE"
    assert 99000 < result["min"] < 101000
    assert 119000 < result["max"] < 121000
    print("  ✅ PASS\n")


def test_doge_to_btc_inference():
    """Test DOGE->BTC conversion with missing price_coin/price_quote.

    Price: BTC_in_DOGE = large number (BTC more valuable, price > 1)
    Should correctly infer and convert DOGE to BTC.
    """
    result = calculate_search_amount_window(
        dst_amount=100000.0,
        dst_asset="DOGE",
        src_asset="BTC",
        price_min=1000000.0,
        price_max=1200000.0,
    )

    print("Test 3: DOGE->BTC (price missing)")
    print(f"  Input: 100000.0 DOGE, price [1000000, 1200000]")
    print(f"  Output: {result}")
    print(f"  Expected: ~0.083 to ~0.1 BTC")

    assert result["asset"] == "BTC"
    assert 0.08 < result["min"] < 0.09
    assert 0.09 < result["max"] < 0.11
    print("  ✅ PASS\n")


def test_with_explicit_price_direction():
    """Test that explicit price_coin/price_quote still work correctly."""
    result = calculate_search_amount_window(
        dst_amount=0.27586129,
        dst_asset="BTC",
        src_asset="ETH",
        price_min=33.6640680369,
        price_max=37.459864431,
        price_coin="BTC",
        price_quote="ETH"
    )

    print("Test 4: Explicit price direction (should not infer)")
    print(f"  Input: 0.27586129 BTC, price [33.66, 37.46], explicit BTC_in_ETH")
    print(f"  Output: {result}")

    assert result["asset"] == "ETH"
    assert 9.0 < result["min"] < 10.0
    assert 10.0 < result["max"] < 11.0
    print("  ✅ PASS\n")

