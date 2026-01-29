"""
Unit test for format_result_node function.

Tests the formatting logic without executing the full subgraph.
Uses mock data structure to verify the output format.
"""

from src.node.tracegrouptx.format_result import format_result_node
from src.state.tracegrouptx_state import TraceGroupTxState
from src.models.core import Transfer, Operation, AccountIdentifier, CrossChainLink
from src.node.tracetx.score import ScoreTable, ScoringParams


def create_mock_state() -> TraceGroupTxState:
    """
    Create mock TraceGroupTxState with all necessary data for format_result_node.

    Mock scenario:
    - 2 dst transactions (BTC)
    - Each has 2 src candidates (ETH)
    - 3 src transactions have ancestor paths
    - 2 common ancestors with hit_count > 1
    """

    # ========== Mock dst_to_src_mapping ==========
    dst_to_src_mapping = {
        "012F9B_c6467df9": [
            "0x16f39b078a040e0426e7d00581d4f96fbeddaa94c36a227ce2de7ed101e27d2b",
            "0x0c19374207c7a00d834c77c615bb1edc4a5503a06a517692db71d34068a90316"
        ],
        "11BF94_e1aSCQ7i": [
            "0x16f39b078a040e0426e7d00581d4f96fbeddaa94c36a227ce2de7ed101e27d2b",  # Overlapping
            "0x067c965f56d25d83713c19b57955e5b6b26f535fdddf99aea7c7ffad7ccb8faa"
        ]
    }

    # ========== Mock crosschain_tracer_details ==========
    # Create realistic Transfer and CrossChainLink objects

    # Dst Transfer 1
    dst_transfer_1 = Transfer(
        txid="012F9B5C839DE8B17EB1E1911F3F212A9918546D8044EA701CD2CC1E442BAD13",
        chain="BTC",
        type="utxo",
        block_time=1740832156,
        operations={
            "vout:0": Operation(
                op_id="vout:0",
                account=AccountIdentifier(address="1vu4txGif6wES1j3fua3ecYxxTVbFFoNz"),
                amount=0.89767266,
                asset="BTC",
                decimals=8
            )
        }
    )

    # Src Transfer 1-1 (account-based)
    src_transfer_1_1 = Transfer(
        txid="0x16f39b078a040e0426e7d00581d4f96fbeddaa94c36a227ce2de7ed101e27d2b",
        chain="ETH",
        type="account",
        block_time=1740828500,
        operations={
            "vin:0": Operation(
                op_id="vin:0",
                account=AccountIdentifier(address="0xaaaa1111bbbb2222cccc3333dddd4444eeee5555"),
                amount=-35.5,
                asset="ETH",
                decimals=18
            ),
            "vout:0": Operation(
                op_id="vout:0",
                account=AccountIdentifier(address="0xbbbb2222cccc3333dddd4444eeee5555ffff6666"),
                amount=35.0,
                asset="ETH",
                decimals=18
            )
        }
    )

    # Src Transfer 1-2 (account-based)
    src_transfer_1_2 = Transfer(
        txid="0x0c19374207c7a00d834c77c615bb1edc4a5503a06a517692db71d34068a90316",
        chain="ETH",
        type="account",
        block_time=1740828600,
        operations={
            "vin:0": Operation(
                op_id="vin:0",
                account=AccountIdentifier(address="0xcccc3333dddd4444eeee5555ffff6666aaaa7777"),
                amount=-40.2,
                asset="ETH",
                decimals=18
            ),
            "vout:0": Operation(
                op_id="vout:0",
                account=AccountIdentifier(address="0xdddd4444eeee5555ffff6666aaaa7777bbbb8888"),
                amount=40.0,
                asset="ETH",
                decimals=18
            )
        }
    )

    # Candidates for dst_transfer_1
    candidates_1 = [
        CrossChainLink(
            id="link_1_1",
            src_transfer=src_transfer_1_1,
            src_op_id="vout:0",
            dst_transfer=dst_transfer_1,
            dst_op_id="vout:0",
            price_min=38.5,
            price_max=39.2,
            time_diff=3656,
            fee_rate_min=0.01,
            fee_rate_max=0.02,
            excluded=False,
            exclude_reason=None,
            f_time=0.95,
            f_amount=0.92,
            confidence=0.93
        ),
        CrossChainLink(
            id="link_1_2",
            src_transfer=src_transfer_1_2,
            src_op_id="vout:0",
            dst_transfer=dst_transfer_1,
            dst_op_id="vout:0",
            price_min=38.5,
            price_max=39.2,
            time_diff=3556,
            fee_rate_min=0.01,
            fee_rate_max=0.02,
            excluded=False,
            exclude_reason=None,
            f_time=0.90,
            f_amount=0.88,
            confidence=0.89
        )
    ]

    # Dst Transfer 2
    dst_transfer_2 = Transfer(
        txid="11BF94A5B710389F25B7060CB53BEA8C27E232FA44D344F0B5CBEF0B46E37EF5",
        chain="BTC",
        type="utxo",
        block_time=1740833200,
        operations={
            "vout:0": Operation(
                op_id="vout:0",
                account=AccountIdentifier(address="1Ff1tKE1aSCQ7irWqDjCeRFysQVYkwM6YQ"),
                amount=1.25,
                asset="BTC",
                decimals=8
            )
        }
    )

    # Src Transfer 2-2 (reuse 1-1 for overlap)
    src_transfer_2_2 = Transfer(
        txid="0x067c965f56d25d83713c19b57955e5b6b26f535fdddf99aea7c7ffad7ccb8faa",
        chain="ETH",
        type="account",
        block_time=1740829000,
        operations={
            "vin:0": Operation(
                op_id="vin:0",
                account=AccountIdentifier(address="0xeeee5555ffff6666aaaa7777bbbb8888cccc9999"),
                amount=-50.8,
                asset="ETH",
                decimals=18
            ),
            "vout:0": Operation(
                op_id="vout:0",
                account=AccountIdentifier(address="0xffff6666aaaa7777bbbb8888cccc9999ddddaaaa"),
                amount=50.0,
                asset="ETH",
                decimals=18
            )
        }
    )

    # Candidates for dst_transfer_2
    candidates_2 = [
        CrossChainLink(
            id="link_2_1",
            src_transfer=src_transfer_1_1,  # Reuse for overlap
            src_op_id="vout:0",
            dst_transfer=dst_transfer_2,
            dst_op_id="vout:0",
            price_min=38.5,
            price_max=39.2,
            time_diff=4700,
            fee_rate_min=0.01,
            fee_rate_max=0.02,
            excluded=False,
            exclude_reason=None,
            f_time=0.88,
            f_amount=0.85,
            confidence=0.86
        ),
        CrossChainLink(
            id="link_2_2",
            src_transfer=src_transfer_2_2,
            src_op_id="vout:0",
            dst_transfer=dst_transfer_2,
            dst_op_id="vout:0",
            price_min=38.5,
            price_max=39.2,
            time_diff=4200,
            fee_rate_min=0.01,
            fee_rate_max=0.02,
            excluded=False,
            exclude_reason=None,
            f_time=0.82,
            f_amount=0.80,
            confidence=0.81
        )
    ]

    # Build crosschain_tracer_details
    scoring_params = ScoringParams(
        tau_time=600,
        w_time=0.3,
        w_amount=0.7,
        max_fee_rate=0.05,
        max_deviation_rate=0.03
    )

    score_table_1 = ScoreTable(
        status="SUCCESS",
        params=scoring_params,
        candidates=candidates_1,
        best_match=candidates_1[0].id,
        summary="Found 2 candidates"
    )

    score_table_2 = ScoreTable(
        status="SUCCESS",
        params=scoring_params,
        candidates=candidates_2,
        best_match=candidates_2[0].id,
        summary="Found 2 candidates"
    )

    crosschain_tracer_details = {
        "012F9B_c6467df9": {
            "success": True,
            "data": {
                "score_table": score_table_1,
                "candidates": candidates_1
            }
        },
        "11BF94_e1aSCQ7i": {
            "success": True,
            "data": {
                "score_table": score_table_2,
                "candidates": candidates_2
            }
        }
    }

    # ========== Mock ancestors_data ==========
    # 所有 ancestors 都是 hop 1（当前数据限制）
    ancestors_data = {
        "0x16f39b078a040e0426e7d00581d4f96fbeddaa94c36a227ce2de7ed101e27d2b": {
            "0x1111111111111111111111111111111111111111111111111111111111111111": {
                "sender": "0xdddd9999eeee8888ffff7777aaaa6666bbbb5555",  # Not a CA
                "recipient": "0xaaaa1111bbbb2222cccc3333dddd4444eeee5555",
                "value": 40.5,
                "timestamp": 1740827000,
                "hop": 1
            },
            "0x2222222222222222222222222222222222222222222222222222222222222222": {
                "sender": "0xf7858da8c8a76e43892fb6a6b85b6c3e1234",  # CA-1 at hop 1
                "recipient": "0xdddd9999eeee8888ffff7777aaaa6666bbbb5555",
                "value": 50.0,
                "timestamp": 1740826000,
                "hop": 1
            },
            "0x3333333333333333333333333333333333333333333333333333333333333333": {
                "sender": "0xeb79f3b9c2d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8",  # CA-2 at hop 1
                "recipient": "0xf7858da8c8a76e43892fb6a6b85b6c3e1234",
                "value": 60.0,
                "timestamp": 1740825000,
                "hop": 1
            }
        },
        "0x0c19374207c7a00d834c77c615bb1edc4a5503a06a517692db71d34068a90316": {
            "0x3333333333333333333333333333333333333333333333333333333333333333": {
                "sender": "0xf7858da8c8a76e43892fb6a6b85b6c3e1234",  # CA-1 (appears again)
                "recipient": "0xcccc3333dddd4444eeee5555ffff6666aaaa7777",
                "value": 45.2,
                "timestamp": 1740827100,
                "hop": 1
            }
        },
        "0x067c965f56d25d83713c19b57955e5b6b26f535fdddf99aea7c7ffad7ccb8faa": {
            "0x4444444444444444444444444444444444444444444444444444444444444444": {
                "sender": "0xeb79f3b9c2d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8",  # CA-2 (appears again)
                "recipient": "0xeeee5555ffff6666aaaa7777bbbb8888cccc9999",
                "value": 55.0,
                "timestamp": 1740827500,
                "hop": 1
            }
        }
    }

    # ========== Mock common_ancestors ==========
    # CA-1: appears in both dst_txs (hit_count=2), min hop = 2 for first dst, 1 for second dst
    # CA-2: appears in both dst_txs (hit_count=2), min hop = 2 for first dst, 1 for second dst
    common_ancestors = {
        "0xf7858da8c8a76e43892fb6a6b85b6c3e1234": {
            "hit_count": 2,
            "votes": {
                "012F9B_c6467df9": {
                    "0x16f39b078a040e0426e7d00581d4f96fbeddaa94c36a227ce2de7ed101e27d2b": [
                        "0x2222222222222222222222222222222222222222222222222222222222222222"  # hop 2
                    ],
                    "0x0c19374207c7a00d834c77c615bb1edc4a5503a06a517692db71d34068a90316": [
                        "0x3333333333333333333333333333333333333333333333333333333333333333"  # hop 1
                    ]
                },
                "11BF94_e1aSCQ7i": {
                    "0x16f39b078a040e0426e7d00581d4f96fbeddaa94c36a227ce2de7ed101e27d2b": [
                        "0x2222222222222222222222222222222222222222222222222222222222222222"  # hop 2
                    ]
                }
            }
        },
        "0xeb79f3b9c2d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8": {
            "hit_count": 2,
            "votes": {
                "012F9B_c6467df9": {
                    "0x16f39b078a040e0426e7d00581d4f96fbeddaa94c36a227ce2de7ed101e27d2b": [
                        "0x3333333333333333333333333333333333333333333333333333333333333333"  # hop 2
                    ]
                },
                "11BF94_e1aSCQ7i": {
                    "0x067c965f56d25d83713c19b57955e5b6b26f535fdddf99aea7c7ffad7ccb8faa": [
                        "0x4444444444444444444444444444444444444444444444444444444444444444"  # hop 1
                    ]
                }
            }
        }
    }

    # ========== Mock result with summary ==========
    result = {
        "success": True,
        "data": {
            "dst_to_src_mapping": dst_to_src_mapping,
            "ancestors_data": ancestors_data,
            "common_ancestors": common_ancestors,
            "summary": {
                "total_dst_tx": 2,
                "total_src_tx": 4,
                "total_unique_src_tx": 3,
                "total_ancestor_addresses": 2,
                "top_hit_count": 2
            }
        }
    }

    # ========== Build state ==========
    state = TraceGroupTxState(
        query="Test query",
        iteration=5,
        action="done",
        dst_to_src_mapping=dst_to_src_mapping,
        crosschain_tracer_details=crosschain_tracer_details,
        ancestors_data=ancestors_data,
        common_ancestors=common_ancestors,
        result=result
    )

    return state


