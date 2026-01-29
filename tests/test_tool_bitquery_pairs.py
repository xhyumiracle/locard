"""Test Bitquery API with eth_btc case."""

import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(name)s - %(message)s')

from src.tools.bitquery import search_eth_transfers_bitquery

# Test with the eth_btc case
# GT: 2025-02-25 12:30:11 UTC (1740488411), 29.96 ETH
# From log: search window 1740486212-1740488012 (30 minutes)
# Amount range: 28.113798591814987-31.256063520998453 ETH

result = search_eth_transfers_bitquery.invoke({
    "min_timestamp": 1740486212,
    "max_timestamp": 1740488012,
    "min_amount": 28.113798591814987,
    "max_amount": 31.256063520998453,
    "direction": "out",
    "limit": 100
})

print(f"\nFound {len(result)} transfers")
for i, tx in enumerate(result[:10]):  # Show first 10
    print(f"\n{i+1}. TX: {tx['txid']}")
    print(f"   Amount: {tx['amount']} ETH")
    print(f"   From: {tx['sender']}")
    print(f"   To: {tx['recipient']}")
    print(f"   Time: {tx['block_time']}")

# Check if GT is in results
gt_txid = "0x93947d2d756cd3fa560f3529695e541931c28370c4189458b7af87d4db59544a"
found_gt = any(tx['txid'].lower() == gt_txid.lower() for tx in result)
print(f"\n{'✓' if found_gt else '✗'} GT transaction {'found!' if found_gt else 'NOT found'}")

if found_gt:
    gt_tx = next(tx for tx in result if tx['txid'].lower() == gt_txid.lower())
    print(f"\nGT transaction details:")
    print(f"  Amount: {gt_tx['amount']} ETH")
    print(f"  Time: {gt_tx['block_time']}")
    print(f"  From: {gt_tx['sender']}")
    print(f"  To: {gt_tx['recipient']}")
