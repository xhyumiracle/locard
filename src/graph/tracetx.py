import logging
from src.node.tracetx.score import score_node
from src.node.tracetx.derive import derive_node
from src.state.tracetx_state import TraceTxState
from langgraph.graph import StateGraph, END
from typing import Literal
from src.node.tracetx.orch import orchestrator_node
from src.node.tracetx.fetcher import fetcher_node
from src.node.tracetx.score import score_node
logger = logging.getLogger(__name__)

# ==================== Route ====================

def route_from_orchestrator(state: TraceTxState) -> Literal["fetcher", "score", "stop"]:
    action = state["action"]

    if action == "fetch":
        return "fetcher"
    elif action == "score":
        return "score"
    else:
        return "stop"

# ==================== create ====================

def create_graph():
    # Create the graph with our state schema
    workflow = StateGraph(TraceTxState)

    # Add nodes
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("fetcher", fetcher_node)
    workflow.add_node("score", score_node)
    workflow.add_node("derive", derive_node)
    # Set entry point
    workflow.set_entry_point("orchestrator")

    # Add edges
    workflow.add_conditional_edges(
        "orchestrator",
        route_from_orchestrator,
        {
            "fetcher": "fetcher",
            "score": "score",
            "stop": END
        }
    )

    workflow.add_edge("fetcher", "derive")
    workflow.add_edge("derive", "orchestrator")

    workflow.add_edge("score", END)

    return workflow.compile()

