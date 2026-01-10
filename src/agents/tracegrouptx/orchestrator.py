#!/usr/bin/env python3
"""TraceGroupOrchestrator agent: LLM-driven workflow orchestration."""

from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

import config
from src.llm import create_chat_model
from src.agents.tool_agent_with_error_handling import create_tool_agent_with_error_handling
from src.prompts.loader import load_prompt
from src.utils.debug import print_messages, print_structure_output


class TraceGroupOrchestratorAgent:
    def __init__(self):
        base_llm = create_chat_model(
            model=config.get_agent_model("trace_group_orchestrator")
        )
        self.agent = create_tool_agent_with_error_handling(
            llm=base_llm,
            tools=[],
            output_schema=TraceGroupOrchestratorOutput
        )
        self.prompt = load_prompt("tracegrouptx/trace_group_orchestrator")

    def process(self, state: Dict[str, Any]) -> "TraceGroupOrchestratorOutput":
        messages = self._build_messages(state)

        print_messages("trace_group_orchestrator", "Input", messages)

        result = self.agent.invoke(messages)

        print_structure_output("trace_group_orchestrator", result.model_dump() if hasattr(result, 'model_dump') else result)

        return result

    def _build_messages(self, state: Dict[str, Any]) -> List:
        messages = [SystemMessage(content=self.prompt)]

        # User query
        query = state.get("query", "")
        messages.append(HumanMessage(content=f"Query: {query}"))

        # Current state summary
        state_summary = self._format_state(state)
        messages.append(SystemMessage(content=f"Current State:\n{state_summary}"))

        return messages

    def _format_state(self, state: Dict[str, Any]) -> str:
        """Format current state for LLM to review."""
        lines = []

        iteration = state.get("iteration", 0)
        action = state.get("action")
        lines.append(f"Iteration: {iteration}")
        lines.append(f"Last action: {action or 'None (initial entry)'}")

        # Dst transfers
        dst_transfers = state.get("dst_transfers")
        if dst_transfers:
            lines.append(f"\nDst transfers: {len(dst_transfers)} provided")

        # CrossChain results
        dst_to_src = state.get("dst_to_src_mapping")
        if dst_to_src:
            total_src = sum(len(v) for v in dst_to_src.values())
            lines.append(f"\nCrossChain results:")
            lines.append(f"  - {len(dst_to_src)} dst_tx mapped")
            lines.append(f"  - {total_src} total src_tx found")

        # SameChain results
        ancestors_data = state.get("ancestors_data")
        if ancestors_data:
            total_anc = sum(len(v) for v in ancestors_data.values())
            lines.append(f"\nSameChain results:")
            lines.append(f"  - {len(ancestors_data)} src_tx traced")
            lines.append(f"  - {total_anc} total ancestors found")

        # Analysis results
        common_ancestors = state.get("common_ancestors")
        if common_ancestors:
            top_hit = list(common_ancestors.values())[0]["hit_count"] if common_ancestors else 0
            lines.append(f"\nAnalysis results:")
            lines.append(f"  - {len(common_ancestors)} common addresses found")
            lines.append(f"  - Top hit count: {top_hit}")

        return "\n".join(lines)


class DstTransferSchema(BaseModel):
    txid: str = Field(description="tx hash")
    chain: str = Field()
    asset: str = Field(description="same as chain if native asset")
    recipient: str = Field(description="recipient address to identify the specific output in the transaction")

class TraceGroupOrchestratorOutput(BaseModel):
    action: Literal["crosschain", "samechain", "analyze", "done", "fail"]
    dst_transfers: Optional[List[DstTransferSchema]] = None
    src_chain: Optional[str] = None
    src_asset: Optional[str] = None
    fail_reason: Optional[str] = None
    reasoning: Optional[str] = None
