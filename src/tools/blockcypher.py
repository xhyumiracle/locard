"""
BlockCypher API tools for BTC/DOGE transaction queries.

API Docs: https://www.blockcypher.com/dev/bitcoin/
Free tier: 1000 requests/day (no API key required for testing)
"""

import time
from typing import Literal, Optional, List, Dict, Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

import config
from src.tools.base import BaseAPIClient, with_retry, FatalError
from src.models.core import (
    TxLocator, Transfer, Operation, AccountIdentifier,
    Currency, Amount, CoinChange, EvidenceRef
)


CoinType = Literal["btc", "doge", "ltc"]
ChainType = Literal["main", "test3"]


class BlockCypherTxInput(BaseModel):
    prev_hash: Optional[str] = None
    output_index: Optional[int] = None
    output_value: Optional[int] = None
    addresses: Optional[List[str]] = None
    script_type: Optional[str] = None


class BlockCypherTxOutput(BaseModel):
    value: int
    addresses: Optional[List[str]] = None
    script_type: Optional[str] = None
    spent_by: Optional[str] = None


class BlockCypherTransaction(BaseModel):
    hash: str
    block_height: Optional[int] = None
    block_hash: Optional[str] = None
    total: int
    fees: int
    size: int
    confirmations: int
    confirmed: Optional[str] = None
    received: Optional[str] = None
    inputs: List[BlockCypherTxInput]
    outputs: List[BlockCypherTxOutput]


class BlockCypherClient(BaseAPIClient):
    """BlockCypher API client for BTC/DOGE queries."""

    BASE_URL = "https://api.blockcypher.com/v1"
    SOURCE_NAME = "blockcypher"

    def __init__(self, token: Optional[str] = None):
        super().__init__()
        self.token = token or config.BLOCKCYPHER_TOKEN

    def _build_url(self, coin: CoinType, chain: ChainType, endpoint: str) -> str:
        url = f"{self.BASE_URL}/{coin}/{chain}{endpoint}"
        # Only add token if it's a valid alphanumeric token (not a comment)
        if self.token and self.token.isalnum():
            url += f"?token={self.token}"
        return url

    @with_retry()
    def get_transaction(
        self,
        tx_hash: str,
        coin: CoinType = "btc",
        chain: ChainType = "main"
    ) -> BlockCypherTransaction:
        """Fetch transaction details."""
        url = self._build_url(coin, chain, f"/txs/{tx_hash}")
        response = self.client.get(url)
        data = self._handle_response(response)
        return BlockCypherTransaction(**data)

    @with_retry()
    def get_address_balance(
        self,
        address: str,
        coin: CoinType = "btc",
        chain: ChainType = "main"
    ) -> Dict[str, Any]:
        """Fetch address balance and stats."""
        url = self._build_url(coin, chain, f"/addrs/{address}/balance")
        response = self.client.get(url)
        return self._handle_response(response)

    @with_retry()
    def get_address_full(
        self,
        address: str,
        coin: CoinType = "btc",
        chain: ChainType = "main",
        limit: int = 50
    ) -> Dict[str, Any]:
        """Fetch address with transaction history."""
        url = self._build_url(coin, chain, f"/addrs/{address}/full")
        if "?" in url:
            url += f"&limit={limit}"
        else:
            url += f"?limit={limit}"
        response = self.client.get(url)
        return self._handle_response(response)


