"""
Electrs-Doge API tools for Dogecoin queries.

This is a free, community-hosted Esplora-compatible API for DOGE.
No API key required.

Base URL: https://doge-electrs-demo.qed.me
"""

import time
from typing import Optional, List, Dict, Any

from langchain_core.tools import tool
from pydantic import BaseModel

import config
from src.tools.base import BaseAPIClient, with_retry, FatalError, cached
from src.models.core import (
    TxLocator, Transfer, Operation, AccountIdentifier,
    Currency, Amount, CoinChange, EvidenceRef
)


class ElectrsChainStats(BaseModel):
    funded_txo_count: int = 0
    funded_txo_sum: int = 0
    spent_txo_count: int = 0
    spent_txo_sum: int = 0
    tx_count: int = 0


class ElectrsAddressInfo(BaseModel):
    address: str
    chain_stats: ElectrsChainStats
    mempool_stats: Optional[ElectrsChainStats] = None

    @property
    def balance(self) -> int:
        """Calculate balance in koinu (1 DOGE = 1e8 koinu)."""
        return self.chain_stats.funded_txo_sum - self.chain_stats.spent_txo_sum


class ElectrsPrevout(BaseModel):
    scriptpubkey: Optional[str] = None
    scriptpubkey_address: Optional[str] = None
    value: int = 0


class ElectrsTxInput(BaseModel):
    txid: str
    vout: int
    prevout: Optional[ElectrsPrevout] = None
    scriptsig: Optional[str] = None
    sequence: int = 0


class ElectrsTxOutput(BaseModel):
    scriptpubkey: Optional[str] = None
    scriptpubkey_address: Optional[str] = None
    scriptpubkey_type: Optional[str] = None
    value: int = 0


class ElectrsTxStatus(BaseModel):
    confirmed: bool = False
    block_height: Optional[int] = None
    block_hash: Optional[str] = None
    block_time: Optional[int] = None


class ElectrsTransaction(BaseModel):
    txid: str
    version: int = 1
    locktime: int = 0
    vin: List[ElectrsTxInput] = []
    vout: List[ElectrsTxOutput] = []
    size: int = 0
    weight: int = 0
    fee: int = 0
    status: ElectrsTxStatus = ElectrsTxStatus()


class ElectrsDogeClient(BaseAPIClient):
    """Electrs-Doge API client (free, no auth) with file caching."""

    BASE_URL = "https://doge-electrs-demo.qed.me"
    SOURCE_NAME = "electrs-doge"

    @cached("electrs-doge", model=ElectrsTransaction)
    @with_retry()
    def get_transaction(self, tx_hash: str) -> ElectrsTransaction:
        """Fetch transaction details (cached)."""
        tx_hash = tx_hash.lower()
        url = f"{self.BASE_URL}/tx/{tx_hash}"
        response = self.client.get(url)
        data = self._handle_response(response)
        return ElectrsTransaction(**data)

    @cached("electrs-doge", model=ElectrsAddressInfo)
    @with_retry()
    def get_address_info(self, address: str) -> ElectrsAddressInfo:
        """Fetch address information (cached)."""
        url = f"{self.BASE_URL}/address/{address}"
        response = self.client.get(url)
        data = self._handle_response(response)
        return ElectrsAddressInfo(**data)

    @cached("electrs-doge")
    @with_retry()
    def get_address_txs(self, address: str) -> List[Dict[str, Any]]:
        """Fetch transactions for an address (cached)."""
        url = f"{self.BASE_URL}/address/{address}/txs"
        response = self.client.get(url)
        return self._handle_response(response)

    @with_retry()
    def get_blocks(self, start_height: int = None) -> List[Dict[str, Any]]:
        """Fetch recent blocks (NOT cached - changes frequently)."""
        if start_height:
            url = f"{self.BASE_URL}/blocks/{start_height}"
        else:
            url = f"{self.BASE_URL}/blocks"
        response = self.client.get(url)
        return self._handle_response(response)

    @cached("electrs-doge")
    @with_retry()
    def get_block_hash_by_height(self, height: int) -> str:
        """Get block hash by height (cached)."""
        url = f"{self.BASE_URL}/block-height/{height}"
        response = self.client.get(url)
        if response.status_code == 200:
            return response.text.strip()
        self._handle_response(response)

    @cached("electrs-doge")
    @with_retry()
    def get_block_txids(self, block_hash: str) -> List[str]:
        """Get all transaction IDs in a block (cached)."""
        url = f"{self.BASE_URL}/block/{block_hash}/txids"
        response = self.client.get(url)
        return self._handle_response(response)

    @cached("electrs-doge")
    @with_retry()
    def get_block_info(self, block_hash: str) -> Dict[str, Any]:
        """Get block information (cached)."""
        url = f"{self.BASE_URL}/block/{block_hash}"
        response = self.client.get(url)
        return self._handle_response(response)

    @cached("electrs-doge")
    @with_retry()
    def get_block_txs(self, block_hash: str, start_index: int = 0) -> List[Dict[str, Any]]:
        """Get full transaction data for a block (up to 25 txs per call, cached)."""
        url = f"{self.BASE_URL}/block/{block_hash}/txs/{start_index}"
        response = self.client.get(url)
        return self._handle_response(response)


