"""
Mempool.space API tools for BTC transaction queries.

Free, no API key required.
API Docs: https://mempool.space/docs/api
"""

import time
from typing import Optional, List, Dict, Any

from langchain_core.tools import tool
from pydantic import BaseModel

from src.tools.base import BaseAPIClient, with_retry, FatalError, cached


class MempoolTxInput(BaseModel):
    txid: str
    vout: int
    prevout: Optional[Dict[str, Any]] = None
    scriptsig: Optional[str] = None
    sequence: int = 0


class MempoolTxOutput(BaseModel):
    scriptpubkey: Optional[str] = None
    scriptpubkey_address: Optional[str] = None
    scriptpubkey_type: Optional[str] = None
    value: int = 0


class MempoolTxStatus(BaseModel):
    confirmed: bool = False
    block_height: Optional[int] = None
    block_hash: Optional[str] = None
    block_time: Optional[int] = None


class MempoolTransaction(BaseModel):
    txid: str
    version: int = 1
    locktime: int = 0
    vin: List[MempoolTxInput] = []
    vout: List[MempoolTxOutput] = []
    size: int = 0
    weight: int = 0
    fee: int = 0
    status: MempoolTxStatus = MempoolTxStatus()


class MempoolClient(BaseAPIClient):
    """Mempool.space API client (free, no auth) with file caching."""

    BASE_URL = "https://mempool.space/api"
    SOURCE_NAME = "mempool.space"

    @cached("mempool", model=MempoolTransaction)
    @with_retry()
    def get_transaction(self, tx_hash: str) -> MempoolTransaction:
        """Fetch transaction details (cached)."""
        tx_hash = tx_hash.lower()
        url = f"{self.BASE_URL}/tx/{tx_hash}"
        response = self.client.get(url)
        data = self._handle_response(response)
        return MempoolTransaction(**data)

    @cached("mempool")
    @with_retry()
    def get_address_info(self, address: str) -> Dict[str, Any]:
        """Fetch address information (cached)."""
        url = f"{self.BASE_URL}/address/{address}"
        response = self.client.get(url)
        return self._handle_response(response)

    @cached("mempool")
    @with_retry()
    def get_address_txs(self, address: str) -> List[Dict[str, Any]]:
        """Fetch transactions for an address (cached)."""
        url = f"{self.BASE_URL}/address/{address}/txs"
        response = self.client.get(url)
        return self._handle_response(response)


def _is_valid_tx_hash(tx_hash: str) -> bool:
    """Validate transaction hash format (64 hex characters)."""
    if not tx_hash or len(tx_hash) != 64:
        return False
    try:
        int(tx_hash, 16)
        return True
    except ValueError:
        return False


def _is_valid_address(address: str) -> bool:
    """Basic address validation (non-empty, reasonable length)."""
    if not address or len(address) < 20 or len(address) > 100:
        return False
    # Reject obvious placeholders
    placeholders = ["sample", "example", "test", "some_", "placeholder", "unknown"]
    lower = address.lower()
    return not any(p in lower for p in placeholders)


@tool
def get_btc_transaction_mempool(tx_hash: str) -> dict:
    """
    Get Bitcoin transaction details using Mempool.space API (free, no API key).

    Args:
        tx_hash: The Bitcoin transaction hash (txid) - must be a valid 64-character hex string

    Returns:
        Transaction details including inputs, outputs, and fees
    """
    # Validate tx_hash format
    if not _is_valid_tx_hash(tx_hash):
        return {
            "success": False,
            "error": f"Invalid transaction hash format: '{tx_hash}'. Must be 64 hex characters.",
            "chain": "BTC",
            "txid": tx_hash
        }

    client = MempoolClient()
    try:
        tx = client.get_transaction(tx_hash)

        inputs_info = []
        for i, inp in enumerate(tx.vin):
            if inp.prevout:
                addr = inp.prevout.get("scriptpubkey_address", "unknown")
                val = inp.prevout.get("value", 0) / 1e8
            else:
                addr = "unknown"
                val = 0
            inputs_info.append(f"vin:{i} <- {addr}: {val:.8f} BTC")

        outputs_info = []
        for i, out in enumerate(tx.vout):
            addr = out.scriptpubkey_address or "unknown"
            val = out.value / 1e8
            outputs_info.append(f"vout:{i} -> {addr}: {val:.8f} BTC")

        return {
            "success": True,
            "chain": "BTC",
            "txid": tx.txid,
            "block_height": tx.status.block_height,
            "block_time": tx.status.block_time,
            "confirmed": tx.status.confirmed,
            "fee_btc": tx.fee / 1e8,
            "size_bytes": tx.size,
            "inputs": inputs_info,
            "outputs": outputs_info,
        }
    except FatalError as e:
        return {"success": False, "error": str(e), "chain": "BTC", "txid": tx_hash}
    except Exception as e:
        return {"success": False, "error": str(e), "chain": "BTC", "txid": tx_hash}


