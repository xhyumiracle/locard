"""
Converters from tool models to domain models (Transfer).

Used by trace workflow to convert blockchain data into Transfer format.
"""

import time
from typing import Dict

from config import get_asset_decimals
from src.tools.models import UtxoTx, UtxoOutput, AccountTx
from src.models.core import (
    Transfer, Operation, AccountIdentifier, TxStatus
)

def utxo_tx_to_transfer(tx: UtxoTx, source: str = "unknown") -> Transfer:
    """Convert UtxoTx to Transfer model.

    Args:
        tx: UTXO transaction data
        source: Data source name (e.g., "mempool.space", "electrs-doge")
    """

    operations: Dict[str, Operation] = {}
    asset = tx.chain  # BTC, DOGE, LTC, etc.
    decimals = get_asset_decimals(tx.chain)

    # Process inputs (spent coins)
    for vin in tx.vin:
        if vin.prev_txid is not None and vin.prev_vout is not None:
            spent_coin_id = f"{vin.prev_txid}:{vin.prev_vout}"
        else:
            spent_coin_id = None

        op_id = f"vin:{vin.n}"
        op = Operation(
            op_id=op_id,
            account=AccountIdentifier(address=vin.addr),
            amount=vin.amount,
            asset=asset,
            decimals=decimals,
            spent_coin_id=spent_coin_id
        )
        operations[op_id] = op

    # Process outputs (created coins)
    for vout in tx.vout:
        op_id = f"vout:{vout.n}"
        op = Operation(
            op_id=op_id,
            account=AccountIdentifier(address=vout.addr),
            amount=vout.amount,
            asset=asset,
            decimals=decimals,
            spent_coin_id=None
        )
        operations[op_id] = op

    return Transfer(
        txid=tx.txid,
        chain=tx.chain,
        block_time=tx.block_time,
        status=tx.status,
        block_height=tx.block_height,
        block_hash=tx.meta.get("block_hash"),
        operations=operations,
        type="utxo"
    )

def utxo_output_to_transfer(output: UtxoOutput, source: str = "unknown") -> Transfer:
    """Convert UtxoOutput to lightweight Transfer model.

    Creates a Transfer with only the single vout operation.
    Used for output search results where we don't have full tx data.

    Transfer.txid is the transaction hash only (no :vout:n suffix).
    Different outputs are distinguished by Operation.op_id (vout:0, vout:1, etc).
    CrossChainLink.id combines both txid and op_id to avoid collisions.

    Args:
        output: Standalone UTXO output
        source: Data source name (e.g., "blockchair")
    """
    asset = output.chain
    decimals = get_asset_decimals(output.chain)

    # Single vout operation
    op_id = f"vout:{output.n}"
    op = Operation(
        op_id=op_id,
        account=AccountIdentifier(address=output.addr),
        amount=output.amount,
        asset=asset,
        decimals=decimals,
        spent_coin_id=None
    )

    return Transfer(
        txid=output.txid,  # Only the transaction hash, no :vout:n suffix
        chain=output.chain,
        block_time=output.block_time,
        status="confirmed",
        block_height=None,
        block_hash=None,
        operations={op_id: op},
        type="utxo"
    )

def account_tx_to_transfer(tx: AccountTx, source: str = "unknown") -> Transfer:
    """Convert AccountTx to Transfer model.

    Args:
        tx: Account transaction data
        source: Data source name (e.g., "blockchair", "etherscan")
    """
    operations: Dict[str, Operation] = {}
    asset = tx.chain  # ETH, etc.
    decimals = get_asset_decimals(tx.chain)

    # Account-based: sender (vin:0) and recipient (vout:0) operations
    # Unified vin/vout convention: vin = outgoing, vout = incoming (amounts always positive)
    if tx.sender:
        op_out = Operation(
            op_id="vin:0",
            account=AccountIdentifier(address=tx.sender),
            amount=tx.amount,
            asset=asset,
            decimals=decimals,
            spent_coin_id=None
        )
        operations["vin:0"] = op_out

    if tx.recipient:
        op_in = Operation(
            op_id="vout:0",
            account=AccountIdentifier(address=tx.recipient),
            amount=tx.amount,
            asset=asset,
            decimals=decimals,
            spent_coin_id=None
        )
        operations["vout:0"] = op_in

    return Transfer(
        txid=tx.txid,
        chain=tx.chain,
        type="account",
        block_time=tx.block_time,
        status=tx.status,
        block_height=tx.block_height,
        block_hash=None,
        operations=operations
    )

def dict_to_transfer(data: dict) -> Transfer:
    """Convert dict to Transfer model."""

    # Check if it's UtxoTx (has 'vin' or 'vout' list)
    if "vin" in data or "vout" in data:
        tx = UtxoTx(**data)
        return utxo_tx_to_transfer(tx)

    # Check if it's UtxoOutput (has 'n' field for output index)
    if "n" in data:
        output = UtxoOutput(**data)
        return utxo_output_to_transfer(output)

    # Check if it's AccountTx (has 'sender' or 'recipient')
    if "sender" in data or "recipient" in data:
        tx = AccountTx(**data)
        return account_tx_to_transfer(tx)

    raise ValueError(f"Invalid data type: {type(data)}")