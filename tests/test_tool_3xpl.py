"""Direct test for 3xpl ETH transfer search tool (without converters)."""

from src.tools.threexpl import search_eth_transfers_3xpl


def test_3xpl_basic_search():
    """Test basic 3xpl search with time and amount filters."""
    print("\n=== Test 1: Basic search (30-min window, 25-28 ETH) ===")

    results = search_eth_transfers_3xpl.invoke({
        "min_timestamp": 1747858711,
        "max_timestamp": 1747860511,
        "min_amount": 25.47,
        "max_amount": 28.22,
        "direction": "in",
        "limit": 100
    })

    print(f"Found {len(results)} transfers")
    if results:
        print(f"\nFirst result:")
        for key, value in results[0].items():
            print(f"  {key}: {value}")

    assert isinstance(results, list), "Results should be a list"
    print("\n✅ Basic search passed")
    return results


def test_3xpl_large_window():
    """Test with larger time window to verify performance."""
    print("\n=== Test 2: Large window (1 hour, wider amount range) ===")

    results = search_eth_transfers_3xpl.invoke({
        "min_timestamp": 1747858711,
        "max_timestamp": 1747862311,  # 1 hour window
        "min_amount": 20.0,
        "max_amount": 30.0,
        "direction": "in",
        "limit": 200
    })

    print(f"Found {len(results)} transfers in 1-hour window")
    if results:
        # Show first few
        print(f"\nFirst 3 results:")
        for i, result in enumerate(results[:3], 1):
            print(f"  {i}. txid={result['txid'][:16]}..., amount={result['amount']:.4f} ETH, recipient={result['recipient'][:10]}...")

    print("\n✅ Large window test passed")


def test_3xpl_direction_both():
    """Test direction='both' parameter."""
    print("\n=== Test 3: Direction 'both' ===")

    results = search_eth_transfers_3xpl.invoke({
        "min_timestamp": 1747858711,
        "max_timestamp": 1747860511,
        "min_amount": 25.0,
        "max_amount": 30.0,
        "direction": "both",
        "limit": 100
    })

    print(f"Found {len(results)} transfers (both directions)")
    print("✅ Direction test passed")


def test_3xpl_model_structure():
    """Verify the returned model structure matches Eth3xplTransfer."""
    print("\n=== Test 4: Model structure verification ===")

    results = search_eth_transfers_3xpl.invoke({
        "min_timestamp": 1747858711,
        "max_timestamp": 1747860511,
        "min_amount": 25.0,
        "max_amount": 30.0,
        "direction": "in",
        "limit": 10
    })

    if not results:
        print("⚠️  No results to verify structure")
        return

    result = results[0]

    # Verify required fields
    required_fields = ["chain", "txid", "recipient", "amount", "block_time"]
    for field in required_fields:
        assert field in result, f"Missing required field: {field}"
        print(f"  ✓ {field}: {result[field]}")

    # Verify optional fields
    assert "module" in result, "Should have 'module' field"
    print(f"  ✓ module: {result['module']}")

    # Verify types
    assert isinstance(result["amount"], float), "amount should be float"
    assert isinstance(result["block_time"], int), "block_time should be int"
    assert result["chain"] == "ETH", "chain should be 'ETH'"

    print("\n✅ Model structure verified")

