"""
Benchmark CLI entry point.

Usage:
    # Run all three modes (default)
    python -m benchmark --yaml data/example_btcdoge.yaml --output benchmark_result/exp1

    # Run specific modes only
    python -m benchmark --yaml data/queries.yaml --output results/exp1 --modes candidate score
    python -m benchmark --yaml data/queries.yaml --output results/exp1 --modes evaluate

    # Run from existing intermediate files
    python -m benchmark --yaml data/queries.yaml --output results/exp1 --modes score evaluate
"""

import argparse
import sys
import logging
from pathlib import Path

import config
from benchmark.runner import run_benchmark


def main():
    parser = argparse.ArgumentParser(
        description="BlockchainMAS Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all three modes (default: candidate -> score -> evaluate)
  python -m benchmark --yaml data/queries.yaml --output results/exp1

  # Run only first query (offset=0, limit=1)
  python -m benchmark --yaml data/queries.yaml --output results/exp1 --limit 1

  # Run queries 5-9 (offset=5, limit=5)
  python -m benchmark --yaml data/queries.yaml --output results/exp1 --offset 5 --limit 5

  # Run only candidate extraction with verbose logging
  python -m benchmark --yaml data/queries.yaml --output results/exp1 --modes candidate -v

  # Run scoring from existing candidate_cclinks.ndjson (debug mode)
  python -m benchmark --yaml data/queries.yaml --output results/exp1 --modes score -vv

  # Re-evaluate existing score_table.ndjson with new metrics
  python -m benchmark --yaml data/queries.yaml --output results/exp1 --modes evaluate
        """
    )

    parser.add_argument(
        "--yaml",
        type=str,
        required=True,
        help="Path to YAML file containing queries"
    )

    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output directory for results (must be empty or non-existent)"
    )

    parser.add_argument(
        "--modes",
        nargs="+",
        choices=["candidate", "score", "evaluate"],
        default=None,
        help="Execution modes to run (default: all three in order)"
    )

    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Limit to N queries from YAML (from offset position)"
    )

    parser.add_argument(
        "--offset",
        type=int,
        metavar="N",
        default=0,
        help="Skip first N queries from YAML (0-indexed, default: 0)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity: -v (INFO), -vv (DEBUG), -vvv (full trace)"
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output (only errors)"
    )

    args = parser.parse_args()

    # Override VERBOSE_LEVEL from command line args (highest priority)
    # Priority: command line args > environment variable > default (0)
    if args.quiet:
        config.VERBOSE_LEVEL = 0  # Override to WARNING
    else:
        config.VERBOSE_LEVEL = args.verbose  # Use -v count (0, 1, 2, 3, ...)

    # Setup logging using unified config
    logging.basicConfig(
        level=config.get_log_level(),
        format=config.LOG_FORMAT,
        datefmt=config.LOG_DATE_FORMAT
    )
    config.setup_logging()  # Apply namespace-specific levels for level 2

    # Validate paths
    yaml_path = Path(args.yaml)
    if not yaml_path.exists():
        print(f"Error: YAML file not found: {yaml_path}")
        sys.exit(1)

    # Run benchmark
    try:
        run_benchmark(
            yaml_path=str(yaml_path),
            output_dir=args.output,
            modes=args.modes,
            limit=args.limit,
            offset=args.offset,
            verbose=not args.quiet
        )
        sys.exit(0)
    except Exception as e:
        print(f"Benchmark failed: {e}")
        if args.verbose >= 2:  # Show traceback in debug mode (-vv or -vvv)
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()