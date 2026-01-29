"""Test trace_ancestors_eth tool"""

from src.tools.blockchair import trace_ancestors_eth


def test_trace_ancestors():
    """Test with 2 real transactions, max 1 hop, min_value 1 ETH"""
    result = trace_ancestors_eth.invoke({
        "start_txs": "0x16f39b078a040e0426e7d00581d4f96fbeddaa94c36a227ce2de7ed101e27d2b,0x5803cc5924d7e4fc372028fe2031d0daac56d98011ff7b4c02ffa22aea608375",
        "max_hops": 1,
        "only_larger_ancestor": False,
        "max_ancestor_per_hop": 5,
        "min_value": 1.0
    })

    # Verify result structure
    assert isinstance(result, dict), "Result should be a dict"
    assert len(result) > 0, "Should have results for at least one source tx"

    for src_tx, ancestors in result.items():
        assert isinstance(ancestors, dict), f"Ancestors for {src_tx} should be a dict"

        if ancestors:
            # Verify ancestor structure
            for anc_tx, info in ancestors.items():
                assert 'hop' in info, "Ancestor should have hop field"
                assert 'value' in info, "Ancestor should have value field"
                assert 'sender' in info, "Ancestor should have sender field"
                assert 'recipient' in info, "Ancestor should have recipient field"
                assert 'timestamp' in info, "Ancestor should have timestamp field"

                # Verify value is numeric
                value = info['value']
                if isinstance(value, str):
                    float(value)  # Should not raise exception
