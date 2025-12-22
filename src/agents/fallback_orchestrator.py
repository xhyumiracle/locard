"""
Fallback Orchestrator Agent - Handles non-trace tasks requiring tools.

Responsibilities:
- Handle tasks that need tools but aren't blockchain tracing
- Coordinate with General Tool Agent
- Can redirect to trace workflow if task is actually blockchain-related
"""

from typing import List, Literal, Optional
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

import config
from src.state.graph_state import GraphState


class FallbackOrchestratorOutput(TypedDict, total=False):
    action: Literal["continue", "stop", "redirect"]
    # if continue
    tool_plan: Optional[str]
    want: Optional[List[str]]
    # if stop
    answer_text: Optional[str]
    sources: Optional[List[str]]
    # if redirect
    redirect_to: Optional[Literal["trace"]]
    reason: Optional[str]


FALLBACK_ORCHESTRATOR_SYSTEM_PROMPT = """You are the Fallback Orchestrator Agent. You handle tasks that require general tool usage but do not match the static blockchain tracing workflow. You coordinate a loop with the General Tool Agent.

## Your Responsibilities
1) Interpret the user request and current state.
2) Manage execution plan.
3) Produce a concrete tool_plan for the General Tool Agent.
4) Evaluate Tool Agent's results against the plan.
5) Refine the plan or stop with an answer.

## When to Redirect
If you detect the task is actually a blockchain tracing task (e.g., trace funds, find source of transaction, cross-chain analysis), set action to "redirect" with redirect_to="trace".

## Principles
- Converge quickly; each plan iteration should be more specific
- Cite sources returned by the Tool Agent
- Do NOT write to blockchain state
- If task seems blockchain-related, redirect to trace workflow"""


class FallbackOrchestratorAgent:
    """Fallback Orchestrator for non-trace tool tasks."""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=config.LLM_MODEL,
            temperature=config.LLM_TEMPERATURE,
            max_tokens=config.LLM_MAX_TOKENS
        ).with_structured_output(FallbackOrchestratorOutput)

    def process(
        self,
        state: GraphState,
        tool_report: Optional[dict] = None
    ) -> FallbackOrchestratorOutput:
        """
        Process current state and optionally a tool report.

        Args:
            state: Current graph state
            tool_report: Optional report from General Tool Agent

        Returns:
            Decision to continue, stop, or redirect
        """
        messages = self._build_messages(state, tool_report)
        result = self.llm.invoke(messages)
        return result

    def _build_messages(
        self,
        state: GraphState,
        tool_report: Optional[dict] = None
    ) -> List:
        """Build message list for LLM."""
        messages = [SystemMessage(content=FALLBACK_ORCHESTRATOR_SYSTEM_PROMPT)]

        # Add conversation history
        conv_messages = state.get("messages", [])
        for msg in conv_messages:
            messages.append(msg)

        # Add fallback state context
        fallback_state = state.get("fallback", {})
        plan = fallback_state.get("plan", {})
        errors = fallback_state.get("errors", [])

        context_parts = []
        if plan:
            context_parts.append(f"Plan iteration: {plan.get('iter', 0)}")
        if errors:
            context_parts.append(f"Errors: {len(errors)}")

        if context_parts:
            context = "\n".join(context_parts)
            messages.append(HumanMessage(content=f"[Current State]\n{context}"))

        # Add tool report if provided
        if tool_report:
            report_str = self._format_tool_report(tool_report)
            messages.append(HumanMessage(content=f"[Tool Report]\n{report_str}"))

        messages.append(HumanMessage(content="Decide your next action."))

        return messages

    def _format_tool_report(self, report: dict) -> str:
        """Format tool report for LLM."""
        parts = [f"Plan: {report.get('plan', 'unknown')}"]

        results = report.get("results", [])
        if results:
            parts.append("Results:")
            for r in results:
                parts.append(f"  - {r.get('item', '')}: {r.get('source', '')}")

        gaps = report.get("gaps", [])
        if gaps:
            parts.append("Gaps:")
            for g in gaps:
                parts.append(f"  - {g}")

        return "\n".join(parts)
