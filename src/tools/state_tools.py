"""
State lookup tools for agents to query existing data.

These tools are created dynamically with captured state context.
"""

from langchain_core.tools import tool

from src.state.tracetx_state import TraceTxState


def create_state_lookup_tool(state: TraceTxState):
    """Create a state_lookup tool with captured state context.

    This uses closure pattern to inject runtime state into tool.
    """

    @tool
    def state_lookup(id_prefix: str) -> dict:
        """
        Look up existing data from state by ID prefix.
        Use when [Existing IDs] hint shows a matching prefix to skip redundant API calls.

        Args:
            id_prefix: Prefix of the ID to look up (any length, matches from start)

        Returns:
            The finding or transfer data if found, error dict otherwise
        """
        id_prefix = id_prefix.lower().strip()

        findings = state.get("findings", [])
        transfers = state.get("transfers", {})

        # Search in findings (prefix match)
        for f in findings:
            fid = f.get("id", "")
            if fid and fid.lower().startswith(id_prefix):
                return f.get("data", {})

        # Search in transfers (prefix match)
        for chain, chain_transfers in transfers.items():
            for tid, transfer in chain_transfers.items():
                if tid.lower().startswith(id_prefix):
                    return transfer.model_dump() if hasattr(transfer, "model_dump") else dict(transfer)

        return {"error": f"No data found for ID prefix '{id_prefix}'"}

    return state_lookup