@tool
def get_btc_address_info_mempool(address: str) -> dict:
    """
    Get Bitcoin address information using Mempool.space API (free, no API key).

    Args:
        address: The Bitcoin address - must be a valid address string

    Returns:
        Address balance and transaction statistics
    """
    # Validate address format
    if not _is_valid_address(address):
        return {
            "success": False,
            "error": f"Invalid address format: '{address}'. Must be a valid Bitcoin address.",
            "chain": "BTC",
            "address": address
        }

    client = MempoolClient()
    try:
        data = client.get_address_info(address)
        chain_stats = data.get("chain_stats", {})
        mempool_stats = data.get("mempool_stats", {})

        funded = chain_stats.get("funded_txo_sum", 0)
        spent = chain_stats.get("spent_txo_sum", 0)

        return {
            "success": True,
            "chain": "BTC",
            "address": data.get("address"),
            "balance_btc": (funded - spent) / 1e8,
            "total_received_btc": funded / 1e8,
            "total_spent_btc": spent / 1e8,
            "tx_count": chain_stats.get("tx_count", 0),
            "funded_txo_count": chain_stats.get("funded_txo_count", 0),
            "spent_txo_count": chain_stats.get("spent_txo_count", 0),
        }
    except FatalError as e:
        return {"success": False, "error": str(e), "chain": "BTC", "address": address}
    except Exception as e:
        return {"success": False, "error": str(e), "chain": "BTC", "address": address}


@tool
def get_btc_address_txs_mempool(
    address: str,
    limit: int = 25,
    min_timestamp: int = 0,
    max_timestamp: int = 0
) -> dict:
    """
    Get recent transactions for a Bitcoin address using Mempool.space API (free, no API key).

    Use this to find transactions associated with an address for cross-chain tracing.
    Supports time-based filtering to narrow down search window.

    Args:
        address: The Bitcoin address - must be a valid address string
        limit: Maximum number of transactions to return (default 25)
        min_timestamp: Only return txs AFTER this Unix timestamp (0 = no filter)
        max_timestamp: Only return txs BEFORE this Unix timestamp (0 = no filter)

    Returns:
        List of transactions with their details (txid, time, amounts), filtered by time window
    """
    if not _is_valid_address(address):
        return {
            "success": False,
            "error": f"Invalid address format: '{address}'. Must be a valid Bitcoin address.",
            "chain": "BTC",
            "address": address
        }

    client = MempoolClient()
    try:
        txs = client.get_address_txs(address)

        tx_list = []
        for tx in txs:
            status = tx.get("status", {})
            block_time = status.get("block_time")

            # Apply time filter if specified
            if min_timestamp > 0 and block_time and block_time < min_timestamp:
                continue
            if max_timestamp > 0 and block_time and block_time > max_timestamp:
                continue

            # Find relevant inputs/outputs for this address
            received = 0
            sent = 0

            for inp in tx.get("vin", []):
                prevout = inp.get("prevout", {})
                if prevout and prevout.get("scriptpubkey_address") == address:
                    sent += prevout.get("value", 0)

            for out in tx.get("vout", []):
                if out.get("scriptpubkey_address") == address:
                    received += out.get("value", 0)

            tx_list.append({
                "txid": tx.get("txid"),
                "block_time": block_time,
                "block_height": status.get("block_height"),
                "confirmed": status.get("confirmed", False),
                "received_btc": received / 1e8,
                "sent_btc": sent / 1e8,
                "net_btc": (received - sent) / 1e8,
                "fee_btc": tx.get("fee", 0) / 1e8,
            })

            # Stop if we have enough
            if len(tx_list) >= limit:
                break

        return {
            "success": True,
            "chain": "BTC",
            "address": address,
            "tx_count": len(tx_list),
            "time_filter": f"{min_timestamp}-{max_timestamp}" if min_timestamp or max_timestamp else "none",
            "transactions": tx_list,
        }
    except FatalError as e:
        return {"success": False, "error": str(e), "chain": "BTC", "address": address}
    except Exception as e:
        return {"success": False, "error": str(e), "chain": "BTC", "address": address}
