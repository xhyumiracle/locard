"""
Test orchestrator's handling of empty findings + gaps scenario.

This tests that when fetcher returns findings=[] and gaps=[...],
the orchestrator correctly builds context and can respond appropriately.
"""

from src.agents.tracetx.orchestrator import TraceOrchestratorAgent
from src.state.tracetx_state import initialize_state


def test_gaps_only_context():
    """Test that orchestrator can handle empty findings + gaps without crashing."""

    # Create initial state
    state = initialize_state(
        query="What is the source transaction for this cross-chain DOGE output to "
              "DSApQxXJZjg1yNm5WWFY43kgDAJj5BUELq in tx "
              "0FEEDE57F16E47D999C0C806DFB3E1E31C4D1F2DEED4F60BA13E11EEAB4A0AD3 on DOGE, "
              "given that it originates from BTC on BTC?"
    )

    # Simulate fetcher returning empty findings + gap
    state["inbox_findings"] = []
    state["inbox_gaps"] = [
        "TOOL_FAILED: Client error '400 Bad Request' for url '...'"
    ]
    state["pending_trajectory"] = {
        "action": "fetch",
        "task_brief": "Fetch DOGE transaction 0FEEDE57F16E47D999C0C806DFB3E1E31C4D1F2DEED4F60BA13E11EEAB4A0AD3",
        "findings_ref": []
    }

    print("\n" + "=" * 80)
    print("Test: Orchestrator handling empty findings + gaps")
    print("=" * 80)

    orchestrator = TraceOrchestratorAgent()

    # Should NOT crash when building messages with empty findings + gaps
    try:
        messages = orchestrator._build_messages(state)
        print(f"\n✅ Successfully built {len(messages)} messages")

        # Check that Latest Feedback message exists and is properly formatted
        latest_feedback = None
        for msg in messages:
            content = getattr(msg, 'content', '')
            # Make sure it's the Latest Feedback section, not just contains the text
            if content.startswith('[Latest Feedback]'):
                latest_feedback = content
                break

        assert latest_feedback is not None, "Should have [Latest Feedback] message"
        print(f"\n[Latest Feedback] message:\n{latest_feedback}")

        # Verify it doesn't show "New findings (0 total):"
        assert "New findings (0 total)" not in latest_feedback, \
            "Should NOT show 'New findings (0 total)' when there are no findings"

        # Verify it shows gaps
        assert "Gaps/Issues" in latest_feedback, "Should show Gaps/Issues section"
        assert "TOOL_FAILED" in latest_feedback, "Should show the gap message"

        print("\n✅ Message format is correct:")
        print("  - No 'New findings (0 total)' line")
        print("  - Shows 'Gaps/Issues' section")
        print("  - Contains gap details")

        # Now test that orchestrator can process this state
        result = orchestrator.process(state)
        print(f"\n✅ Orchestrator processed successfully")
        print(f"  Action: {result.action}")
        print(f"  Task brief: {result.task_brief}")

        # Orchestrator should recognize the failure and either retry or fail
        assert result.action in ["fetch", "fail"], \
            f"Expected 'fetch' or 'fail', got '{result.action}'"

        print("\n✅ All checks passed!")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        raise

