"""
BlockchainMAS - Main entry point.

Usage:
    python -m src.main                    # Interactive mode
    python -m src.main "trace tx ..."     # Single query mode
    python -m src.main --example          # Run example from docs
    python -m src.main --batch FILE       # Run queries from YAML batch file
"""

import sys
import logging
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List

import yaml

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

import config
from src.graph.workflow import run_graph, create_graph


# Removed: setup_logging() now in config.py and called from main()


def get_final_response(state: dict) -> str:
    """Extract final response from state."""
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "content"):
            return last_msg.content
    return "No response generated."


def run_single_query(query: str, params: Optional[Dict[str, Any]] = None) -> str:
    """
    Run a single query through the system.

    Args:
        query: User query string
        params: Optional parameters to override defaults

    Returns:
        Response string
    """
    state = run_graph(query, params=params)
    return get_final_response(state)


def run_interactive():
    """Run interactive CLI mode."""
    print("\n" + "=" * 60)
    print("BlockchainMAS - Blockchain Forensics Multi-Agent System")
    print("=" * 60)
    print("\nType your query to trace transactions across blockchains.")
    print("Commands: 'quit' or 'exit' to exit, 'help' for info\n")

    while True:
        try:
            user_input = input("\n> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break

            if user_input.lower() == "help":
                print_help()
                continue

            print("\nProcessing...\n")
            response = run_single_query(user_input)
            print(f"\n{response}")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")
            if config.VERBOSE_LEVEL >= 2:
                import traceback
                traceback.print_exc()


def print_help():
    """Print help information."""
    print("""
BlockchainMAS Help
==================

This system can trace transactions across multiple blockchains including
Bitcoin (BTC), Dogecoin (DOGE), and Ethereum (ETH).

Example queries:
- "Trace the source of BTC in tx <txhash>"
- "Where did the funds in <address> come from?"
- "Find cross-chain transactions from DOGE to BTC around <timestamp>"

Supported chains: BTC, DOGE, LTC, ETH (more coming)

Tips:
- Provide transaction hashes or addresses for specific traces
- Mention source/destination chains if known (helps narrow search)
- Include timestamps or time ranges for cross-chain matching
""")


def parse_params(param_list: Optional[List[str]]) -> Dict[str, Any]:
    """
    Parse --param arguments into dict.

    Simple prefix convention:
    - "max_hops=1" → {"max_hops": 1}
    - "tracetx.search_time_offset=50" → {"tracetx_params": {"search_time_offset": 50}}

    Args:
        param_list: List of "key=value" strings from --param arguments

    Returns:
        Dict with parsed parameters (tracetx.* becomes nested under tracetx_params)
    """
    if not param_list:
        return {}

    params = {}
    tracetx_params = {}

    for param_str in param_list:
        if "=" not in param_str:
            print(f"Warning: Invalid param format '{param_str}', expected KEY=VALUE")
            continue

        key, value_str = param_str.split("=", 1)

        # Auto-convert value type
        try:
            value = int(value_str)
        except ValueError:
            try:
                value = float(value_str)
            except ValueError:
                if value_str.lower() in ("true", "false"):
                    value = value_str.lower() == "true"
                else:
                    value = value_str

        # Route to correct dict based on prefix
        if key.startswith("tracetx."):
            # tracetx.search_time_offset → tracetx_params["search_time_offset"]
            actual_key = key[8:]  # Remove "tracetx." prefix
            tracetx_params[actual_key] = value
        else:
            # Direct parameter
            params[key] = value

    # Add tracetx_params if any
    if tracetx_params:
        params["tracetx_params"] = tracetx_params

    return params


def run_example():
    """Run the example from docs/example_data.md."""
    print("\n" + "=" * 60)
    print("Running Example: DOGE -> BTC Cross-chain Trace")
    print("=" * 60)

    example_query = """please help me to trace the source of this BTC: in tx 749534249453B75EE5F193B8B71629C642B8AD3CF772212D518468615231AE1B, there's a vout to bc1qzjuhrwr50sd7njkf40qa469n38sl25mg9lxdvp, hint: it may come from doge coin"""

    print(f"\nQuery: {example_query}\n")
    print("-" * 60)
    print("Processing...\n")

    response = run_single_query(example_query)
    print("\nResponse:")
    print("-" * 60)
    print(response)
    print("-" * 60)

    print("\nExpected: Should identify DOGE tx 71B1ED1276B53803272A0E2F0860961F4BE0B49CCF72415210BB2EEAAFF6C3D0")

    return 0


def run_batch(batch_file: str, limit: Optional[int] = None, offset: int = 0, params: Optional[Dict[str, Any]] = None) -> int:
    """
    Run multiple queries from a YAML batch file.

    Args:
        batch_file: Path to YAML file containing queries
        limit: Maximum number of queries to run (None = all)
        offset: Skip first N queries (default: 0)
        params: Global params from CLI --param (applied to all queries)

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    batch_path = Path(batch_file)
    if not batch_path.exists():
        print(f"Error: Batch file not found: {batch_file}")
        return 1

    try:
        with open(batch_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        return 1

    queries = data
    if not queries:
        print("No queries found in batch file.")
        return 0

    # Apply offset and limit
    total_queries = len(queries)
    if offset >= total_queries:
        print(f"Error: Offset {offset} exceeds total queries {total_queries}")
        return 1

    queries = queries[offset:]
    if limit is not None:
        queries = queries[:limit]

    print("\n" + "=" * 60)
    print(f"Running Batch: {batch_path.name}")
    print(f"Total queries in file: {total_queries}")
    print(f"Running queries: {offset + 1}-{offset + len(queries)}")
    print("=" * 60)

    errors = 0
    for i, item in enumerate(queries, offset + 1):
        query = item.get("query", "").strip()
        groundtruth = item.get("groundtruth", "")
        # Backward compatibility: fallback to 'comment' if 'groundtruth' not present
        if not groundtruth:
            groundtruth = item.get("comment", "")

        if not query:
            continue

        print(f"\n[{i}/{offset + len(queries)}] Query:")
        print("-" * 60)
        print(query)
        print("-" * 60)
        if params:
            print(f"Params: {params}")
            print("-" * 60)
        print("Processing...\n")

        try:
            response = run_single_query(query, params=params)
            print("\nResponse:")
            print("-" * 60)
            print(response)
            print("-" * 60)
            if groundtruth:
                print(f"\nGround Truth: {groundtruth}")
        except Exception as e:
            print(f"\nError: {e}")
            if config.VERBOSE_LEVEL >= 2:
                import traceback
                traceback.print_exc()
            errors += 1

    print("\n" + "=" * 60)
    print(f"Batch complete. {len(queries) - errors}/{len(queries)} succeeded.")
    print("=" * 60)

    return 1 if errors > 0 else 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="BlockchainMAS - Blockchain Forensics Multi-Agent System"
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Single query to process (optional, starts interactive mode if not provided)"
    )
    parser.add_argument(
        "--example",
        action="store_true",
        help="Run the example from documentation"
    )
    parser.add_argument(
        "--batch",
        type=str,
        metavar="FILE",
        help="Run queries from a YAML batch file"
    )
    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Maximum number of queries to run from batch file (default: all)"
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        metavar="N",
        help="Skip first N queries in batch file (default: 0)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity: -v (INFO), -vv (DEBUG business code), -vvv (full DEBUG)"
    )
    parser.add_argument(
        "--param",
        action="append",
        metavar="KEY=VALUE",
        help="Set parameter (use tracetx. prefix for TraceTx params, e.g., --param max_hops=1 --param tracetx.search_time_offset=50)"
    )

    args = parser.parse_args()

    # Override VERBOSE_LEVEL from command line args (highest priority)
    # Priority: command line args > environment variable > default (0)
    if args.verbose:
        config.VERBOSE_LEVEL = args.verbose

    # Setup logging using unified config
    logging.basicConfig(
        level=config.get_log_level(),
        format=config.LOG_FORMAT,
        datefmt=config.LOG_DATE_FORMAT
    )
    config.setup_logging()  # Apply namespace-specific levels for level 2

    # Parse params if provided
    params = parse_params(args.param) if args.param else None

    if args.example:
        sys.exit(run_example())
    elif args.batch:
        sys.exit(run_batch(args.batch, limit=args.limit, offset=args.offset, params=params))
    elif args.query:
        response = run_single_query(args.query, params=params)
        print(response)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
