"""Finding models and utilities.

Centralized location for all finding-related types and formatting functions.
"""

from typing import Any, Dict, List, TypedDict
from src.tools.models import UtxoTx, UtxoOutput, AccountTx
from src.tools.converters import utxo_tx_to_transfer, utxo_output_to_transfer, account_tx_to_transfer
from src.models.core import format_transfer


class Finding(TypedDict, total=False):
    """Finding data structure used in TraceTxState."""
    kind: str           # "tx", "address", "price", "search_txs", "address_txs"
    id: str             # txid, address, or price key
    source: str         # tool name that produced this finding
    rationale: str
    data: Dict[str, Any]


def format_finding_data(data) -> str:
    """Format finding data into compact string for LLM context.

    Handles:
    - Transaction data (UtxoTx, UtxoOutput, AccountTx) → converts to Transfer format
    - Price data (price_min/max)
    - List data (search results)
    - Other scalar fields
    """
    if not data:
        return ""

    # Handle list data (e.g., from search tools) - format each item
    if isinstance(data, list):
        if len(data) == 1:
            return format_finding_data(data[0])
        # Multiple items: format all
        formatted = [format_finding_data(item) for item in data]
        return f"[{len(data)} items: " + "; ".join(formatted) + "]"

    # Check if it's UtxoTx (has 'vin' or 'vout' list)
    if "vin" in data or "vout" in data:
        tx = UtxoTx(**data)
        transfer = utxo_tx_to_transfer(tx)
        return format_transfer(transfer)

    # Check if it's UtxoOutput (has 'n' field for output index)
    if "n" in data and "chain" in data and "txid" in data:
        output = UtxoOutput(**data)
        transfer = utxo_output_to_transfer(output)
        return format_transfer(transfer)

    # Check if it's AccountTx (has 'sender' or 'recipient')
    if "sender" in data or "recipient" in data:
        tx = AccountTx(**data)
        transfer = account_tx_to_transfer(tx)
        return format_transfer(transfer)

    parts = []

    # Scalar fields
    for key in ("chain", "txid", "n", "amount", "addr", "block_time", "balance", "address", "tx_count", "fee"):
        if key in data:
            parts.append(f"{key}={data[key]}")

    # Price range - use full decimal to avoid LLM misunderstanding scientific notation
    if "price_min" in data and "price_max" in data:
        parts.append(f"price=[{data['price_min']:.10f}, {data['price_max']:.10f}]")

    # address_txs format: {addr: [txs]}
    for key, val in data.items():
        if isinstance(val, list) and val and isinstance(val[0], dict) and "txid" in val[0]:
            parts.append(f"{key}: {len(val)} txs")

    return " | ".join(parts) if parts else str(data)[:100]


def format_findings(findings: List[Finding], indent: int = 0) -> str:
    """Format a list of findings into a readable string.

    Args:
        findings: List of Finding dicts
        indent: Indentation level (number of 2-space indents)

    Returns:
        Formatted string representation of findings
    """
    _s = []
    for f in findings:
        kind = f["kind"]
        fid = f["id"]
        data = f.get("data", {})
        _s.append(f"{'  ' * indent}- [{kind}] {fid}\n")
        _s.append(f"{'  ' * indent}  {format_finding_data(data)}\n")
    return "".join(_s)
