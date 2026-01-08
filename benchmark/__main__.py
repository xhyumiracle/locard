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
  python -m benchmark --yaml data/queries.yaml --work-dir results/exp1

  # Run only first query (offset=0, limit=1)
  python -m benchmark --yaml data/queries.yaml --work-dir results/exp1 --limit 1

  # Run queries 5-9 (offset=5, limit=5)
  python -m benchmark --yaml data/queries.yaml --work-dir results/exp1 --offset 5 --limit 5

  # Run only candidate extraction with verbose logging
  python -m benchmark --yaml data/queries.yaml --work-dir results/exp1 --modes candidate -v

  # Run scoring from existing candidates (no --yaml needed)
  python -m benchmark --work-dir results/exp1 --modes score --force -v

  # Re-evaluate with new metrics (needs --yaml for ground truth)
  python -m benchmark --yaml data/queries.yaml --work-dir results/exp1 --modes evaluate --force
        """
    )

    parser.add_argument(
        "--yaml",
        type=str,
        required=False,
        help="Path to YAML file containing queries (required for candidate/evaluate modes)"
    )

    parser.add_argument(
        "--work-dir",
        type=str,
        required=True,
        help="Working directory (candidate: create & write, score/evaluate: read & write in-place)",
        dest="work_dir"
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

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing results (only for score/evaluate modes, candidate never overwrites)"
    )

    parser.add_argument(
        "--continue",
        action="store_true",
        dest="continue_mode",
        help="Continue mode - append to existing work directory (allows incremental runs)"
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

    # Determine which modes need yaml
    modes = args.modes or ["candidate", "score", "evaluate"]
    modes_need_yaml = {"candidate", "evaluate"}
    needs_yaml = any(mode in modes_need_yaml for mode in modes)

    # Validate yaml path if needed
    yaml_path = None
    if needs_yaml:
        if not args.yaml:
            print(f"Error: --yaml is required for modes: {', '.join(set(modes) & modes_need_yaml)}")
            sys.exit(1)
        yaml_path = Path(args.yaml)
        if not yaml_path.exists():
            print(f"Error: YAML file not found: {yaml_path}")
            sys.exit(1)
    elif args.yaml:
        # Warn if yaml provided but not needed
        print(f"Warning: --yaml provided but not needed for score-only mode (ignored)")

    # Run benchmark
    try:
        run_benchmark(
            yaml_path=str(yaml_path) if yaml_path else None,
            output_dir=args.work_dir,
            modes=modes,
            limit=args.limit,
            offset=args.offset,
            verbose=not args.quiet,
            force=args.force,
            continue_mode=args.continue_mode
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