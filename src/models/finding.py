"""Finding models and utilities.

Centralized location for all finding-related types and formatting functions.
"""

from typing import Any, Dict, List, Optional, TypedDict, Literal
from src.tools.models import PriceRange
from src.tools.converters import dict_to_transfer
from src.models.core import format_transfer


# ========== Finding ID Specs ==========

class GetTxIdFields(TypedDict):
    """Fields required to build a 'get_tx' finding ID.

    txids: List of transaction hashes (single or multiple)
        - Single: ["abc123"] → "get_tx:abc123"
        - Batch: ["abc123", "def456"] → "get_tx:abc123|def456"
    """
    txids: List[str]

class PriceIdFields(TypedDict):
    """Fields required to build a 'price' finding ID."""
    coin: str
    quote: str
    start_ts: int
    end_ts: int

class SearchTxsIdFields(TypedDict):
    """Fields required to build a 'search_txs' finding ID."""
    chain: str
    min_timestamp: int
    max_timestamp: int

FindingKind = Literal["get_tx", "price", "search_txs"]

FINDING_ID_SPECS: Dict[str, type] = {
    "get_tx": GetTxIdFields,
    "price": PriceIdFields,
    "search_txs": SearchTxsIdFields,
}

FINDING_KINDS: List[str] = list(FINDING_ID_SPECS.keys())


# ========== Finding TypedDict ==========

class Finding(TypedDict, total=False):
    """Finding data structure used in TraceTxState."""
    kind: str           # One of FINDING_KINDS
    id: str             # Built using build_finding_id()
    source: str         # tool name that produced this finding
    data: Dict[str, Any]


# ========== Public API - ID Building ==========

def get_finding_kinds_hint() -> str:
    """Get formatted finding kinds for LLM prompts.

    Returns:
        Comma-separated string of all valid finding kinds
    """
    return ", ".join(FINDING_KINDS)


def build_finding_id(kind: FindingKind, **fields) -> str:
    """Build finding ID from fields with runtime validation.

    Args:
        kind: Finding kind (one of FINDING_KINDS)
        **fields: ID fields matching the spec for this kind

    Returns:
        Formatted finding ID string

    Raises:
        ValueError: If kind is unknown or required fields are missing/extra
        TypeError: If field types don't match spec

    Examples:
        >>> build_finding_id("get_tx", txids=["abc123"])
        'get_tx:abc123'

        >>> build_finding_id("get_tx", txids=["abc123", "def456"])
        'get_tx:abc123|def456'

        >>> build_finding_id("price", coin="BTC", quote="DOGE", start_ts=100, end_ts=200)
        'price:BTC_in_DOGE@time(100-200)'

        >>> build_finding_id("search_txs", chain="DOGE", min_timestamp=100, max_timestamp=200)
        'search_txs:DOGE@100-200'
    """
    spec = FINDING_ID_SPECS.get(kind)
    if not spec:
        raise ValueError(f"Unknown finding kind: {kind}. Valid kinds: {FINDING_KINDS}")

    # Runtime validation: check required fields
    required_fields = set(spec.__annotations__.keys())
    provided_fields = set(fields.keys())

    missing = required_fields - provided_fields
    if missing:
        raise ValueError(
            f"Missing required fields for kind '{kind}': {missing}. "
            f"Required: {required_fields}"
        )

    extra = provided_fields - required_fields
    if extra:
        raise ValueError(
            f"Extra fields for kind '{kind}': {extra}. "
            f"Expected only: {required_fields}"
        )

    # Build ID based on kind
    if kind == "get_tx":
        txids = fields['txids']
        if not txids:
            raise ValueError("get_tx requires at least one txid")
        # Join multiple txids with pipe separator
        return f"get_tx:{('|'.join(txids))}"
    elif kind == "price":
        return f"price:{fields['coin']}_in_{fields['quote']}@time({fields['start_ts']}-{fields['end_ts']})"
    elif kind == "search_txs":
        return f"search_txs:{fields['chain']}@{fields['min_timestamp']}-{fields['max_timestamp']}"
    else:
        # Should never reach here due to FindingKind type constraint
        raise ValueError(f"Unhandled finding kind: {kind}")

