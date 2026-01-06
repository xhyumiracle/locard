"""
Simple unit test for search_eth_calls_blockchair tool.
Run with: uv run python tests/test_eth_calls_simple.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timezone
from src.tools.blockchair import BlockchairClient
from src.tools.models import EthCall
from config import get_asset_unit
import config


def _search_eth_calls(
    min_timestamp: int = 0,
    max_timestamp: int = 0,
    recipient: str = "",
    sender: str = "",
    min_amount: float = 0,
    max_amount: float = 0,
    limit: int = 100
):
    """Helper function that directly calls the implementation."""
    if min_timestamp <= 0 and max_timestamp <= 0:
        raise ValueError("At least one of min_timestamp or max_timestamp must be specified")

    if not recipient and not sender:
        raise ValueError(
            "Must specify either recipient or sender address for performance. "
            "Searching without address filter would return too many results."
        )

    if not config.BLOCKCHAIR_API_KEY:
        raise ValueError("Blockchair API key required. Set BLOCKCHAIR_API_KEY.")

    client = BlockchairClient()

    calls_raw = client.search_calls(
        chain="ETH",
        min_timestamp=min_timestamp,
        max_timestamp=max_timestamp,
        recipient=recipient,
        sender=sender,
        min_amount=min_amount,
        max_amount=max_amount,
        transferred_only=True,
        limit=limit
    )

    unit = get_asset_unit("ETH")  # 10^18 wei per ETH

    # Convert to EthCall model
    results = []
    for call in calls_raw:
        eth_call = EthCall(
            chain="ETH",
            txid=call.get("transaction_hash"),
            index=call.get("index", ""),
            depth=call.get("depth", 0),
            call_type=call.get("type", "call"),
            sender=call.get("sender"),
            recipient=call.get("recipient"),
            amount=int(call.get("value", 0)) / unit,  # Convert wei to ETH
            transferred=call.get("transferred", True),
            block_time=client._parse_time(call.get("time")),
        )
        results.append(eth_call.model_dump())

    return results


def test_unit_conversion():
    """Test that wei to ETH conversion is correct."""
    print("\n=== Test 1: Unit Conversion ===")
    unit = get_asset_unit("ETH")
    assert unit == 10**18, "ETH unit should be 10^18"
    print(f"✅ ETH unit: {unit}")

    # Test conversion
    wei_value = 10000000000000000000  # 10 ETH in wei
    eth_value = wei_value / unit
    assert eth_value == 10.0, "10^19 wei should be 10 ETH"
    print(f"✅ Conversion: {wei_value} wei = {eth_value} ETH")


def test_known_lifi_transfer():
    """Test searching for a known 10 ETH transfer through LiFi protocol."""
    print("\n=== Test 2: Known LiFi Transfer ===")

    # Known transaction: 0x92697636e1bd52829497ce8573d41310bcba74c0bf27a03dee11acc7a7755d8e
    # Block: 21917009
    # Time: 2025-02-24 15:14:35
    # Transfer: 10 ETH through LiFi to THORChain vault

    recipient = "0xd03d56ef7d11a1a5a0933c1d524ff0bc1e916c98"

    # Convert time to Unix timestamp
    block_time = datetime(2025, 2, 24, 15, 14, 35, tzinfo=timezone.utc)
    timestamp = int(block_time.timestamp())

    print(f"Searching for calls to {recipient[:10]}...")
    print(f"Time window: {timestamp-60} to {timestamp+60}")
    print(f"Amount range: 9.9 - 10.1 ETH")

    # Search with ±1 minute window
    calls = _search_eth_calls(
        recipient=recipient,
        min_timestamp=timestamp - 60,
        max_timestamp=timestamp + 60,
        min_amount=9.9,  # Allow small tolerance
        max_amount=10.1,
        limit=10
    )

    # Verify results
    assert len(calls) > 0, "Should find at least one call"
    print(f"✅ Found {len(calls)} call(s)")

    # Find the specific call
    target_call = None
    for i, call in enumerate(calls):
        print(f"\nCall {i+1}:")
        print(f"  TxID: {call['txid'][:20]}...")
        print(f"  Amount: {call['amount']} ETH")
        print(f"  Depth: {call['depth']}, Index: {call['index']}")
        print(f"  Sender: {call['sender'][:10]}...")
        print(f"  Recipient: {call['recipient'][:10]}...")

        if call["txid"] == "0x92697636e1bd52829497ce8573d41310bcba74c0bf27a03dee11acc7a7755d8e":
            target_call = call

    assert target_call is not None, "Should find the specific transaction"
    print(f"\n✅ Found target transaction!")
    print(f"   Chain: {target_call['chain']}")
    print(f"   Amount: {target_call['amount']} ETH")
    print(f"   Depth: {target_call['depth']}")
    print(f"   Index: {target_call['index']}")
    print(f"   Transferred: {target_call['transferred']}")

    assert target_call["chain"] == "ETH"
    assert target_call["recipient"].lower() == recipient.lower()
    assert 9.9 <= target_call["amount"] <= 10.1, f"Amount should be ~10 ETH, got {target_call['amount']}"
    assert target_call["transferred"] is True
    assert target_call["depth"] == 3, "Should be at depth 3 (internal call)"
    assert target_call["index"] == "0.0.0.0"

    print("✅ All assertions passed!")


def test_value_filter_works():
    """Test that value filtering actually works with ETH units."""
    print("\n=== Test 3: Value Filter ===")

    recipient = "0xd03d56ef7d11a1a5a0933c1d524ff0bc1e916c98"

    # Time window: 2025-02-24 15:14:00 to 15:15:00
    timestamp = int(datetime(2025, 2, 24, 15, 14, 30, tzinfo=timezone.utc).timestamp())

    # Test 1: Query for 10 ETH transfers
    print("\n3a. Testing 9.9-10.1 ETH filter...")
    calls_10eth = _search_eth_calls(
        recipient=recipient,
        min_timestamp=timestamp - 30,
        max_timestamp=timestamp + 30,
        min_amount=9.9,
        max_amount=10.1,
        limit=10
    )

    print(f"Found {len(calls_10eth)} calls in 9.9-10.1 ETH range")
    # All results should be around 10 ETH
    for call in calls_10eth:
        print(f"  - {call['amount']} ETH")
        assert 9.9 <= call["amount"] <= 10.1, f"Should only return ~10 ETH transfers, got {call['amount']}"

    print("✅ All calls are in 9.9-10.1 ETH range")

    # Test 2: Query for > 5 ETH transfers
    print("\n3b. Testing >= 5 ETH filter...")
    calls_5plus = _search_eth_calls(
        recipient=recipient,
        min_timestamp=timestamp - 30,
        max_timestamp=timestamp + 30,
        min_amount=5,
        limit=10
    )

    print(f"Found {len(calls_5plus)} calls >= 5 ETH")
    # Should return calls with >= 5 ETH
    for call in calls_5plus:
        print(f"  - {call['amount']} ETH")
        assert call["amount"] >= 5, f"Should return >= 5 ETH, got {call['amount']}"

    print("✅ All calls are >= 5 ETH")


def test_eth_call_model():
    """Test that EthCall model has correct fields."""
    print("\n=== Test 4: EthCall Model ===")

    from src.tools.models import EthCall

    call = EthCall(
        chain="ETH",
        txid="0x1234567890abcdef",
        index="0.0.0",
        depth=2,
        call_type="call",
        sender="0xabcd",
        recipient="0xefgh",
        amount=10.5,
        transferred=True,
        block_time=1234567890
    )

    assert call.chain == "ETH"
    assert call.amount == 10.5  # In ETH, not wei
    assert call.depth == 2
    assert call.transferred is True

    print(f"✅ EthCall model structure:")
    print(f"   Chain: {call.chain}")
    print(f"   Amount: {call.amount} ETH")
    print(f"   Depth: {call.depth}")
    print(f"   Transferred: {call.transferred}")


def test_error_cases():
    """Test error handling."""
    print("\n=== Test 5: Error Handling ===")

    # Test 1: Missing time filter
    print("\n5a. Testing missing time filter...")
    try:
        _search_eth_calls(
            recipient="0xd03d56ef7d11a1a5a0933c1d524ff0bc1e916c98",
            min_amount=10,
            limit=10
        )
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "At least one of min_timestamp or max_timestamp" in str(e)
        print(f"✅ Correct error: {e}")

    # Test 2: Missing address filter
    print("\n5b. Testing missing address filter...")
    timestamp = int(datetime.now(timezone.utc).timestamp())
    try:
        _search_eth_calls(
            min_timestamp=timestamp - 3600,
            max_timestamp=timestamp,
            min_amount=10,
            limit=10
        )
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "Must specify either recipient or sender" in str(e)
        print(f"✅ Correct error: {e}")


def main():
    """Run all tests."""
    print("=" * 80)
    print("ETH Calls Search - Unit Tests")
    print("=" * 80)

    tests = [
        ("Unit Conversion", test_unit_conversion),
        ("Known LiFi Transfer", test_known_lifi_transfer),
        ("Value Filter", test_value_filter_works),
        ("EthCall Model", test_eth_call_model),
        ("Error Handling", test_error_cases),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n❌ Test '{name}' FAILED:")
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print(f"Test Summary: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 80)

    if failed > 0:
        sys.exit(1)
    else:
        print("\n🎉 All tests passed!")


if __name__ == "__main__":
    main()
