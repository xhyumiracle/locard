"""Blockchain data tools for BlockchainMAS

Naming convention: {action}_{resource}[_{chain}]_{source}
- action: get, search
- resource: tx, address, address_txs, block_txs, price
- chain: btc, doge, eth (optional for multi-chain tools)
- source: mempoolspace, electrs, blockchair, blockcypher, binance
"""

# from src.tools.blockcypher import get_tx_blockcypher
from src.tools.electrs import (
    get_txs_doge_electrs,
    get_address_doge_electrs,
    get_addresses_txs_doge_electrs,
    search_txs_doge_electrs,
)
# from src.tools.mempool import (
#     get_tx_btc_mempoolspace,
#     get_address_btc_mempoolspace,
#     get_address_txs_btc_mempoolspace,
#     get_block_txs_btc_mempoolspace,
# )
from src.tools.binance import get_price_binance
from src.tools.registry import (
    get_all_tools,
    get_trace_tools,
    get_trace_fetcher_tools,
)

__all__ = [
    # BlockCypher (multi-chain fallback)
    "get_tx_blockcypher",
    # Mempool.space (BTC - free)
    "get_tx_btc_mempoolspace",
    "get_address_btc_mempoolspace",
    "get_address_txs_btc_mempoolspace",
    "get_block_txs_btc_mempoolspace",
    # Electrs (DOGE only - free)
    "get_txs_doge_electrs",
    "get_address_doge_electrs",
    "get_addresses_txs_doge_electrs",
    "search_txs_doge_electrs",
    # Binance (price)
    "get_price_binance",
    # Registry functions
    "get_all_tools",
    "get_trace_tools",
    "get_trace_fetcher_tools",
]
