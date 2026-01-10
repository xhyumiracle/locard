#!/usr/bin/env python3
"""
TraceGroupTx subgraph: Analyze a group of dst_transfers to find common ancestors.

Workflow:
1. Orchestrator: Parse query, coordinate flow
2. CrossChainTracer: Batch invoke TraceTx subgraph for each dst_transfer
3. SameChainTracer: Batch trace ancestors for all src_transfers
4. Analyzer: Find common ancestor addresses
5. Orchestrator: Output final results

Flow diagram:
[START]
  ↓
[Orchestrator] (action=None → "crosschain")
  ↓
[CrossChainTracer]
  ↓
[Orchestrator] (action="crosschain" → "samechain")
  ↓
[SameChainTracer]
  ↓
[Orchestrator] (action="samechain" → "analyze")
  ↓
[Analyzer]
  ↓
[Orchestrator] (action="analyze" → "done")
  ↓
[END]
"""

from langgraph.graph import StateGraph, END
from src.state.tracegrouptx_state import TraceGroupTxState
from src.node.tracegrouptx.orch import orchestrator_node
from src.node.tracegrouptx.crosschain_tracer import crosschain_tracer_node
from src.node.tracegrouptx.samechain_tracer import samechain_tracer_node
from src.node.tracegrouptx.analyzer import analyzer_node
from src.node.tracegrouptx.format_result import format_result_node


def create_graph():
    """Create TraceGroupTx subgraph."""

    # Use TraceGroupTxState as state schema
    workflow = StateGraph(TraceGroupTxState)

    # Add 5 nodes
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("crosschain_tracer", crosschain_tracer_node)
    workflow.add_node("samechain_tracer", samechain_tracer_node)
    workflow.add_node("analyzer", analyzer_node)
    workflow.add_node("format_result", format_result_node)

    # Set entry point
    workflow.set_entry_point("orchestrator")

    # Add conditional edges from orchestrator
    def route_from_orchestrator(state: TraceGroupTxState) -> str:
        """Route based on action set by orchestrator."""
        action = state.get("action")

        if action == "crosschain":
            return "crosschain_tracer"
        elif action == "samechain":
            return "samechain_tracer"
        elif action == "analyze":
            return "analyzer"
        elif action == "done":
            return "format_result"
        elif action == "fail":
            return END
        else:
            # Unknown action, fail
            return END

    workflow.add_conditional_edges(
        "orchestrator",
        route_from_orchestrator,
        {
            "crosschain_tracer": "crosschain_tracer",
            "samechain_tracer": "samechain_tracer",
            "analyzer": "analyzer",
            "format_result": "format_result",
            END: END
        }
    )

    # Add edges back to orchestrator from worker nodes
    workflow.add_edge("crosschain_tracer", "orchestrator")
    workflow.add_edge("samechain_tracer", "orchestrator")
    workflow.add_edge("analyzer", "orchestrator")

    # format_result is the final node (similar to TraceTx's score node)
    workflow.add_edge("format_result", END)

    return workflow.compile()
