from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from benchmark.metrics import aggregate_metrics, calculate_hit_rate
from benchmark.baseline.io_utils import extract_ground_truth, get_query_results_dir, make_bench_id, save_case_log, write_json
from benchmark.baseline.tracing import execute_trace_steps
from src.models.core import CrossChainLink
from src.node.tracetx.score import ScoreTable, ScoringParams, score_candidates
import config

logger = logging.getLogger(__name__)


def run_candidate_mode(
    queries: list[dict[str, Any]],
    output_dir: Path,
    params: dict[str, Any],
    verbose: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results_dir = output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    mode_start = time.time()
    run_record = {
        "timestamp": datetime.now().isoformat(),
        "yaml_file": str(params["yaml_path"]),
        "offset": params["offset"],
        "limit": params["limit"],
        "duplicated_cases": 0,
        "new_cases": len(queries),
        "processed_cases": 0,
        "execution_seconds": 0.0,
        "graph_params": {
            "search_time_span": params["search_time_span"],
            "search_time_offset": params["search_time_offset"],
            "search_price_buffer": params["search_price_buffer"],
            "check_time_span": params["check_time_span"],
            "search_limit": params["search_limit"],
        },
    }
    candidate_results: list[dict[str, Any]] = []

    if verbose:
        print(f"\n{'=' * 60}")
        print("MODE: CANDIDATE - Extracting CCLinks")
        print(f"{'=' * 60}")
        print(f"Processing {len(queries)} queries...")

    for i, query_item in enumerate(queries, 1):
        metadata = query_item.get("metadata", {})
        query_id = metadata["query_id"]
        query_idx = metadata.get("query_idx")
        query = query_item["query"].strip()
        result_dir = get_query_results_dir(results_dir, query_id, query_idx)
        start_time = time.time()

        if verbose:
            print(f"\n[{i}/{len(queries)}] Query idx={query_idx}, {query_id[:16]}...: {query[:60]}...")

        try:
            cclinks, baseline, log_lines = execute_trace_steps(query_id=query_id, query=query, params=params)
            execution_time = time.time() - start_time
            logger.info("[%s] candidate success: %d cclinks", query_id, len(cclinks))

            candidate_payload = {
                "query_id": query_id,
                "metadata": metadata,
                "cclinks": [cclink.to_dict() for cclink in cclinks],
                "execution_time": execution_time,
                "success": True,
                "baseline": baseline,
            }
            write_json(result_dir / "candidate_cclinks.json", candidate_payload)
            save_case_log(result_dir / "workflow.log", log_lines)

            if verbose:
                print(f"  ✓ Found {len(cclinks)} CCLinks in {execution_time:.2f}s")

            candidate_results.append(candidate_payload)

        except Exception as e:
            execution_time = time.time() - start_time
            error_payload = {
                "query_id": query_id,
                "metadata": metadata,
                "cclinks": [],
                "execution_time": execution_time,
                "success": False,
                "error": str(e),
            }
            write_json(result_dir / "candidate_cclinks.json", error_payload)
            save_case_log(result_dir / "workflow.log", [f"error={e}"])
            candidate_results.append(error_payload)
            logger.exception("[%s] candidate failed", query_id)
            if verbose:
                print(f"  ✗ ERROR: {e}")

        run_record["processed_cases"] = i
        run_record["execution_seconds"] = time.time() - mode_start

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"CANDIDATE MODE COMPLETED in {time.time() - mode_start:.2f}s")
        print(f"{'=' * 60}")

    return candidate_results, run_record


def run_score_mode(
    queries: list[dict[str, Any]],
    candidate_results: list[dict[str, Any]],
    output_dir: Path,
    verbose: bool,
):
    results_dir = output_dir / "results"
    if verbose:
        print(f"\n{'=' * 60}")
        print("MODE: SCORE - Generating Score Tables")
        print(f"{'=' * 60}")
        print(f"Processing {len(candidate_results)} cases...")

    score_results: list[dict[str, Any]] = []

    for i, (query_item, case) in enumerate(zip(queries, candidate_results), 1):
        metadata = query_item.get("metadata", {})
        query_id = metadata["query_id"]
        query_idx = metadata.get("query_idx")
        result_dir = get_query_results_dir(results_dir, query_id, query_idx)
        start_time = time.time()

        if verbose:
            print(f"\n[{i}/{len(candidate_results)}] {make_bench_id(query_id, query_idx)} scoring...")

        try:
            if not case.get("success"):
                raise ValueError(case.get("error", "candidate mode failed"))

            cclinks = [CrossChainLink.from_dict(item) for item in case.get("cclinks", [])]
            if not cclinks:
                score_table = ScoreTable(
                    status="NO_CANDIDATES",
                    params=ScoringParams(
                        tau_time=config.SCORING_TAU_TIME,
                        w_time=config.SCORING_W_TIME,
                        w_amount=config.SCORING_W_VALUE,
                        max_fee_rate=config.PRICE_MAX_FEE_RATE,
                        max_deviation_rate=config.PRICE_MAX_DEVIATION_RATE,
                    ),
                    candidates=[],
                    best_match=None,
                    summary="No CCLinks to score",
                )
            else:
                score_table = score_candidates(cclinks)

            execution_time = time.time() - start_time
            payload = {
                "query_id": query_id,
                "metadata": metadata,
                "score_table": score_table.to_dict(),
                "execution_time": execution_time,
                "success": True,
            }
            write_json(result_dir / "score_table.json", payload)
            score_results.append(payload)

            if verbose:
                print(f"  ✓ Status: {score_table.status}, {len(score_table.candidates)} candidates in {execution_time:.2f}s")

        except Exception as e:
            execution_time = time.time() - start_time
            payload = {
                "query_id": query_id,
                "metadata": metadata,
                "score_table": None,
                "execution_time": execution_time,
                "success": False,
                "error": str(e),
            }
            write_json(result_dir / "score_table.json", payload)
            score_results.append(payload)
            logger.exception("[%s] score failed", query_id)
            if verbose:
                print(f"  ✗ ERROR: {e}")

    return score_results


