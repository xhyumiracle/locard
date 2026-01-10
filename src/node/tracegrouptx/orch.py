#!/usr/bin/env python3
"""Orchestrator node for TraceGroupTx subgraph (LLM-driven)."""

import logging
from typing import Dict, Any
from src.state.tracegrouptx_state import TraceGroupTxState
from src.agents.tracegrouptx.trace_group_orchestrator import TraceGroupOrchestratorAgent
from src.models.core import SrcInfo
import config

logger = logging.getLogger(__name__)


def orchestrator_node(state: TraceGroupTxState) -> Dict[str, Any]:
    """
    Orchestrator node: LLM agent decides next action.

    Similar to TraceTx orchestrator pattern:
    - Agent makes all decisions based on current state
    - Pure decision-making, no tool calls
    """

    iteration = state.get("iteration", 0)

    # Check max iterations
    if iteration >= config.TRACE_MAX_ITERATIONS:
        return {
            "action": "fail",
            "result": {"success": False, "reason": "Max iterations reached"}
        }

    # Invoke LLM agent for decision
    agent = TraceGroupOrchestratorAgent()
    output = agent.process(state)

    logger.info(f"TraceGroupTx Orchestrator action: {output.action}")

    updates = {
        "iteration": iteration + 1,
        "action": output.action
    }

    # Initial entry: Store dst_transfers and src info
    if state.get("action") is None and output.dst_transfers:
        updates["dst_transfers"] = [dt.model_dump() for dt in output.dst_transfers]
        updates["src_info"] = SrcInfo(
            chain=output.src_chain or "ETH",
            asset=output.src_asset or "ETH"
        )
    
    if output.action == "samechain":
        task_brief = _build_task_brief(state)
        if task_brief:
            updates["samechain_task_brief"] = task_brief
        else:
            updates["action"] = "fail"
            updates["result"] = {
                "success": False,
                "reason": "No src_txs to trace"
            }
            return updates

    # Done: Store result with calculated summary
    if output.action == "done":
        dst_to_src = state.get("dst_to_src_mapping", {})
        ancestors_data = state.get("ancestors_data", {})
        common_ancestors = state.get("common_ancestors", {})

        # Calculate summary from state
        all_src_txs = set()
        for src_list in dst_to_src.values():
            all_src_txs.update(src_list)

        summary = {
            "total_dst_tx": len(dst_to_src),
            "total_src_tx": sum(len(src_list) for src_list in dst_to_src.values()),
            "total_unique_src_tx": len(all_src_txs),
            "total_ancestor_addresses": len(common_ancestors),
            "top_hit_count": list(common_ancestors.values())[0]["hit_count"] if common_ancestors else 0
        }

        updates["result"] = {
            "success": True,
            "data": {
                "dst_to_src_mapping": dst_to_src,
                "ancestors_data": ancestors_data,
                "common_ancestors": common_ancestors,
                "summary": summary
            }
        }

    # Fail: Store failure reason
    if output.action == "fail":
        updates["result"] = {
            "success": False,
            "reason": output.fail_reason or "Unknown error"
        }

    return updates


def _build_task_brief(state: TraceGroupTxState) -> str:
    """Build task brief for SameChainTracerAgent with only necessary information."""

    dst_to_src = state.get("dst_to_src_mapping", {})
    if not dst_to_src:
        raise ValueError("No dst_to_src_mapping provided to SameChainTracer")

    # get max_src_per_dst from params
    params = state.get("params", {})
    max_src_per_dst = params.get("max_src_per_dst", None)
    if max_src_per_dst and max_src_per_dst > 0:
        max_src_per_dst = int(max_src_per_dst)

    # collect all unique src_txs, and limit the number of src_txs per dst_tx
    all_src_txs = set()
    for src_list in dst_to_src.values():
        if max_src_per_dst and len(src_list) > max_src_per_dst:
            all_src_txs.update(src_list[:max_src_per_dst])
        else:
            all_src_txs.update(src_list)

    if not all_src_txs:
        # No src_txs to trace
        return None

    src_txs_list = sorted(list(all_src_txs))
    src_txs_str = "\n".join([f"- {tx}" for tx in src_txs_list])

    max_hops = params.get("max_hops", None)
    min_value = params.get("min_value", None)
    only_larger_ancestor = params.get("only_larger_ancestor", False)
    max_ancestor_per_hop = params.get("max_ancestor_per_hop", None)

    src_chain = state.get("src_chain", "ETH")
    src_asset = state.get("src_asset", "ETH")

    # build task brief
    task_brief = f"Trace ancestors for these {src_chain} transactions:\n{src_txs_str}"

    requirements = []
    if max_hops:
        requirements.append(f"Only trace up to {max_hops} hop{'s' if max_hops > 1 else ''}")
    if max_ancestor_per_hop:
        requirements.append(f"Only trace up to {max_ancestor_per_hop} ancestors per hop")
    if min_value:
        requirements.append(f"Only trace txs with value >= {min_value} {src_asset}")
    if only_larger_ancestor:
        requirements.append(f"Only trace txs with larger value than the current tx")
    
    if requirements:
        req_str = "\n- ".join(requirements)
        task_brief += f"\nRequirements:\n- {req_str}"

    return task_brief