"""
Core data models for blockchain transaction data.

Only for on-chain transaction data that needs Transfer conversion.

Design principles:
- Pure blockchain data structures, no API-layer concerns
- Field names follow common chain conventions (vin, vout, txid, etc.)
- Minimal fields, low-frequency data goes to meta
- Human-readable units (BTC not satoshi, ETH not wei)
"""

from typing import Optional, List, Dict, Any, Literal, Union
from pydantic import BaseModel


# On-chain transaction status:
# - "confirmed": included in block and executed successfully
# - "pending": in mempool, not yet mined
# - "failed": included in block but execution failed (e.g., ETH reverted)
TxStatus = Literal["confirmed", "pending", "failed"]

# ==================== UTXO Transaction ====================

class Vin(BaseModel):
    """UTXO input."""
    n: int  # vin index
    amount: Optional[float] = None  # Human units, None for coinbase
    addr: Optional[str] = None # sender
    prev_txid: Optional[str] = None
    prev_vout: Optional[int] = None


class Vout(BaseModel):
    """UTXO output (within a transaction context)."""
    n: int  # vout index
    amount: float
    addr: Optional[str] = None # recipient


class UtxoTx(BaseModel):
    """UTXO chain transaction (BTC, DOGE, LTC, BCH)."""
    chain: str
    txid: str
    status: TxStatus
    block_height: Optional[int] = None  # block height
    block_time: Optional[int] = None  # block time (unix)
    fee: float = 0
    vin: List[Vin] = []
    vout: List[Vout] = []
    meta: Dict[str, Any] = {}  # size, weight, block_hash, etc.



class UtxoOutput(BaseModel):
    """Standalone UTXO output (self-contained, from output search).

    Unlike Vout which exists within UtxoTx context, Output is independent
    and contains all info needed for cross-chain candidate matching.
    """
    chain: str
    txid: str
    n: int  # vout index
    amount: float
    addr: Optional[str] = None # recipient
    block_time: Optional[int] = None

# ==================== Account Transaction ====================

class AccountTx(BaseModel):
    """Account chain transaction (ETH, etc.)."""
    chain: str
    txid: str
    status: TxStatus
    block_height: Optional[int] = None
    block_time: Optional[int] = None
    sender: Optional[str] = None
    recipient: Optional[str] = None
    amount: float = 0
    fee: float = 0
    meta: Dict[str, Any] = {}  # gas_used, gas_price, etc.


class EthCall(BaseModel):
    """Standalone ETH internal call/transaction (from calls search).

    Similar to UtxoOutput, this is independent and contains all info
    needed for cross-chain matching of ETH internal transfers.
    """
    chain: str  # Always "ETH"
    txid: str   # Parent transaction hash
    index: str  # Call index like "0", "0.0", "0.0.0"
    depth: int  # Call depth (0 = top level)
    call_type: str  # "call", "delegatecall", "staticcall", etc
    sender: Optional[str] = None
    recipient: Optional[str] = None
    amount: float = 0  # In ETH (not wei)
    transferred: bool = True  # Whether ETH was actually transferred
    block_time: Optional[int] = None

class PriceRange(BaseModel):
    price_min: float
    price_max: float
    via: Optional[str]


ToolTx = Union[UtxoTx, AccountTx, UtxoOutput, EthCall]
