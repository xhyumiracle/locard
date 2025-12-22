"""
LangGraph workflow definition for BlockchainMAS.

Implements the workflow described in systemdesign.md:
- Router -> routes to trace, fallback, or chat
- Trace loop: Orchestrator <-> Fetcher
- Fallback loop: Orchestrator <-> Tool Agent
- Chat: direct response
"""

import logging
from typing import Literal

from langgraph.graph import StateGraph, END

import config
from src.state.graph_state import (
    GraphState,
    BlockchainState,
    SubgraphExecState,
    Plan,
    create_initial_state,
    create_error_event
)
from src.agents.router import RouterAgent
from src.agents.trace_orchestrator import TraceOrchestratorAgent, create_crosschain_link
from src.agents.trace_fetcher import TraceFetcherAgent, direct_fetch_transaction, direct_fetch_price
from src.agents.fallback_orchestrator import FallbackOrchestratorAgent
from src.agents.tool_agent import GeneralToolAgent
from src.agents.chat import ChatAgent
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)


# ==================== Node Functions ====================

def router_node(state: GraphState) -> dict:
    """Route user input to appropriate subgraph."""
    router = RouterAgent()

    messages = state.get("messages", [])
    if not messages:
        return {"current_subgraph": "chat"}

    last_message = messages[-1]
    user_input = last_message.content if hasattr(last_message, "content") else str(last_message)

    logger.info(f"Router analyzing: {user_input[:100]}...")

    try:
        result = router.route(user_input)
        logger.info(f"Router decision: {result['route']} ({result['why']})")
        return {"current_subgraph": result["route"]}
    except Exception as e:
        logger.error(f"Router error: {e}")
        return {"current_subgraph": "chat"}


def trace_orchestrator_node(state: GraphState) -> dict:
    """Trace Orchestrator processes state and decides next action."""
    orchestrator = TraceOrchestratorAgent()

    # Check iteration limits
    trace_state = state.get("trace", {})
    plan = trace_state.get("plan", {"iter": 0, "cursor": 0, "steps": []})

    if plan.get("iter", 0) >= config.TRACE_MAX_ITERATIONS:
        logger.warning("Max trace iterations reached")
        return {
            "messages": [AIMessage(content="Maximum iterations reached. Unable to complete trace.")],
            "trace": {"plan": plan},
            "trace_action": "stop"
        }

    # Get any pending fetch report from state
    fetch_report = state.get("fetch_report")

    # Debug: log what fetch report we received
    if fetch_report:
        findings_count = len(fetch_report.get("findings", []))
        gaps_count = len(fetch_report.get("gaps", []))
        logger.info(f"Orchestrator received fetch_report: {findings_count} findings, {gaps_count} gaps")
        for f in fetch_report.get("findings", [])[:2]:
            logger.info(f"  Finding: {f.get('kind')} - {f.get('id')} - {f.get('rationale')}")
    else:
        logger.info("Orchestrator: No fetch_report in state (first iteration)")

    result = orchestrator.process(state, fetch_report)

    logger.info(f"Trace Orchestrator action: {result.get('action')}")

    updates: dict = {}

    if result.get("action") == "stop":
        # Return final answer
        answer = result.get("answer_text", "Analysis complete.")
        updates["messages"] = [AIMessage(content=answer)]
        updates["trace_action"] = "stop"
    else:
        # Continue with task brief
        task_brief = result.get("task_brief", "")

        # Track recent task briefs to detect loops
        last_briefs = list(state.get("last_task_briefs") or [])

        # Normalize task brief for comparison (just check if same tx hash mentioned)
        def extract_key(brief: str) -> str:
            # Extract first hex string that looks like a tx hash
            import re
            match = re.search(r'[0-9a-fA-F]{32,}', brief)
            return match.group(0).lower() if match else brief[:50].lower()

        current_key = extract_key(task_brief)

        # Count how many times we've tried similar tasks
        similar_count = sum(1 for b in last_briefs if extract_key(b) == current_key)

        if similar_count >= 2:
            # Too many retries on same task - force stop or change direction
            logger.warning(f"Detected {similar_count} similar tasks for key {current_key[:20]}..., forcing different approach")

            # Add instruction for orchestrator to try different approach
            updates["messages"] = [AIMessage(content=f"Note: Previous {similar_count} attempts to fetch data for this task had issues. Consider trying a different approach or checking the hint about DOGE.")]

        # Keep last 5 task briefs
        last_briefs.append(task_brief)
        if len(last_briefs) > 5:
            last_briefs = last_briefs[-5:]

        updates["trace_action"] = "continue"
        updates["task_brief"] = task_brief
        updates["last_task_briefs"] = last_briefs

        # Increment iteration
        new_plan = Plan(
            iter=plan.get("iter", 0) + 1,
            cursor=plan.get("cursor", 0),
            steps=plan.get("steps", [])
        )
        updates["trace"] = {"plan": new_plan}

    return updates


