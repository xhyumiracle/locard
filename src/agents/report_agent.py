"""
Report Agent - Generates natural language reports from trace results.

Uses gpt-4o-mini for cost efficiency.
"""

from typing import Any, Dict

from langchain_core.messages import SystemMessage, HumanMessage

import config
from src.node.tracetx.score import ScoreTable, format_score_table
from src.agents.prompts import load_prompt
from src.utils.llm import create_chat_openai_with_retry

class ReportAgent:
    """Report Agent that generates natural language reports from trace results."""

    def __init__(self):
        self.llm = create_chat_openai_with_retry(
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
                    - success case: {"success": True, "data": <score_table>}
                    - failure case: {"success": False, "reason": <str>}
            user_query: Original user query for context

        Returns:
            Natural language report string
        """
        # Handle failure case
        if not result.get("success"):
            reason = result.get("reason", "Unknown error")
            return f"Trace failed: {reason}"

        # Success case - format scoring table
        score_table = result["data"]
        messages = self._build_messages(score_table, user_query)
        response = self.llm.invoke(messages)
        return response.content

    def _build_messages(
        self,
        score_table: ScoreTable,
        user_query: str
    ):
        """Build messages for LLM."""
        messages = [SystemMessage(content=load_prompt("report_agent"))]

        # Format scoring table as structured input
        table_str = format_score_table(score_table)

        content = f"User Query: {user_query}\n\n" if user_query else ""
        content += f"Scoring Results:\n{table_str}"

        messages.append(HumanMessage(content=content))
        return messages