def _electrs_tx_to_transfer(
    tx: ElectrsTransaction,
    source: str = "electrs-doge"
) -> Transfer:
    """Convert Electrs transaction to internal Transfer model."""
    chain = "DOGE"
    currency = Currency(symbol=chain, decimals=8)

    locator = TxLocator(
        chain=chain,
        txid=tx.txid,
        status="confirmed" if tx.status.confirmed else "mempool",
        block_height=tx.status.block_height,
        block_hash=tx.status.block_hash,
        block_time=tx.status.block_time
    )

    operations: List[Operation] = []

    # Process inputs (spent coins)
    for i, inp in enumerate(tx.vin):
        addr = None
        value = None
        if inp.prevout:
            addr = inp.prevout.scriptpubkey_address
            value = str(-inp.prevout.value) if inp.prevout.value else None

        amount = Amount(value=value, currency=currency) if value else None

        coin_change = CoinChange(
            coin_id=f"{inp.txid}:{inp.vout}",
            action="coin_spent"
        )

        op = Operation(
            op_id=f"vin:{i}",
            account=AccountIdentifier(address=addr),
            amount=amount,
            coin_change=coin_change
        )
        operations.append(op)

    # Process outputs (created coins)
    for i, out in enumerate(tx.vout):
        addr = out.scriptpubkey_address
        amount = Amount(value=str(out.value), currency=currency)

        coin_change = CoinChange(
            coin_id=f"{tx.txid}:{i}",
            action="coin_created"
        )

        op = Operation(
            op_id=f"vout:{i}",
            account=AccountIdentifier(address=addr),
            amount=amount,
            coin_change=coin_change
        )
        operations.append(op)

    evidence = EvidenceRef(
        source=source,
        locator=locator,
        retrieved_at=int(time.time()),
        raw_pointer=f"electrs-doge:{tx.txid}",
        metadata={"endpoint": f"/tx/{tx.txid}"}
    )

    fee_amount = Amount(value=str(-tx.fee), currency=currency) if tx.fee else None

    return Transfer(
        id=tx.txid,
        locator=locator,
        operations=operations,
        evidence_refs=[evidence],
        fee=fee_amount
    )


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
    """Basic address validation (non-empty, reasonable length, alphanumeric)."""
    if not address or len(address) < 20 or len(address) > 100:
        return False
    # Reject obvious placeholders
    placeholders = ["sample", "example", "test", "some_", "placeholder", "unknown"]
    lower = address.lower()
    return not any(p in lower for p in placeholders)


@tool
def get_doge_transaction_electrs(tx_hash: str) -> dict:
    """
    Get Dogecoin transaction details using Electrs API (free, no API key).

    Args:
        tx_hash: The Dogecoin transaction hash (txid) - must be a valid 64-character hex string

    Returns:
        Transaction details including inputs, outputs, confirmations, and fees
    """
    # Validate tx_hash format
    if not _is_valid_tx_hash(tx_hash):
        return {
            "success": False,
            "error": f"Invalid transaction hash format: '{tx_hash}'. Must be 64 hex characters.",
            "chain": "DOGE",
            "txid": tx_hash
        }

    client = ElectrsDogeClient()
    try:
        tx = client.get_transaction(tx_hash)
        transfer = _electrs_tx_to_transfer(tx)

        inputs_info = []
        for i, inp in enumerate(tx.vin):
            if inp.prevout:
                addr = inp.prevout.scriptpubkey_address or "unknown"
                val = inp.prevout.value / 1e8
            else:
                addr = "unknown"
                val = 0
            inputs_info.append(f"vin:{i} <- {addr}: {val:.8f} DOGE")

        outputs_info = []
        for i, out in enumerate(tx.vout):
            addr = out.scriptpubkey_address or "unknown"
            val = out.value / 1e8
            outputs_info.append(f"vout:{i} -> {addr}: {val:.8f} DOGE")

        return {
            "success": True,
            "chain": "DOGE",
            "txid": tx.txid,
            "block_height": tx.status.block_height,
            "block_time": tx.status.block_time,
            "confirmed": tx.status.confirmed,
            "fee_doge": tx.fee / 1e8,
            "size_bytes": tx.size,
            "inputs": inputs_info,
            "outputs": outputs_info,
        }
    except FatalError as e:
        return {"success": False, "error": str(e), "chain": "DOGE", "txid": tx_hash}
    except Exception as e:
        return {"success": False, "error": str(e), "chain": "DOGE", "txid": tx_hash}


