"""
Core data structures for BlockchainMAS.

Based on Rosetta protocol abstractions for cross-chain transaction representation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)


TxStatus = Literal["confirmed", "pending", "failed"]
TransferType = Literal["utxo", "account"]

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
class Operation:
    """
    Operation: one account/coin state change.

    Unified vin/vout convention across all chain types:
    - vin:N = outgoing/spent
    - vout:N = incoming/created

    For UTXO chains: spent_coin_id tracks coin continuity (which previous output is spent).
    For Account chains: spent_coin_id is None.

    Amount is always in human-readable units (e.g., 1.5 BTC, not satoshis) and always positive.
    The `decimals` field defines the precision for the asset.

    op_id naming convention:
    - UTXO/Account native: "vin:N" (outgoing), "vout:N" (incoming)
    - Account ERC20 (future): "e:N:vin", "e:N:vout" where N = log index
    """
    op_id: str                          # semantic id; e.g. "vin:0", "vout:2"
    account: AccountIdentifier = None
    amount: Optional[float] = None      # unsigned amount in human-readable units (always positive)
    asset: Optional[str] = None         # e.g. "BTC", "ETH", "USDC"
    decimals: Optional[int] = None      # precision for this asset (e.g., 8 for BTC, 18 for ETH)
    spent_coin_id: Optional[str] = None  # only for UTXO vin, format "prev_txid:prev_vout"

@dataclass
class Transfer:
    """
    Transaction-level transfer group.
    """
    txid: str                  # tx hash / id (string)
    chain: str                 # e.g. "BTC", "DOGE", "ETH"
    type: TransferType                             # "utxo" for BTC/DOGE/LTC, "account" for ETH/etc.
    block_time: Optional[int] = None  # unix seconds
    status: TxStatus = "confirmed"
    block_height: Optional[int] = None  # unimportant
    block_hash: Optional[str] = None  # unimportant
    operations: Dict[str, Operation] = field(default_factory=dict)  # key = op_id
    # evidence_refs: List[EvidenceRef] = field(default_factory=list)


def format_transfer(transfer: Transfer) -> str:
    """Format Transfer into compact string for LLM context.

    Args:
        transfer: Transfer object to format

    Returns:
        Formatted string showing chain, txid, block_time, and operations
    """
    parts = []

    # Basic info
    parts.append(f"chain={transfer.chain}")
    parts.append(f"txid={transfer.txid}")
    if transfer.block_time:
        parts.append(f"block_time={transfer.block_time}")

    # Operations - separate vin and vout
    vins = []
    vouts = []
    for op_id, op in transfer.operations.items():
        addr = op.account.address if op.account and op.account.address else "?"
        amount = op.amount if op.amount is not None else 0

        if op_id.startswith("vin:"):
            idx = op_id.split(":")[1]
            vins.append(f"vin-{idx}:{addr}:{amount}")
        elif op_id.startswith("vout:"):
            idx = op_id.split(":")[1]
            vouts.append(f"vout-{idx}:{addr}:{amount}")

    if vins:
        parts.append(f"[{', '.join(vins)}]")
    if vouts:
        parts.append(f"[{', '.join(vouts)}]")

    return " | ".join(parts)


@dataclass
class CrossChainLink:
    """
    Inference edge between two chains' operations, with scoring data.

    Links a source operation (e.g., DOGE vout) to a destination operation (e.g., BTC vout).
    Includes all data needed for scoring and reporting. Self-contained with Transfer references.

    Uses op_id to directly access operations via transfer.operations[op_id] dict lookup.

    Price Direction Convention (SOURCE_in_DEST for scoring):
    - price_min/price_max represent: 1 src_coin = X dst_coin
    - Example: BTC->DOGE trace (user spent BTC to get DOGE), price is how many DOGE per 1 BTC
    - These are raw prices from Binance at src tx time (±10min window), NO buffer applied
    - Buffers are applied during scoring using config.PRICE_MAX_FEE_RATE and PRICE_MAX_DEVIATION_RATE
    - Note: Orchestrator uses DEST_in_SOURCE for raw search (Step 2), but Step 5 fetches SOURCE_in_DEST for scoring
    """
    id: str

    # Source operation reference
    src_transfer: Transfer
    src_op_id: str

    # Destination operation reference
    dst_transfer: Transfer
    dst_op_id: str

    # Price data: 1 src_coin = [price_min, price_max] dst_coin at src tx time (raw, no buffer)
    price_min: Optional[float] = None
    price_max: Optional[float] = None

    # Computed fields (filled during scoring)
    time_diff: Optional[int] = None              # dst_time - src_time (seconds)
    fee_rate_min: Optional[float] = None         # min possible fee rate
    fee_rate_max: Optional[float] = None         # max possible fee rate

    # Exclusion logic
    excluded: bool = False
    exclude_reason: Optional[str] = None

    # Feature scores
    f_time: float = 0.0                          # exp(-time_diff / tau_time)
    f_amount: float = 0.0                         # based on fee_rate range width

    # Final score (0..1)
    confidence: float = 0.0

    # Audit trail
    # evidence_refs: List[EvidenceRef] = field(default_factory=list)

    # Convenience properties
    @property
    def src_chain(self) -> str:
        return self.src_transfer.chain

    @property
    def dst_chain(self) -> str:
        return self.dst_transfer.chain

    @staticmethod
    def make_id(
        src_transfer: Transfer, src_op_id: str,
        dst_transfer: Transfer, dst_op_id: str
    ) -> str:
        """Generate canonical link ID using op_id."""
        return f"{src_transfer.chain}:{src_transfer.txid}:{src_op_id}->{dst_transfer.chain}:{dst_transfer.txid}:{dst_op_id}"


def get_transfer(transfers: Dict[str, Dict[str, Transfer]], chain: str, txid: str, op_id: str):
    rst = transfers[chain].get(f"{txid}:{op_id}")
    if rst:
        return rst
    rst = transfers[chain].get(f"{txid}")
    return rst