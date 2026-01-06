"""
State lookup tools for agents to query existing data.

These tools are created dynamically with captured state context.
"""

from langchain_core.tools import tool
from typing import List
from src.state.tracetx_state import TraceTxState
from src.models.finding import find_all_by_prefix, Finding


def create_state_lookup_tool(state: TraceTxState):
    """Create a state_lookup tool with captured state context.

    This uses closure pattern to inject runtime state into tool.
    """

    @tool
    def state_lookup(id_prefix: str) -> List[Finding]:
        """
        Look up existing data from state by ID prefix.
        Use with caution, only use when you are sure the ID prefix is correct.

        Args:
            id_prefix: Prefix of the ID to look up (any length, matches from start)

        Returns:
            The finding list if found, empty list otherwise
        """
        id_prefix = id_prefix.lower().strip()

        findings = state.get("findings", [])
        filtered_findings = find_all_by_prefix(findings, id_prefix, ignore_case_sensitive=True)
        return filtered_findings or []

    return state_lookup
