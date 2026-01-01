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

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field

import config
from src.agents.prompts import load_prompt
from src.state.tracetx_state import SrcInfo, TraceTxState, DestInfo
from src.models.finding import format_finding_data, format_findings
from src.utils.debug import print_messages, print_structure_output
from src.utils.llm import create_chat_openai_with_retry

logger = logging.getLogger(__name__)

class TaskWant(BaseModel):
    """What the orchestrator wants from the fetcher."""
    k: int = Field(default=5, description="Top-k hits desired")
    kinds: List[Literal["tx", "event", "address"]] = Field(
        default_factory=list,
        description="Types of data to fetch"
    )


class CandidateOutput(BaseModel):
    """Candidate data output from orchestrator (source side of cross-chain link).

    Price direction: SOURCE_in_DEST (1 src_coin = X dst_coin)
    This allows scoring to use multiplication: expected_dest = src_amount * price
    """
    txid: str = Field(description="Source tx hash")
    # chain: str = Field(description="Source chain")
    op_id: str = Field(description="Operation ID in format 'vout:N' for both UTXO and Account-based")
    amount: float = Field(description="Amount in human-readable units")
    block_time: int = Field()
    price_min: float = Field(description="Min price at candidate's timestamp (raw, no buffer)")
    price_max: float = Field(description="Max price at candidate's timestamp (raw, no buffer)")

class TraceOrchestratorOutput(BaseModel):
    """Output from the trace orchestrator."""
    action: Literal["fetch", "score", "stop"] = Field(description="Whether to continue fetching or stop")
    # if action=fetch
    task_brief: Optional[str] = Field(default=None, description="Task for fetcher to execute")
    want: Optional[TaskWant] = Field(default=None, description="What data is needed")
    src_info: Optional[SrcInfo] = Field(default=None, description="Source tx info - output as soon as source tx is fetched, regardless of action")
    dest_info: Optional[DestInfo] = Field(default=None, description="Destination tx info - output as soon as dest tx is fetched, regardless of action")
    # if action=score - structured candidate data for scoring
    candidates: Optional[List[CandidateOutput]] = Field(default=None, description="Source tx candidates")
    stop_reason: Optional[str] = Field(default=None, description="Why stopping: ready_for_scoring, no_candidates, tool_failure")


class TraceOrchestratorAgent:
    """Trace Orchestrator Agent that controls the tracing workflow."""

    def __init__(self):
        llm = create_chat_openai_with_retry(
            model=config.get_agent_model("trace_orchestrator")
        )
        self.llm = llm.with_structured_output(TraceOrchestratorOutput)

    def process(
        self,
        state: TraceTxState,
    ):
        messages = self._build_messages(state)

        print_messages("trace_orchestrator", "Input", messages)
        result = self.llm.invoke(messages)
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
            context_parts.append(f"Params: {params}")

        derived = state.get("derived", {})
        search_window = derived.get("search_window", {})
        if search_window:
            time_w = search_window.get("time")
            amount_w = search_window.get("amount")
            if time_w:
                context_parts.append(f"Search Window - Time: {time_w['start_ts']} to {time_w['end_ts']}")
            if amount_w:
                context_parts.append(f"Search Window - Amount: {amount_w['min']:.8f} to {amount_w['max']:.8f}")

        findings = state.get("findings")
        if findings:
            context_parts.append(f"Findings ({len(findings)} total):\n")
            context_parts.append(format_findings(findings, indent=0))
        
        if context_parts:
            context = "\n".join(context_parts)
            messages.append(HumanMessage(content=f"[Context]\n{context}"))

        #################
        # Append last task brief
        #################
        task_brief = state.get("task_brief")
        if task_brief:
            messages.append(HumanMessage(content=f"[Fetch Task Brief]\n{task_brief}"))
        
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
            messages.append(HumanMessage(content=f"[Fetch Report]\n{inbox}"))

        return messages
