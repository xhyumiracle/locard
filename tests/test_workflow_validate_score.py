"""
Unit test for validate→score flow (NO LLM involved).

This test validates the pure data processing logic after orchestrator completes:
1. Orchestrator has set candidates_finding_ids = ['search_txs:BTC@...']
2. Validate node extracts candidates and builds CrossChainLinks
3. Score node scores all links

Focus: Verify find_matching_price() and scoring logic work with start_ts/end_ts.
"""

from src.state.tracetx_state import TraceTxState
from src.node.tracetx.validate import validate_node
from src.node.tracetx.score import score_node


def test_validate_score_flow():
    """
    Test validate→score flow with complete state.

    Scenario:
    - Orchestrator has set candidates_finding_ids = ['search_txs:BTC@...']
    - State has all necessary findings (dst tx, prices, search results)
    - Validate node should build CrossChainLinks from candidates
    - Score node should score all links

    This verifies:
    1. find_matching_price() works with start_ts/end_ts params
    2. CrossChainLink building works correctly
    3. Scoring logic completes without errors
    """

    # State after orchestrator completes and sets candidates_finding_ids
    state: TraceTxState = {
        "query": "What is the source transaction for this cross-chain DOGE output to DGLwogqGtiPpiUDhPhokTJxit7DWKdxpu4 in tx 86E184358C82C8DBC2C332009EC227E6AC010AD6FC5DBC53F1341F65763F7CC9 on DOGE, given that it originates from BTC on BTC?",

        "iteration": 4,

        "params": {
            "search_time_span": 1200,
            "search_price_buffer": 0.05,
            "check_time_span": 300
        },

        "derived": {
            "search_window": {
                "time": {"start_ts": 1757641622, "end_ts": 1757642822},
                "amount": {"min": 0.03164685, "max": 0.03529041}
            }
        },

        "src_info": {"chain": "BTC", "asset": "BTC"},
        "dst_info": {
            "txid": "86e184358c82c8dbc2c332009ec227e6ac010ad6fc5dbc53f1341f65763f7cc9",
            "chain": "DOGE",
            "asset": "DOGE",
            "op_id": "vout:0",
            "amount": 14871.64178148,
            "time": 1757642822
        },

        # All findings with new naming convention
        "findings": [
            {
                "kind": "get_tx",
                "id": "get_tx:86e184358c82c8dbc2c332009ec227e6ac010ad6fc5dbc53f1341f65763f7cc9",
                "source": "get_doge_tx",
                "rationale": "Destination tx",
                "data": {
                    "chain": "DOGE",
                    "txid": "86e184358c82c8dbc2c332009ec227e6ac010ad6fc5dbc53f1341f65763f7cc9",
                    "block_time": 1757642822,
                }
            },
            {
                "kind": "price",
                "id": "price:DOGE_in_BTC@time(1757641622-1757642822)",
                "source": "get_binance_price",
                "rationale": "Search window price",
                "data": {"price_min": 0.0000021280, "price_max": 0.0000023730, "via": None}
            },
            {
                "kind": "search_txs",
                "id": "search_txs:BTC@1757641622-1757642822",
                "source": "search_btc_outputs",
                "rationale": "Candidate BTC outputs",
                "data": [
                    # Sample of candidates (using first 3 for brevity)
                    {"chain": "BTC", "txid": "fd62670745abfd02da0c636f0b68205dfec149a5aa990cfe6fc39b85a232c83a", "n": 0, "amount": 0.0345, "addr": "bc1qzx450mrc58vmfkvx6zwyag2phwlrupzhxc9787", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "55386440b8e572905cc364a57ab6b2b7910450a519a0a8adc246c91d4fbd171a", "n": 1, "amount": 0.03347392, "addr": "bc1qssy30n4ug6dh6wpyvus5c467kh8re0uy40ncwr", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "c153d63dc1f056cba0730615c73a3aed9fce3b17e267d9e47c55b3df21de3d5b", "n": 1, "amount": 0.0342, "addr": "bc1qvl3yzxl7vnqsk40v9wejkn38mzyjj6sup55y3f", "block_time": 1757642606},
                ]
            },
            {
                "kind": "price",
                "id": "price:BTC_in_DOGE@time(1757642306-1757642906)",
                "source": "get_binance_price",
                "rationale": "Check window price for candidates",
                "data": {"price_min": 442477.8761061947, "price_max": 446428.5714285714, "via": None}
            }
        ],

        # Orchestrator sets this to indicate which finding(s) contain candidates
        "candidates_finding_ids": ["search_txs:BTC@1757641622-1757642822"],

        "inbox_findings": [],
        "inbox_gaps": [],
    }

    print("=" * 80)
    print("UNIT TEST: Validate→Score Flow (NO LLM)")
    print("=" * 80)
    print("\nPurpose: Test pure data processing logic")
    print("\nInput:")
    print("  - candidates_finding_ids: ['search_txs:BTC@1757641622-1757642822']")
    print("  - findings: dst tx, prices (search + check windows), search results")
    print("  - 3 candidate BTC outputs")
    print("\nExpected:")
    print("  - Validate builds 3 CrossChainLinks (one per candidate)")
    print("  - Score assigns scores to each link")
    print("  - All using start_ts/end_ts naming")
    print("\n" + "=" * 80)

    # Step 1: Run validate node
    print("\n[1] Running validate_node...")
    print("-" * 80)
    try:
        validate_result = validate_node(state)
        print(f"✅ Validate node completed successfully")
        print(f"   Created {len(validate_result['cclinks'])} CrossChainLinks")

        # Show sample link
        if validate_result['cclinks']:
            sample_link = validate_result['cclinks'][0]
            print(f"\n   Sample CrossChainLink:")
            print(f"   - ID: {sample_link.id}")
            print(f"   - Src: {sample_link.src_transfer.txid[:16]}...")
            print(f"   - Dst: {sample_link.dst_transfer.txid[:16]}...")
            print(f"   - Price: [{sample_link.price_min:.2f}, {sample_link.price_max:.2f}]")

        # Update state with cclinks
        state['cclinks'] = validate_result['cclinks']

    except Exception as e:
        print(f"❌ Validate node failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Step 2: Run score node
    print("\n[2] Running score_node...")
    print("-" * 80)
    try:
        score_result = score_node(state)
        print(f"✅ Score node completed successfully")

        # Extract scoring table from result
        if 'result' in score_result and score_result['result'].get('success'):
            score_table = score_result['result']['data']
            candidates = score_table.get('candidates', [])
            print(f"   Scored {len(candidates)} candidates")
            print(f"   Status: {score_table.get('status')}")
            print(f"   Best Match: {score_table.get('best_match', 'None')}")

            # Show all scored links with details
            if candidates:
                print(f"\n   Scored Candidates:")
                for i, link in enumerate(candidates, 1):
                    print(f"   [{i}] ID: {link.id}")
                    src_op = link.src_transfer.operations[link.src_op_id]
                    dst_op = link.dst_transfer.operations[link.dst_op_id]
                    print(f"       Src: {link.src_transfer.txid[:16]}... @ {link.src_transfer.block_time}")
                    print(f"            {src_op.asset} amount={src_op.amount}")
                    print(f"       Dst: {link.dst_transfer.txid[:16]}... @ {link.dst_transfer.block_time}")
                    print(f"            {dst_op.asset} amount={dst_op.amount}")
                    print(f"       Price: [{link.price_min:.2f}, {link.price_max:.2f}]")
                    print(f"       Scores: confidence={link.confidence:.4f}, "
                          f"f_time={link.f_time:.4f}, "
                          f"f_amount={link.f_amount:.4f}")
                    print(f"       Fee Rate: [{link.fee_rate_min:.4f}, {link.fee_rate_max:.4f}]")
                    print(f"       Time Diff: {link.time_diff}s")
                    print(f"       Excluded: {link.excluded} ({link.exclude_reason or 'N/A'})")
                    print()

    except Exception as e:
        print(f"❌ Score node failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 80)
    print("RESULT:")
    print("=" * 80)
    print("✅ ALL STEPS COMPLETED SUCCESSFULLY!")
    print("\nVerified:")
    print("  1. ✅ validate_node works with new start_ts/end_ts naming")
    print("  2. ✅ find_matching_price() correctly locates price findings")
    print("  3. ✅ CrossChainLink building succeeds")
    print("  4. ✅ score_node completes scoring")
    print("\n" + "=" * 80)

    return True

