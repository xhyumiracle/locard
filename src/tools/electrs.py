"""
Electrs-Doge API tools for Dogecoin queries.

Free, no API key. May have rate limits - use judiciously.
"""

from typing import Optional, List, Dict, Any

from langchain_core.tools import tool
from pydantic import BaseModel

from config import get_asset_unit
from src.tools.base import BaseAPIClient, with_retry, FatalError, cached
from src.tools.models import UtxoTx, Vin, Vout
from src.tools.filters import filter_tx_by_time, filter_tx_by_address_direction


# ==================== Pydantic Models for API Response ====================

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


# ==================== API Client ====================

class ElectrsDogeClient(BaseAPIClient):
    """Electrs-Doge API client (free, no auth) with file caching."""

    BASE_URL = "https://doge-electrs-demo.qed.me"
    SOURCE_NAME = "electrs-doge"

    @cached("electrs-doge")
    @with_retry()
    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """Fetch transaction details (cached)."""
        tx_hash = tx_hash.lower()
        url = f"{self.BASE_URL}/tx/{tx_hash}"
        response = self.client.get(url)
        return self._handle_response(response)

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


# ==================== Conversion Helpers ====================

# DOGE unit conversion factor
DOGE_UNIT = get_asset_unit("DOGE")

def _raw_tx_to_model(tx_data: dict) -> dict:
    """Convert raw Electrs tx dict to UtxoTx model dict."""
    status = tx_data.get("status", {})
    block_time = status.get("block_time")

    vin_list = []
    for i, inp in enumerate(tx_data.get("vin", [])):
        prevout = inp.get("prevout", {})
        vin_list.append(Vin(
            n=i,
            addr=prevout.get("scriptpubkey_address") if prevout else None,
            amount=prevout.get("value", 0) / DOGE_UNIT if prevout and prevout.get("value") else None,
            prev_txid=inp.get("txid"),
            prev_vout=inp.get("vout")
        ))

    vout_list = []
    for i, out in enumerate(tx_data.get("vout", [])):
        addr = out.get("scriptpubkey_address")
        if addr is None and out.get("scriptpubkey_type") == "op_return":
            addr = "OP_RETURN"
        vout_list.append(Vout(
            n=i,
            addr=addr,
            amount=out.get("value", 0) / DOGE_UNIT
        ))

    return UtxoTx(
        chain="DOGE",
        txid=tx_data.get("txid"),
        status="confirmed" if status.get("confirmed") else "pending",
        block_height=status.get("block_height"),
        block_time=block_time,
        fee=tx_data.get("fee", 0) / DOGE_UNIT,
        vin=vin_list,
        vout=vout_list,
        meta={
            "size": tx_data.get("size"),
            "weight": tx_data.get("weight"),
        }
    ).model_dump()


# ==================== Validation Helpers ====================

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
    placeholders = ["sample", "example", "test", "some_", "placeholder", "unknown"]
    lower = address.lower()
    return not any(p in lower for p in placeholders)


def _validate_direction_for_search(direction: str, min_amount: float, max_amount: float) -> str:
    """Validate direction parameter for search_txs (UTXO + amount requires direction)."""
    if min_amount > 0 or max_amount > 0:
        if not direction or direction not in ("in", "out", "both"):
            raise ValueError(
                "direction is required when amount filter is specified. "
                "Use 'in' (vout), 'out' (vin), or 'both'."
            )
    return direction if direction else "both"


def _check_tx_amount(tx: dict, direction: str, min_amount: float, max_amount: float) -> bool:
    """Check if tx has vin/vout within amount range."""
    if min_amount <= 0 and max_amount <= 0:
        return True

    def matches(val):
        if val is None:
            return False
        if min_amount > 0 and val < min_amount:
            return False
        if max_amount > 0 and val > max_amount:
            return False
        return True

    if direction in ("out", "both"):
        for vin in tx.get("vin", []):
            if matches(vin.get("value")):
                return True
    if direction in ("in", "both"):
        for vout in tx.get("vout", []):
            if matches(vout.get("value")):
                return True
    return False


