#!/usr/bin/env python3
"""
CrossChainTracer node for TraceGroupTx subgraph.

Responsibilities:
1. Batch invoke TraceTx subgraph for each dst_transfer
2. Extract src_transfer candidates from results
3. Build dst_tx -> [src_tx] mapping

Pure code node (no LLM agent).
"""

import logging
from typing import Dict, Any, List
from src.state.tracegrouptx_state import TraceGroupTxState
from src.graph import tracetx
from src.state.tracetx_state import TraceTxState, initialize_state as initialize_tracetx_state

logger = logging.getLogger(__name__)


def crosschain_tracer_node(state: TraceGroupTxState) -> Dict[str, Any]:
    """
    CrossChainTracer node: Batch invoke TraceTx subgraph.

    Input: dst_transfers (list of dst_transfer dicts)
    Output: dst_to_src_mapping, crosschain_tracer_details

    Process:
    1. For each dst_transfer:
       - Build query string for TraceTx subgraph
       - Invoke TraceTx subgraph
       - Extract non-excluded candidates
       - Extract src_txids
    2. Build mapping: {dst_tx_id: [src_tx_id_list]}
    """

    dst_transfers = state.get("dst_transfers", [])

    if not dst_transfers:
        raise ValueError("No dst_transfers provided to CrossChainTracer")

    # Get TraceTx subgraph
    tracetx_graph = tracetx.create_graph()

    dst_to_src_mapping = {}
    crosschain_tracer_details = {}


    for dst_transfer in dst_transfers:
        # Generate unique dst_tx_id (for mapping key)
        dst_tx_id = _generate_dst_tx_id(dst_transfer)

        # Build query for TraceTx subgraph
        # Get src_info from state
        src_info = state.get("src_info")
        if not src_info:
            raise ValueError("src_info not provided in state")

        src_chain = src_info.chain
        src_asset = src_info.asset

        query = _build_tracetx_query(dst_transfer, src_chain, src_asset)

        logger.debug(f"CrossChainTracer: Processing dst_tx_id={dst_tx_id}")
        logger.debug(f"  Query: {query}")

        # Initialize TraceTx state using initialize_state() to ensure defaults
        # Extract tracetx_params if provided, otherwise pass all params
        params = state.get("params", {})
        tracetx_params = params.get("tracetx_params", params)

        # Use initialize_state() to properly set defaults for params
        tracetx_state = initialize_tracetx_state(query, params=tracetx_params)

        # Invoke TraceTx subgraph
        result_state = tracetx_graph.invoke(tracetx_state)
        result = result_state.get("result", {})

        if not result.get("success"):
            # TraceTx failed for this dst_transfer
            crosschain_tracer_details[dst_tx_id] = {
                "success": False,
                "reason": result.get("reason", "Unknown error")
            }
            dst_to_src_mapping[dst_tx_id] = []
            continue

        # Extract candidates from score_table (ScoreTable is a dataclass)
        score_table = result.get("data")
        if not score_table:
            # No score_table in result
            crosschain_tracer_details[dst_tx_id] = {
                "success": False,
                "reason": "No score_table in TraceTx result"
            }
            dst_to_src_mapping[dst_tx_id] = []
            continue

        candidates = score_table.candidates  # Direct attribute access

        # Filter non-excluded candidates (CrossChainLink is a dataclass)
        valid_candidates = [c for c in candidates if not c.excluded]

        logger.info(f"CrossChainTracer: dst_tx_id={dst_tx_id}, valid_candidates={len(valid_candidates)}/{len(candidates)}")

        # Apply max_src_per_dst limit if specified
        max_src_per_dst = state.get("params", {}).get("max_src_per_dst", 0)
        if max_src_per_dst > 0 and len(valid_candidates) > max_src_per_dst:
            logger.info(f"  Limiting to top {max_src_per_dst} candidates (max_src_per_dst={max_src_per_dst})")
            valid_candidates = valid_candidates[:max_src_per_dst]

        # Extract src_txids (CrossChainLink and Transfer are dataclasses)
        src_txids = []
        for candidate in valid_candidates:
            src_txid = candidate.src_transfer.txid
            if src_txid:
                src_txids.append(src_txid)

        logger.info(f"  Extracted {len(src_txids)} src_txids")
        if len(src_txids) > 0:
            logger.debug(f"  src_txids: {src_txids[:5]}{'...' if len(src_txids) > 5 else ''}")

        # Store results
        dst_to_src_mapping[dst_tx_id] = src_txids
        crosschain_tracer_details[dst_tx_id] = {
            "success": True,
            "data": {
                "score_table": score_table,
                "candidates": valid_candidates,
                "total_candidates": len(candidates),
                "valid_candidates": len(valid_candidates)
            }
        }

    return {
        "dst_to_src_mapping": dst_to_src_mapping,
        "crosschain_tracer_details": crosschain_tracer_details
    }


def _generate_dst_tx_id(dst_transfer: Dict[str, Any]) -> str:
    """
    Generate unique dst_tx_id from dst_transfer.

    Format: "{txid}:recipient_{addr_suffix}" to uniquely identify a specific output.
    Uses last 8 chars of address for brevity.
    """
    txid = dst_transfer.get("txid", "")
    recipient = dst_transfer.get("recipient", "")
    # Use last 8 chars of address for brevity
    addr_suffix = recipient[-8:] if len(recipient) > 8 else recipient
    return f"{txid}:recipient_{addr_suffix}"


def _build_tracetx_query(
    dst_transfer: Dict[str, Any],
    src_chain: str,
    src_asset: str
) -> str:
    """
    Build TraceTx query string from dst_transfer.
    """
    dst_chain = dst_transfer.get("chain", "")
    dst_asset = dst_transfer.get("asset", "")
    dst_txid = dst_transfer.get("txid", "")
    recipient = dst_transfer.get("recipient", "")

    query = (
        f"What is the source transaction for this cross-chain {dst_asset} output "
        f"to {recipient} in tx {dst_txid} on {dst_chain}, "
        f"given that it originates from {src_asset} on {src_chain}?"
    )

    return query
