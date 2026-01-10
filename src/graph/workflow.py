"""
LangGraph workflow definition for BlockchainMAS.

Implements the workflow described in systemdesign.md:
- Router -> routes to trace, fallback, or chat
- Trace loop: Orchestrator <-> Fetcher
- Fallback loop: Orchestrator <-> Tool Agent
- Chat: direct response
"""

import logging
from typing import Literal, Optional, Dict, Any

from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage

from src.agents.report_agent import ReportAgent
from src.state.graph_state import GraphState, create_initial_state
from src.agents.router import RouterAgent
from src.graph.registry import SUBGRAPH_MAP, STATE_INIT_MAP
from src.utils.debug import print_messages

logger = logging.getLogger(__name__)


# ==================== Router & Chat Nodes ====================

def router_node(state: GraphState) -> dict:
    """Route user input to appropriate subgraph."""
    router = RouterAgent()

    messages = state["messages"]
    if len(messages) == 0:
        raise Exception("No messages found.")
    user_input = messages[0].content

    logger.info(f"Router start")
    result = router.route(user_input)
    logger.info(f"Router decision: {result['route']}")
    if result['route'] == 'unknown':
        raise Exception("Router return unknown.")
    return {"route": result['route']}

def dispatch_node(state: GraphState) -> dict:
    """Dispatch the query to the appropriate subgraph."""
    key = state["route"]

    logger.info("Dispatch begin")

    user_input = state["messages"][0].content
    params = state.get("params")

    # Initialize state using the appropriate function
    subgraph_state = STATE_INIT_MAP[key](user_input, params=params)
    out_substate = SUBGRAPH_MAP[key].invoke(subgraph_state)
    logger.info("Dispatch done")

    return {"result": out_substate["result"]}

def reporter_node(state: GraphState) -> dict:
    user_input = state["messages"][0].content
    result = state["result"]

    # Generate report
    logger.info("Reporter begin")
    report = ReportAgent().generate_report(result, user_input)
    logger.info("Reporter done")

    # Print report output
    print_messages("reporter", "Agent Begin")
    report_message = AIMessage(content=report)
    print_messages("reporter", "Agent End")

    return {
        "messages": [report_message]
    }

# ==================== Graph Construction ====================

def create_graph() -> StateGraph:
    # Create the graph with our state schema
    workflow = StateGraph(GraphState)

    # Add nodes
    workflow.add_node("router", router_node) # agent node
    workflow.add_node("dispatch", dispatch_node) # logic node
    workflow.add_node("reporter", reporter_node) # agent node

    # Set entry point
    workflow.set_entry_point("router")

    # Add edges
    workflow.add_edge("router", "dispatch")
    workflow.add_edge("dispatch", "reporter")
    workflow.add_edge("reporter", END)

    return workflow.compile()

def run_graph(user_input: str, thread_id: str = None, params: Optional[Dict[str, Any]] = None) -> dict:
    """
    Run the graph with user input.

    Args:
        user_input: User's message
        thread_id: Optional thread ID for session tracking
        params: Optional parameters to override defaults

    Returns:
        Final state after graph execution
    """
    initial_state = create_initial_state(user_input, thread_id, params=params)

    logger.info(f"Starting graph execution for: {user_input[:100]}...")

    try:
        final_state = main_workflow.invoke(initial_state)
        logger.info("Graph execution completed")
        return final_state
    except Exception as e:
        logger.error(f"Graph execution failed: {e}")
        raise

# compile only once
main_workflow = create_graph()