def _check_tx_amount_for_address(
    tx: dict, address: str, direction: str, min_amount: float, max_amount: float
) -> bool:
    """Check if tx has vin/vout involving address within amount range."""
    if min_amount <= 0 and max_amount <= 0:
        return True

    addr_lower = address.lower()

    def matches(val):
        if val is None:
            return False
        if min_amount > 0 and val < min_amount:
            return False
        if max_amount > 0 and val > max_amount:
            return False
        return True

    if direction in ("out", "both"):
        for vin in tx.get("vin", []):
            if vin.get("addr") and vin["addr"].lower() == addr_lower:
                if matches(vin.get("value")):
                    return True
    if direction in ("in", "both"):
        for vout in tx.get("vout", []):
            if vout.get("addr") and vout["addr"].lower() == addr_lower:
                if matches(vout.get("value")):
                    return True
    return False


# ==================== Trace Tools (Core) ====================

@tool
def get_txs_doge_electrs(tx_hashes: str) -> dict:
    """
    Batch get DOGE transaction details. DOGE ONLY - do not use for other chains.

    Free API (no batch endpoint, uses loop internally).

    Args:
        tx_hashes: Comma-separated DOGE transaction hashes

    Returns:
        txs[]: List of UtxoTx with full details
    """
    hashes = [h.strip() for h in tx_hashes.split(",") if h.strip()]
    if not hashes:
        raise ValueError("No valid transaction hashes provided")

    for h in hashes:
        if not _is_valid_tx_hash(h):
            raise ValueError(f"Invalid tx hash format: '{h}'. Must be 64 hex characters.")

    client = ElectrsDogeClient()
    results = []

    # Electrs has no batch endpoint - loop through each hash
    for tx_hash in hashes:
        try:
            tx_data = client.get_transaction(tx_hash)
            results.append(_raw_tx_to_model(tx_data))
        except FatalError:
            # Skip not found txs, continue with others
            pass

    return results


@tool
def search_txs_doge_electrs(
    min_timestamp: int = 0,
    max_timestamp: int = 0,
    direction: str = "",
    min_amount: float = 0,
    max_amount: float = 0,
    limit: int = 100
) -> dict:
    """
    Search DOGE transactions by time and amount. DOGE ONLY - do not use for other chains.

    Free API. Scans blocks in time range.

    Args:
        min_timestamp: Start time (Unix), 0 = no lower bound
        max_timestamp: End time (Unix), 0 = no upper bound
        direction: "in" (vout), "out" (vin), "both" - REQUIRED when amount specified
        min_amount: Min single vin/vout amount (DOGE), 0 = no filter
        max_amount: Max single vin/vout amount, 0 = no upper bound, equal to min = exact match
        limit: Max results (default 100)

    Returns:
        txs[]: List of UtxoTx matching criteria
    """
    direction = _validate_direction_for_search(direction, min_amount, max_amount)

    if min_timestamp <= 0 and max_timestamp <= 0:
        raise ValueError("At least one of min_timestamp or max_timestamp must be specified")

    client = ElectrsDogeClient()

    # Get recent blocks to find the time range
    recent_blocks = client.get_blocks()
    if not recent_blocks:
        raise ValueError("Could not fetch recent blocks")

    latest_block = recent_blocks[0]
    latest_height = latest_block.get("height")
    latest_time = latest_block.get("timestamp")

    # Binary search to find block at target time
    def find_block_at_time(target_time: int) -> int:
        time_diff = latest_time - target_time
        estimated_blocks_back = int(time_diff / 60) + 10000
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

    # Find block heights for time window
    if max_timestamp > 0:
        end_height = find_block_at_time(max_timestamp) + 5
    else:
        end_height = latest_height

    if min_timestamp > 0:
        start_height = find_block_at_time(min_timestamp) - 5
        start_height = max(0, start_height)
    else:
        # Default to scanning last 100 blocks if no min time
        start_height = max(0, end_height - 100)

    # Auto-compute max blocks from time window
    max_blocks = int((end_height - start_height) * 1.2) + 10

    # Scan blocks
    tx_list = []
    blocks_scanned = 0
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

            # Check time bounds
            if min_timestamp > 0 and block_time < min_timestamp:
                break
            if max_timestamp > 0 and block_time > max_timestamp:
                current_height -= 1
                continue

            blocks_scanned += 1

            # Fetch txs in batches of 25
            start_index = 0
            max_txs_per_block = 100

            while start_index < max_txs_per_block and len(tx_list) < limit:
                try:
                    txs_batch = client.get_block_txs(block_hash, start_index)
                    if not txs_batch:
                        break

                    for tx_raw in txs_batch:
                        if len(tx_list) >= limit:
                            break

                        tx_model = _raw_tx_to_model(tx_raw)

                        # Apply amount filter
                        if not _check_tx_amount(tx_model, direction, min_amount, max_amount):
                            continue

                        tx_list.append(tx_model)

                    start_index += len(txs_batch)
                    if len(txs_batch) < 25:
                        break
                except Exception:
                    break

            current_height -= 1
        except Exception:
            current_height -= 1
            continue

    return tx_list


