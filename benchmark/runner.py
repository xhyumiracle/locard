"""
Benchmark runner for batch evaluation with 3-mode support.

This module supports three execution modes:
1. candidate: Extract candidate CCLinks from queries
2. score: Generate score tables from CCLinks
3. evaluate: Calculate metrics from score tables

Modes can be chained together or run independently.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Literal
from datetime import datetime

import yaml

from src.state.tracetx_state import initialize_state
from src.graph.registry import SUBGRAPH_MAP
from src.models.core import CrossChainLink
from src.node.tracetx.score import ScoreTable, ScoringParams, score_node
from benchmark.metrics import calculate_hit_rate, aggregate_metrics
import config


logger = logging.getLogger(__name__)

BenchmarkMode = Literal["candidate", "score", "evaluate"]


def serialize_cclink(cclink: CrossChainLink) -> dict:
    """
    Serialize CrossChainLink to JSON-compatible dict using mashumaro.

    Thanks to DataClassDictMixin, this is a one-liner that handles
    all nested dataclasses automatically.
    """
    return cclink.to_dict()


def deserialize_cclink(data: dict) -> CrossChainLink:
    """
    Deserialize CrossChainLink from JSON dict using mashumaro.

    Reconstructs all nested dataclass structures automatically.
    """
    return CrossChainLink.from_dict(data)




class BenchmarkRunner:
    """Runner for batch benchmark evaluation with 3-mode support."""

    def __init__(
        self,
        output_dir: Path,
        modes: List[BenchmarkMode] = None,
        verbose: bool = True
    ):
        """
        Initialize benchmark runner.

        Args:
            output_dir: Directory to save results
            modes: List of modes to execute in order (default: all three)
            verbose: Print progress to console

        Raises:
            ValueError: If output_dir is not empty
        """
        self.output_dir = Path(output_dir)
        self.modes = modes or ["candidate", "score", "evaluate"]
        self.verbose = verbose

        # Check output directory based on modes
        if self.output_dir.exists():
            # Only check if directory is empty when running candidate mode
            # (candidate creates new data, should start fresh)
            if "candidate" in self.modes:
                if any(self.output_dir.iterdir()):
                    raise ValueError(
                        f"Output directory is not empty: {self.output_dir}\n"
                        f"Candidate mode requires an empty directory.\n"
                        f"Please use a different directory or remove existing files."
                    )
        else:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # Directory structure:
        # results/{query_id}/agent.log, candidate_cclinks.json, score_table.json, metrics.json
        # summary_stats.json, summary_aggregated_metrics.json (at root)
        self.results_dir = self.output_dir / "results"
        self.stats_path = self.output_dir / "summary_stats.json"
        self.aggregated_metrics_path = self.output_dir / "summary_aggregated_metrics.json"

        # Create directories
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Runtime stats
        self.stats = {
            "total_cases": 0,
            "completed_cases": 0,
            "failed_cases": 0,
            "modes_executed": [],
            "start_time": None,
            "end_time": None,
            "execution_times": {}  # mode -> total seconds
        }

        # Note: Per-query agent logging is set up dynamically during candidate mode execution

    def get_query_results_dir(self, query_id: str) -> Path:
        """Get results directory for a specific query."""
        return self.results_dir / query_id

    def get_query_result_path(self, query_id: str, filename: str) -> Path:
        """Get result file path for a specific query."""
        results_dir = self.get_query_results_dir(query_id)
        results_dir.mkdir(parents=True, exist_ok=True)
        return results_dir / filename

    def load_queries(self, yaml_path: Path) -> List[dict]:
        """
        Load queries from YAML file.

        Expected format:
        ```yaml
        queries:
          - query: "trace source of ..."
            groundtruth: "TXHASH123..."
            metadata:
              query_id: "abc123..."
              pair: BTC-DOGE
              time_diff: 166
        ```

        Returns:
            List of query dicts, each with query_id from metadata

        Raises:
            ValueError: If any query is missing query_id in metadata
        """
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        queries = data.get('queries', [])

        # Validate that all queries have query_id in metadata
        for i, query_item in enumerate(queries, 1):
            metadata = query_item.get('metadata', {})
            if 'query_id' not in metadata:
                raise ValueError(
                    f"Query at index {i} is missing 'query_id' in metadata.\n"
                    f"Each query must have metadata.query_id field."
                )

        logger.info(f"Loaded {len(queries)} queries from {yaml_path}")
        return queries

    def _extract_ground_truth(self, query_item: dict) -> str | None:
        """
        Extract ground truth transaction hash from query item.

        Expects `groundtruth` field in YAML.
        """
        gt = query_item.get("groundtruth")
        if gt and isinstance(gt, str):
            return gt.strip().upper()
        return None

    def validate_modes(self, yaml_path: Path):
        """
        Validate that required input files exist for the selected modes.

        Raises:
            ValueError: If required input files are missing
        """
        for mode in self.modes:
            if mode == "candidate":
                # candidate只需要yaml
                if not yaml_path.exists():
                    raise ValueError(f"YAML file not found: {yaml_path}")

            elif mode == "score":
                # score需要yaml + results/{query_id}/candidate_cclinks.json
                if not yaml_path.exists():
                    raise ValueError(f"YAML file not found: {yaml_path}")
                # Only check if candidate results exist when candidate mode is NOT in the pipeline
                if "candidate" not in self.modes:
                    if not self.results_dir.exists() or not any(self.results_dir.iterdir()):
                        raise ValueError(
                            f"Score mode requires candidate results in {self.results_dir}\n"
                            f"Please run 'candidate' mode first."
                        )

            elif mode == "evaluate":
                # evaluate需要yaml + results/{query_id}/score_table.json
                if not yaml_path.exists():
                    raise ValueError(f"YAML file not found: {yaml_path}")
                # Only check if score results exist when score mode is NOT in the pipeline
                if "score" not in self.modes:
                    if not self.results_dir.exists() or not any(self.results_dir.iterdir()):
                        raise ValueError(
                            f"Evaluate mode requires score results in {self.results_dir}\n"
                            f"Please run 'score' mode first."
                        )

    def run_candidate_mode(self, yaml_path: Path, limit: int = None, offset: int = 0):
        """
        Mode 1: Run queries through validate_node, extract and save CCLinks.

        For each query:
        1. Initialize state with query
        2. Run graph to validate_node
        3. Extract state["cclinks"]
        4. Save to results/{query_id}/candidate_cclinks.json
        5. Log to results/{query_id}/agent.log

        Args:
            yaml_path: Path to YAML file
            limit: Limit to N queries (from offset position)
            offset: Skip first N queries (0-indexed)
        """
        all_queries = self.load_queries(yaml_path)

        # Apply offset and limit
        end_idx = offset + limit if limit else len(all_queries)
        queries = all_queries[offset:end_idx]

        if not queries:
            logger.warning(f"No queries to process (offset={offset}, limit={limit}, total={len(all_queries)})")
            return

        mode_start = time.time()

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"MODE: CANDIDATE - Extracting CCLinks")
            print(f"{'=' * 60}")
            if offset > 0 or limit:
                print(f"Processing queries [{offset}:{end_idx}] ({len(queries)} queries)")
            else:
                print(f"Processing {len(queries)} queries...")

        logger.info(f"[candidate mode] Processing {len(queries)} queries (offset={offset}, limit={limit})")

        # Get graph
        graph = SUBGRAPH_MAP["tracetx"]

        for i, query_item in enumerate(queries, 1):
            # Extract query_id from metadata
            query_id = query_item.get("metadata", {}).get("query_id")
            if not query_id:
                logger.warning(f"[Index {i}] Skipped (missing query_id in metadata)")
                continue

            query = query_item.get("query", "").strip()
            if not query:
                logger.info(f"[Query {query_id}] Skipped (empty)")
                continue

            if self.verbose:
                print(f"\n[{i}/{len(queries)}] Query {query_id[:16]}...: {query[:60]}...")

            # Setup per-query agent log file
            agent_log_path = self.get_query_result_path(query_id, "agent.log")
            case_handler = logging.FileHandler(agent_log_path, mode='w', encoding='utf-8')
            case_handler.setLevel(logging.DEBUG)  # Handler accepts DEBUG and above
            case_handler.setFormatter(logging.Formatter(config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT))

            # Add handler to root logger to capture logs
            # Note: We don't change logger levels here - they are controlled by config.setup_logging()
            # This way, the file handler respects the global VERBOSE_LEVEL settings
            root_logger = logging.getLogger()
            root_logger.addHandler(case_handler)

            start_time = time.time()

            try:
                # Initialize state
                state = initialize_state(query=query)

                # Run graph to END (goes through validate -> score)
                # Graph execution will automatically use the current log level
                final_state = graph.invoke(state)

                execution_time = time.time() - start_time

                # Extract cclinks
                cclinks = final_state.get("cclinks", [])

                if self.verbose:
                    print(f"  ✓ Found {len(cclinks)} CCLinks in {execution_time:.2f}s")

                logger.info(
                    f"[Query {query_id}] Success: {len(cclinks)} cclinks in {execution_time:.2f}s"
                )

                # Save to individual JSON file
                result_data = {
                    "query_id": query_id,
                    "metadata": query_item.get("metadata", {}),
                    "cclinks": [serialize_cclink(cclink) for cclink in cclinks],
                    "execution_time": execution_time,
                    "success": True
                }
                result_path = self.get_query_result_path(query_id, "candidate_cclinks.json")
                with open(result_path, 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, indent=2, ensure_ascii=False)

                self.stats["completed_cases"] += 1

            except Exception as e:
                execution_time = time.time() - start_time
                error_msg = str(e)

                if self.verbose:
                    print(f"  ✗ ERROR: {error_msg}")

                logger.error(
                    f"[Query {query_id}] Failed after {execution_time:.2f}s: {error_msg}",
                    exc_info=True
                )

                # Save error case
                result_data = {
                    "query_id": query_id,
                    "metadata": query_item.get("metadata", {}),
                    "cclinks": [],
                    "execution_time": execution_time,
                    "success": False,
                    "error": error_msg
                }
                result_path = self.get_query_result_path(query_id, "candidate_cclinks.json")
                with open(result_path, 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, indent=2, ensure_ascii=False)

                self.stats["failed_cases"] += 1

            finally:
                # Remove case-specific log handler
                root_logger.removeHandler(case_handler)
                case_handler.close()

        mode_time = time.time() - mode_start
        self.stats["execution_times"]["candidate"] = mode_time
        self.stats["modes_executed"].append("candidate")

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"CANDIDATE MODE COMPLETED in {mode_time:.2f}s")
            print(f"Successful: {self.stats['completed_cases']}")
            print(f"Failed: {self.stats['failed_cases']}")
            print(f"{'=' * 60}")

        logger.info(f"[candidate mode] Completed in {mode_time:.2f}s")

    def run_score_mode(self):
        """
        Mode 2: Read CCLinks, run score_node, save score tables.

        For each case:
        1. Read cclinks from results/{query_id}/candidate_cclinks.json
        2. Run score_node with cclinks
        3. Extract state["score_table"]
        4. Save to results/{query_id}/score_table.json

        Note: No separate log file for score mode (pure logic, results contain all info)
        """
        mode_start = time.time()

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"MODE: SCORE - Generating Score Tables")
            print(f"{'=' * 60}")

        logger.info(f"[score mode] Starting")

        # Collect all query IDs from results directory
        query_ids = []
        for query_dir in sorted(self.results_dir.iterdir()):
            if query_dir.is_dir():
                candidate_path = query_dir / "candidate_cclinks.json"
                if candidate_path.exists():
                    query_id = query_dir.name
                    query_ids.append(query_id)

        if self.verbose:
            print(f"Processing {len(query_ids)} cases...")

        completed = 0
        failed = 0

        for query_id in query_ids:
            if self.verbose:
                print(f"\n[{query_id}] Scoring...")

            start_time = time.time()

            try:
                # Read candidate cclinks
                candidate_path = self.get_query_result_path(query_id, "candidate_cclinks.json")
                with open(candidate_path, 'r', encoding='utf-8') as f:
                    case = json.load(f)

                # Deserialize cclinks
                cclinks = [
                    deserialize_cclink(cclink_data)
                    for cclink_data in case["cclinks"]
                ]

                if not cclinks:
                    # No candidates to score - create empty ScoreTable
                    score_table = ScoreTable(
                        status="NO_CANDIDATES",
                        params=ScoringParams(
                            tau_time=config.SCORING_TAU_TIME,
                            w_time=config.SCORING_W_TIME,
                            w_amount=config.SCORING_W_VALUE,
                            max_fee_rate=config.PRICE_MAX_FEE_RATE,
                            max_deviation_rate=config.PRICE_MAX_DEVIATION_RATE
                        ),
                        candidates=[],
                        best_match=None,
                        summary="No CCLinks to score"
                    )
                else:
                    # Create minimal state for score_node (query not needed by score_node)
                    state = {
                        "cclinks": cclinks,
                        "result": {},
                        "findings": []
                    }

                    # Run score_node
                    updates = score_node(state)
                    score_table = updates.get("score_table")

                execution_time = time.time() - start_time

                if self.verbose:
                    status = score_table.status
                    candidates_count = len(score_table.candidates)
                    print(f"  ✓ Status: {status}, {candidates_count} candidates in {execution_time:.2f}s")

                logger.info(
                    f"[Query {query_id}] Score success in {execution_time:.2f}s"
                )

                # Save to individual JSON file
                result_data = {
                    "query_id": query_id,
                    "metadata": case.get("metadata", {}),
                    "score_table": score_table.to_dict(),  # Serialize with mashumaro
                    "execution_time": execution_time,
                    "success": True
                }
                result_path = self.get_query_result_path(query_id, "score_table.json")
                with open(result_path, 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, indent=2, ensure_ascii=False)

                completed += 1

            except Exception as e:
                execution_time = time.time() - start_time
                error_msg = str(e)

                if self.verbose:
                    print(f"  ✗ ERROR: {error_msg}")

                logger.error(
                    f"[Query {query_id}] Score failed after {execution_time:.2f}s: {error_msg}",
                    exc_info=True
                )

                # Save error case
                result_data = {
                    "query_id": query_id,
                    "metadata": case.get("metadata", {}) if 'case' in locals() else {},
                    "score_table": None,
                    "execution_time": execution_time,
                    "success": False,
                    "error": error_msg
                }
                result_path = self.get_query_result_path(query_id, "score_table.json")
                with open(result_path, 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, indent=2, ensure_ascii=False)

                failed += 1

        mode_time = time.time() - mode_start
        self.stats["execution_times"]["score"] = mode_time
        self.stats["modes_executed"].append("score")

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"SCORE MODE COMPLETED in {mode_time:.2f}s")
            print(f"Successful: {completed}")
            print(f"Failed: {failed}")
            print(f"{'=' * 60}")

        logger.info(f"[score mode] Completed in {mode_time:.2f}s")

    def run_evaluate_mode(self, yaml_path: Path):
        """
        Mode 3: Read score tables, calculate metrics.

        For each case:
        1. Read score_table from results/{query_id}/score_table.json
        2. Read ground_truth from yaml
        3. Calculate metrics (top-k hit rates, MRR)
        4. Save to results/{query_id}/metrics.json

        Also generates aggregated metrics summary.
        """
        mode_start = time.time()

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"MODE: EVALUATE - Calculating Metrics")
            print(f"{'=' * 60}")

        logger.info(f"[evaluate mode] Starting")

        # Load ground truth from yaml
        queries = self.load_queries(yaml_path)
        ground_truth_map = {}  # query_id -> ground_truth
        for query_item in queries:
            query_id = query_item.get("metadata", {}).get("query_id")
            if not query_id:
                continue
            gt = self._extract_ground_truth(query_item)
            if gt:
                ground_truth_map[query_id] = gt

        # Collect all query IDs from results directory
        query_ids = []
        for query_dir in sorted(self.results_dir.iterdir()):
            if query_dir.is_dir():
                score_path = query_dir / "score_table.json"
                if score_path.exists():
                    query_id = query_dir.name
                    query_ids.append(query_id)

        if self.verbose:
            print(f"Evaluating {len(query_ids)} cases...")
            print(f"Ground truth available for {len(ground_truth_map)} cases")

        metric_results = []

        for query_id in query_ids:
            # Read score table
            score_path = self.get_query_result_path(query_id, "score_table.json")
            with open(score_path, 'r', encoding='utf-8') as f:
                case = json.load(f)

            score_table = case.get("score_table")
            ground_truth = ground_truth_map.get(query_id)

            if not ground_truth:
                if self.verbose:
                    print(f"\n[{query_id}] Skipped (no ground truth)")
                logger.info(f"[Query {query_id}] Skipped - no ground truth")
                continue

            if not score_table or not case.get("success"):
                if self.verbose:
                    print(f"\n[{query_id}] Skipped (scoring failed)")
                logger.info(f"[Query {query_id}] Skipped - scoring failed")
                continue

            # Calculate metrics
            metric = calculate_hit_rate(
                score_table=score_table,
                ground_truth=ground_truth,
                k_values=[1, 3, 5, 10]
            )

            metric_results.append(metric)

            # Save individual metric (only rank and total, hit_at_k can be derived)
            result_data = {
                "query_id": query_id,
                "predicted_rank": metric["predicted_rank"],
                "total_candidates": metric["total_candidates"]
            }
            result_path = self.get_query_result_path(query_id, "metrics.json")
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, indent=2, ensure_ascii=False)

            if self.verbose:
                rank = metric["predicted_rank"]
                rank_str = f"#{rank}" if rank else "NOT_FOUND"
                print(f"[{query_id}] Ground truth rank: {rank_str}")

        # Calculate aggregated metrics
        if metric_results:
            aggregated = aggregate_metrics(metric_results)

            if self.verbose:
                print(f"\n{'=' * 60}")
                print(f"AGGREGATED METRICS")
                print(f"{'=' * 60}")
                print(f"Total evaluated: {len(metric_results)}")
                print(f"Found rate: {aggregated['found_rate']:.2%}")
                print(f"\nTop-K Hit Rates:")
                for k, rate in sorted(aggregated['hit_rates'].items()):
                    print(f"  Top-{k:2d}: {rate:6.2%}")
                print(f"\nMRR: {aggregated['mrr']:.4f}")
                print(f"Avg Initial Candidates: {aggregated['avg_initial_candidates']:.1f}")
                print(f"Avg Valid Candidates: {aggregated['avg_valid_candidates']:.1f}")

            # Save aggregated summary
            aggregated["timestamp"] = datetime.now().isoformat()
            with open(self.aggregated_metrics_path, 'w', encoding='utf-8') as f:
                json.dump(aggregated, f, indent=2, ensure_ascii=False)

        else:
            if self.verbose:
                print(f"\nNo valid cases to evaluate")

        mode_time = time.time() - mode_start
        self.stats["execution_times"]["evaluate"] = mode_time
        self.stats["modes_executed"].append("evaluate")

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"EVALUATE MODE COMPLETED in {mode_time:.2f}s")
            print(f"{'=' * 60}")

        logger.info(f"[evaluate mode] Completed in {mode_time:.2f}s")

    def save_stats(self):
        """Save runtime statistics to stats.json."""
        with open(self.stats_path, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, indent=2, ensure_ascii=False)

        logger.info(f"Stats saved to {self.stats_path}")

    def run_batch(self, yaml_path: Path, limit: int = None, offset: int = 0):
        """
        Run batch evaluation with selected modes.

        Args:
            yaml_path: Path to YAML file with queries
            limit: Limit to N queries (from offset position)
            offset: Skip first N queries (0-indexed)

        The method will:
        1. Validate that required input files exist
        2. Run each mode in order
        3. Save stats.json with execution summary
        """
        self.stats["start_time"] = datetime.now().isoformat()

        if self.verbose:
            print(f"\n{'#' * 60}")
            print(f"BENCHMARK RUN: {yaml_path.name}")
            print(f"{'#' * 60}")
            print(f"Modes: {' -> '.join(self.modes)}")
            print(f"Output: {self.output_dir}")
            print(f"{'#' * 60}")

        logger.info(f"Starting benchmark run: {yaml_path}")
        logger.info(f"Modes: {self.modes}")

        # Validate modes
        try:
            self.validate_modes(yaml_path)
        except ValueError as e:
            logger.error(f"Mode validation failed: {e}")
            if self.verbose:
                print(f"\n❌ ERROR: {e}")
            raise

        # Run each mode
        for mode in self.modes:
            if mode == "candidate":
                self.run_candidate_mode(yaml_path, limit=limit, offset=offset)
            elif mode == "score":
                self.run_score_mode()
            elif mode == "evaluate":
                self.run_evaluate_mode(yaml_path)

        # Save final stats
        self.stats["end_time"] = datetime.now().isoformat()
        self.save_stats()

        if self.verbose:
            print(f"\n{'#' * 60}")
            print(f"BENCHMARK COMPLETED")
            print(f"{'#' * 60}")
            total_time = sum(self.stats["execution_times"].values())
            print(f"Total time: {total_time:.2f}s")
            print(f"Modes executed: {' -> '.join(self.stats['modes_executed'])}")
            print(f"Results saved to: {self.output_dir}")
            print(f"{'#' * 60}")

        logger.info(f"Benchmark run completed")


def run_benchmark(
    yaml_path: str,
    output_dir: str,
    modes: List[BenchmarkMode] = None,
    limit: int = None,
    offset: int = 0,
    verbose: bool = True
):
    """
    Convenience function to run benchmark.

    Args:
        yaml_path: Path to YAML file with queries
        output_dir: Directory to save results
        modes: List of modes to execute (default: all three)
        limit: Limit to N queries (from offset position)
        offset: Skip first N queries (0-indexed)
        verbose: Print progress to console
    """
    runner = BenchmarkRunner(
        output_dir=Path(output_dir),
        modes=modes,
        verbose=verbose
    )

    runner.run_batch(yaml_path=Path(yaml_path), limit=limit, offset=offset)