def trace_fetcher_node(state: GraphState) -> dict:
    """Trace Fetcher executes the task brief."""
    task_brief = state.get("task_brief", "")

    if not task_brief:
        logger.warning("No task brief for fetcher")
        return {"fetch_report": {"task": "", "findings": [], "gaps": ["No task brief provided"]}}

    logger.info(f"Trace Fetcher executing: {task_brief[:100]}...")

    fetcher = TraceFetcherAgent()
    report = fetcher.fetch(task_brief, state)

    logger.info(f"Fetcher found {len(report.get('findings', []))} findings, {len(report.get('gaps', []))} gaps")

    # Store transfers from findings
    blockchain_updates = {}
    transfers_update = {}

    for finding in report.get("findings", []):
        data = finding.get("data", {})
        if "_transfer" in data:
            transfer = data["_transfer"]
            chain = transfer.locator.chain
            if chain not in transfers_update:
                transfers_update[chain] = {}
            transfers_update[chain][transfer.id] = transfer

    if transfers_update:
        blockchain_updates["transfers"] = transfers_update

    # Accumulate findings in trace state
    trace_state = state.get("trace", {})
    existing_findings = trace_state.get("findings", [])
    new_findings = report.get("findings", [])

    updates = {
        "fetch_report": dict(report),  # Convert TypedDict to regular dict
        "blockchain": blockchain_updates,
        "trace": {"findings": existing_findings + new_findings}
    }

    # Log errors if any
    if report.get("gaps"):
        for gap in report["gaps"]:
            logger.warning(f"  Gap: {gap}")
        errors = [create_error_event("trace_fetcher", gap) for gap in report["gaps"]]
        existing_errors = trace_state.get("errors", [])
        updates["trace"]["errors"] = existing_errors + errors

    return updates


def fallback_orchestrator_node(state: GraphState) -> dict:
    """Fallback Orchestrator handles non-trace tool tasks."""
    orchestrator = FallbackOrchestratorAgent()

    fallback_state = state.get("fallback", {})
    plan = fallback_state.get("plan", {"iter": 0, "cursor": 0, "steps": []})

    if plan.get("iter", 0) >= config.FALLBACK_MAX_ITERATIONS:
        logger.warning("Max fallback iterations reached")
        return {
            "messages": [AIMessage(content="Maximum iterations reached.")],
            "fallback": {"plan": plan},
            "fallback_action": "stop"
        }

    tool_report = state.get("tool_report")
    result = orchestrator.process(state, tool_report)

    logger.info(f"Fallback Orchestrator action: {result.get('action')}")

    updates: dict = {}

    if result.get("action") == "stop":
        answer = result.get("answer_text", "Task complete.")
        updates["messages"] = [AIMessage(content=answer)]
        updates["fallback_action"] = "stop"
    elif result.get("action") == "redirect":
        updates["current_subgraph"] = result.get("redirect_to", "trace")
        updates["fallback_action"] = "redirect"
    else:
        tool_plan = result.get("tool_plan", "")
        updates["fallback_action"] = "continue"
        updates["tool_plan"] = tool_plan

        new_plan = Plan(
            iter=plan.get("iter", 0) + 1,
            cursor=plan.get("cursor", 0),
            steps=plan.get("steps", [])
        )
        updates["fallback"] = {"plan": new_plan}

    return updates


