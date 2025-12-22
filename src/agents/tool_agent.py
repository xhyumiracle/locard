"""
General Tool Agent - Executes tool plans for fallback workflow.

Responsibilities:
- Parse tool plans from Fallback Orchestrator
- Execute general purpose tools
- Return structured results
"""

from typing import List, Optional
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

import config
from src.tools.registry import get_fallback_tools


class ToolResult(TypedDict):
    item: str         # what was found
    source: str       # where it came from


class ToolReport(TypedDict):
    plan: str                # echoed tool plan
    results: List[ToolResult]
    sources: List[str]       # list of source URLs/titles
    gaps: List[str]          # optional, remaining uncertainties


TOOL_AGENT_SYSTEM_PROMPT = """You are the General Tool Agent. You execute the Fallback Orchestrator's tool plans by calling external tools and return structured results.

## Your Responsibilities
1) Parse the tool_plan to understand what information is needed.
2) Execute tool calls; retry transient failures internally.
3) On persistent failure, report in gaps.
4) Summarize findings concisely with sources.

## Principles
- Follow the plan strictly; only fill gaps when necessary.
- Provide sources suitable for citation.
- Explicitly note uncertainty or conflicting information.
- Keep results concise; do not dump raw data."""


class GeneralToolAgent:
    """General Tool Agent for fallback workflow."""

    def __init__(self):
        self.tools = get_fallback_tools()
        self.llm = ChatOpenAI(
            model=config.LLM_MODEL,
            temperature=0,
            max_tokens=config.LLM_MAX_TOKENS
        )

        self.agent = create_react_agent(
            self.llm,
            self.tools,
            prompt=TOOL_AGENT_SYSTEM_PROMPT
        )

    def execute(self, tool_plan: str) -> ToolReport:
        """
        Execute a tool plan.

        Args:
            tool_plan: The plan from Fallback Orchestrator

        Returns:
            ToolReport with results and gaps
        """
        try:
            result = self.agent.invoke({
                "messages": [HumanMessage(content=tool_plan)]
            })

            return self._parse_output(tool_plan, result)

        except Exception as e:
            return ToolReport(
                plan=tool_plan,
                results=[],
                sources=[],
                gaps=[f"Execution failed: {str(e)}"]
            )

    def _parse_output(self, tool_plan: str, result: dict) -> ToolReport:
        """Parse react agent output into ToolReport."""
        results: List[ToolResult] = []
        sources: List[str] = []
        gaps: List[str] = []

        messages = result.get("messages", [])

        for msg in messages:
            if hasattr(msg, "type") and msg.type == "tool":
                tool_name = getattr(msg, "name", "unknown")
                try:
                    content = msg.content
                    if isinstance(content, str):
                        import json
                        import ast
                        try:
                            content = json.loads(content)
                        except json.JSONDecodeError:
                            try:
                                content = ast.literal_eval(content)
                            except (ValueError, SyntaxError):
                                content = {"raw": content}

                    if isinstance(content, dict) and content.get("success"):
                        results.append(ToolResult(
                            item=str(content),
                            source=tool_name
                        ))
                        sources.append(tool_name)
                    elif isinstance(content, dict):
                        gaps.append(f"{tool_name}: {content.get('error', 'failed')}")
                except Exception as e:
                    gaps.append(f"Error parsing {tool_name}: {e}")

        # Get final response if no results
        if not results:
            for msg in reversed(messages):
                if hasattr(msg, "type") and msg.type == "ai":
                    results.append(ToolResult(
                        item=msg.content,
                        source="agent"
                    ))
                    break

        return ToolReport(
            plan=tool_plan,
            results=results,
            sources=sources,
            gaps=gaps
        )