def find_all_by_prefix(findings: List[Finding], prefix: str, ignore_case_sensitive:bool=True) -> List[Finding]:
    """Find all findings by prefix.

    Args:
        findings: List of findings to search
        prefix: Prefix to look for

    Returns:
        List of findings that match the prefix
    """
    results = []
    prefix = prefix.lower() if ignore_case_sensitive else prefix
    for finding in findings:
        fid = finding.get("id", "")
        if ignore_case_sensitive:
            fid = fid.lower()
        if fid and fid.startswith(prefix):
            results.append(finding)
    return results

def find_by_id(findings: List[Finding], id: str, ignore_case_sensitive:bool=True) -> Optional[Finding]:
    """Find a finding by ID.

    Args:
        findings: List of findings to search
        id: Finding ID to look for

    Returns:
        The matching finding

    Raises:
        ValueError: If finding not found
    """

    # Search in findings
    target_id = id.lower() if ignore_case_sensitive else id
    for finding in findings:
        fid = finding.get("id", "")
        if ignore_case_sensitive:
            fid = fid.lower()
        if fid and fid == target_id:
            return finding
    return None


def find_matching_price(findings: List[Finding], coin: str, quote: str, start_ts: int, end_ts: int) -> Optional[PriceRange]:
    """Find matching price range for a given coin and quote and time window.
    
    Searches for a price finding matching the given coin/quote pair and time window.
    If not found, attempts to find the inverted pair (quote/coin) and inverts the price.
    
    Args:
        findings: List of findings to search
        coin: Base coin symbol
        quote: Quote coin symbol
        start_ts: Start timestamp
        end_ts: End timestamp
    
    Returns:
        PriceRange if found, None otherwise
    """
    # Try direct pair first
    price_id = build_finding_id("price", coin=coin, quote=quote, start_ts=start_ts, end_ts=end_ts)
    price_finding = find_by_id(findings, price_id)

    if price_finding:
        return PriceRange(**price_finding.get("data"))

    # Try inverted pair
    invert_price_id = build_finding_id("price", coin=quote, quote=coin, start_ts=start_ts, end_ts=end_ts)
    price_finding = find_by_id(findings, invert_price_id)
    
    if not price_finding:
        return None
    
    # Invert the price range
    data = price_finding.get("data")
    return PriceRange(
        price_min=1.0 / data["price_max"],
        price_max=1.0 / data["price_min"],
        via=data.get("via")
    )

def format_finding_data(data) -> str:
    """Format finding data into compact string for LLM context.

    Handles:
    - Transaction data (UtxoTx, UtxoOutput, EthTransfer) → converts to Transfer format
    - Price data (price_min/max)
    - List data (search results)
    - Other scalar fields
    """
    if not data:
        return ""

    # Handle list data (e.g., from search tools)
    if isinstance(data, list):
        if len(data) == 1:
            return format_finding_data(data[0])

        # Multiple items: extract unique block_times for orchestrator
        # Orchestrator only needs count + unique block_times to calculate price windows
        block_times = []
        for item in data:
            if isinstance(item, dict) and "block_time" in item:
                block_times.append(item["block_time"])

        if block_times:
            unique_times = sorted(set(block_times))
            return f"{len(data)} candidates with unique block_times: {unique_times}"

        # Fallback: old format (commented out but kept for reference)
        # formatted = [format_finding_data(item) for item in data]
        # return f"[{len(data)} items: " + "; ".join(formatted) + "]"

        # If no block_times found, just show count
        return f"{len(data)} items"

    try:
        transfer = dict_to_transfer(data)
        return format_transfer(transfer)
    except ValueError:
        pass # continue if not tx

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