def tool_agent_node(state: GraphState) -> dict:
    """General Tool Agent executes tool plans."""
    tool_plan = state.get("tool_plan", "")

    if not tool_plan:
        return {"tool_report": {"plan": "", "results": [], "sources": [], "gaps": ["No tool plan"]}}

    logger.info(f"Tool Agent executing: {tool_plan[:100]}...")

    agent = GeneralToolAgent()
    report = agent.execute(tool_plan)

    logger.info(f"Tool Agent got {len(report.get('results', []))} results")

    return {"tool_report": dict(report)}


def chat_node(state: GraphState) -> dict:
    """Chat agent for simple conversations."""
    agent = ChatAgent()
    response = agent.respond(state)
    return {"messages": [AIMessage(content=response)]}


# ==================== Routing Functions ====================

def route_from_router(state: GraphState) -> Literal["trace_orchestrator", "fallback_orchestrator", "chat"]:
    """Route based on router decision."""
    subgraph = state.get("current_subgraph", "chat")

    if subgraph == "trace":
        return "trace_orchestrator"
    elif subgraph == "fallback":
        return "fallback_orchestrator"
    else:
        return "chat"


def route_from_trace_orchestrator(state: GraphState) -> Literal["trace_fetcher", END]:
    """Route after trace orchestrator."""
    action = state.get("trace_action", "stop")
    logger.info(f"Routing from trace_orchestrator: action={action}")

    if action == "continue":
        return "trace_fetcher"
    else:
        return END


def route_from_trace_fetcher(state: GraphState) -> Literal["trace_orchestrator"]:
    """Route after trace fetcher - always back to orchestrator."""
    return "trace_orchestrator"


def route_from_fallback_orchestrator(state: GraphState) -> Literal["tool_agent", "router", END]:
    """Route after fallback orchestrator."""
    action = state.get("fallback_action", "stop")
    logger.info(f"Routing from fallback_orchestrator: action={action}")

    if action == "continue":
        return "tool_agent"
    elif action == "redirect":
        return "router"
    else:
        return END


def route_from_tool_agent(state: GraphState) -> Literal["fallback_orchestrator"]:
    """Route after tool agent - always back to orchestrator."""
    return "fallback_orchestrator"


# ==================== Graph Construction ====================

def create_graph() -> StateGraph:
    """Create the BlockchainMAS workflow graph."""

    # Create the graph with our state schema
    workflow = StateGraph(GraphState)

    # Add nodes
    workflow.add_node("router", router_node)
    workflow.add_node("trace_orchestrator", trace_orchestrator_node)
    workflow.add_node("trace_fetcher", trace_fetcher_node)
    workflow.add_node("fallback_orchestrator", fallback_orchestrator_node)
    workflow.add_node("tool_agent", tool_agent_node)
    workflow.add_node("chat", chat_node)

    # Set entry point
    workflow.set_entry_point("router")

    # Add conditional edges from router
    workflow.add_conditional_edges(
        "router",
        route_from_router,
        {
            "trace_orchestrator": "trace_orchestrator",
            "fallback_orchestrator": "fallback_orchestrator",
            "chat": "chat",
        }
    )

    # Trace workflow edges
    workflow.add_conditional_edges(
        "trace_orchestrator",
        route_from_trace_orchestrator,
        {
            "trace_fetcher": "trace_fetcher",
            END: END,
        }
    )
    workflow.add_edge("trace_fetcher", "trace_orchestrator")

    # Fallback workflow edges
    workflow.add_conditional_edges(
        "fallback_orchestrator",
        route_from_fallback_orchestrator,
        {
            "tool_agent": "tool_agent",
            "router": "router",
            END: END,
        }
    )
    workflow.add_edge("tool_agent", "fallback_orchestrator")

    # Chat goes to END
    workflow.add_edge("chat", END)

    return workflow.compile()


def run_graph(user_input: str, thread_id: str = None) -> dict:
    """
    Run the graph with user input.

    Args:
        user_input: User's message
        thread_id: Optional thread ID for session tracking

    Returns:
        Final state after graph execution
    """
    graph = create_graph()
    initial_state = create_initial_state(user_input, thread_id)

    logger.info(f"Starting graph execution for: {user_input[:100]}...")

    try:
        final_state = graph.invoke(initial_state)
        logger.info("Graph execution completed")
        return final_state
    except Exception as e:
        logger.error(f"Graph execution failed: {e}")
        raise
