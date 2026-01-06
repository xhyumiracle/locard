"""
Metrics calculation for benchmark evaluation.

Implements top-k hit rate calculation and metric aggregation.
"""

import logging
from typing import Dict, List, Optional, Any
from typing_extensions import TypedDict


logger = logging.getLogger(__name__)


class MetricResult(TypedDict):
    """Result of metric calculation for a single query."""
    hit_at_k: Dict[int, bool]  # {k: whether ground truth is in top-k}
    ground_truth: str
    predicted_rank: Optional[int]  # Rank of ground truth (1-indexed), None if not found
    total_candidates: int  # Initial candidates before exclusion
    valid_candidates: int  # Candidates after excluding invalid ones


def normalize_txhash(txhash: str) -> str:
    """
    Normalize transaction hash for comparison.

    - Convert to uppercase
    - Remove common prefixes (0x, etc.)
    """
    if not txhash:
        return ""

    normalized = txhash.strip().upper()

    # Remove 0x prefix if present
    if normalized.startswith("0X"):
        normalized = normalized[2:]

    return normalized


def calculate_hit_rate(
    score_table: Dict[str, Any],
    ground_truth: str,
    k_values: List[int] = [1, 3, 5, 10]
) -> MetricResult:
    """
    Calculate top-k hit rate for a single query.

    Args:
        score_table: ScoreTable dict from score_node
        ground_truth: Ground truth transaction hash
        k_values: List of k values to calculate hit rate for

    Returns:
        MetricResult with hit information
    """
    candidates = score_table.get("candidates", [])
    gt_normalized = normalize_txhash(ground_truth)

    # Count valid candidates (not excluded)
    valid_candidates = [c for c in candidates if not c.get("excluded", False)]
    valid_count = len(valid_candidates)

    # Find rank of ground truth (only search in valid candidates)
    predicted_rank = None
    for i, candidate in enumerate(valid_candidates, 1):
        src_transfer = candidate.get("src_transfer", {})
        src_txid = normalize_txhash(src_transfer.get("txid", ""))

        logger.debug(f"Candidate {i}: src_txid={src_txid[:16]}... vs gt={gt_normalized[:16]}...")

        if src_txid == gt_normalized:
            predicted_rank = i
            logger.debug(f"Match found at rank {i}")
            break

    # Calculate hit@k for each k
    hit_at_k = {}
    for k in k_values:
        hit_at_k[k] = predicted_rank is not None and predicted_rank <= k

    logger.debug(
        f"Ground truth: {gt_normalized[:8]}... "
        f"Rank: {predicted_rank or 'NOT_FOUND'} "
        f"Hit@1={hit_at_k.get(1, False)}"
    )

    return MetricResult(
        hit_at_k=hit_at_k,
        ground_truth=ground_truth,
        predicted_rank=predicted_rank,
        total_candidates=len(candidates),
        valid_candidates=valid_count
    )


def aggregate_metrics(results: List[MetricResult]) -> Dict[str, Any]:
    """
    Aggregate metrics across multiple queries.

    Args:
        results: List of MetricResult from individual queries

    Returns:
        Dict with aggregated metrics:
        - hit_rates: {k: hit_rate} for each k value
        - hit_counts: {k: hit_count} for each k value
        - mrr: Mean Reciprocal Rank
        - found_rate: Percentage of queries where ground truth was found
        - avg_initial_candidates: Average number of initial candidates per query (before exclusion)
        - avg_valid_candidates: Average number of valid candidates per query (after exclusion)
        - rank_details: List of "{rank}/{valid_candidates}" strings for each query
        - rank_stats: Statistics about ranks (mean, median, min, max)
    """
    if not results:
        return {
            "hit_rates": {},
            "hit_counts": {},
            "mrr": 0.0,
            "found_rate": 0.0,
            "avg_initial_candidates": 0.0,
            "avg_valid_candidates": 0.0,
            "total_queries": 0,
            "found_count": 0,
            "rank_details": [],
            "rank_stats": {}
        }

    total_queries = len(results)

    # Collect all k values
    k_values = set()
    for result in results:
        k_values.update(result["hit_at_k"].keys())
    k_values = sorted(k_values)

    # Calculate hit rates and counts for each k
    hit_rates = {}
    hit_counts = {}
    for k in k_values:
        hits = sum(1 for r in results if r["hit_at_k"].get(k, False))
        hit_counts[k] = hits
        hit_rates[k] = hits / total_queries

    # Calculate MRR (Mean Reciprocal Rank)
    reciprocal_ranks = []
    for result in results:
        rank = result["predicted_rank"]
        if rank is not None:
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)

    # Calculate found rate
    found_count = sum(1 for r in results if r["predicted_rank"] is not None)
    found_rate = found_count / total_queries

    # Calculate average candidates (initial and valid)
    avg_initial_candidates = sum(r["total_candidates"] for r in results) / total_queries
    avg_valid_candidates = sum(r["valid_candidates"] for r in results) / total_queries

    # Collect rank details: "{rank}/{valid_candidates}" for each query
    rank_details = []
    valid_ranks = []  # Only ranks that were found
    for result in results:
        rank = result["predicted_rank"]
        valid_cands = result["valid_candidates"]
        if rank is not None:
            rank_details.append(f"{rank}/{valid_cands}")
            valid_ranks.append(rank)
        else:
            rank_details.append(f"NOT_FOUND/{valid_cands}")

    # Calculate rank statistics (only for found queries)
    rank_stats = {}
    if valid_ranks:
        valid_ranks_sorted = sorted(valid_ranks)
        rank_stats = {
            "mean": sum(valid_ranks) / len(valid_ranks),
            "median": valid_ranks_sorted[len(valid_ranks_sorted) // 2] if len(valid_ranks_sorted) % 2 == 1
                      else (valid_ranks_sorted[len(valid_ranks_sorted) // 2 - 1] + valid_ranks_sorted[len(valid_ranks_sorted) // 2]) / 2,
            "min": min(valid_ranks),
            "max": max(valid_ranks),
            "count": len(valid_ranks)
        }

    return {
        "hit_rates": hit_rates,
        "hit_counts": hit_counts,
        "mrr": mrr,
        "found_rate": found_rate,
        "avg_initial_candidates": avg_initial_candidates,
        "avg_valid_candidates": avg_valid_candidates,
        "total_queries": total_queries,
        "found_count": found_count,
        "rank_details": rank_details,
        "rank_stats": rank_stats
    }


def print_metrics_report(
    metrics: Dict[str, Any],
    detailed: bool = False
):
    """
    Print formatted metrics report.

    Args:
        metrics: Aggregated metrics dict
        detailed: Whether to print detailed statistics
    """
    print("\n" + "=" * 60)
    print("METRICS REPORT")
    print("=" * 60)

    print(f"\nTotal Queries: {metrics['total_queries']}")
    print(f"Ground Truth Found: {metrics['found_count']}/{metrics['total_queries']} "
          f"({metrics['found_rate']:.2%})")

    print("\nTop-K Hit Rates:")
    for k, rate in sorted(metrics['hit_rates'].items()):
        print(f"  Top-{k:2d}: {rate:6.2%}")

    print(f"\nMean Reciprocal Rank (MRR): {metrics['mrr']:.4f}")
    print(f"Avg Initial Candidates: {metrics['avg_initial_candidates']:.1f}")
    print(f"Avg Valid Candidates: {metrics['avg_valid_candidates']:.1f}")

    if detailed:
        print("\n" + "-" * 60)
        print("DETAILED STATISTICS")
        print("-" * 60)
        # Add more detailed stats here if needed

    print("=" * 60)
