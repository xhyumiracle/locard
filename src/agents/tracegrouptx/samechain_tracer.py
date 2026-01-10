#!/usr/bin/env python3
"""
SameChainTracer agent for TraceGroupTx subgraph.

LLM agent that calls trace_ancestors_eth tool and potentially other future tools.
"""

import logging
from typing import Dict, Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field, ConfigDict

import config
from src.llm import create_chat_model
from src.tools.blockchair import trace_ancestors_eth
from src.utils.debug import print_messages, print_structure_output
from src.prompts.loader import load_prompt

logger = logging.getLogger(__name__)

class SameChainTracerAgent:
    """
    SameChainTracer agent: Calls trace_ancestors_eth tool.

    Future extensions may include:
    - trace_ancestors_utxo
    - Other same-chain analysis tools
    """

    def __init__(self):
        self.llm = create_chat_model(
            model=config.get_agent_model("samechain_tracer"),
            temperature=0
        ).bind(parallel_tool_calls=False)

        self.tools = [trace_ancestors_eth]
        self.system_prompt = load_prompt("tracegrouptx/trace_group_samechain")

        # Create react agent without structured output
        # (we'll extract ancestors_data from tool call results directly)
        self.agent = create_react_agent(
            self.llm,
            self.tools,
            prompt=self.system_prompt
        )

    def trace(
        self,
        task_brief: str,
        state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute ancestor tracing task.

        Args:
            task_brief: Task description with src_txs and parameters
            state: Optional TraceGroupTxState for context

        Returns:
            {
                "ancestors_data": {src_tx: {ancestor_tx: {...}}}
            }
        """

        # Build messages
        messages = [HumanMessage(content=task_brief)]
        print_messages("samechain_tracer", "Agent Input", messages)

        # Invoke agent
        result = self.agent.invoke({"messages": messages})

        # Print all messages including tool calls and results
        messages_out = result.get("messages", [])
        print_messages("samechain_tracer", "Agent Output", messages_out)

        # Extract structured output
        structured = result.get("structured_response")
        print_structure_output("samechain_tracer", structured)

        if structured:
            return {
                "ancestors_data": structured.ancestors_data
            }

        # Fallback: Try to extract from tool calls
        ancestors_data = self._extract_from_tool_calls(messages_out)

        return {"ancestors_data": ancestors_data}

    def _extract_from_tool_calls(self, messages) -> Dict[str, Any]:
        """
        Extract ancestors_data from tool call results in messages.

        Looks for trace_ancestors_eth tool calls and returns the content.
        """
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "tool":
                # Tool message contains the result
                if msg.name == "trace_ancestors_eth":
                    try:
                        import json
                        return json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                    except Exception:
                        pass

        return {}

class SameChainTracerOutput(BaseModel):
    """
    Structured output schema for SameChainTracer agent.

    Simple dict output - tool returns the data we need directly.
    """
    model_config = ConfigDict(extra='forbid')

    # Just return empty dict - we'll extract from tool calls
    success: bool = Field(default=True, description="Whether trace completed successfully")
