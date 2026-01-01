from typing import Any, Dict, List, Optional, Annotated, TypedDict
from typing_extensions import Annotated
from pydantic import BaseModel, Field
from src.models.core import Transfer, CrossChainLink
from src.models.finding import Finding
import operator


class SrcInfo(BaseModel):
    """Source tx base info ."""
    chain: str = Field()
    asset: str = Field(description="same as chain if native asset")

class DestInfo(BaseModel):
    """Destination tx base info."""
    txid: str = Field(description="tx hash")
    chain: str = Field()
    asset: str = Field(description="same as chain if native asset")
    op_id: str = Field(description="Operation ID in format 'vout:N' for both UTXO and Account chains (unified naming)")
    amount: float = Field(description="Amount in human-readable units for the target operation")
    time: int = Field(description="Timestamp in seconds")


def merge_nested_dict(a: Dict[str, Dict], b: Dict[str, Dict]) -> Dict[str, Dict]:
    """Merge two nested dicts (e.g., {chain: {txid: Transfer}}).

    For each key in b, merge with a's value if exists, otherwise add.
    """
    result = dict(a)
    for key, inner_dict in b.items():
        if key in result:
            result[key] = {**result[key], **inner_dict}
        else:
            result[key] = inner_dict
    return result


class TraceTxState(TypedDict, total=False):
    query: str

    # execution control
    iteration: int                  # current iteration count
    action: Optional[str]           # "fetch" or "score"

    task_brief: Optional[str]       # task for fetcher

    src_info: SrcInfo
    dest_info: DestInfo

    dest_transfer: Transfer
    findings: Annotated[List[Finding], operator.add]

    # inbox from fetcher
    inbox_findings: List[Finding]   # clear when update (may merge multi fetcher on parallel)
    inbox_gaps: List[str]

    params: Dict[str, Any]
    # search_time_span: int (seconds)
    # search_price_buffer: float (0.1 = 10%)
    # check_time_span: int (seconds)
    # TODO: check_buffer_perc etc.

    derived: Dict[str, Any]
    # derived["search_window"]["time"] = {"start_ts": int, "end_ts": int}
    # derived["search_window"]["amount"] = {"min": float, "max": float}

    # final results
    transfers: Annotated[Dict[str, Dict[str, Transfer]], merge_nested_dict]  # [chain][transfer_id] -> Transfer
    cclinks: List[CrossChainLink]              # cross-chain links

    result: dict # {success: bool, data: dict, reason: str}, reason for failed cases


# TODO
def state_ids_hint(state: TraceTxState) -> str:
    """Build compact hint of existing IDs from state.

    Only truncates known hash-like IDs (tx, address) to 8 chars.
    Other IDs (price, search_txs) are kept intact.
    """
    # Kinds with long hash-like IDs that are safe to truncate
    TRUNCATABLE_KINDS = {"tx", "address", "address_txs"}

    def _shorten(s: str, kind: str = "") -> str:
        if kind in TRUNCATABLE_KINDS and len(s) > 20:
            return s[:8].lower()
        return kind + ":" + s.lower()

    ids = []

    for f in state.get("findings", []):
        fid = f["id"]
        kind = f["kind"]
        ids.append(_shorten(fid, kind))

    # Transfer IDs are always tx hashes, safe to truncate
    for chain_transfers in state.get("transfers", {}).values():
        for tid in chain_transfers.keys():
            if tid:
                ids.append(_shorten(tid, "tx"))

    unique_ids = list(dict.fromkeys(ids))
    return ", ".join(unique_ids)

def initialize_state(query: str) -> TraceTxState:
    return {
        "query": query,
        "iteration": 0,
        "params": {"search_time_span": 1800, "search_price_buffer": 0.1, "check_time_span": 600},
    }