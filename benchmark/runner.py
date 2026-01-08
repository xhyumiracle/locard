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
import sys
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


class TeeOutput:
    """Redirect stdout/stderr to both console and file."""
    def __init__(self, file_path: Path, original_stream):
        self.file = open(file_path, 'w', encoding='utf-8')
        self.original_stream = original_stream

    def write(self, message):
        self.original_stream.write(message)
        self.file.write(message)
        self.file.flush()

    def flush(self):
        self.original_stream.flush()
        self.file.flush()

    def close(self):
        self.file.close()

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
        verbose: bool = True,
        force: bool = False,
        continue_mode: bool = False
    ):
        """
        Initialize benchmark runner.

        Args:
            output_dir: Directory to save results
            modes: List of modes to execute in order (default: all three)
            verbose: Print progress to console
            force: Force overwrite for score/evaluate modes (candidate never overwrites)
            continue_mode: Continue mode - append to existing work directory

        Raises:
            ValueError: If candidate mode and output_dir is not empty
        """
        self.output_dir = Path(output_dir)
        self.modes = modes or ["candidate", "score", "evaluate"]
        self.verbose = verbose
        self.force = force
        self.continue_mode = continue_mode

        # Check output directory based on modes
        if continue_mode:
            # Continue mode: work directory must exist
            if not self.output_dir.exists():
                raise ValueError(
                    f"--continue requires existing work directory: {self.output_dir}\n"
                    f"The directory does not exist. Please check the path."
                )
        elif self.output_dir.exists():
            # Directory exists - give helpful hints and exit gracefully
            if "candidate" in self.modes:
                if any(self.output_dir.iterdir()):
                    # Check if there are existing results
                    results_dir = self.output_dir / "results"
                    has_results = results_dir.exists() and any(results_dir.iterdir())

                    if has_results:
                        print(f"💡 Work directory already contains results: {self.output_dir}")
                        print(f"   To add more cases, use: --continue")
                        print(f"   To overwrite existing cases, use: --continue --force")
                        import sys
                        sys.exit(0)
            # Score/Evaluate modes: Give hint if not using force
            elif not force:
                # Check if results directory exists and has content
                results_dir = self.output_dir / "results"
                if results_dir.exists() and any(results_dir.iterdir()):
                    print(f"💡 Overwriting existing score_table.json and metrics.json files")
                    print(f"   Use --force to confirm overwriting")
                    import sys
                    sys.exit(0)
        else:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # Directory structure:
        # results/{query_id}/agent.log, candidate_cclinks.json, score_table.json, metrics.json
        # run_info.json, overall_metrics.json (at root)
        self.results_dir = self.output_dir / "results"
        self.run_info_path = self.output_dir / "run_info.json"
        self.overall_metrics_path = self.output_dir / "overall_metrics.json"

        # Create directories
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Load existing run_info if in continue mode
        if continue_mode and self.run_info_path.exists():
            with open(self.run_info_path, 'r', encoding='utf-8') as f:
                self.run_info = json.load(f)
        else:
            # Initialize new run_info structure
            self.run_info = {
                "total_cases": 0,  # Total unique cases in work directory
                "execution_time": 0.0,  # Cumulative execution time from all runs
                "runs": []  # List of candidate mode runs
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

    def scan_existing_cases(self) -> set:
        """
        Scan results/ directory to get existing case IDs.

        Returns:
            Set of query_id strings that have results directories
        """
        if not self.results_dir.exists():
            return set()

        existing = set()
        for item in self.results_dir.iterdir():
            if item.is_dir():
                existing.add(item.name)

        return existing

    def update_total_cases(self):
        """Update total_cases in run_info by scanning results/ directory."""
        self.run_info["total_cases"] = len(self.scan_existing_cases())

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

    def validate_modes(self, yaml_path: Path = None):
        """
        Validate that required input files exist for the selected modes.

        Args:
            yaml_path: Path to YAML file (can be None for score-only mode)

        Raises:
            ValueError: If required input files are missing
        """
        for mode in self.modes:
            if mode == "candidate":
                # candidate needs yaml
                if not yaml_path or not yaml_path.exists():
                    raise ValueError(f"Candidate mode requires --yaml parameter with valid file")

            elif mode == "score":
                # score only needs existing candidate results (no yaml needed)
                # Only check if candidate results exist when candidate mode is NOT in the pipeline
                if "candidate" not in self.modes:
                    if not self.results_dir.exists():
                        raise ValueError(
                            f"Score mode requires candidate results in {self.results_dir}\n"
                            f"Please run 'candidate' mode first."
                        )
                    # Check if at least one candidate_cclinks.json exists
                    has_candidate = False
                    for query_dir in self.results_dir.iterdir():
                        if query_dir.is_dir() and (query_dir / "candidate_cclinks.json").exists():
                            has_candidate = True
                            break
                    if not has_candidate:
                        raise ValueError(
                            f"Score mode requires candidate_cclinks.json files in {self.results_dir}\n"
                            f"Please run 'candidate' mode first."
                        )

            elif mode == "evaluate":
                # evaluate needs yaml + score_table.json
                if not yaml_path or not yaml_path.exists():
                    raise ValueError(f"Evaluate mode requires --yaml parameter with valid file (for ground truth)")
                # Only check if score results exist when score mode is NOT in the pipeline
                if "score" not in self.modes:
                    if not self.results_dir.exists():
                        raise ValueError(
                            f"Evaluate mode requires score results in {self.results_dir}\n"
                            f"Please run 'score' mode first."
                        )
                    # Check if at least one score_table.json exists
                    has_score_table = False
                    for query_dir in self.results_dir.iterdir():
                        if query_dir.is_dir() and (query_dir / "score_table.json").exists():
                            has_score_table = True
                            break
                    if not has_score_table:
                        raise ValueError(
                            f"Evaluate mode requires score_table.json files in {self.results_dir}\n"
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

        # Check for duplicates if in continue mode
        existing_cases = self.scan_existing_cases()
        query_ids_from_yaml = [q.get("metadata", {}).get("query_id") for q in queries if q.get("metadata", {}).get("query_id")]
        duplicated_cases = [qid for qid in query_ids_from_yaml if qid in existing_cases]
        new_cases = [qid for qid in query_ids_from_yaml if qid not in existing_cases]

        # Handle duplicates in continue mode
        if self.continue_mode:
            if duplicated_cases and not self.force:
                # Skip duplicates - filter to only new cases
                queries = [q for q in queries if q.get("metadata", {}).get("query_id") in new_cases]
            elif duplicated_cases and self.force:
                # Overwrite duplicates - process all queries
                if self.verbose:
                    print(f"⚠️  Overwriting {len(duplicated_cases)} existing case(s)")
            else:
                # No duplicates - process all queries (which are all new)
                pass

        if not queries:
            logger.warning(f"No new queries to process after filtering duplicates")
            return

        mode_start = time.time()
        mode_start_iso = datetime.now().isoformat()

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"MODE: CANDIDATE - Extracting CCLinks")
            print(f"{'=' * 60}")
            if self.continue_mode:
                print(f"Continue mode: {len(existing_cases)} existing, {len(duplicated_cases)} duplicated, {len(new_cases)} new")
            if offset > 0 or limit:
                print(f"Processing queries [{offset}:{end_idx}] ({len(queries)} queries)")
            else:
                print(f"Processing {len(queries)} queries...")

        logger.info(f"[candidate mode] Processing {len(queries)} queries (offset={offset}, limit={limit})")

        # Track stats for this run
        processed_count = 0
        completed_count = 0
        failed_count = 0

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

            processed_count += 1

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

                completed_count += 1

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

                failed_count += 1

            finally:
                # Remove case-specific log handler
                root_logger.removeHandler(case_handler)
                case_handler.close()

        mode_time = time.time() - mode_start

        # Update total_cases by scanning actual results
        self.update_total_cases()

        # Record this run
        run_record = {
            "timestamp": mode_start_iso,
            "yaml_file": str(yaml_path),  # Store user-provided path (relative, not absolute)
            "offset": offset,
            "limit": limit,
            "duplicated_cases": len(duplicated_cases),
            "new_cases": len(new_cases),
            "processed_cases": processed_count,
            "execution_seconds": mode_time
        }
        self.run_info["runs"].append(run_record)

        # Update cumulative execution time
        self.run_info["execution_time"] = sum(r["execution_seconds"] for r in self.run_info["runs"])

        # Save run_info after candidate mode
        self.save_run_info()

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"CANDIDATE MODE COMPLETED in {mode_time:.2f}s")
            print(f"Successful: {completed_count}")
            print(f"Failed: {failed_count}")
            print(f"Total cases in work directory: {self.run_info['total_cases']}")
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
        mode_start_iso = datetime.now().isoformat()

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

        # Update total_cases (in case score mode was run independently)
        self.update_total_cases()

        # Save run_info after score mode
        self.save_run_info()

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
        mode_start_iso = datetime.now().isoformat()

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
                k_values=[1, 3, 5, 10, 20, 50]
            )

            metric_results.append(metric)

            # Save per-case metric with detailed info
            hit_at_k = metric["hit_at_k"]
            result_data = {
                "ground_truth": ground_truth,
                "predicted_rank": metric["predicted_rank"],
                "total_candidates": metric["total_candidates"],
                "valid_candidates": metric["valid_candidates"],
                "hit_at_k": {str(k): v for k, v in hit_at_k.items()}  # Convert int keys to str for JSON
            }
            result_path = self.get_query_result_path(query_id, "metrics.json")
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, indent=2, ensure_ascii=False)

            # Real-time update overall_metrics.json
            aggregated = aggregate_metrics(metric_results)
            aggregated["metadata"] = {"timestamp": datetime.now().isoformat()}
            with open(self.overall_metrics_path, 'w', encoding='utf-8') as f:
                json.dump(aggregated, f, indent=2, ensure_ascii=False)

            if self.verbose:
                rank = metric["predicted_rank"]
                valid_count = metric["valid_candidates"]
                if rank:
                    rank_str = f"#{rank}/{valid_count}"
                else:
                    rank_str = f"NOT_FOUND/{valid_count}"
                # Format: [query_id] GT: HASH... Rank: #3/12
                gt_short = ground_truth[:8] if ground_truth else "N/A"
                print(f"[{query_id}] GT: {gt_short}... Rank: {rank_str}")

        # Calculate aggregated metrics
        if metric_results:
            aggregated = aggregate_metrics(metric_results)

            if self.verbose:
                print(f"\n{'=' * 60}")
                print(f"OVERALL METRICS")
                print(f"{'=' * 60}")
                print(f"Evaluated: {aggregated['summary']['evaluated_cases']}")
                print(f"Found: {aggregated['summary']['found_cases']} ({aggregated['summary']['found_rate']:.2%})")

                print(f"\nTop-K Hit Rates:")
                # Separate numeric keys and "found" key
                numeric_keys = sorted([k for k in aggregated['hit_rates'].keys() if isinstance(k, int)])
                for k in numeric_keys:
                    rate = aggregated['hit_rates'][k]
                    count = aggregated['hit_counts'][k]
                    print(f"  Top-{k:2d}: {rate:6.2%} ({count})")
                # Show "found" at the end
                if "found" in aggregated['hit_rates']:
                    rate = aggregated['hit_rates']["found"]
                    count = aggregated['hit_counts']["found"]
                    print(f"  Found (all): {rate:6.2%} ({count})")

                print(f"\nRanking:")
                print(f"  MRR: {aggregated['ranking']['mrr']:.4f}")
                print(f"  Mean:   {aggregated['ranking']['mean_rank']:.2f}")
                print(f"  Median: {aggregated['ranking']['median_rank']:.1f}")
                print(f"  Min:    {aggregated['ranking']['min_rank']}")
                print(f"  Max:    {aggregated['ranking']['max_rank']}")

                print(f"\nCandidates:")
                print(f"  Avg Initial: {aggregated['candidates']['avg_initial']:.1f}")
                print(f"  Avg Valid:   {aggregated['candidates']['avg_valid']:.1f}")

            # Add metadata and save
            aggregated["metadata"] = {"timestamp": datetime.now().isoformat()}
            with open(self.overall_metrics_path, 'w', encoding='utf-8') as f:
                json.dump(aggregated, f, indent=2, ensure_ascii=False)

        else:
            if self.verbose:
                print(f"\nNo valid cases to evaluate")

        mode_time = time.time() - mode_start

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"EVALUATE MODE COMPLETED in {mode_time:.2f}s")
            print(f"{'=' * 60}")

        logger.info(f"[evaluate mode] Completed in {mode_time:.2f}s")

    def save_run_info(self):
        """Save runtime execution info to run_info.json."""
        with open(self.run_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.run_info, f, indent=2, ensure_ascii=False)

        logger.info(f"Run info saved to {self.run_info_path}")

    def get_run_log_filename(self, yaml_path: Path, limit: int = None, offset: int = 0) -> str:
        """
        Generate log filename for this run.

        Format: run_{filename_without_extension}[_limit{limit}][_offset{offset}].log

        Example:
            - run_cases_1_3.log
            - run_cases_4_10_limit5.log
            - run_cases_4_10_limit5_offset2.log
        """
        if yaml_path:
            base_name = yaml_path.stem  # filename without extension
        else:
            base_name = "score"  # If no yaml (score-only mode)

        parts = [f"run_{base_name}"]

        if limit is not None:
            parts.append(f"limit{limit}")

        if offset > 0:
            parts.append(f"offset{offset}")

        return "_".join(parts) + ".log"

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
        3. Save run_info.json with execution summary
        4. Automatically save full log to run_{filename}.log
        """

        # Setup full run log file (only for candidate mode)
        tee_stdout = None
        tee_stderr = None
        original_stdout = None
        original_stderr = None
        run_log_handler = None

        if "candidate" in self.modes and yaml_path:
            log_filename = self.get_run_log_filename(yaml_path, limit, offset)
            run_log_path = self.output_dir / log_filename

            # Redirect stdout and stderr to capture all output
            original_stdout = sys.stdout
            original_stderr = sys.stderr
            tee_stdout = TeeOutput(run_log_path, original_stdout)
            sys.stdout = tee_stdout
            sys.stderr = tee_stdout  # Also capture errors

            # Also add logging handler for logger outputs
            run_log_handler = logging.FileHandler(run_log_path, mode='a', encoding='utf-8')
            run_log_handler.setLevel(logging.DEBUG)
            run_log_handler.setFormatter(logging.Formatter(config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT))
            root_logger = logging.getLogger()
            root_logger.addHandler(run_log_handler)

            if self.verbose:
                print(f"Full run log will be saved to: {log_filename}")

        if self.verbose:
            print(f"\n{'#' * 60}")
            if yaml_path:
                print(f"BENCHMARK RUN: {yaml_path.name}")
            else:
                print(f"BENCHMARK RUN")
            print(f"{'#' * 60}")
            print(f"Modes: {' -> '.join(self.modes)}")
            print(f"Work Dir: {self.output_dir}")
            print(f"{'#' * 60}")

        if yaml_path:
            logger.info(f"Starting benchmark run: {yaml_path}")
        else:
            logger.info(f"Starting benchmark run")
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

        # Save final run info
        self.save_run_info()

        if self.verbose:
            print(f"\n{'#' * 60}")
            print(f"BENCHMARK COMPLETED")
            print(f"{'#' * 60}")
            if self.run_info["runs"]:
                print(f"Total candidate time: {self.run_info['execution_time']:.2f}s")
                print(f"Total runs: {len(self.run_info['runs'])}")
            print(f"Total cases: {self.run_info['total_cases']}")
            print(f"Results saved to: {self.output_dir}")
            print(f"{'#' * 60}")

        logger.info(f"Benchmark run completed")

        # Restore stdout/stderr and close file handlers
        if tee_stdout:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            tee_stdout.close()
            if self.verbose:
                print(f"Full run log saved to: {run_log_path}")

        if run_log_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(run_log_handler)
            run_log_handler.close()


def run_benchmark(
    yaml_path: str = None,
    output_dir: str = None,
    modes: List[BenchmarkMode] = None,
    limit: int = None,
    offset: int = 0,
    verbose: bool = True,
    force: bool = False,
    continue_mode: bool = False
):
    """
    Convenience function to run benchmark.

    Args:
        yaml_path: Path to YAML file with queries (required for candidate/evaluate modes, optional for score)
        output_dir: Directory to save results
        modes: List of modes to execute (default: all three)
        limit: Limit to N queries (from offset position)
        offset: Skip first N queries (0-indexed)
        verbose: Print progress to console
        force: Force overwrite existing results (only for score/evaluate, candidate never overwrites)
        continue_mode: Continue mode - append to existing work directory
    """
    runner = BenchmarkRunner(
        output_dir=Path(output_dir),
        modes=modes,
        verbose=verbose,
        force=force,
        continue_mode=continue_mode
    )

    runner.run_batch(yaml_path=Path(yaml_path) if yaml_path else None, limit=limit, offset=offset)