def _blockcypher_tx_to_transfer(
    tx: BlockCypherTransaction,
    coin: str,
    source: str = "blockcypher"
) -> Transfer:
    """Convert BlockCypher transaction to internal Transfer model."""
    chain = coin.upper()
    currency = Currency(symbol=chain, decimals=8)

    # Parse block time if available
    block_time = None
    if tx.confirmed:
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(tx.confirmed.replace("Z", "+00:00"))
            block_time = int(dt.timestamp())
        except:
            pass

    locator = TxLocator(
        chain=chain,
        txid=tx.hash,
        status="confirmed" if tx.confirmations > 0 else "mempool",
        block_height=tx.block_height,
        block_hash=tx.block_hash,
        block_time=block_time
    )

    operations: List[Operation] = []

    # Process inputs (spent coins)
    for i, inp in enumerate(tx.inputs):
        if inp.addresses:
            addr = inp.addresses[0]
        else:
            addr = None

        value = str(-inp.output_value) if inp.output_value else None
        amount = Amount(value=value, currency=currency) if value else None

        coin_change = None
        if inp.prev_hash:
            coin_change = CoinChange(
                coin_id=f"{inp.prev_hash}:{inp.output_index}",
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
    for i, out in enumerate(tx.outputs):
        addr = out.addresses[0] if out.addresses else None
        amount = Amount(value=str(out.value), currency=currency)

        coin_change = CoinChange(
            coin_id=f"{tx.hash}:{i}",
            action="coin_created"
        )

        op = Operation(
            op_id=f"vout:{i}",
            account=AccountIdentifier(address=addr),
            amount=amount,
            coin_change=coin_change
        )
        operations.append(op)

    # Build evidence ref
    evidence = EvidenceRef(
        source=source,
        locator=locator,
        retrieved_at=int(time.time()),
        raw_pointer=f"blockcypher:{coin}:{tx.hash}",
        metadata={"endpoint": f"/txs/{tx.hash}"}
    )

    fee_amount = Amount(value=str(-tx.fees), currency=currency) if tx.fees else None

    return Transfer(
        id=tx.hash,
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
    """Basic address validation (non-empty, reasonable length)."""
    if not address or len(address) < 20 or len(address) > 100:
        return False
    # Reject obvious placeholders
    placeholders = ["sample", "example", "test", "some_", "placeholder", "unknown"]
    lower = address.lower()
    return not any(p in lower for p in placeholders)


@tool
def get_btc_transaction(tx_hash: str) -> dict:
    """
    Get Bitcoin transaction details by transaction hash.

    Args:
        tx_hash: The Bitcoin transaction hash (txid) - must be a valid 64-character hex string

    Returns:
        Transaction details including inputs, outputs, confirmations, and fees
    """
    if not _is_valid_tx_hash(tx_hash):
        return {
            "success": False,
            "error": f"Invalid transaction hash format: '{tx_hash}'. Must be 64 hex characters.",
            "chain": "BTC",
            "txid": tx_hash
        }

    client = BlockCypherClient()
    try:
        tx = client.get_transaction(tx_hash, coin="btc")
        transfer = _blockcypher_tx_to_transfer(tx, "btc")

        # Format for LLM consumption
        inputs_info = []
        for inp in tx.inputs:
            addrs = inp.addresses[0] if inp.addresses else "unknown"
            val = inp.output_value / 1e8 if inp.output_value else 0
            inputs_info.append(f"{addrs}: {val:.8f} BTC")

        outputs_info = []
        for i, out in enumerate(tx.outputs):
            addrs = out.addresses[0] if out.addresses else "unknown"
            val = out.value / 1e8
            outputs_info.append(f"vout:{i} -> {addrs}: {val:.8f} BTC")

        return {
            "success": True,
            "chain": "BTC",
            "txid": tx.hash,
            "block_height": tx.block_height,
            "confirmations": tx.confirmations,
            "total_btc": tx.total / 1e8,
            "fee_btc": tx.fees / 1e8,
            "inputs": inputs_info,
            "outputs": outputs_info,
            "confirmed_time": tx.confirmed,
        }
    except FatalError as e:
        return {"success": False, "error": str(e), "chain": "BTC", "txid": tx_hash}
    except Exception as e:
        return {"success": False, "error": str(e), "chain": "BTC", "txid": tx_hash}


@tool
def get_doge_transaction(tx_hash: str) -> dict:
    """
    Get Dogecoin transaction details by transaction hash.

    Args:
        tx_hash: The Dogecoin transaction hash (txid) - must be a valid 64-character hex string

    Returns:
        Transaction details including inputs, outputs, confirmations, and fees
    """
    if not _is_valid_tx_hash(tx_hash):
        return {
            "success": False,
            "error": f"Invalid transaction hash format: '{tx_hash}'. Must be 64 hex characters.",
            "chain": "DOGE",
            "txid": tx_hash
        }

    client = BlockCypherClient()
    try:
        tx = client.get_transaction(tx_hash, coin="doge")
        transfer = _blockcypher_tx_to_transfer(tx, "doge")

        inputs_info = []
        for inp in tx.inputs:
            addrs = inp.addresses[0] if inp.addresses else "unknown"
            val = inp.output_value / 1e8 if inp.output_value else 0
            inputs_info.append(f"{addrs}: {val:.8f} DOGE")

        outputs_info = []
        for i, out in enumerate(tx.outputs):
            addrs = out.addresses[0] if out.addresses else "unknown"
            val = out.value / 1e8
            outputs_info.append(f"vout:{i} -> {addrs}: {val:.8f} DOGE")

        return {
            "success": True,
            "chain": "DOGE",
            "txid": tx.hash,
            "block_height": tx.block_height,
            "confirmations": tx.confirmations,
            "total_doge": tx.total / 1e8,
            "fee_doge": tx.fees / 1e8,
            "inputs": inputs_info,
            "outputs": outputs_info,
            "confirmed_time": tx.confirmed,
        }
    except FatalError as e:
        return {"success": False, "error": str(e), "chain": "DOGE", "txid": tx_hash}
    except Exception as e:
        return {"success": False, "error": str(e), "chain": "DOGE", "txid": tx_hash}


@tool
def get_btc_address_info(address: str) -> dict:
    """
    Get Bitcoin address balance and transaction count.

    Args:
        address: The Bitcoin address - must be a valid address string

    Returns:
        Address balance in BTC and transaction statistics
    """
    if not _is_valid_address(address):
        return {
            "success": False,
            "error": f"Invalid address format: '{address}'. Must be a valid Bitcoin address.",
            "chain": "BTC",
            "address": address
        }

    client = BlockCypherClient()
    try:
        data = client.get_address_balance(address, coin="btc")
        return {
            "success": True,
            "chain": "BTC",
            "address": data.get("address"),
            "balance_btc": data.get("final_balance", 0) / 1e8,
            "total_received_btc": data.get("total_received", 0) / 1e8,
            "total_sent_btc": data.get("total_sent", 0) / 1e8,
            "tx_count": data.get("n_tx", 0),
            "unconfirmed_balance_btc": data.get("unconfirmed_balance", 0) / 1e8,
        }
    except FatalError as e:
        return {"success": False, "error": str(e), "chain": "BTC", "address": address}
    except Exception as e:
        return {"success": False, "error": str(e), "chain": "BTC", "address": address}


@tool
def get_doge_address_info(address: str) -> dict:
    """
    Get Dogecoin address balance and transaction count.

    Args:
        address: The Dogecoin address - must be a valid address string

    Returns:
        Address balance in DOGE and transaction statistics
    """
    if not _is_valid_address(address):
        return {
            "success": False,
            "error": f"Invalid address format: '{address}'. Must be a valid Dogecoin address.",
            "chain": "DOGE",
            "address": address
        }

    client = BlockCypherClient()
    try:
        data = client.get_address_balance(address, coin="doge")
        return {
            "success": True,
            "chain": "DOGE",
            "address": data.get("address"),
            "balance_doge": data.get("final_balance", 0) / 1e8,
            "total_received_doge": data.get("total_received", 0) / 1e8,
            "total_sent_doge": data.get("total_sent", 0) / 1e8,
            "tx_count": data.get("n_tx", 0),
            "unconfirmed_balance_doge": data.get("unconfirmed_balance", 0) / 1e8,
        }
    except FatalError as e:
        return {"success": False, "error": str(e), "chain": "DOGE", "address": address}
    except Exception as e:
        return {"success": False, "error": str(e), "chain": "DOGE", "address": address}
