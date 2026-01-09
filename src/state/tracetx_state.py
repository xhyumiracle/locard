from typing import Any, Dict, List, Optional, TypedDict
from typing_extensions import Annotated
from src.models.core import DstInfo, SrcInfo, Transfer, CrossChainLink
from src.models.finding import Finding
import operator
import config


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

class Trajectory(TypedDict):
    action: str
    task_brief: Optional[str]
    findings_ref: List[str] # finding id

class TraceTxState(TypedDict, total=False):
    query: str

    # execution control
    iteration: int                  # current iteration count
    action: Optional[str]           

    trajectories: Annotated[List[Trajectory], operator.add]
    pending_trajectory: Trajectory  # running trajectory w/o findings_ref, contains task_brief

    src_info: SrcInfo
    dst_info: DstInfo

    findings: Annotated[List[Finding], operator.add]

    # inbox from fetcher
    inbox_findings: List[Finding]   # clear when update (may merge multi fetcher on parallel)
    inbox_gaps: List[str]

    # finding IDs that contains all candidates (set by orchestrator)
    candidates_finding_ids: List[str]

    params: Dict[str, Any]
    # search_time_span: int (seconds)
    # search_price_buffer: float (0.1 = 10%)
    # check_time_span: int (seconds)
    # TODO: check_buffer_perc etc.

    reflection: Dict[str, Any]
    # Self-reflection tracking for orchestrator (behavior only, not results)
    # reflection["step_1"] = {"task_issued": bool}
    # reflection["step_2"] = {"dst_tx_received": bool, "tool_called": bool, "task_issued": bool}
    # reflection["step_3"] = {"price_received": bool, "tool_called": bool, "reused_step2_window": bool, "task_issued": bool}
    # reflection["step_4"] = {"search_received": bool, "tool_called": bool, "task_issued": bool}
    # reflection["step_5"] = {"price_received": bool}
    # reflection["notes"] = [str] - free text for issues/corrections

    # final results
    # transfers: Annotated[Dict[str, Dict[str, Transfer]], merge_nested_dict]  # [chain][transfer_id] -> Transfer
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
        # IDs now include kind: prefix, so we can safely truncate hash-like IDs
        if kind in TRUNCATABLE_KINDS and ":" in s:
            # For tx IDs like "tx:abc123...", keep "tx:" and truncate hash part
            prefix, hash_part = s.split(":", 1)
            if len(hash_part) > 8:
                return f"{prefix}:{hash_part[:8].lower()}"
        # Non-truncatable IDs (price, search_txs) are kept intact
        return s.lower()

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
        "params": {
            "search_time_span": config.TRACETX_SEARCH_TIME_SPAN,
            "search_price_buffer": config.TRACETX_SEARCH_PRICE_BUFFER,
            "check_time_span": config.TRACETX_CHECK_TIME_SPAN,
        },
        "reflection": {
            "step_1": {"task_issued": False},
            "step_2": {"dst_tx_received": False, "tool_called": False, "task_issued": False},
            "step_3": {"price_received": False, "tool_called": False, "reused_step2_window": False, "task_issued": False},
            "step_4": {"search_received": False, "tool_called": False, "task_issued": False},
            "step_5": {"price_received": False},
            "notes": []
        },
    }

def get_all_findings(state: TraceTxState) -> List[Finding]:
    return state.get("findings", []) + state.get("inbox_findings", [])