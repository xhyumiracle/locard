#!/usr/bin/env python3
"""Analyzer node for TraceGroupTx subgraph (pure computation)."""

from typing import Dict, Any
from src.state.tracegrouptx_state import TraceGroupTxState
from src.tools.samechain import find_common_ancestor_addresses


def analyzer_node(state: TraceGroupTxState) -> Dict[str, Any]:
    """
    Analyzer node: Find common ancestor addresses.

    Pure computation node (no LLM):
    - Reorganize dst_to_src_mapping + ancestors_data into multipath format
    - Call find_common_ancestor_addresses tool
    - Return common_ancestors
    """

    dst_to_src = state.get("dst_to_src_mapping", {})
    ancestors_data = state.get("ancestors_data", {})

    # Reorganize data into multipath format
    multipath_data = {}
    for dst_tx, src_list in dst_to_src.items():
        multipath_data[dst_tx] = {}
        for src_tx in src_list:
            multipath_data[dst_tx][src_tx] = ancestors_data.get(src_tx, {})

    # Call find_common_ancestor_addresses tool
    try:
        common_ancestors = find_common_ancestor_addresses.invoke({
            "data": multipath_data
        })
    except Exception as e:
        return {
            "action": "fail",
            "result": {
                "success": False,
                "reason": f"Failed to analyze common ancestors: {str(e)}"
            }
        }

    return {"common_ancestors": common_ancestors}
