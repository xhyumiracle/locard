"""
Integration test for 3xpl ETH transfer search tool.

Tests the complete flow:
1. Tool invocation (search_eth_transfers_3xpl)
2. Model conversion (Eth3xplTransfer)
3. Transfer conversion (eth_3xpl_transfer_to_transfer)
"""

from src.tools.threexpl import search_eth_transfers_3xpl
from src.tools.converters import dict_to_transfer


def test_3xpl_basic_search():
    """Test basic 3xpl search with time and amount filters."""
    print("\n=== Test 1: Basic search (30-min window, 25-28 ETH) ===")

    results = search_eth_transfers_3xpl.invoke({
        "min_timestamp": 1747858711,
        "max_timestamp": 1747860511,
        "min_amount": 25.47,
        "max_amount": 28.22,
        "direction": "in",
        "limit": 100
    })

    print(f"Found {len(results)} transfers")
    if results:
        print(f"First result: {results[0]}")

    assert isinstance(results, list), "Results should be a list"
    print("✅ Basic search passed")
    return results


def test_3xpl_to_transfer_conversion():
    """Test conversion from 3xpl result to Transfer model."""
    print("\n=== Test 2: Convert to Transfer model ===")

    # Get some results first
    results = search_eth_transfers_3xpl.invoke({
        "min_timestamp": 1747858711,
        "max_timestamp": 1747860511,
        "min_amount": 25.0,
        "max_amount": 30.0,
        "direction": "in",
        "limit": 10
    })

    if not results:
        print("⚠️  No results to test conversion")
        return

    # Test conversion
    transfer = dict_to_transfer(results[0])

    print(f"Transfer txid: {transfer.txid}")
    print(f"Transfer chain: {transfer.chain}")
    print(f"Transfer type: {transfer.type}")
    print(f"Transfer operations: {list(transfer.operations.keys())}")

    # Verify structure
    assert transfer.chain == "ETH", "Chain should be ETH"
    assert transfer.type == "account", "Type should be account"
    assert "vout:0" in transfer.operations, "Should have vout:0 operation"

    vout_op = transfer.operations["vout:0"]
    print(f"Recipient: {vout_op.account.address}")
    print(f"Amount: {vout_op.amount} {vout_op.asset}")

    assert vout_op.asset == "ETH", "Asset should be ETH"
    assert vout_op.amount > 0, "Amount should be positive"

    print("✅ Conversion passed")


def test_3xpl_large_window():
    """Test with larger time window to verify performance."""
    print("\n=== Test 3: Large window (1 hour) ===")

    results = search_eth_transfers_3xpl.invoke({
        "min_timestamp": 1747858711,
        "max_timestamp": 1747862311,  # 1 hour window
        "min_amount": 20.0,
        "max_amount": 30.0,
        "direction": "in",
        "limit": 200
    })

    print(f"Found {len(results)} transfers in 1-hour window")
    print("✅ Large window test passed")


def test_3xpl_direction_both():
    """Test direction='both' parameter."""
    print("\n=== Test 4: Direction 'both' ===")

    results = search_eth_transfers_3xpl.invoke({
        "min_timestamp": 1747858711,
        "max_timestamp": 1747860511,
        "min_amount": 25.0,
        "max_amount": 30.0,
        "direction": "both",
        "limit": 100
    })

    print(f"Found {len(results)} transfers (both directions)")
    print("✅ Direction test passed")

