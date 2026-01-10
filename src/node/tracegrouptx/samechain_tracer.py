#!/usr/bin/env python3
"""
SameChainTracer node for TraceGroupTx subgraph.

Responsibilities:
1. Collect unique src_txs from dst_to_src_mapping
2. Call trace_ancestors_eth tool (batch processing)
3. Return ancestors_data

LLM agent node (for potential future extensions with more tools).
"""

from typing import Dict, Any
from src.state.tracegrouptx_state import TraceGroupTxState
from src.agents.tracegrouptx.samechain_tracer import SameChainTracerAgent


def samechain_tracer_node(state: TraceGroupTxState) -> Dict[str, Any]:
    """
    SameChainTracer node: Trace ancestors for all src transfers.

    Input: dst_to_src_mapping, params
    Output: ancestors_data
    """

    # invoke agent with task brief
    task_brief = state.get("samechain_task_brief", None)
    if not task_brief:
        return {"ancestors_data": {}}

    # Invoke agent
    agent = SameChainTracerAgent()
    result = agent.trace(task_brief, state)

    ancestors_data = result.get("ancestors_data", {})

    return {"ancestors_data": ancestors_data}
