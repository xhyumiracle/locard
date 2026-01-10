#!/usr/bin/env python3
"""Format result node for TraceGroupTx subgraph (pure computation)."""

import logging
from typing import Dict, Any
from src.state.tracegrouptx_state import TraceGroupTxState

logger = logging.getLogger(__name__)


def format_result_node(state: TraceGroupTxState) -> Dict[str, Any]:
    """
    Format result node: Add formatted_data to result for ReportAgent.

    Pure computation node (no LLM):
    - Read result.data dict
    - Format it into human-readable string
    - Add formatted_data field to result
    """
    result = state.get("result", {})
    if not result.get("success"):
        # Failure case, no formatting needed
        return {}

    data = result.get("data", {})
    summary = data.get("summary", {})
    dst_to_src = data.get("dst_to_src_mapping", {})
    common_ancestors = data.get("common_ancestors", {})
    ancestors_data = data.get("ancestors_data", {})

    # Get crosschain_tracer_details for complete candidate information
    crosschain_details = state.get("crosschain_tracer_details", {})

    # Build CommonAncestor index (CA-1, CA-2, ...) for hit_count > 1
    ca_index = {}
    ca_candidates = [(addr, info) for addr, info in common_ancestors.items() if info.get("hit_count", 0) > 1]
    ca_candidates.sort(key=lambda x: x[1].get("hit_count", 0), reverse=True)
    for i, (addr, _) in enumerate(ca_candidates, 1):
        ca_index[addr] = f"CA-{i}"

    formatted_lines = []

    # ========== Part 1: Crosschain Tracking ==========
    formatted_lines.append(f"Crosschain Tracking ({len(dst_to_src)} dst txs):")

    for dst_tx_id in dst_to_src.keys():
        # Get candidate details
        details = crosschain_details.get(dst_tx_id, {})
        if not details.get("success"):
            formatted_lines.append(f"- DstTx {dst_tx_id}: [Failed]")
            continue

        candidates = details.get("data", {}).get("candidates", [])
        if not candidates:
            formatted_lines.append(f"- DstTx {dst_tx_id}: [No candidates]")
            continue

        # Get dst_transfer from first candidate (all have same dst_transfer)
        dst_transfer = candidates[0].dst_transfer
        dst_chain = dst_transfer.chain
        dst_txid = dst_transfer.txid

        # Get dst operation details from the crosschain operation
        # Use first candidate since all candidates share same dst_transfer
        candidate = candidates[0]
        dst_op_id = candidate.dst_op_id
        dst_op = dst_transfer.operations.get(dst_op_id)
        if not dst_op:
            # Fallback: find first vout
            for op_id, op in dst_transfer.operations.items():
                if op_id.startswith("vout:"):
                    dst_op_id = op_id
                    dst_op = op
                    break

        dst_recipient = dst_op.account.address if (dst_op and dst_op.account) else "N/A"
        dst_value = dst_op.amount if dst_op else "N/A"
        dst_asset = dst_op.asset if dst_op else "N/A"
        dst_timestamp = dst_transfer.block_time

        # For account-based chains (ETH), get sender from corresponding vin operation
        # dst_op_id is vout:i, find corresponding vin:i
        dst_from = None
        if dst_transfer.type == "account" and dst_op_id.startswith("vout:"):
            vout_index = dst_op_id.split(":")[1]
            vin_op_id = f"vin:{vout_index}"
            vin_op = dst_transfer.operations.get(vin_op_id)
            if vin_op and vin_op.account:
                dst_from = vin_op.account.address

        formatted_lines.append(f"- DstTx: [{dst_chain}] {dst_txid}")
        formatted_lines.append(f"    Operation: {dst_op_id}")
        if dst_from:
            formatted_lines.append(f"    From: {dst_from}  # Crosschain Endpoint")
        if dst_recipient and dst_recipient != "N/A":
            formatted_lines.append(f"    Recipient: {dst_recipient}  # Crosschain Recipient")
        formatted_lines.append(f"    Value: {dst_value} {dst_asset}")
        formatted_lines.append(f"    Timestamp: {dst_timestamp}")

        # SourceCandidates
        formatted_lines.append(f"    SourceCandidates ({len(candidates)} candidates):")

        for candidate in candidates:
            src_transfer = candidate.src_transfer
            src_op_id = candidate.src_op_id
            src_chain = src_transfer.chain
            src_txid = src_transfer.txid
            src_timestamp = src_transfer.block_time

            # Get src operation details from the crosschain operation
            src_op = src_transfer.operations.get(src_op_id)
            if not src_op:
                # Fallback: shouldn't happen but handle gracefully
                continue

            src_from = None
            src_to = src_op.account.address if src_op.account else "N/A"
            src_value = src_op.amount
            src_asset = src_op.asset

            # For account-based chains (ETH), get sender from corresponding vin operation
            # src_op_id is vout:i, find corresponding vin:i
            if src_transfer.type == "account" and src_op_id.startswith("vout:"):
                vout_index = src_op_id.split(":")[1]
                vin_op_id = f"vin:{vout_index}"
                vin_op = src_transfer.operations.get(vin_op_id)
                if vin_op and vin_op.account:
                    src_from = vin_op.account.address

            formatted_lines.append(f"      - SrcTx: [{src_chain}] {src_txid}")
            if src_from:
                formatted_lines.append(f"          From: {src_from}  # Crosschain Sender")
            if src_to and src_to != "N/A":
                formatted_lines.append(f"          To: {src_to}  # Crosschain Endpoint")
            formatted_lines.append(f"          Value: {src_value} {src_asset}")
            formatted_lines.append(f"          Timestamp: {src_timestamp}")

            # ParentPaths - Each ancestor is a separate path (currently all hop 1)
            src_ancestors = ancestors_data.get(src_txid, {})
            if src_ancestors:
                formatted_lines.append(f"          ParentPaths [{src_chain}]:")

                # Sort ancestors by value descending
                sorted_ancestors = sorted(
                    src_ancestors.items(),
                    key=lambda x: x[1].get("value", 0),
                    reverse=True
                )

                # Each ancestor is a separate path
                for path_num, (anc_tx, anc_info) in enumerate(sorted_ancestors, 1):
                    formatted_lines.append(f"            - Path {path_num}:")

                    hop = anc_info.get("hop", 1)
                    anc_sender = anc_info.get("sender", "N/A")
                    anc_recipient = anc_info.get("recipient", "N/A")
                    anc_value = anc_info.get("value", "N/A")
                    anc_timestamp = anc_info.get("timestamp", "N/A")

                    # Check if this sender is a common ancestor
                    ca_label = ""
                    if anc_sender in ca_index:
                        ca_label = f" # CommonAncestor {ca_index[anc_sender]}"

                    formatted_lines.append(f"                - Hop {hop} Tx: {anc_tx}")
                    formatted_lines.append(f"                  From: {anc_sender}{ca_label}")
                    formatted_lines.append(f"                  To: {anc_recipient}")
                    formatted_lines.append(f"                  Value: {anc_value} {src_asset}")
                    formatted_lines.append(f"                  Timestamp: {anc_timestamp}")

    formatted_lines.append("")

    # ========== Part 2: Common Ancestor Candidates ==========
    if ca_candidates:
        formatted_lines.append(f"Common Ancestor Candidates ({len(ca_candidates)} found):")
        for addr, info in ca_candidates:
            ca_label = ca_index[addr]
            hit_count = info.get("hit_count", 0)
            votes = info.get("votes", {})

            formatted_lines.append(f"  - CommonAncestor {ca_label} ([ETH] {addr})")
            formatted_lines.append(f"      Hit count (dst tx): {hit_count}")

            # Calculate min hop for each dst_tx that contains this ancestor
            appears_in = []
            for dst_tx_id, src_dict in votes.items():
                min_hop = float('inf')
                for src_tx, anc_txs in src_dict.items():
                    for anc_tx in anc_txs:
                        # Get hop from ancestors_data
                        anc_info = ancestors_data.get(src_tx, {}).get(anc_tx, {})
                        hop = anc_info.get("hop", float('inf'))
                        if hop < min_hop:
                            min_hop = hop

                if min_hop != float('inf'):
                    appears_in.append(f"DstTx {dst_tx_id} (min hop = {min_hop})")

            if appears_in:
                formatted_lines.append(f"      Appears in:")
                for item in appears_in:
                    formatted_lines.append(f"        - {item}")
    else:
        formatted_lines.append("Common Ancestor Candidates: None found (hit_count > 1)")

    formatted_lines.append("")

    # ========== Part 3: Summary ==========
    formatted_lines.append("Summary:")
    formatted_lines.append(f"  Total destination transactions: {summary.get('total_dst_tx', 0)}")
    formatted_lines.append(f"  Total source transactions: {summary.get('total_unique_src_tx', 0)}")
    formatted_lines.append(f"  Common ancestors (hit_count > 1): {len(ca_candidates)}")
    formatted_lines.append(f"  Total ancestor addresses: {summary.get('total_ancestor_addresses', 0)}")

    # Update result with formatted_data
    formatted_output = "\n".join(formatted_lines)
    result["formatted_data"] = formatted_output

    # Log formatted output for debugging
    logger.debug(f"TraceGroupTx result:\n{formatted_output}")

    return {"result": result}