@tool
def get_addresses_txs_doge_electrs(
    addresses: str,
    min_timestamp: int = 0,
    max_timestamp: int = 0,
    direction: str = "both",
    min_amount: float = 0,
    max_amount: float = 0,
    limit: int = 100
) -> dict:
    """
    Get DOGE transaction history for addresses with filtering. DOGE ONLY - do not use for other chains.

    Free API.

    Args:
        addresses: Comma-separated DOGE addresses
        min_timestamp: Filter after this Unix time (0 = no filter)
        max_timestamp: Filter before this Unix time (0 = no filter)
        direction: "in" (receiving), "out" (sending), "both" (default)
        min_amount: Min single vin/vout amount involving the address (DOGE), 0 = no filter
        max_amount: Max single vin/vout amount, 0 = no upper bound
        limit: Max txs per address (default 100)

    Returns:
        {address: txs[]} - Transactions grouped by address
    """
    addr_list = [a.strip() for a in addresses.split(",") if a.strip()]
    if not addr_list:
        raise ValueError("No valid addresses provided")

    for addr in addr_list:
        if not _is_valid_address(addr):
            raise ValueError(f"Invalid address format: '{addr}'")

    if direction not in ("in", "out", "both"):
        raise ValueError(f"Invalid direction: {direction}. Use 'in', 'out', or 'both'.")

    client = ElectrsDogeClient()
    result: Dict[str, list] = {addr: [] for addr in addr_list}

    # Electrs has no batch address endpoint - loop through each
    for addr in addr_list:
        try:
            txs_raw = client.get_address_txs(addr)

            for tx_raw in txs_raw:
                if len(result[addr]) >= limit:
                    break

                tx_model = _raw_tx_to_model(tx_raw)

                # Apply time filter
                if not filter_tx_by_time(tx_model, min_timestamp, max_timestamp):
                    continue

                # Apply direction filter
                if not filter_tx_by_address_direction(tx_model, addr, direction, is_utxo=True):
                    continue

                # Apply amount filter for this address
                if not _check_tx_amount_for_address(tx_model, addr, direction, min_amount, max_amount):
                    continue

                result[addr].append(tx_model)

        except FatalError:
            # Address not found - leave empty list
            pass

    return result


# ==================== Utility Tools (Non-trace) ====================

@tool
def get_address_doge_electrs(address: str) -> dict:
    """
    Get DOGE address balance and stats (no tx details). DOGE ONLY - do not use for other chains.

    Free API.

    Args:
        address: DOGE address

    Returns:
        chain, balance, total_received, total_spent, tx_count
    """
    if not _is_valid_address(address):
        raise ValueError(f"Invalid address format: '{address}'")

    client = ElectrsDogeClient()
    info = client.get_address_info(address)

    return {
        "chain": "DOGE",
        "balance": info.balance / DOGE_UNIT,
        "total_received": info.chain_stats.funded_txo_sum / DOGE_UNIT,
        "total_spent": info.chain_stats.spent_txo_sum / DOGE_UNIT,
        "tx_count": info.chain_stats.tx_count,
    }
