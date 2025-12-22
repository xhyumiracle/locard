"""
Tool registry for BlockchainMAS agents.

Provides organized access to tools by category.
"""

from typing import List
from langchain_core.tools import BaseTool

from src.tools.blockcypher import (
    get_btc_transaction,
    get_doge_transaction,
    get_btc_address_info,
    get_doge_address_info,
)
from src.tools.electrs import (
    get_doge_transaction_electrs,
    get_doge_address_info_electrs,
    get_doge_address_txs_electrs,
    search_doge_txs_by_time,
)
from src.tools.mempool import (
    get_btc_transaction_mempool,
    get_btc_address_info_mempool,
    get_btc_address_txs_mempool,
)
from src.tools.binance import (
    get_historical_price,
    get_price_at_timestamp,
)


def get_blockchain_tools() -> List[BaseTool]:
    """Get all blockchain data query tools."""
    return [
        # BTC tools (prefer mempool.space - free, no rate limit)
        get_btc_transaction_mempool,
        get_btc_address_info_mempool,
        get_btc_address_txs_mempool,  # Address transaction history
        get_btc_transaction,  # BlockCypher fallback
        get_btc_address_info,
        # DOGE tools (prefer electrs - free)
        get_doge_transaction_electrs,
        get_doge_address_info_electrs,
        get_doge_address_txs_electrs,  # Address transaction history
        search_doge_txs_by_time,  # Search txs by time window + amount filter
        get_doge_transaction,  # BlockCypher fallback
        get_doge_address_info,
    ]


def get_price_tools() -> List[BaseTool]:
    """Get price/exchange rate tools."""
    return [
        get_historical_price,
        get_price_at_timestamp,
    ]


def get_all_tools() -> List[BaseTool]:
    """Get all available tools."""
    return get_blockchain_tools() + get_price_tools()


def get_trace_fetcher_tools() -> List[BaseTool]:
    """Get tools specifically for Trace Fetcher Agent."""
    return get_blockchain_tools() + get_price_tools()


def get_fallback_tools() -> List[BaseTool]:
    """Get tools for General Tool Agent (fallback workflow)."""
    # For v0, same as all tools. In v1+, might include web search, etc.
    return get_all_tools()
