"""
Test full flow: tool → converter → Transfer model.

This tests the complete integration that the trace workflow would use.
"""

from src.tools.threexpl import search_eth_transfers_3xpl
from src.tools.models import Eth3xplTransfer
from src.tools.converters import eth_3xpl_transfer_to_transfer


def test_full_conversion_flow():
    """Test: tool result → Eth3xplTransfer → Transfer."""
    print("\n=== Test: Full conversion flow ===")

    # Step 1: Get results from tool
    results = search_eth_transfers_3xpl.invoke({
        "min_timestamp": 1747858711,
        "max_timestamp": 1747860511,
        "min_amount": 25.0,
        "max_amount": 30.0,
        "direction": "in",
        "limit": 5
    })

    print(f"Step 1: Got {len(results)} results from tool")
    if not results:
        print("⚠️  No results to test")
        return

    # Step 2: Convert dict to Eth3xplTransfer model
    transfer_data = results[0]
    eth_transfer = Eth3xplTransfer(**transfer_data)
    print(f"Step 2: Created Eth3xplTransfer model")
    print(f"  txid: {eth_transfer.txid[:16]}...")
    print(f"  recipient: {eth_transfer.recipient[:10]}...")
    print(f"  amount: {eth_transfer.amount:.4f} ETH")

    # Step 3: Convert to Transfer model
    transfer = eth_3xpl_transfer_to_transfer(eth_transfer)
    print(f"Step 3: Converted to Transfer model")
    print(f"  chain: {transfer.chain}")
    print(f"  type: {transfer.type}")
    print(f"  operations: {list(transfer.operations.keys())}")

    # Verify
    assert transfer.chain == "ETH"
    assert transfer.type == "account"
    assert "vout:0" in transfer.operations

    vout_op = transfer.operations["vout:0"]
    assert vout_op.asset == "ETH"
    assert vout_op.amount == eth_transfer.amount
    assert vout_op.account.address == eth_transfer.recipient

    print("\n✅ Full conversion flow passed!")

