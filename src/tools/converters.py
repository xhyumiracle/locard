"""
Converters from tool models to domain models (Transfer).

Used by trace workflow to convert blockchain data into Transfer format.
"""

import time
from typing import Dict

from config import get_asset_decimals
from src.tools.models import UtxoTx, UtxoOutput, EthTransfer, EthCall, Eth3xplTransfer
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

def account_tx_to_transfer(tx: EthTransfer, source: str = "unknown") -> Transfer:
    """Convert EthTransfer to Transfer model.

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

def eth_call_to_transfer(call: EthCall, source: str = "unknown") -> Transfer:
    """Convert EthCall to lightweight Transfer model.

    Creates a Transfer with single or dual operations representing the internal call.
    Similar to utxo_output_to_transfer - represents a single internal transfer.

    For cross-chain matching, we typically only need the recipient operation (incoming),
    but we include both sender and recipient when available for completeness.

    Args:
        call: ETH internal call/transfer
        source: Data source name (e.g., "blockchair")
    """
    asset = call.chain  # Always "ETH"
    decimals = get_asset_decimals(call.chain)

    # Use call index as the operation identifier
    # For internal calls, we use vout (recipient) as the primary operation
    # since we're matching incoming transfers in cross-chain scenarios
    operations: Dict[str, Operation] = {}

    if call.recipient:
        # Incoming operation - this is what we match against dst in cross-chain
        op_id = f"vout:{call.index}"
        op_in = Operation(
            op_id=op_id,
            account=AccountIdentifier(address=call.recipient),
            amount=call.amount,
            asset=asset,
            decimals=decimals,
            spent_coin_id=None
        )
        operations[op_id] = op_in

    if call.sender:
        # Outgoing operation - included for completeness
        op_id = f"vin:{call.index}"
        op_out = Operation(
            op_id=op_id,
            account=AccountIdentifier(address=call.sender),
            amount=call.amount,
            asset=asset,
            decimals=decimals,
            spent_coin_id=None
        )
        operations[op_id] = op_out

    return Transfer(
        txid=call.txid,
        chain=call.chain,
        block_time=call.block_time,
        status="confirmed",
        block_height=None,
        block_hash=None,
        operations=operations,
        type="account"  # Internal calls are part of account model
    )

def eth_3xpl_transfer_to_transfer(transfer: Eth3xplTransfer, source: str = "unknown") -> Transfer:
    """Convert Eth3xplTransfer to lightweight Transfer model.

    Creates a Transfer with only the recipient operation (vout:0).
    Similar to utxo_output_to_transfer - represents a single incoming transfer.

    Args:
        transfer: ETH transfer event from 3xpl ClickHouse
        source: Data source name (default: "3xpl-clickhouse")
    """
    asset = transfer.chain  # Always "ETH"
    decimals = get_asset_decimals(transfer.chain)

    # Single vout operation (recipient-side)
    op_id = "vout:0"
    op = Operation(
        op_id=op_id,
        account=AccountIdentifier(address=transfer.recipient),
        amount=transfer.amount,
        asset=asset,
        decimals=decimals,
        spent_coin_id=None
    )

    return Transfer(
        txid=transfer.txid,
        chain=transfer.chain,
        block_time=transfer.block_time,
        status="confirmed",
        block_height=transfer.block,
        block_hash=None,
        operations={op_id: op},
        type="account"  # ETH transfers are part of account model
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

    # Check if it's EthCall (has 'depth' and 'index' fields - unique to internal calls)
    if "depth" in data and "index" in data:
        call = EthCall(**data)
        return eth_call_to_transfer(call)

    # Check if it's Eth3xplTransfer (has 'module' field - unique to 3xpl)
    if "module" in data:
        transfer = Eth3xplTransfer(**data)
        return eth_3xpl_transfer_to_transfer(transfer)

    # Check if it's EthTransfer (has 'sender' or 'recipient')
    if "sender" in data or "recipient" in data:
        tx = EthTransfer(**data)
        return account_tx_to_transfer(tx)

    raise ValueError(f"Invalid data type: {type(data)}")