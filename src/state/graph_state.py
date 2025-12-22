"""
GraphState schema for BlockchainMAS LangGraph workflow.
"""

from typing import Any, Dict, List, Literal, Optional, Annotated
from typing_extensions import TypedDict
import operator
import uuid
from datetime import datetime

from langchain_core.messages import BaseMessage, HumanMessage

from src.models.core import Transfer, CrossChainLink


class PlanStep(TypedDict):
    id: str            # stable step id, e.g. "fetch_btc_tx"
    owner: str         # agent name, e.g. "fetcher"
    desc: str          # short instruction


class Plan(TypedDict):
    iter: int          # replan counter
    cursor: int        # current step index
    steps: List[PlanStep]


class ErrorEvent(TypedDict, total=False):
    t: str             # ISO timestamp
    where: str         # node / agent / tool name
    msg: str           # 1-line summary
    retry: int         # optional
    data: Any          # optional small payload


Subgraph = Literal["chat", "trace", "fallback"]


class BlockchainState(TypedDict, total=False):
    transfers: Dict[str, Dict[str, Transfer]]  # [chain][transfer_id] -> Transfer
    cclinks: List[CrossChainLink]              # cross-chain links


class Finding(TypedDict, total=False):
    kind: str           # "tx", "address", "price"
    id: str             # txid, address, or price key
    rationale: str
    data: Dict[str, Any]


class SubgraphExecState(TypedDict, total=False):
    plan: Plan
    errors: List[ErrorEvent]
    findings: List[Finding]  # accumulated findings across iterations


def merge_messages(left: List[BaseMessage], right: List[BaseMessage]) -> List[BaseMessage]:
    """Merge message lists (append new messages)."""
    return left + right


def merge_blockchain_state(
    left: BlockchainState,
    right: BlockchainState
) -> BlockchainState:
    """Merge blockchain states (combine transfers and cclinks)."""
    merged_transfers = dict(left.get("transfers", {}))
    for chain, chain_transfers in right.get("transfers", {}).items():
        if chain not in merged_transfers:
            merged_transfers[chain] = {}
        merged_transfers[chain].update(chain_transfers)

    merged_cclinks = list(left.get("cclinks", []))
    for link in right.get("cclinks", []):
        if link.id not in [l.id for l in merged_cclinks]:
            merged_cclinks.append(link)

    return BlockchainState(
        transfers=merged_transfers,
        cclinks=merged_cclinks
    )


def merge_subgraph_state(
    left: SubgraphExecState,
    right: SubgraphExecState
) -> SubgraphExecState:
    """Merge subgraph execution states."""
    result: SubgraphExecState = {}

    if "plan" in right:
        result["plan"] = right["plan"]
    elif "plan" in left:
        result["plan"] = left["plan"]

    left_errors = left.get("errors", [])
    right_errors = right.get("errors", [])
    if left_errors or right_errors:
        result["errors"] = left_errors + right_errors

    # Merge findings (deduplicate by id)
    left_findings = left.get("findings", [])
    right_findings = right.get("findings", [])
    if left_findings or right_findings:
        seen_ids = set()
        merged_findings = []
        for f in left_findings + right_findings:
            fid = f.get("id", "")
            if fid not in seen_ids:
                merged_findings.append(f)
                seen_ids.add(fid)
        result["findings"] = merged_findings

    return result


class GraphState(TypedDict, total=False):
    # identity / session
    thread_id: str

    # conversation (shared thread) - using Annotated for automatic merging
    messages: Annotated[List[BaseMessage], merge_messages]

    # cache for deterministic tools: [tool][args_hash] -> result
    tool_cache: Dict[str, Dict[str, Any]]
    tool_cache_args: Dict[str, Any]  # readability: args_hash -> original args

    # domain state - using Annotated for automatic merging
    blockchain: Annotated[BlockchainState, merge_blockchain_state]

    # per-subgraph control - using Annotated for automatic merging
    trace: Annotated[SubgraphExecState, merge_subgraph_state]
    fallback: Annotated[SubgraphExecState, merge_subgraph_state]

    # routing decision
    current_subgraph: Optional[Subgraph]

    # workflow control (transient fields for inter-node communication)
    trace_action: Optional[str]      # "continue" or "stop"
    task_brief: Optional[str]        # task for fetcher
    fetch_report: Optional[Dict]     # report from fetcher
    fallback_action: Optional[str]   # "continue", "stop", or "redirect"
    tool_plan: Optional[str]         # plan for tool agent
    tool_report: Optional[Dict]      # report from tool agent

    # retry tracking (to prevent infinite loops on same task)
    last_task_briefs: Optional[List[str]]  # recent task briefs for dedup


def create_initial_state(user_input: str, thread_id: Optional[str] = None) -> GraphState:
    """Create initial GraphState for a new conversation."""
    return GraphState(
        thread_id=thread_id or str(uuid.uuid4()),
        messages=[HumanMessage(content=user_input)],
        tool_cache={},
        tool_cache_args={},
        blockchain=BlockchainState(transfers={}, cclinks=[]),
        trace=SubgraphExecState(
            plan=Plan(iter=0, cursor=0, steps=[]),
            errors=[]
        ),
        fallback=SubgraphExecState(
            plan=Plan(iter=0, cursor=0, steps=[]),
            errors=[]
        ),
        current_subgraph=None
    )


def create_error_event(where: str, msg: str, retry: int = 0, data: Any = None) -> ErrorEvent:
    """Helper to create an ErrorEvent."""
    event: ErrorEvent = {
        "t": datetime.utcnow().isoformat(),
        "where": where,
        "msg": msg,
    }
    if retry:
        event["retry"] = retry
    if data:
        event["data"] = data
    return event
