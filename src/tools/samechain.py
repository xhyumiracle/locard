#!/usr/bin/env python3
"""
Same-chain analysis tools for finding common ancestors and patterns.
Pure local computation, no API calls.
"""

from typing import Dict, Set, List
from langchain_core.tools import tool


@tool
def find_common_ancestors(ancestors_data: dict) -> dict:
    """
    Find common ancestors from trace_ancestors_eth output. Pure local computation.

    Args:
        ancestors_data: Output from trace_ancestors_eth (dict of src_tx -> ancestor set)

    Returns:
        {ancestor_tx: hit_count} sorted by hit_count descending.
        Each src_tx votes once per ancestor, so max hit_count = number of src_txs.
    """
    if not ancestors_data:
        return {}

    # Count how many source transactions each ancestor appears in
    # Each src_tx can only vote once per ancestor (even if ancestor appears multiple times)
    ancestor_votes: Dict[str, Set[str]] = {}  # ancestor_tx -> set of src_txs that have it

    for src_tx, ancestors in ancestors_data.items():
        # Normalize src_tx hash
        src_tx_lower = src_tx.lower()

        # Each ancestor in this src_tx's set gets one vote
        for ancestor_tx in ancestors.keys():
            ancestor_tx_lower = ancestor_tx.lower()

            if ancestor_tx_lower not in ancestor_votes:
                ancestor_votes[ancestor_tx_lower] = set()

            # Add this src_tx's vote for this ancestor
            ancestor_votes[ancestor_tx_lower].add(src_tx_lower)

    # Convert to hit counts
    candidates = {
        ancestor_tx: len(voting_src_txs)
        for ancestor_tx, voting_src_txs in ancestor_votes.items()
    }

    # Sort by hit_count descending
    candidates_sorted = dict(sorted(
        candidates.items(),
        key=lambda x: x[1],
        reverse=True
    ))

    return candidates_sorted


@tool
def find_common_ancestor_addresses(data: dict) -> dict:
    """
    Find common ancestor addresses across confirmed dst_tx nodes with path tracking.
    Votes by ancestor sender ADDRESS (not tx hash). Pure local computation.

    Args:
        data: {
            dst_tx: {
                src_tx: {
                    ancestor_tx: {
                        "sender": "0x...",
                        "recipient": "0x...",
                        "value": 100.5,
                        "timestamp": 1234567890,
                        "hop": 1
                    }
                }
            }
        }

    Returns:
        {
            ancestor_sender_address: {
                "hit_count": int,  # Number of dst_tx that voted for this address
                "votes": {
                    dst_tx: {
                        src_tx: [anc_tx1, anc_tx2, ...]  # Ancestor txs with this sender
                    }
                }
            }
        }
        Sorted by hit_count descending.

    Example:
        Input: {
            "dst_tx1": {
                "src_tx_a": {
                    "anc_tx_1": {"sender": "0xAAA", ...},
                    "anc_tx_2": {"sender": "0xAAA", ...},
                    "anc_tx_3": {"sender": "0xBBB", ...}
                },
                "src_tx_b": {
                    "anc_tx_4": {"sender": "0xAAA", ...}
                }
            }
        }
        Output: {
            "0xaaa": {
                "hit_count": 1,
                "votes": {
                    "dst_tx1": {
                        "src_tx_a": ["anc_tx_1", "anc_tx_2"],
                        "src_tx_b": ["anc_tx_4"]
                    }
                }
            }
        }
    """
    if not data:
        return {}

    # Step 1: For each dst_tx, collect unique ancestor addresses and track paths
    # dst_ancestors: {dst_tx: {ancestor_address: {src_tx: [anc_tx_list]}}}
    dst_ancestors: Dict[str, Dict[str, Dict[str, List[str]]]] = {}

    for dst_tx, src_dict in data.items():
        dst_tx_lower = dst_tx.lower()
        dst_ancestors[dst_tx_lower] = {}

        for src_tx, ancestors in src_dict.items():
            src_tx_lower = src_tx.lower()

            for anc_tx, anc_info in ancestors.items():
                anc_tx_lower = anc_tx.lower()

                # Get ancestor sender address (normalized)
                anc_sender = anc_info.get("sender", "").lower()
                if not anc_sender:
                    continue

                # Initialize nested dicts if needed
                if anc_sender not in dst_ancestors[dst_tx_lower]:
                    dst_ancestors[dst_tx_lower][anc_sender] = {}

                if src_tx_lower not in dst_ancestors[dst_tx_lower][anc_sender]:
                    dst_ancestors[dst_tx_lower][anc_sender][src_tx_lower] = []

                # Track which ancestor tx has this sender
                dst_ancestors[dst_tx_lower][anc_sender][src_tx_lower].append(anc_tx_lower)

    # Step 2: Count votes - each dst_tx votes once per unique ancestor address
    address_votes: Dict[str, dict] = {}

    for dst_tx, address_paths in dst_ancestors.items():
        for anc_address, src_paths in address_paths.items():
            if anc_address not in address_votes:
                address_votes[anc_address] = {"hit_count": 0, "votes": {}}

            # Each dst_tx contributes 1 vote to this address
            address_votes[anc_address]["hit_count"] += 1
            address_votes[anc_address]["votes"][dst_tx] = src_paths

    # Sort by hit_count descending
    return dict(sorted(
        address_votes.items(),
        key=lambda x: x[1]["hit_count"],
        reverse=True
    ))