def run_evaluate_mode(
    queries: list[dict[str, Any]],
    score_results: list[dict[str, Any]],
    output_dir: Path,
    verbose: bool,
):
    results_dir = output_dir / "results"
    metric_results: list[dict[str, Any]] = []

    if verbose:
        print(f"\n{'=' * 60}")
        print("MODE: EVALUATE - Calculating Metrics")
        print(f"{'=' * 60}")
        print(f"Evaluating {len(score_results)} cases...")

    for query_item, case in zip(queries, score_results):
        metadata = query_item.get("metadata", {})
        query_id = metadata["query_id"]
        query_idx = metadata.get("query_idx")
        result_dir = get_query_results_dir(results_dir, query_id, query_idx)
        ground_truth = extract_ground_truth(query_item)

        if not ground_truth or not case.get("success") or not case.get("score_table"):
            continue

        metric = calculate_hit_rate(
            score_table=case["score_table"],
            ground_truth=ground_truth,
            k_values=[1, 3, 5, 10, 20, 50],
        )
        metric_results.append(metric)
        write_json(
            result_dir / "metrics.json",
            {
                "ground_truth": ground_truth,
                "predicted_rank": metric["predicted_rank"],
                "total_candidates": metric["total_candidates"],
                "valid_candidates": metric["valid_candidates"],
                "hit_at_k": {str(k): v for k, v in metric["hit_at_k"].items()},
            },
        )

        if verbose:
            rank = metric["predicted_rank"]
            rank_str = f"#{rank}/{metric['valid_candidates']}" if rank else f"NOT_FOUND/{metric['valid_candidates']}"
            print(f"[{make_bench_id(query_id, query_idx)}] GT: {ground_truth[:8]}... Rank: {rank_str}")

    aggregated = aggregate_metrics(metric_results)
    aggregated["metadata"] = {"timestamp": datetime.now().isoformat()}
    write_json(output_dir / "overall_metrics.json", aggregated)

    if verbose:
        print(f"\n{'=' * 60}")
        print("OVERALL METRICS")
        print(f"{'=' * 60}")
        print(f"Evaluated: {aggregated['summary']['evaluated_cases']}")
        print(f"Found: {aggregated['summary']['found_cases']} ({aggregated['summary']['found_rate']:.2%})")
        print("\nTop-K Hit Rates:")
        for k in sorted(k for k in aggregated["hit_rates"].keys() if isinstance(k, int)):
            print(f"  Top-{k:2d}: {aggregated['hit_rates'][k]:6.2%} ({aggregated['hit_counts'][k]})")
        if "found" in aggregated["hit_rates"]:
            print(f"  Found (all): {aggregated['hit_rates']['found']:6.2%} ({aggregated['hit_counts']['found']})")
        print("\nRanking:")
        print(f"  MRR: {aggregated['ranking']['mrr']:.4f}")
        print(f"  Mean:   {aggregated['ranking']['mean_rank']:.2f}")
        print(f"  Median: {aggregated['ranking']['median_rank']:.1f}")
        print(f"  Min:    {aggregated['ranking']['min_rank']}")
        print(f"  Max:    {aggregated['ranking']['max_rank']}")
        print("\nCandidates:")
        print(f"  Avg Initial: {aggregated['candidates']['avg_initial']:.1f}")
        print(f"  Avg Valid:   {aggregated['candidates']['avg_valid']:.1f}")

    return aggregated


def save_run_info(output_dir: Path, run_info: dict[str, Any]):
    write_json(output_dir / "run_info.json", run_info)
