"""Test Bitquery API integration."""

import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(name)s - %(message)s')

from src.tools.bitquery import search_eth_transfers_bitquery

# Test with the failed case from the log
# GT: 2025-12-20 18:36:47 UTC (1766255807), 24.44394463 ETH
# Search window: 1766255375-1766257175 (30 minutes)
# Amount range: 22.88-25.34 ETH

result = search_eth_transfers_bitquery.invoke({
    "min_timestamp": 1766255375,
    "max_timestamp": 1766257175,
    "min_amount": 22.88,
    "max_amount": 25.34,
    "direction": "out",
    "limit": 100
})

print(f"Found {len(result)} transfers")
for i, tx in enumerate(result[:5]):  # Show first 5
    print(f"\n{i+1}. TX: {tx['txid']}")
    print(f"   Amount: {tx['amount']} ETH")
    print(f"   From: {tx['sender']}")
    print(f"   To: {tx['recipient']}")
    print(f"   Time: {tx['block_time']}")

# Check if GT is in results
gt_txid = "0x621b0ac749603d31cf3e4df1348d0441e6812600039c4e484d954b9877931a9a"
found_gt = any(tx['txid'].lower() == gt_txid.lower() for tx in result)
print(f"\n✓ GT transaction found!" if found_gt else "\n✗ GT transaction NOT found")
