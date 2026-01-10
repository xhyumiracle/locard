#!/usr/bin/env python3
"""
State definition for TraceGroupTx subgraph.

TraceGroupTx workflow:
1. Orchestrator: Parse query, invoke CrossChainTracer, invoke SameChainTracer, find common ancestors
2. CrossChainTracer: Batch invoke TraceTx subgraph for each dst_transfer
3. SameChainTracer: Batch trace ancestors for all src_transfers using trace_ancestors_eth tool
"""

from typing import TypedDict, List, Dict, Any, Optional
from typing_extensions import Annotated
import operator

from src.models.core import SrcInfo


class TraceGroupTxState(TypedDict, total=False):
    """
    State for TraceGroupTx subgraph.

    Flow:
    1. User provides query with multiple dst_transfers to analyze
    2. CrossChainTracer gets src_transfer candidates for each dst_transfer
    3. SameChainTracer traces ancestors for all unique src_transfers
    4. Orchestrator finds common ancestor addresses and returns analysis
    """

    # === Input ===
    query: str                                  # User query describing dst_transfers to analyze
    src_info: SrcInfo                           # Source chain/asset information

    # === Dst Transfers (extracted by orchestrator) ===
    dst_transfers: List[Dict[str, Any]]         # List of {txid, chain, asset, recipient}
    # Format:
    # {
    #   "txid": "0x...",
    #   "chain": "BTC",
    #   "asset": "BTC",
    #   "recipient": "1vu4txGif6wES1j3fua3ecYxxTVbFFoNz"
    # }

    # === Step 1 Output: CrossChainTracer Results ===
    dst_to_src_mapping: Dict[str, List[str]]    # {dst_tx_id: [src_tx_id_list]}
    # Example:
    # {
    #   "021169_c6467df9": [
    #     "0x16f39b078a040e0426e7d00581d4f96fbeddaa94c36a227ce2de7ed101e27d2b",
    #     "0x5803cc5924d7e4fc372028fe2031d0daac56d98011ff7b4c02ffa22aea608375"
    #   ]
    # }

    crosschain_tracer_details: Dict[str, Any]   # Detailed results from TraceTx subgraphs
    # Structure:
    # {
    #   "021169_c6467df9": {
    #     "success": true,
    #     "data": {
    #       "score_table": {...},
    #       "candidates": [...]  # Non-excluded candidates
    #     }
    #   }
    # }

    samechain_task_brief: str                      # Task brief for SameChainTracer

    # === Step 2 Output: SameChainTracer Results ===
    ancestors_data: Dict[str, Dict[str, Dict[str, Any]]]  # {src_tx: {ancestor_tx: {sender, recipient, value, timestamp, hop}}}
    # Directly from trace_ancestors_eth output format

    # === Step 3 Output: Common Ancestor Analysis ===
    common_ancestors: Dict[str, Dict[str, Any]]  # {ancestor_address: {hit_count, votes}}
    # Output from find_common_ancestor_addresses tool

    # === Parameters (configurable) ===
    params: Dict[str, Any]                      # Configuration parameters
    # {
    #   # TraceGroupTx parameters
    #   "max_hops": 1,                    # For trace_ancestors_eth
    #   "min_value": 1.0,                 # Minimum ancestor value in ETH
    #   "only_larger_ancestor": false,
    #   "max_ancestor_per_hop": 0,        # 0 = no limit
    #   "max_src_per_dst": 0,             # 0 = no limit per dst_tx
    #
    #   # TraceTx parameters (nested under tracetx_params)
    #   "tracetx_params": {
    #     "search_time_offset": 50,      # Minutes offset for search window
    #     "max_time_delta": 3600         # Max time difference in seconds
    #   }
    # }

    # === Execution Tracking ===
    iteration: int                              # Current iteration (for tracking)
    action: Optional[str]                       # Current action ("crosschain", "samechain", "analyze", "done", "fail")

    # === Final Result ===
    result: Dict[str, Any]                      # Final output
    # {
    #   "success": bool,
    #   "data": {
    #     "dst_to_src_mapping": {...},
    #     "ancestors_data": {...},
    #     "common_ancestors": {...},
    #     "summary": {
    #       "total_dst_tx": 5,
    #       "total_src_tx": 34,
    #       "total_unique_src_tx": 28,
    #       "total_ancestor_addresses": 150,
    #       "top_hit_count": 5
    #     }
    #   },
    #   "reason": str  # If failed
    # }


def initialize_state(query: str, params: Optional[Dict[str, Any]] = None) -> TraceGroupTxState:
    """Initialize TraceGroupTxState from user query."""
    import config

    if params is None:
        params = {}

    return TraceGroupTxState(
        query=query,
        iteration=0,
        trajectories=[],
        findings=[],
        inbox_findings=[],
        inbox_gaps=[],
        params={
            "max_hops": params.get("max_hops", config.TRACEGROUPTX_MAX_HOPS),
            "min_value": params.get("min_value", config.TRACEGROUPTX_MIN_VALUE),
            "only_larger_ancestor": params.get("only_larger_ancestor", config.TRACEGROUPTX_ONLY_LARGER_ANCESTOR),
            "max_ancestor_per_hop": params.get("max_ancestor_per_hop", config.TRACEGROUPTX_MAX_ANCESTOR_PER_HOP),
            "max_src_per_dst": params.get("max_src_per_dst", config.TRACEGROUPTX_MAX_SRC_PER_DST),
            **params  # Allow additional params
        }
    )