@tool
def get_doge_address_info_electrs(address: str) -> dict:
    """
    Get Dogecoin address information using Electrs API (free, no API key).

    Args:
        address: The Dogecoin address - must be a valid address string

    Returns:
        Address balance and transaction statistics
    """
    # Validate address format
    if not _is_valid_address(address):
        return {
            "success": False,
            "error": f"Invalid address format: '{address}'. Must be a valid Dogecoin address.",
            "chain": "DOGE",
            "address": address
        }

    client = ElectrsDogeClient()
    try:
        info = client.get_address_info(address)
        return {
            "success": True,
            "chain": "DOGE",
            "address": info.address,
            "balance_doge": info.balance / 1e8,
            "total_received_doge": info.chain_stats.funded_txo_sum / 1e8,
            "total_spent_doge": info.chain_stats.spent_txo_sum / 1e8,
            "tx_count": info.chain_stats.tx_count,
            "funded_txo_count": info.chain_stats.funded_txo_count,
            "spent_txo_count": info.chain_stats.spent_txo_count,
        }
    except FatalError as e:
        return {"success": False, "error": str(e), "chain": "DOGE", "address": address}
    except Exception as e:
        return {"success": False, "error": str(e), "chain": "DOGE", "address": address}


@tool
def get_doge_address_txs_electrs(
    address: str,
    limit: int = 25,
    min_timestamp: int = 0,
    max_timestamp: int = 0
) -> dict:
    """
    Get recent transactions for a Dogecoin address using Electrs API (free, no API key).

    Use this to find transactions associated with an address for cross-chain tracing.
    Supports time-based filtering to narrow down search window.

    Args:
        address: The Dogecoin address - must be a valid address string
        limit: Maximum number of transactions to return (default 25)
        min_timestamp: Only return txs AFTER this Unix timestamp (0 = no filter)
        max_timestamp: Only return txs BEFORE this Unix timestamp (0 = no filter)

    Returns:
        List of transactions with their details (txid, time, amounts), filtered by time window
    """
    if not _is_valid_address(address):
        return {
            "success": False,
            "error": f"Invalid address format: '{address}'. Must be a valid Dogecoin address.",
            "chain": "DOGE",
            "address": address
        }

    client = ElectrsDogeClient()
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
                "received_doge": received / 1e8,
                "sent_doge": sent / 1e8,
                "net_doge": (received - sent) / 1e8,
                "fee_doge": tx.get("fee", 0) / 1e8,
            })

            # Stop if we have enough
            if len(tx_list) >= limit:
                break

        return {
            "success": True,
            "chain": "DOGE",
            "address": address,
            "tx_count": len(tx_list),
            "time_filter": f"{min_timestamp}-{max_timestamp}" if min_timestamp or max_timestamp else "none",
            "transactions": tx_list,
        }
    except FatalError as e:
        return {"success": False, "error": str(e), "chain": "DOGE", "address": address}
    except Exception as e:
        return {"success": False, "error": str(e), "chain": "DOGE", "address": address}