def test_format_result_node():
    """Test format_result_node with mock data."""

    print("=" * 80)
    print("Test: format_result_node")
    print("=" * 80)

    # Create mock state
    state = create_mock_state()

    print("\n[Input State]")
    print(f"  dst_to_src_mapping: {len(state['dst_to_src_mapping'])} dst txs")
    print(f"  crosschain_tracer_details: {len(state['crosschain_tracer_details'])} entries")
    print(f"  ancestors_data: {len(state['ancestors_data'])} src txs")
    print(f"  common_ancestors: {len(state['common_ancestors'])} addresses")

    # Call format_result_node
    print("\n[Calling format_result_node...]")
    updates = format_result_node(state)

    # Check result
    assert "result" in updates
    result = updates["result"]
    assert result.get("success") == True
    assert "formatted_data" in result

    formatted_output = result["formatted_data"]

    print("\n[Formatted Output]")
    print("-" * 80)
    print(formatted_output)
    print("-" * 80)

    # Verify output structure
    print("\n[Verification]")

    # Check Part 1: Crosschain Tracking
    assert "Crosschain Tracking (2 dst txs):" in formatted_output
    assert "- DstTx: [BTC]" in formatted_output
    assert "Operation: vout:0" in formatted_output
    assert "Recipient:" in formatted_output
    assert "Value:" in formatted_output
    assert "Timestamp:" in formatted_output
    assert "SourceCandidates (2 candidates):" in formatted_output
    assert "- SrcTx: [ETH]" in formatted_output
    assert "From:" in formatted_output
    assert "To:" in formatted_output
    assert "ParentPaths [ETH]:" in formatted_output
    assert "- Path 1:" in formatted_output
    assert "- Hop 1 Tx:" in formatted_output
    print("  ✓ Part 1: Crosschain Tracking format correct")

    # Check Part 2: Common Ancestor Candidates
    assert "Common Ancestor Candidates (2 found):" in formatted_output
    assert "- CommonAncestor CA-1" in formatted_output
    assert "- CommonAncestor CA-2" in formatted_output
    assert "Hit count (dst tx): 2" in formatted_output
    assert "Appears in:" in formatted_output
    assert "min hop = 1" in formatted_output or "min hop = 2" in formatted_output
    print("  ✓ Part 2: Common Ancestor Candidates format correct")

    # Check CA labels in AncestorPath
    assert "# CommonAncestor CA-1" in formatted_output or "# CommonAncestor CA-2" in formatted_output
    print("  ✓ CA labels appear in AncestorPath")

    # Check Part 3: Summary
    assert "Summary:" in formatted_output
    assert "Total destination transactions: 2" in formatted_output
    assert "Total source transactions: 3" in formatted_output
    assert "Common ancestors (hit_count > 1): 2" in formatted_output
    assert "Total ancestor addresses: 2" in formatted_output
    print("  ✓ Part 3: Summary format correct")

    print("\n" + "=" * 80)
    print("✓ Test passed! format_result_node works correctly.")
    print("=" * 80)

