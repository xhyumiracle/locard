"""
BlockchainMAS - Main entry point.

Usage:
    python -m src.main                    # Interactive mode
    python -m src.main "trace tx ..."     # Single query mode
    python -m src.main --example          # Run example from docs
"""

import sys
import logging
import argparse
from typing import Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

import config
from src.graph.workflow import run_graph, create_graph


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=config.LOG_FORMAT
    )


def get_final_response(state: dict) -> str:
    """Extract final response from state."""
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "content"):
            return last_msg.content
    return "No response generated."


def run_single_query(query: str) -> str:
    """
    Run a single query through the system.

    Args:
        query: User query string

    Returns:
        Response string
    """
    state = run_graph(query)
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
            if config.DEBUG_MODE:
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


def run_example():
    """Run the example from docs/example_data.md."""
    print("\n" + "=" * 60)
    print("Running Example: DOGE -> BTC Cross-chain Trace")
    print("=" * 60)

    example_query = """please help me to trace the source of this BTC: in tx 749534249453B75EE5F193B8B71629C642B8AD3CF772212D518468615231AE1B, there's a vout to bc1qzjuhrwr50sd7njkf40qa469n38sl25mg9lxdvp, hint: it may come from doge coin"""

    print(f"\nQuery: {example_query}\n")
    print("-" * 60)
    print("Processing...\n")

    try:
        response = run_single_query(example_query)
        print("\nResponse:")
        print("-" * 60)
        print(response)
        print("-" * 60)

        print("\nExpected: Should identify DOGE tx 71B1ED1276B53803272A0E2F0860961F4BE0B49CCF72415210BB2EEAAFF6C3D0")

    except Exception as e:
        print(f"\nError running example: {e}")
        if config.DEBUG_MODE:
            import traceback
            traceback.print_exc()
        return 1

    return 0


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
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )

    args = parser.parse_args()

    if args.debug:
        config.DEBUG_MODE = True
        config.LOG_LEVEL = "DEBUG"

    setup_logging()

    if args.example:
        sys.exit(run_example())
    elif args.query:
        response = run_single_query(args.query)
        print(response)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
