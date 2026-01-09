"""
Trace Orchestrator Agent - Controls the blockchain tracing workflow.

Responsibilities:
- Interpret user objectives and current blockchain state
- Manage execution plan
- Issue task briefs to Trace Fetcher
- Process fetch reports and identify cross-chain links
- Decide when to continue or stop
"""

import logging
from typing import Dict, List, Literal, Optional

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from pydantic import BaseModel, Field
import yaml

import config
from src.prompts import load_prompt
from src.agents.tool_agent_with_error_handling import create_tool_agent_with_error_handling
from src.state.tracetx_state import TraceTxState
from src.models.core import (
    DstInfoSchema, SrcInfoSchema,
    dst_info_schema_to_state, src_info_schema_to_state
)
from src.models.finding import format_finding_data, format_findings
from src.utils.debug import print_messages, print_structure_output
from src.llm import create_chat_model
from src.tools.calculators import (
    calculate_search_time_window,
    calculate_search_amount_window,
    calculate_check_time_windows
)

logger = logging.getLogger(__name__)


# class CandidateOutput(BaseModel):
#     """Candidate data output from orchestrator (source side of cross-chain link).

#     Price direction: SOURCE_in_DESTINATION (1 src_coin = X dst_coin)
#     This allows scoring to use multiplication: expected_dst = src_amount * price
#     """
#     txid: str = Field(description="Source tx hash")
#     # chain: str = Field(description="Source chain")
#     op_id: str = Field(description="Operation ID in format 'vout:N' for both UTXO and Account-based")
#     amount: float = Field(description="Amount in human-readable units")
#     block_time: int = Field()
#     price_min: float = Field(description="Min price at candidate's timestamp (raw, no buffer)")
#     price_max: float = Field(description="Max price at candidate's timestamp (raw, no buffer)")

class TraceOrchestratorOutput(BaseModel):
    """Output from the trace orchestrator."""
    action: Literal["fetch", "done", "fail"] = Field(description="Action: 'fetch' to continue fetching data, 'done' when ready for scoring, 'fail' when cannot proceed")
    # if action=fetch
    task_brief: Optional[str] = Field(default=None, description="Task for fetcher to execute")
    src_info: Optional[SrcInfoSchema] = Field(default=None, description="Source tx info - output as soon as source tx is fetched, regardless of action")
    dst_info: Optional[DstInfoSchema] = Field(default=None, description="Destination tx info - output as soon as dst tx is fetched, regardless of action")
    # if action=done - finding IDs that contain the candidate and price data
    candidates_finding_ids: Optional[List[str]] = Field(default=None, description="Finding IDs of search_txs to use for candidates (e.g., ['search_txs:BTC@1757641622-1757642822'])")
    # candidates: Optional[List[CandidateOutput]] = Field(default=None, description="All source tx candidates")
    fail_reason: Optional[str] = Field(default=None, description="Why failed: no candidates, tool failure, etc.")

    # Self-reflection tracking (optional)
    reflection_update: Optional[Dict[str, Dict[str, bool]]] = Field(
        default=None,
        description="""Optional: Update reflection tracking for self-verification. Only records BEHAVIOR (whether tools were called), NOT results.
        Example: {"step_2": {"tool_called": True, "verified": True}}
        DO NOT include calculation results (window, windows) - extract those from findings."""
    )


class TraceOrchestratorAgent:
    """Trace Orchestrator Agent that controls the tracing workflow."""

    def __init__(self):
        base_llm = create_chat_model(
            model=config.get_agent_model("trace_orchestrator")
        )

        # Prepare calculator tools (these are already @tool decorated)
        calculator_tools = [
            calculate_search_time_window,
            calculate_search_amount_window,
            calculate_check_time_windows
        ]

        # Create tool agent with error handling and structured output
        # Tool errors will be caught and converted to error messages
        # This allows the LLM to see "Error: Fetch price first" and return action="fetch"
        self.agent = create_tool_agent_with_error_handling(
            llm=base_llm,
            tools=calculator_tools,
            output_schema=TraceOrchestratorOutput
        )

    def process(
        self,
        state: TraceTxState,
    ):
        messages = self._build_messages(state)

        print_messages("trace_orchestrator", "Input", messages)

        # Invoke tool agent (handles tool calling + error handling + structured output)
        result = self.agent.invoke(messages)

        print_messages("trace_orchestrator", "Output", result)
        return result


    def _build_messages(
        self,
        state: TraceTxState,
    ) -> List:
        """Build message list for LLM."""
        messages = [SystemMessage(content=load_prompt("trace_orchestrator"))]

        messages.append(SystemMessage(content=state["query"]))

        context_parts = []

        #################
        # Append Context
        #################
        params = state.get("params", {})
        if params:
            # Format time-related params with explicit "seconds" suffix for clarity
            param_strs = []
            for key, val in params.items():
                if 'time_span' in key or 'time' in key:
                    param_strs.append(f"{key}={val} (seconds)")
                else:
                    param_strs.append(f"{key}={val}")
            context_parts.append(f"Params: {', '.join(param_strs)}")

        trajectories = state.get("trajectories", [])
        if trajectories:
            context_parts.append(f"Previous Actions ({len(trajectories)} total):")
            for trajectory in trajectories:
                context_parts.append(f"  - action: {trajectory['action']}")
                context_parts.append(f"    task: {trajectory['task_brief']}")
                context_parts.append(f"    finding IDs: {trajectory['findings_ref']}\n")
                
        findings = state.get("findings")
        if findings:
            context_parts.append(f"Previous Findings ({len(findings)} total):\n")
            context_parts.append(format_findings(findings, indent=0))

        # Add reflection status
        reflection = state.get("reflection", {})
        if reflection:
            reflection_str = yaml.dump(reflection, default_flow_style=False, sort_keys=False).rstrip()
            context_parts.append(f"[Self-Reflection Status]\n{reflection_str}")

        if context_parts:
            context = "\n".join(context_parts)
            messages.append(HumanMessage(content=f"[Context]\n{context}"))

        #################
        # Append last task brief
        #################
        pending_traj = state.get("pending_trajectory", {})
        task_brief = pending_traj.get("task_brief")
        if task_brief:
            messages.append(HumanMessage(content=f"[Last Task]\n{task_brief}"))
        
        #################
        # Append inbox findings and gaps
        #################
        inbox_parts = []
        inbox_findings  = state.get("inbox_findings")
        inbox_gaps = state.get("inbox_gaps", [])
        if inbox_findings or inbox_gaps:
            inbox_parts.append(f"New findings ({len(inbox_findings)} total):\n")
            inbox_parts.append(format_findings(inbox_findings))
            inbox_parts.append("Gaps/Issues:")
            for g in inbox_gaps:
                inbox_parts.append(f"  - {g}")
            inbox = "\n".join(inbox_parts)
            messages.append(HumanMessage(content=f"[Latest Feedback]\n{inbox}"))

        return messages
