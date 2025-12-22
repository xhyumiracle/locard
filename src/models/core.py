"""
Core data structures for BlockchainMAS.

Based on Rosetta protocol abstractions for cross-chain transaction representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


TxStatus = Literal["confirmed", "mempool", "dropped"]


@dataclass(frozen=True)
class TxLocator:
    """Canonical on-chain locator (facts)."""
    chain: str                 # e.g. "BTC", "DOGE", "ETH"
    txid: str                  # tx hash / id (string)
    status: TxStatus = "confirmed"
    block_height: Optional[int] = None
    block_hash: Optional[str] = None
    block_time: Optional[int] = None  # unix seconds


@dataclass(frozen=True)
class EvidenceRef:
    """How/where you retrieved the raw data for a locator (audit/replay)."""
    source: str                       # e.g. "blockcypher", "blockchair", "electrs"
    locator: Optional[TxLocator] = None
    retrieved_at: int = 0             # unix seconds
    raw_pointer: str = ""             # file path / object key / db id
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountIdentifier:
    """
    Rosetta-style account identifier.
    For UTXO outputs, address may be the decoded address if available;
    otherwise keep address=None and put script-hash/type in metadata.
    """
    address: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Currency:
    """Rosetta-style currency. For tokens, use contract address as 'symbol' or put in metadata."""
    symbol: str                       # e.g. "BTC", "ETH", "USDC"
    decimals: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Amount:
    """Signed string value in smallest units (e.g., satoshi, wei, token base units)."""
    value: str                        # e.g. "-500000000" or "+25000000"
    currency: Currency


CoinAction = Literal["coin_created", "coin_spent"]


@dataclass(frozen=True)
class CoinChange:
    """UTXO-only: identifies discrete coin lifecycle changes."""
    coin_id: str              # "txid:vout" (created) or "prev_txid:prev_vout" (spent)
    action: CoinAction


@dataclass(frozen=True)
class Operation:
    """
    Rosetta-style operation: one account/coin state change.
    - Account-based chains: use account + signed amount (coin_change usually None)
    - UTXO chains: coin_change anchors coin continuity
    """
    op_id: str         # stable within tx; e.g. "vin:0", "vout:2", "log:7"
    account: AccountIdentifier
    amount: Optional[Amount] = None
    coin_change: Optional[CoinChange] = None
    related_operations: List[str] = field(default_factory=list)


@dataclass
class Transfer:
    """
    Transaction-level transfer group.
    Essentially Rosetta Transaction semantics: a group of operations for one on-chain tx.
    """
    id: str                                        # usually == txid
    locator: TxLocator
    operations: List[Operation]
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    fee: Optional[Amount] = None


@dataclass(frozen=True)
class OpRef:
    """Reference to a specific operation within a transfer."""
    chain: str
    transfer_id: str
    op_id: str


@dataclass
class CrossChainLink:
    """Inference edge between two chains' operations."""
    id: str
    src: OpRef
    dst: OpRef
    confidence: float = 0.0                        # 0..1
    evidence_refs: List[EvidenceRef] = field(default_factory=list)

    @staticmethod
    def make_id(src: OpRef, dst: OpRef) -> str:
        """Generate canonical link ID."""
        return f"{src.chain}:{src.transfer_id}:{src.op_id}->{dst.chain}:{dst.transfer_id}:{dst.op_id}"
