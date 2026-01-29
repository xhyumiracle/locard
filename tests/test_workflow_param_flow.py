"""
Test parameter flow from CLI -> State -> Subgraph.

Verifies that params correctly flow through:
1. parse_params() (CLI parsing)
2. initialize_state() (State creation)
3. Subgraph invocation (Parameter extraction)
"""

from src.main import parse_params
from src.state.tracegrouptx_state import initialize_state as initialize_tracegrouptx_state
from src.state.tracetx_state import initialize_state as initialize_tracetx_state


def test_cli_to_state_flow():
    """Test parameter flow from CLI args to state initialization."""

    print("=" * 80)
    print("Test: CLI -> State Parameter Flow")
    print("=" * 80)

    # Step 1: Simulate CLI parsing
    print("\n[Step 1] Parse CLI arguments")
    cli_args = [
        "max_hops=2",
        "min_value=1.5",
        "tracetx.search_time_offset=120",
        "tracetx.max_time_delta=7200"
    ]
    print(f"  Input: {cli_args}")

    params = parse_params(cli_args)
    print(f"  Output: {params}")

    expected_params = {
        "max_hops": 2,
        "min_value": 1.5,
        "tracetx_params": {
            "search_time_offset": 120,
            "max_time_delta": 7200
        }
    }
    assert params == expected_params, f"Expected {expected_params}, got {params}"
    print("  ✓ CLI parsing correct")

    # Step 2: Initialize TraceGroupTx state
    print("\n[Step 2] Initialize TraceGroupTx state")
    query = "Test query for BTC tx"
    tracegrouptx_state = initialize_tracegrouptx_state(query, params=params)

    state_params = tracegrouptx_state.get("params", {})
    print(f"  State params: {state_params}")

    # Verify key params are present (initialize_state adds defaults)
    assert state_params["max_hops"] == 2, f"max_hops mismatch"
    assert state_params["min_value"] == 1.5, f"min_value mismatch"
    assert state_params["tracetx_params"] == expected_params["tracetx_params"], f"tracetx_params mismatch"
    print("  ✓ TraceGroupTx state contains all user-provided params (plus defaults)")

    # Step 3: Verify TraceTx param extraction
    print("\n[Step 3] Extract TraceTx params (simulating crosschain_tracer)")
    tracetx_params = state_params.get("tracetx_params", state_params)
    print(f"  TraceTx params: {tracetx_params}")

    expected_tracetx = {
        "search_time_offset": 120,
        "max_time_delta": 7200
    }
    assert tracetx_params == expected_tracetx, f"Expected {expected_tracetx}, got {tracetx_params}"
    print("  ✓ TraceTx params correctly extracted")

    # Step 4: Initialize TraceTx state (what happens inside crosschain_tracer)
    print("\n[Step 4] Initialize TraceTx state with extracted params")
    tracetx_query = "Source of BTC output in tx ABC..."
    tracetx_state = initialize_tracetx_state(tracetx_query, params=tracetx_params)

    tracetx_state_params = tracetx_state.get("params", {})
    print(f"  TraceTx state params: {tracetx_state_params}")

    # Verify user-provided params are present
    assert tracetx_state_params["search_time_offset"] == 120, f"search_time_offset mismatch"
    print("  ✓ TraceTx state contains user-provided param (search_time_offset)")

    # Verify default params are added
    assert "check_time_span" in tracetx_state_params, "check_time_span default should be added"
    assert "search_time_span" in tracetx_state_params, "search_time_span default should be added"
    assert "search_price_buffer" in tracetx_state_params, "search_price_buffer default should be added"
    print("  ✓ TraceTx state has default params added by initialize_state()")

    # Verify TraceGroupTx params are NOT in TraceTx state
    assert "max_hops" not in tracetx_state_params, "max_hops should not be in TraceTx params"
    assert "min_value" not in tracetx_state_params, "min_value should not be in TraceTx params"
    print("  ✓ TraceGroupTx params correctly excluded from TraceTx")

    print("\n" + "=" * 80)
    print("✓ All parameter flow tests passed!")
    print("=" * 80)

    return True


def test_no_tracetx_params_fallback():
    """Test fallback behavior when tracetx_params not provided."""

    print("\n" + "=" * 80)
    print("Test: Fallback when no tracetx_params (legacy behavior)")
    print("=" * 80)

    # Old style params without tracetx_params nesting
    params = {
        "search_time_offset": 60,
        "max_time_delta": 3600
    }

    print(f"\n  Input params (no tracetx_params key): {params}")

    # Simulate crosschain_tracer extraction with fallback
    tracetx_params = params.get("tracetx_params", params)
    print(f"  Extracted tracetx_params: {tracetx_params}")

    assert tracetx_params == params, "Fallback should return full params"
    print("  ✓ Fallback correctly returns all params when tracetx_params not found")

    print("\n" + "=" * 80)
    print("✓ Fallback test passed!")
    print("=" * 80)

