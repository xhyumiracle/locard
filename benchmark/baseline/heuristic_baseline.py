"""
Heuristic baseline entrypoint for TraceTx benchmark.

The implementation is split across `benchmark/baseline/*` modules so the CLI
stays thin and the tracing/scoring logic remains easier to audit and maintain.
"""

from __future__ import annotations

import argparse
import logging
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import dotenv  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    dotenv = types.ModuleType("dotenv")

    def _load_dotenv(*args, **kwargs):
        return False

    dotenv.load_dotenv = _load_dotenv  # type: ignore[attr-defined]
    sys.modules["dotenv"] = dotenv

import config
from benchmark.baseline.io_utils import TeeOutput, ensure_dir, load_queries
from benchmark.baseline.runner import run_candidate_mode, run_evaluate_mode, run_score_mode, save_run_info


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run heuristic TraceTx baseline")
    parser.add_argument(
        "--yaml",
        type=Path,
        default=Path("data/thorchain/queries/thorchain-2025-high-fast-mini/BTC-DOGE.yaml"),
        help="Benchmark YAML file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for benchmark outputs",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process at most N queries")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N queries")
    parser.add_argument(
        "--search-time-span",
        type=int,
        default=config.TRACETX_SEARCH_TIME_SPAN,
        help="Search time span in seconds",
    )
    parser.add_argument(
        "--search-time-offset",
        type=int,
        default=0,
        help="Optional backward offset applied to search window end",
    )
    parser.add_argument(
        "--search-price-buffer",
        type=float,
        default=config.TRACETX_SEARCH_PRICE_BUFFER,
        help="Relative expansion for search price range",
    )
    parser.add_argument(
        "--check-time-span",
        type=int,
        default=config.TRACETX_CHECK_TIME_SPAN,
        help="Candidate price check span in seconds",
    )
    parser.add_argument("--search-limit", type=int, default=100, help="Max candidate outputs fetched from source chain search")
    parser.add_argument("--verbose", action="store_true", help="Print progress to console")
    return parser.parse_args()


def setup_logging(verbose: bool):
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    args = parse_args()
    setup_logging(args.verbose)

    ensure_dir(args.output_dir)
    ensure_dir(args.output_dir / "results")

    run_log_name = f"run_{args.yaml.stem}.log"
    run_log_path = args.output_dir / run_log_name
    stdout_tee = TeeOutput(run_log_path, sys.stdout)
    stderr_tee = TeeOutput(run_log_path.with_suffix(".err.log"), sys.stderr)
    original_stdout, original_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = stdout_tee, stderr_tee

    try:
        print(f"Full run log will be saved to: {run_log_path.name}")
        print(f"\n{'#' * 60}")
        print(f"BENCHMARK RUN: {args.yaml.name}")
        print(f"{'#' * 60}")
        print("Modes: candidate -> score -> evaluate")
        print(f"Work Dir: {args.output_dir}")
        print(f"{'#' * 60}")

        all_queries = load_queries(args.yaml)
        end_idx = args.offset + args.limit if args.limit else len(all_queries)
        queries = all_queries[args.offset:end_idx]

        params = {
            "yaml_path": args.yaml,
            "limit": args.limit,
            "offset": args.offset,
            "search_time_span": args.search_time_span,
            "search_time_offset": args.search_time_offset,
            "search_price_buffer": args.search_price_buffer,
            "check_time_span": args.check_time_span,
            "search_limit": args.search_limit,
        }

        candidate_results, run_record = run_candidate_mode(
            queries=queries,
            output_dir=args.output_dir,
            params=params,
            verbose=True,
        )
        score_results = run_score_mode(
            queries=queries,
            candidate_results=candidate_results,
            output_dir=args.output_dir,
            verbose=True,
        )
        aggregated = run_evaluate_mode(
            queries=queries,
            score_results=score_results,
            output_dir=args.output_dir,
            verbose=True,
        )

        run_info = {
            "total_cases": len(queries),
            "execution_time": run_record["execution_seconds"],
            "runs": [run_record],
            "metadata": {
                "baseline": "heuristic_trace_orchestrator",
                "query_source": str(args.yaml),
                "overall_metrics_found_rate": aggregated["summary"]["found_rate"],
            },
        }
        save_run_info(args.output_dir, run_info)

        print(f"\n{'#' * 60}")
        print("BENCHMARK COMPLETED")
        print(f"{'#' * 60}")
        print(f"Total candidate time: {run_record['execution_seconds']:.2f}s")
        print(f"Total runs: {len(run_info['runs'])}")
        print(f"Total cases: {run_info['total_cases']}")
        print(f"Results saved to: {args.output_dir}")
        print(f"{'#' * 60}")

    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        stdout_tee.close()
        stderr_tee.close()


if __name__ == "__main__":
    main()
