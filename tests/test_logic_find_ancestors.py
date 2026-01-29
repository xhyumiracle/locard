"""Test find_common_ancestors tool"""

from src.tools.blockchair import trace_ancestors_eth
from src.tools.samechain import find_common_ancestors


def test_find_common_ancestors():
    """Test finding common ancestors from real trace data"""
    # First, get ancestor data from trace_ancestors_eth
    ancestors_data = trace_ancestors_eth.invoke({
        "start_txs": "0x16f39b078a040e0426e7d00581d4f96fbeddaa94c36a227ce2de7ed101e27d2b,0x5803cc5924d7e4fc372028fe2031d0daac56d98011ff7b4c02ffa22aea608375",
        "max_hops": 1,
        "only_larger_ancestor": False,
        "max_ancestor_per_hop": 0,
        "min_value": 1.0
    })

    assert len(ancestors_data) > 0, "Should have ancestor data"

    # Now find common ancestors
    candidates = find_common_ancestors.invoke({"ancestors_data": ancestors_data})

    # Verify structure
    assert isinstance(candidates, dict), "Candidates should be a dict"

    max_possible_hits = len(ancestors_data)

    # Verify each candidate has valid hit count
    for ancestor_tx, hit_count in candidates.items():
        assert isinstance(hit_count, int), "Hit count should be an integer"
        assert 1 <= hit_count <= max_possible_hits, f"Hit count should be between 1 and {max_possible_hits}"

        # Verify the ancestor exists in at least one source tx
        found = False
        for src_tx, ancestors in ancestors_data.items():
            if ancestor_tx in ancestors:
                found = True
                # Verify ancestor info structure
                info = ancestors[ancestor_tx]
                assert 'value' in info, "Ancestor should have value"
                assert 'hop' in info, "Ancestor should have hop"
                assert 'sender' in info, "Ancestor should have sender"
                assert 'recipient' in info, "Ancestor should have recipient"
                break

        assert found, f"Ancestor {ancestor_tx} should exist in at least one source tx"