@tool
def search_doge_txs_by_time(
    min_timestamp: int,
    max_timestamp: int,
    min_amount_doge: float = 0,
    max_amount_doge: float = 0,
    limit: int = 20,
    max_blocks: int = 0
) -> dict:
    """
    Search DOGE transactions within a time window, optionally filtered by amount.

    This tool scans blocks in the time range and returns matching transactions.
    Useful for finding cross-chain source transactions when you don't have a specific address.

    Args:
        min_timestamp: Start of time window (Unix timestamp)
        max_timestamp: End of time window (Unix timestamp)
        min_amount_doge: Minimum transaction output amount in DOGE (0 = no filter)
        max_amount_doge: Maximum transaction output amount in DOGE (0 = no filter)
        limit: Maximum transactions to return (default 20)
        max_blocks: Maximum blocks to scan (0 = auto-compute from time window, ~1 block/min)

    Returns:
        List of transactions matching the criteria with their details
    """
    if min_timestamp <= 0 or max_timestamp <= 0:
        return {
            "success": False,
            "error": "Both min_timestamp and max_timestamp must be positive Unix timestamps",
            "chain": "DOGE"
        }

    if min_timestamp >= max_timestamp:
        return {
            "success": False,
            "error": "min_timestamp must be less than max_timestamp",
            "chain": "DOGE"
        }

    # Auto-compute max_blocks from time window if not specified
    # DOGE block time is ~60 seconds, add 20% buffer
    if max_blocks <= 0:
        time_window_seconds = max_timestamp - min_timestamp
        max_blocks = int((time_window_seconds / 60) * 1.2) + 5  # 20% buffer + 5 extra

    client = ElectrsDogeClient()
    try:
        # Step 1: Find blocks in the time window using binary search
        recent_blocks = client.get_blocks()
        if not recent_blocks:
            return {"success": False, "error": "Could not fetch recent blocks", "chain": "DOGE"}

        latest_block = recent_blocks[0]
        latest_height = latest_block.get("height")
        latest_time = latest_block.get("timestamp")

        # Binary search to find block at max_timestamp
        def find_block_at_time(target_time: int) -> int:
            """Binary search to find block height closest to target time."""
            # Estimate how far back we need to go based on ~60 sec block time
            time_diff = latest_time - target_time
            estimated_blocks_back = int(time_diff / 60) + 10000  # Add buffer
            low = max(0, latest_height - estimated_blocks_back)
            high = latest_height

            while low < high:
                mid = (low + high) // 2
                try:
                    block_hash = client.get_block_hash_by_height(mid)
                    block_info = client.get_block_info(block_hash)
                    block_time = block_info.get("timestamp", 0)

                    if block_time < target_time:
                        low = mid + 1
                    else:
                        high = mid
                except Exception:
                    high = mid
            return low

        # Find block heights for the time window
        end_height = find_block_at_time(max_timestamp) + 5  # Add buffer
        start_height = find_block_at_time(min_timestamp) - 5  # Add buffer
        start_height = max(0, start_height)

        # Step 2: Scan blocks in the range using batch tx endpoint
        blocks_scanned = 0
        tx_list = []
        current_height = end_height

        while current_height >= start_height and blocks_scanned < max_blocks and len(tx_list) < limit:
            try:
                block_hash = client.get_block_hash_by_height(current_height)
                if not block_hash:
                    current_height -= 1
                    continue

                block_info = client.get_block_info(block_hash)
                block_time = block_info.get("timestamp", 0)
                block_height = block_info.get("height", current_height)

                # Check if block is in our time window
                if block_time < min_timestamp:
                    break  # Past our window, stop
                if block_time > max_timestamp:
                    current_height -= 1
                    continue  # Not yet in our window

                blocks_scanned += 1

                # Fetch transactions in batches of 25 using the batch endpoint
                start_index = 0
                max_txs_per_block = 50  # Limit how many txs we check per block

                while start_index < max_txs_per_block and len(tx_list) < limit:
                    try:
                        # Fetch batch of transactions (up to 25 per call)
                        txs_batch = client.get_block_txs(block_hash, start_index)
                        if not txs_batch:
                            break  # No more transactions in this block

                        for tx in txs_batch:
                            if len(tx_list) >= limit:
                                break

                            # Calculate total output value
                            vouts = tx.get("vout", [])
                            total_output = sum(out.get("value", 0) for out in vouts) / 1e8

                            # Apply amount filter if specified
                            if min_amount_doge > 0 and total_output < min_amount_doge:
                                continue
                            if max_amount_doge > 0 and total_output > max_amount_doge:
                                continue

                            # Build output info
                            outputs_info = []
                            for i, out in enumerate(vouts[:5]):  # First 5 outputs
                                addr = out.get("scriptpubkey_address") or "unknown"
                                val = out.get("value", 0) / 1e8
                                outputs_info.append(f"vout:{i} -> {addr}: {val:.8f} DOGE")

                            tx_list.append({
                                "txid": tx.get("txid"),
                                "block_height": block_height,
                                "block_time": block_time,
                                "total_output_doge": total_output,
                                "fee_doge": tx.get("fee", 0) / 1e8,
                                "outputs": outputs_info,
                            })

                        start_index += len(txs_batch)
                        if len(txs_batch) < 25:
                            break  # No more transactions

                    except Exception:
                        break  # Skip remaining txs in this block on error

                current_height -= 1

            except Exception:
                current_height -= 1
                continue

        return {
            "success": True,
            "chain": "DOGE",
            "time_window": f"{min_timestamp}-{max_timestamp}",
            "amount_filter": f"{min_amount_doge}-{max_amount_doge}" if min_amount_doge or max_amount_doge else "none",
            "blocks_scanned": blocks_scanned,
            "tx_count": len(tx_list),
            "transactions": tx_list,
        }
    except FatalError as e:
        return {"success": False, "error": str(e), "chain": "DOGE"}
    except Exception as e:
        return {"success": False, "error": str(e), "chain": "DOGE"}
