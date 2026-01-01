"""
Tool registry for BlockchainMAS agents.

Provides organized access to tools by category.
"""

from typing import List
from langchain_core.tools import BaseTool

from src.tools.electrs import (
    get_txs_doge_electrs,
    get_addresses_txs_doge_electrs,
    search_txs_doge_electrs,
    get_address_doge_electrs,
)
from src.tools.blockchair import (
    get_txs_blockchair,
    get_addresses_txs_blockchair,
    search_txs_blockchair,
    search_utxo_outputs_blockchair,
    get_block_txs_blockchair,
    get_address_blockchair,
)
from src.tools.binance import get_price_binance


def get_trace_tools() -> List[BaseTool]:
    """
    Core trace tools: tx lookup, address tx history, time-based search.
    Minimal set for cross-chain tracing.
    """
    return [
        # Batch tx lookup
        get_txs_doge_electrs,      # DOGE only - free
        get_txs_blockchair,        # Multi-chain: BTC/DOGE/ETH/LTC/BCH (paid)

        # Address tx history with filtering
        get_addresses_txs_doge_electrs,  # DOGE only - free
        get_addresses_txs_blockchair,    # Multi-chain (paid)

        # Time-based transaction search
        search_txs_doge_electrs,   # DOGE only - free (scans blocks)
        search_txs_blockchair,     # Multi-chain (paid) - filters by tx total
        search_utxo_outputs_blockchair,  # Multi-chain (paid) - filters by individual output amount

        # Price for cross-chain amount matching
        get_price_binance,
    ]


def get_utility_tools() -> List[BaseTool]:
    """Utility tools: block queries, address info (non-trace)."""
    return [
        get_block_txs_blockchair,  # Block tx list
        get_address_blockchair,    # Address balance/stats
        get_address_doge_electrs,  # DOGE only - address balance
    ]


def get_all_tools() -> List[BaseTool]:
    """Get all available tools."""
    return get_trace_tools() + get_utility_tools()


def get_trace_fetcher_tools() -> List[BaseTool]:
    """Trace Fetcher Agent: only trace-related tools to minimize tokens."""
    return get_trace_tools()
