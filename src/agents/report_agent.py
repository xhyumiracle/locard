"""
Report Agent - Generates natural language reports from trace results.

Uses gpt-4o-mini for cost efficiency.
"""

from typing import Any, Dict

from langchain_core.messages import SystemMessage, HumanMessage

import config
from src.prompts import load_prompt
from src.llm import create_chat_model

class ReportAgent:
    """Report Agent that generates natural language reports from trace results."""

    def __init__(self):
        self.llm = create_chat_model(
            model=config.get_agent_model("report"),
            temperature=0.3,
            max_tokens=2048
        )

    def generate_report(
        self,
        result: Dict[str, Any],
        user_query: str = ""
    ) -> str:
        """
        Generate a natural language report from trace result.

        Args:
            result: The result dict from subgraph, structure:
                    - success case: {"success": True, "data": <...>, "formatted_data": <str>}
                    - failure case: {"success": False, "reason": <str>}
            user_query: Original user query for context

        Returns:
            Natural language report string
        """
        # Handle failure case
        if not result.get("success"):
            reason = result.get("reason", "Unknown error")
            return f"Trace failed: {reason}"

        # Success case - use formatted_data provided by subgraph
        formatted_data = result.get("formatted_data")
        if not formatted_data:
            return "Error: No formatted_data in result"

        messages = self._build_messages(formatted_data, user_query)
        response = self.llm.invoke(messages)
        return response.content

    def _build_messages(
        self,
        formatted_data: str,
        user_query: str
    ):
        """Build messages for LLM."""
        messages = [SystemMessage(content=load_prompt("report_agent"))]

        content = f"User Query: {user_query}\n\n" if user_query else ""
        content += f"Trace Results:\n{formatted_data}"

        messages.append(HumanMessage(content=content))
        return messages
