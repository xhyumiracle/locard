"""
Common filter utilities for blockchain transaction data.

These filters operate on standardized tx dicts (UtxoTx/EthTransfer model_dump format).
Used by various API tool implementations for consistent filtering logic.
"""

from typing import List


def filter_tx_by_time(
    tx: dict,
    min_timestamp: int = 0,
    max_timestamp: int = 0
) -> bool:
    """
    Check if transaction is within time range.

    Args:
        tx: Transaction dict with 'block_time' field
        min_timestamp: Minimum block time (Unix), 0 = no lower bound
        max_timestamp: Maximum block time (Unix), 0 = no upper bound

    Returns:
        True if tx is within range (or range not specified)
    """
    block_time = tx.get("block_time")
    if block_time is None:
        return True  # Pending tx - include by default
    if min_timestamp > 0 and block_time < min_timestamp:
        return False
    if max_timestamp > 0 and block_time > max_timestamp:
        return False
    return True


def filter_tx_by_amount(
    tx: dict,
    direction: str,
    min_amount: float = 0,
    max_amount: float = 0,
    is_utxo: bool = True
) -> bool:
    """
    Check if transaction has vin/vout (or amount for account) within amount range.

    For UTXO chains: checks individual vin or vout amounts based on direction.
    For Account chains: checks the transaction amount field.

    Args:
        tx: Transaction dict (UtxoTx or EthTransfer format)
        direction: "in" (vout/recipient), "out" (vin/sender), "both"
        min_amount: Minimum amount, 0 = no lower bound
        max_amount: Maximum amount, 0 = no upper bound (equal to min = exact match)
        is_utxo: True for UTXO chains, False for account chains

    Returns:
        True if tx has at least one matching vin/vout or amount
    """
    if min_amount <= 0 and max_amount <= 0:
        return True  # No amount filter

    def amount_matches(amount: float) -> bool:
        if amount is None:
            return False
        if min_amount > 0 and amount < min_amount:
            return False
        if max_amount > 0 and amount > max_amount:
            return False
        return True

    if is_utxo:
        # UTXO chain - check vin/vout
        if direction in ("out", "both"):
            for vin in tx.get("vin", []):
                if amount_matches(vin.get("amount")):
                    return True
        if direction in ("in", "both"):
            for vout in tx.get("vout", []):
                if amount_matches(vout.get("amount")):
                    return True
        return False
    else:
        # Account chain - check amount field
        return amount_matches(tx.get("amount"))


def filter_tx_by_address_direction(
    tx: dict,
    address: str,
    direction: str,
    is_utxo: bool = True
) -> bool:
    """
    Check if transaction involves address in the specified direction.

    Args:
        tx: Transaction dict
        address: Address to check (case-insensitive)
        direction: "in" (address receives), "out" (address sends), "both"
        is_utxo: True for UTXO chains, False for account chains

    Returns:
        True if address is involved in specified direction
    """
    addr_lower = address.lower()

    if is_utxo:
        if direction in ("out", "both"):
            for vin in tx.get("vin", []):
                if vin.get("addr") and vin["addr"].lower() == addr_lower:
                    return True
        if direction in ("in", "both"):
            for vout in tx.get("vout", []):
                if vout.get("addr") and vout["addr"].lower() == addr_lower:
                    return True
        return False
    else:
        # Account chain
        if direction in ("out", "both"):
            if tx.get("sender") and tx["sender"].lower() == addr_lower:
                return True
        if direction in ("in", "both"):
            if tx.get("recipient") and tx["recipient"].lower() == addr_lower:
                return True
        return False


def filter_txs(
    txs: List[dict],
    min_timestamp: int = 0,
    max_timestamp: int = 0,
    direction: str = "both",
    min_amount: float = 0,
    max_amount: float = 0,
    is_utxo: bool = True,
    limit: int = 0
) -> List[dict]:
    """
    Apply all filters to a list of transactions.

    Args:
        txs: List of transaction dicts
        min_timestamp: Minimum block time (Unix), 0 = no filter
        max_timestamp: Maximum block time (Unix), 0 = no filter
        direction: "in", "out", or "both" for amount filtering
        min_amount: Minimum vin/vout amount, 0 = no filter
        max_amount: Maximum vin/vout amount, 0 = no filter
        is_utxo: True for UTXO chains, False for account chains
        limit: Maximum results to return, 0 = no limit

    Returns:
        Filtered list of transactions
    """
    result = []
    for tx in txs:
        if not filter_tx_by_time(tx, min_timestamp, max_timestamp):
            continue
        if not filter_tx_by_amount(tx, direction, min_amount, max_amount, is_utxo):
            continue
        result.append(tx)
        if limit > 0 and len(result) >= limit:
            break
    return result
