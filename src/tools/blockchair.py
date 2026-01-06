"""
Blockchair API tools for multi-chain blockchain queries.

Supports BTC, DOGE, ETH, LTC, BCH.
API Docs: https://blockchair.com/api/docs

Pricing: Free tier 1440 req/day, paid plans available.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from langchain_core.tools import tool

import config
from config import is_utxo_chain, get_asset_unit
from src.tools.base import BaseAPIClient, with_retry, cached
from src.tools.models import UtxoTx, UtxoOutput, AccountTx, Vin, Vout, EthCall
from src.tools.filters import filter_txs, filter_tx_by_address_direction


# Chain name mapping for Blockchair API
CHAIN_MAP = {
    "BTC": "bitcoin",
    "DOGE": "dogecoin",
    "ETH": "ethereum",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
}


class BlockchairClient(BaseAPIClient):
    """Blockchair API client with optional API key."""

    BASE_URL = "https://api.blockchair.com"
    SOURCE_NAME = "blockchair"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_key = config.BLOCKCHAIR_API_KEY

    def _build_url(self, chain: str, endpoint: str) -> str:
        """Build API URL with optional API key."""
        chain_name = CHAIN_MAP.get(chain.upper(), chain.lower())
        url = f"{self.BASE_URL}/{chain_name}/{endpoint}"
        if self.api_key:
            url += f"?key={self.api_key}"
        return url

    def _add_key(self, url: str) -> str:
        """Add API key to URL if available."""
        if self.api_key:
            sep = "&" if "?" in url else "?"
            return f"{url}{sep}key={self.api_key}"
        return url

    def _parse_time(self, time_val) -> Optional[int]:
        """Parse Blockchair time field (can be string or int)."""
        if not time_val:
            return None
        if isinstance(time_val, int):
            return time_val
        if isinstance(time_val, str):
            try:
                dt = datetime.fromisoformat(time_val.replace("Z", "+00:00"))
                # If datetime is naive (no timezone), treat it as UTC
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp())
            except (ValueError, AttributeError):
                return None
        return None

    def to_tx_model_json(self, chain: str, data: Dict[str, Any]) -> dict:
        """Convert Blockchair tx data to UtxoTx/AccountTx model dict.

        Handles both dashboard response (with transaction/inputs/outputs)
        and list response (flat tx dict with hash field).
        """
        # Detect format: dashboard has nested 'transaction', list has flat 'hash'
        if "transaction" in data:
            # Dashboard format
            tx_info = data.get("transaction", {})
            tx_hash = tx_info.get("hash", "")
            inputs = data.get("inputs", [])
            outputs = data.get("outputs", [])
        else:
            # List/search format (flat dict)
            tx_info = data
            tx_hash = data.get("hash", "")
            inputs = []
            outputs = []

        block_id = tx_info.get("block_id")
        block_time = self._parse_time(tx_info.get("time"))
        unit = get_asset_unit(chain)

        if is_utxo_chain(chain):
            # Determine status
            status = "confirmed" if block_id and block_id > 0 else "pending"

            # Parse vin/vout if available (dashboard format)
            vin_list = []
            for i, inp in enumerate(inputs):
                vin_list.append(Vin(
                    n=i,
                    addr=inp.get("recipient"),
                    amount=inp.get("value", 0) / unit if inp.get("value") else None,
                    prev_txid=inp.get("spending_transaction_hash"),
                    prev_vout=inp.get("spending_index")
                ))

            vout_list = []
            for i, out in enumerate(outputs):
                addr = out.get("recipient")
                if addr is None and out.get("type") == "nulldata":
                    addr = "OP_RETURN"
                vout_list.append(Vout(
                    n=i,
                    addr=addr,
                    amount=out.get("value", 0) / unit
                ))

            return UtxoTx(
                chain=chain,
                txid=tx_hash,
                status=status,
                block_height=block_id if block_id and block_id > 0 else None,
                block_time=block_time,
                fee=tx_info.get("fee", 0) / unit if tx_info.get("fee") else 0,
                vin=vin_list,
                vout=vout_list,
                meta={
                    "size": tx_info.get("size"),
                    "weight": tx_info.get("weight"),
                    "input_total": tx_info.get("input_total", 0) / unit if tx_info.get("input_total") else 0,
                    "output_total": tx_info.get("output_total", 0) / unit if tx_info.get("output_total") else 0,
                }
            ).model_dump()
        else:
            # Account chain (ETH)
            if block_id and block_id > 0:
                status = "failed" if tx_info.get("failed", False) else "confirmed"
            else:
                status = "pending"

            return AccountTx(
                chain=chain,
                txid=tx_hash,
                status=status,
                block_height=block_id if block_id and block_id > 0 else None,
                block_time=block_time,
                sender=tx_info.get("sender"),
                recipient=tx_info.get("recipient"),
                amount=int(tx_info.get("value", 0)) / unit if tx_info.get("value") else 0,
                fee=int(tx_info.get("fee", 0)) / unit if tx_info.get("fee") else 0,
                meta={
                    "gas_used": tx_info.get("gas_used"),
                    "gas_price": tx_info.get("gas_price"),
                    "gas_limit": tx_info.get("gas_limit"),
                    "nonce": tx_info.get("nonce"),
                }
            ).model_dump()

    # ==================== Core API Methods ====================

    @cached("blockchair")
    @with_retry()
    def get_transaction(self, chain: str, tx_hash: str) -> Dict[str, Any]:
        """Fetch single transaction details (raw)."""
        tx_hash = tx_hash.lower()
        url = self._build_url(chain, f"dashboards/transaction/{tx_hash}")
        response = self.client.get(url)
        data = self._handle_response(response)
        return data.get("data", {}).get(tx_hash, {})

    @cached("blockchair")
    @with_retry()
    def get_transactions_batch(self, chain: str, tx_hashes: List[str]) -> Dict[str, Any]:
        """Fetch multiple transactions in one API call (max 10 per request)."""
        chain_name = CHAIN_MAP.get(chain.upper(), chain.lower())
        hashes_str = ",".join(h.lower() for h in tx_hashes[:10])
        url = f"{self.BASE_URL}/{chain_name}/dashboards/transactions/{hashes_str}"
        url = self._add_key(url)
        response = self.client.get(url)
        data = self._handle_response(response)
        return data.get("data", {})

    @cached("blockchair")
    @with_retry()
    def get_address(self, chain: str, address: str) -> Dict[str, Any]:
        """Fetch address information."""
        url = self._build_url(chain, f"dashboards/address/{address}")
        response = self.client.get(url)
        data = self._handle_response(response)
        return data.get("data", {}).get(address, {})

    @cached("blockchair")
    @with_retry()
    def get_addresses_txs(
        self,
        chain: str,
        addresses: List[str],
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Fetch address(es) with transaction details.

        Uses batch endpoint for both single and multiple addresses.
        Returns raw API response with 'addresses' and 'transactions' keys.
        """
        chain_name = CHAIN_MAP.get(chain.upper(), chain.lower())
        addr_str = ",".join(addresses[:100])  # Max 100 addresses
        url = f"{self.BASE_URL}/{chain_name}/dashboards/addresses/{addr_str}?limit={limit}&offset={offset}&transaction_details=true"
        url = self._add_key(url)
        response = self.client.get(url)
        data = self._handle_response(response)
        return data.get("data", {})

    @cached("blockchair")
    @with_retry()
    def search_transactions(
        self,
        chain: str,
        min_timestamp: int,
        max_timestamp: int,
        direction: str,
        min_amount: float,
        max_amount: float,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search transactions by time and amount range."""
        chain_name = CHAIN_MAP.get(chain.upper(), chain.lower())
        unit = get_asset_unit(chain)

        # Build query based on chain type
        if is_utxo_chain(chain):
            # For UTXO chains, use output_total or input_total based on direction
            if direction == "in":
                amount_field = "output_total"
            elif direction == "out":
                amount_field = "input_total"
            else:
                # For 'both', default to output_total (more common use case)
                amount_field = "output_total"
        else:
            amount_field = "value"

        # Convert timestamps to ISO format for Blockchair API
        min_time_str = datetime.fromtimestamp(min_timestamp, tz=timezone.utc).strftime("%Y-%m-%d+%H:%M:%S")
        max_time_str = datetime.fromtimestamp(max_timestamp, tz=timezone.utc).strftime("%Y-%m-%d+%H:%M:%S")

        query_parts = [f"time({min_time_str}..{max_time_str})"]

        # Add amount filter if specified
        if min_amount > 0 or max_amount > 0:
            min_sat = int(min_amount * unit) if min_amount > 0 else 0
            max_sat = int(max_amount * unit) if max_amount > 0 else int(1e18)  # Large default max
            query_parts.append(f"{amount_field}({min_sat}..{max_sat})")

        query = f"q={','.join(query_parts)}&limit={limit}&s=time(desc)"
        url = f"{self.BASE_URL}/{chain_name}/transactions?{query}"
        url = self._add_key(url)

        response = self.client.get(url)
        data = self._handle_response(response)
        return data.get("data", [])

    @cached("blockchair")
    @with_retry()
    def search_outputs(
        self,
        chain: str,
        min_timestamp: int,
        max_timestamp: int,
        min_amount: float = 0,
        max_amount: float = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search outputs by amount and time range using infinitable endpoint.

        This endpoint filters on individual output amounts (not tx totals),
        making it suitable for cross-chain tracing where we match single UTXOs.

        Returns list of output dicts with transaction_hash, amount, time, recipient.
        """
        chain_name = CHAIN_MAP.get(chain.upper(), chain.lower())
        unit = get_asset_unit(chain)

        # Build time filter
        min_time_str = datetime.fromtimestamp(min_timestamp, tz=timezone.utc).strftime("%Y-%m-%d+%H:%M:%S")
        max_time_str = datetime.fromtimestamp(max_timestamp, tz=timezone.utc).strftime("%Y-%m-%d+%H:%M:%S")

        query_parts = [f"time({min_time_str}..{max_time_str})"]

        # Add amount filter
        if min_amount > 0 or max_amount > 0:
            min_sat = int(min_amount * unit) if min_amount > 0 else 0
            max_sat = int(max_amount * unit) if max_amount > 0 else int(1e18)
            query_parts.append(f"value({min_sat}..{max_sat})")

        query = f"q={','.join(query_parts)}&s=time(desc)"

        # Fetch with pagination if needed (API max 100 per request)
        all_outputs = []
        offset = 0
        api_limit = min(limit, 100)

        while len(all_outputs) < limit:
            url = f"{self.BASE_URL}/{chain_name}/outputs?{query}&limit={api_limit}&offset={offset}"
            url = self._add_key(url)

            response = self.client.get(url)
            data = self._handle_response(response)
            outputs = data.get("data", [])

            if not outputs:
                break

            all_outputs.extend(outputs)
            offset += len(outputs)

            # Check if we got fewer than requested (no more data)
            if len(outputs) < api_limit:
                break

        return all_outputs[:limit]

    @cached("blockchair")
    @with_retry()
    def search_calls(
        self,
        chain: str,
        min_timestamp: int,
        max_timestamp: int,
        recipient: str = "",
        sender: str = "",
        min_amount: float = 0,
        max_amount: float = 0,
        transferred_only: bool = True,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search internal transactions (calls) by time, address, and amount.

        Only supported for Ethereum mainnet and Goerli testnet.

        IMPORTANT: Value filtering uses ETH unit (not wei) in API queries.
        - Query: value(10) means 10 ETH
        - Response: "value": "10000000000000000000" (wei)

        Args:
            chain: Chain (ETH or ethereum/testnet for Goerli)
            min_timestamp: Start time (Unix)
            max_timestamp: End time (Unix)
            recipient: Recipient address (recommended for performance)
            sender: Sender address
            min_amount: Min amount in ETH (e.g., 9.5)
            max_amount: Max amount in ETH (e.g., 10.5)
            transferred_only: Only return calls with actual ETH transfer
            limit: Max results

        Returns:
            List of call dicts with sender, recipient, value (wei), time, etc.
        """
        chain_name = CHAIN_MAP.get(chain.upper(), chain.lower())

        # Build time filter
        min_time_str = datetime.fromtimestamp(min_timestamp, tz=timezone.utc).strftime("%Y-%m-%d+%H:%M:%S")
        max_time_str = datetime.fromtimestamp(max_timestamp, tz=timezone.utc).strftime("%Y-%m-%d+%H:%M:%S")
        query_parts = [f"time({min_time_str}..{max_time_str})"]

        # Address filter (at least one recommended)
        if recipient:
            query_parts.append(f"recipient({recipient.lower()})")
        elif sender:
            query_parts.append(f"sender({sender.lower()})")

        # Value filter - use ETH directly (NOT wei!)
        if min_amount > 0 or max_amount > 0:
            if max_amount > 0:
                query_parts.append(f"value({min_amount}..{max_amount})")
            else:
                query_parts.append(f"value({min_amount}..)")

        # Only actual transfers
        if transferred_only:
            query_parts.append("transferred(true)")

        query = f"q={','.join(query_parts)}&s=time(desc)"

        # Fetch with pagination
        all_calls = []
        offset = 0
        api_limit = min(limit, 100)

        while len(all_calls) < limit:
            url = f"{self.BASE_URL}/{chain_name}/calls?{query}&limit={api_limit}&offset={offset}"
            url = self._add_key(url)

            response = self.client.get(url)
            data = self._handle_response(response)
            calls = data.get("data", [])

            if not calls:
                break

            all_calls.extend(calls)
            offset += len(calls)

            if len(calls) < api_limit:
                break

        return all_calls[:limit]

    @cached("blockchair")
    @with_retry()
    def get_block(self, chain: str, block_id: str, limit: int = 100) -> Dict[str, Any]:
        """Fetch block dashboard with transaction list."""
        chain_name = CHAIN_MAP.get(chain.upper(), chain.lower())
        url = f"{self.BASE_URL}/{chain_name}/dashboards/block/{block_id}?limit={limit}"
        url = self._add_key(url)
        response = self.client.get(url)
        data = self._handle_response(response)
        return data.get("data", {}).get(str(block_id), {})


# ==================== Validation Helpers ====================

def _is_valid_tx_hash(tx_hash: str) -> bool:
    """Validate transaction hash format."""
    if not tx_hash or len(tx_hash) < 32:
        return False
    try:
        int(tx_hash.replace("0x", ""), 16)
        return True
    except ValueError:
        return False


def _is_valid_address(address: str) -> bool:
    """Basic address validation."""
    if not address or len(address) < 20:
        return False
    placeholders = ["sample", "example", "test", "some_", "placeholder"]
    return not any(p in address.lower() for p in placeholders)


def _validate_chain(chain: str) -> str:
    """Validate and normalize chain name."""
    chain = chain.upper()
    if chain not in CHAIN_MAP:
        raise ValueError(f"Unsupported chain: {chain}. Supported: {list(CHAIN_MAP.keys())}")
    return chain


def _validate_direction_for_search(chain: str, direction: str, min_amount: float, max_amount: float) -> str:
    """Validate direction parameter for search_txs (UTXO + amount requires direction)."""
    if is_utxo_chain(chain) and (min_amount > 0 or max_amount > 0):
        if not direction or direction not in ("in", "out", "both"):
            raise ValueError(
                f"direction is required for UTXO chain '{chain}' when amount filter is specified. "
                f"Use 'in' (vout), 'out' (vin), or 'both'."
            )
    return direction if direction else "both"


# ==================== Trace Tools (Core) ====================

@tool
def get_txs_blockchair(chain: str, tx_hashes: str) -> dict:
    """
    Batch get transaction details. Multi-chain: BTC/DOGE/ETH/LTC/BCH. Paid API.

    Args:
        chain: Chain (BTC, DOGE, ETH, LTC, BCH)
        tx_hashes: Comma-separated transaction hashes

    Returns:
        txs[]: List of UtxoTx or AccountTx with full details
    """
    chain = _validate_chain(chain)

    # Parse and validate hashes
    hashes = [h.strip() for h in tx_hashes.split(",") if h.strip()]
    if not hashes:
        raise ValueError("No valid transaction hashes provided")

    for h in hashes:
        if not _is_valid_tx_hash(h):
            raise ValueError(f"Invalid tx hash format: '{h}'")

    client = BlockchairClient()
    results = []

    # Blockchair supports batch of 10 txs per request
    for i in range(0, len(hashes), 10):
        batch = hashes[i:i+10]
        data = client.get_transactions_batch(chain, batch)
        for tx_hash in batch:
            tx_data = data.get(tx_hash.lower())
            if tx_data:
                results.append(client.to_tx_model_json(chain, tx_data))

    return results


@tool
def search_txs_blockchair(
    chain: str,
    min_timestamp: int = 0,
    max_timestamp: int = 0,
    direction: str = "",
    min_amount: float = 0,
    max_amount: float = 0,
    limit: int = 100
) -> dict:
    """
    Search transactions across the chain. Multi-chain: BTC/DOGE/ETH/LTC/BCH. Paid API.

    Args:
        chain: Chain (BTC, DOGE, ETH, LTC, BCH)
        min_timestamp: Start time (Unix), 0 = no lower bound
        max_timestamp: End time (Unix), 0 = no upper bound
        direction: "in" (vout), "out" (vin), "both" - REQUIRED for UTXO chains when amount specified
        min_amount: Min single vin/vout amount (native unit: BTC/DOGE/ETH), 0 = no filter
        max_amount: Max single vin/vout amount, 0 = no upper bound, equal to min = exact match
        limit: Max results (default 100)

    Returns:
        txs[]: List of UtxoTx or AccountTx matching criteria
    """
    chain = _validate_chain(chain)
    direction = _validate_direction_for_search(chain, direction, min_amount, max_amount)

    if min_timestamp <= 0 and max_timestamp <= 0:
        raise ValueError("At least one of min_timestamp or max_timestamp must be specified")

    if not config.BLOCKCHAIR_API_KEY:
        raise ValueError("Blockchair API key required for transaction search. Set BLOCKCHAIR_API_KEY.")

    client = BlockchairClient()
    is_utxo = is_utxo_chain(chain)

    # For UTXO chains: API filters by input_total/output_total (tx total), but we want
    # single vin/vout matching. So we DON'T pass amount to API and filter in Python instead.
    # This avoids missing txs where single vin/vout matches but total doesn't.
    # NOTE: Blockchair transactions endpoint has max limit=100
    if is_utxo and (min_amount > 0 or max_amount > 0):
        # Fetch without amount filter, then filter in Python by individual vin/vout
        # API max is 100, so we use that and hope time window is narrow enough
        api_limit = 100
        txs_raw = client.search_transactions(
            chain, min_timestamp, max_timestamp, direction,
            min_amount=0, max_amount=0, limit=api_limit
        )
    else:
        # Account chains or no amount filter - use API filtering directly
        txs_raw = client.search_transactions(
            chain, min_timestamp, max_timestamp, direction, min_amount, max_amount, limit
        )

    # Convert to model format - need full tx details for vin/vout filtering
    # API search only returns summary, so fetch full details for amount filtering
    if is_utxo and (min_amount > 0 or max_amount > 0) and txs_raw:
        # Batch fetch full tx details
        tx_hashes = [tx.get("hash") for tx in txs_raw if tx.get("hash")]
        txs = []
        for i in range(0, len(tx_hashes), 10):
            batch = tx_hashes[i:i+10]
            batch_data = client.get_transactions_batch(chain, batch)
            for h in batch:
                tx_data = batch_data.get(h.lower())
                if tx_data:
                    txs.append(client.to_tx_model_json(chain, tx_data))
    else:
        txs = [client.to_tx_model_json(chain, tx) for tx in txs_raw]

    # Apply Python filter for individual vin/vout amounts
    if min_amount > 0 or max_amount > 0:
        txs = filter_txs(
            txs,
            direction=direction,
            min_amount=min_amount,
            max_amount=max_amount,
            is_utxo=is_utxo,
            limit=limit
        )

    return txs[:limit]


@tool
def search_utxo_outputs_blockchair(
    chain: str,
    min_timestamp: int = 0,
    max_timestamp: int = 0,
    min_amount: float = 0,
    max_amount: float = 0,
    limit: int = 100
) -> List[dict]:
    """
    Search individual outputs (vouts) by amount and time. Only for UTXO chain: BTC/DOGE/LTC/BCH. Paid API.

    This is a search_txs category tool - it searches and filters transaction outputs.
    Unlike other search_txs tools which filter by tx total, this filters by INDIVIDUAL output amount.
    Best for cross-chain tracing where you need to match a specific UTXO amount.

    Args:
        chain: Chain (BTC, DOGE, LTC, BCH) - NOT ETH (no UTXO)
        min_timestamp: Start time (Unix), 0 = no lower bound
        max_timestamp: End time (Unix), 0 = no upper bound
        min_amount: Min output amount (native unit: BTC/DOGE), 0 = no filter
        max_amount: Max output amount, 0 = no upper bound
        limit: Max results (default 100, supports pagination internally)

    Returns:
        List[Transfer]: List of lightweight Transfers, each with single vout operation.
        Each Transfer has operations dict with "vout:N" key containing amount and address.
    """
    chain = _validate_chain(chain)

    if not is_utxo_chain(chain):
        raise ValueError(f"search_outputs only supports UTXO chains. {chain} is not supported.")

    if min_timestamp <= 0 and max_timestamp <= 0:
        raise ValueError("At least one of min_timestamp or max_timestamp must be specified")

    if not config.BLOCKCHAIR_API_KEY:
        raise ValueError("Blockchair API key required. Set BLOCKCHAIR_API_KEY.")

    client = BlockchairClient()

    outputs_raw = client.search_outputs(
        chain, min_timestamp, max_timestamp, min_amount, max_amount, limit
    )

    unit = get_asset_unit(chain)

    # Convert to UtxoOutput model
    results = []
    for out in outputs_raw:
        output = UtxoOutput(
            chain=chain,
            txid=out.get("transaction_hash"),
            n=out.get("index"),
            amount=out.get("value", 0) / unit,
            addr=out.get("recipient"),
            block_time=client._parse_time(out.get("time")),
        )
        results.append(output.model_dump())

    return results


@tool
def search_eth_calls_blockchair(
    min_timestamp: int = 0,
    max_timestamp: int = 0,
    recipient: str = "",
    sender: str = "",
    min_amount: float = 0,
    max_amount: float = 0,
    limit: int = 100
) -> List[dict]:
    """
    Search ETH internal transactions (calls) by time, address, and amount. Only for ETH mainnet. Paid API.

    This is a search_txs category tool - it searches and filters internal calls/transfers.
    Unlike ETH transactions which show only top-level transfers, this shows ALL internal
    transfers including those from smart contracts (e.g., LiFi, THORChain Router, etc.).
    Best for cross-chain tracing where ETH transfers happen through intermediary contracts.

    IMPORTANT: Value amounts use ETH unit (not wei):
    - Query: value(10) = 10 ETH
    - Response: "value": "10000000000000000000" (wei, converted to ETH in result)

    Args:
        min_timestamp: Start time (Unix), 0 = no lower bound
        max_timestamp: End time (Unix), 0 = no upper bound
        recipient: Recipient address (strongly recommended for performance)
        sender: Sender address (use if recipient unknown)
        min_amount: Min transfer amount in ETH (e.g., 9.5), 0 = no filter
        max_amount: Max transfer amount in ETH (e.g., 10.5), 0 = no upper bound
        limit: Max results (default 100, supports pagination internally)

    Returns:
        List[EthCall]: List of internal calls with sender, recipient, amount (ETH), time.
        Each call represents an actual ETH transfer at any call depth.

    Example:
        # Find 10 ETH transfers through LiFi to THORChain vault
        search_eth_calls_blockchair(
            recipient="0xd03d56ef7d11a1a5a0933c1d524ff0bc1e916c98",
            min_timestamp=swap_time - 600,
            max_timestamp=swap_time + 600,
            min_amount=9.5,
            max_amount=10.5,
            limit=100
        )
    """
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


@tool
def get_addresses_txs_blockchair(
    chain: str,
    addresses: str,
    min_timestamp: int = 0,
    max_timestamp: int = 0,
    direction: str = "both",
    min_amount: float = 0,
    max_amount: float = 0,
    limit: int = 100
) -> dict:
    """
    Get transaction history for addresses with filtering. Multi-chain: BTC/DOGE/ETH/LTC/BCH. Paid API.

    Args:
        chain: Chain (BTC, DOGE, ETH, LTC, BCH)
        addresses: Comma-separated addresses (max 100)
        min_timestamp: Filter after this Unix time (0 = no filter)
        max_timestamp: Filter before this Unix time (0 = no filter)
        direction: "in" (receiving), "out" (sending), "both" (default)
        min_amount: Min single vin/vout amount involving the address (native unit), 0 = no filter
        max_amount: Max single vin/vout amount, 0 = no upper bound
        limit: Max txs per address (default 100)

    Returns:
        {address: txs[]} - Transactions grouped by address
    """
    chain = _validate_chain(chain)

    # Parse and validate addresses
    addr_list = [a.strip() for a in addresses.split(",") if a.strip()]
    if not addr_list:
        raise ValueError("No valid addresses provided")
    if len(addr_list) > 100:
        raise ValueError("Max 100 addresses per request")

    for addr in addr_list:
        if not _is_valid_address(addr):
            raise ValueError(f"Invalid address: {addr}")

    if direction not in ("in", "out", "both"):
        raise ValueError(f"Invalid direction: {direction}. Use 'in', 'out', or 'both'.")

    client = BlockchairClient()
    is_utxo = is_utxo_chain(chain)

    # Fetch txs from API
    api_limit = min(limit * 2, 1000)  # Fetch extra for filtering
    data = client.get_addresses_txs(chain, addr_list, limit=api_limit)
    if not data:
        raise ValueError("No data returned for addresses")

    txs_data = data.get("transactions", [])

    # Group txs by address
    result: Dict[str, list] = {addr: [] for addr in addr_list}

    for tx in txs_data:
        tx_model = client.to_tx_model_json(chain, tx)

        # Apply time filter
        block_time = tx_model.get("block_time")
        if min_timestamp > 0 and block_time and block_time < min_timestamp:
            continue
        if max_timestamp > 0 and block_time and block_time > max_timestamp:
            continue

        # Find which addresses this tx involves and check direction
        for orig_addr in addr_list:
            if len(result[orig_addr]) >= limit:
                continue

            # Check if this tx involves the address in the specified direction
            if not filter_tx_by_address_direction(tx_model, orig_addr, direction, is_utxo):
                continue

            # Check amount filter (only for vin/vout involving this address)
            if min_amount > 0 or max_amount > 0:
                has_matching_amount = False
                if is_utxo:
                    addr_lower = orig_addr.lower()
                    if direction in ("out", "both"):
                        for vin in tx_model.get("vin", []):
                            if vin.get("addr") and vin["addr"].lower() == addr_lower:
                                val = vin.get("value")
                                if val is not None:
                                    if (min_amount <= 0 or val >= min_amount) and (max_amount <= 0 or val <= max_amount):
                                        has_matching_amount = True
                                        break
                    if not has_matching_amount and direction in ("in", "both"):
                        for vout in tx_model.get("vout", []):
                            if vout.get("addr") and vout["addr"].lower() == addr_lower:
                                val = vout.get("value")
                                if val is not None:
                                    if (min_amount <= 0 or val >= min_amount) and (max_amount <= 0 or val <= max_amount):
                                        has_matching_amount = True
                                        break
                else:
                    # Account chain - just check amount
                    val = tx_model.get("value")
                    if val is not None:
                        if (min_amount <= 0 or val >= min_amount) and (max_amount <= 0 or val <= max_amount):
                            has_matching_amount = True

                if not has_matching_amount:
                    continue

            result[orig_addr].append(tx_model)

    return result


# ==================== Utility Tools (Non-trace) ====================

@tool
def get_block_txs_blockchair(chain: str, block_id: str, limit: int = 100) -> dict:
    """
    Get block tx hashes (not full details). Multi-chain: BTC/DOGE/ETH/LTC/BCH. Paid API.

    Note: Returns tx hashes only. Use get_txs_blockchair for full tx details.

    Args:
        chain: Chain (BTC, DOGE, ETH, LTC, BCH)
        block_id: Block height or hash
        limit: Max tx hashes to return (default 100, max 10000)

    Returns:
        block_id, block_hash, time, tx_count, tx_hashes[]
    """
    chain = _validate_chain(chain)

    client = BlockchairClient()
    api_limit = min(limit, 10000)
    data = client.get_block(chain, block_id, limit=api_limit)
    if not data:
        raise ValueError(f"Block not found: {block_id}")

    block_info = data.get("block", {})
    tx_hashes = data.get("transactions", [])

    result = {
        "block_id": block_info.get("id"),
        "block_hash": block_info.get("hash"),
        "time": block_info.get("time"),
        "tx_count": block_info.get("transaction_count", len(tx_hashes)),
        "tx_hashes": tx_hashes[:limit],
    }

    return result


@tool
def get_address_blockchair(chain: str, address: str) -> dict:
    """
    Get address balance and stats (no tx details). Multi-chain: BTC/DOGE/ETH/LTC/BCH. Paid API.

    Args:
        chain: Chain (BTC, DOGE, ETH, LTC, BCH)
        address: Wallet address

    Returns:
        balance, tx_count, first_seen, last_seen
    """
    chain = _validate_chain(chain)

    if not _is_valid_address(address):
        raise ValueError(f"Invalid address: {address}")

    client = BlockchairClient()
    data = client.get_address(chain, address)
    if not data:
        raise ValueError(f"Address not found: {address}")

    addr_info = data.get("address", {})

    return {
        "balance": addr_info.get("balance"),
        "tx_count": addr_info.get("transaction_count") or addr_info.get("call_count", 0),
        "first_seen": addr_info.get("first_seen_receiving"),
        "last_seen": addr_info.get("last_seen_receiving"),
    }
