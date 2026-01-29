"""Test parse_params function from main.py"""

from src.main import parse_params


def test_simple_direct_parameters():
    """Test simple direct parameters."""
    params = parse_params(["max_hops=1", "min_value=0.5"])
    assert params == {"max_hops": 1, "min_value": 0.5}


def test_tracetx_prefixed_parameters():
    """Test TraceTx prefixed parameters."""
    params = parse_params(["tracetx.search_time_offset=50", "tracetx.max_time_delta=3600"])
    expected = {"tracetx_params": {"search_time_offset": 50, "max_time_delta": 3600}}
    assert params == expected


def test_mixed_parameters():
    """Test mixed parameters."""
    params = parse_params([
        "max_hops=2",
        "tracetx.search_time_offset=30",
        "min_value=1.5",
        "tracetx.max_time_delta=1800"
    ])
    expected = {
        "max_hops": 2,
        "min_value": 1.5,
        "tracetx_params": {
            "search_time_offset": 30,
            "max_time_delta": 1800
        }
    }
    assert params == expected


def test_type_conversion():
    """Test type conversion (int, float, bool, string)."""
    params = parse_params([
        "int_param=42",
        "float_param=3.14",
        "bool_true=true",
        "bool_false=false",
        "string_param=hello"
    ])
    assert params["int_param"] == 42 and isinstance(params["int_param"], int)
    assert params["float_param"] == 3.14 and isinstance(params["float_param"], float)
    assert params["bool_true"] is True and isinstance(params["bool_true"], bool)
    assert params["bool_false"] is False and isinstance(params["bool_false"], bool)
    assert params["string_param"] == "hello" and isinstance(params["string_param"], str)


def test_empty_input():
    """Test empty input."""
    params = parse_params([])
    assert params == {}


def test_none_input():
    """Test None input."""
    params = parse_params(None)
    assert params == {}


def test_invalid_format():
    """Test invalid format (no equals sign) - should skip invalid params."""
    params = parse_params(["invalid_param", "valid_param=123"])
    assert params == {"valid_param": 123}
