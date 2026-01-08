# Benchmark System

Batch evaluation system for BlockchainMAS with three-stage pipeline and incremental runs.

## Quick Start

### 1. Basic Usage

Run all three stages (candidate → score → evaluate):

```bash
uv run python -m benchmark \
  --yaml data/queries.yaml \
  --work-dir output/exp1
```

### 2. Run Specific Stages

```bash
# Only candidate extraction
uv run python -m benchmark \
  --yaml data/queries.yaml \
  --work-dir output/exp1 \
  --modes candidate

# Only scoring (no yaml needed)
uv run python -m benchmark \
  --work-dir output/exp1 \
  --modes score

# Only evaluation
uv run python -m benchmark \
  --yaml data/queries.yaml \
  --work-dir output/exp1 \
  --modes evaluate
```

### 3. Incremental Runs

Add more cases to existing directory:

```bash
# First batch
uv run python -m benchmark \
  --yaml data/batch1.yaml \
  --work-dir output/exp1 \
  --modes candidate

# Add more cases (automatically skips duplicates)
uv run python -m benchmark \
  --yaml data/batch2.yaml \
  --work-dir output/exp1 \
  --modes candidate \
  --continue

# Overwrite duplicates if needed
uv run python -m benchmark \
  --yaml data/batch2.yaml \
  --work-dir output/exp1 \
  --modes candidate \
  --continue --force
```

### 4. Limit Queries

```bash
# First 10 queries
uv run python -m benchmark \
  --yaml data/queries.yaml \
  --work-dir output/exp1 \
  --limit 10

# Queries 10-19 (offset 10, limit 10)
uv run python -m benchmark \
  --yaml data/queries.yaml \
  --work-dir output/exp1 \
  --offset 10 \
  --limit 10
```

## Output Files

After running, the work directory contains:

```
output/exp1/
├── run_info.json              # Execution metadata
├── overall_metrics.json       # Aggregated metrics (hit rates, MRR, etc.)
├── run_queries_limit10.log    # Full execution log (auto-saved)
└── results/
    └── {bench_id}/                # Format: NNNNNN_XXXXXXXX (e.g., 000000_d4d39e5c)
        ├── agent.log                # Per-case execution log
        ├── candidate_cclinks.json   # Candidate CCLinks
        ├── score_table.json         # Scoring results
        └── metrics.json             # Per-case metrics with hit_at_k
```

**Benchmark ID (bench_id) Format:**
- Format: `{query_idx:06d}_{query_id[:8]}` (e.g., `000000_d4d39e5c`, `000001_bf444429`)
- `query_idx`: 0-indexed position in YAML (required in `metadata.query_idx`)
- `query_id[:8]`: First 8 characters of query_id hash for uniqueness
- Enables natural sorting in file explorers and IDEs

### Key Metrics (overall_metrics.json)

```json
{
  "summary": {
    "evaluated_cases": 10,
    "found_cases": 9,
    "found_rate": 0.9
  },
  "hit_rates": {
    "1": 0.6,
    "3": 0.7,
    "5": 0.8,
    "10": 0.9,
    "found": 0.9
  },
  "ranking": {
    "mrr": 0.75,
    "mean_rank": 3.2,
    "median_rank": 2.0
  }
}
```

**Key fields:**
- `hit_rates`: Top-K accuracy (includes `"found"` for overall hit rate)
- `mrr`: Mean Reciprocal Rank
- `mean_rank`: Average rank of ground truth in candidates

## Command Reference

### Required Arguments

- `--work-dir DIR`: Working directory for results

### Optional Arguments

- `--yaml FILE`: Query file (required for candidate/evaluate modes)
- `--modes MODE [...]`: Execution stages (default: all three)
  - Options: `candidate`, `score`, `evaluate`
- `--limit N`: Process first N queries (from offset)
- `--offset N`: Skip first N queries (default: 0)
- `--continue`: Continue mode - add cases to existing directory
- `--force`: Force overwrite (for score/evaluate modes or with --continue)
- `-v, -vv, -vvv`: Increase verbosity (INFO, DEBUG, TRACE)
- `--quiet`: Suppress output (errors only)

## Features

- **Three-stage pipeline**: Separate expensive candidate extraction from fast scoring/evaluation
- **Incremental runs**: Use `--continue` to add more cases without re-running existing ones
- **Real-time updates**: Metrics files update after each case completion
- **Complete logging**: All output (print, logging, errors) captured automatically
- **Top-K metrics**: Hit rates for top-1, 3, 5, 10, 20, 50 plus overall found rate

## YAML Format

```yaml
queries:
  - query: "Transfer 0.5 BTC to address xyz..."
    groundtruth: "TX_HASH_123..."
    metadata:
      query_id: "unique_id_123"  # Required: unique identifier
      pair: BTC-DOGE
      time_diff: 166
```

**Important**: Each query must have a unique `query_id` in metadata.

## Common Workflows

### Re-score with new parameters

```bash
# Modify scoring logic
vim src/node/tracetx/score.py

# Re-run score and evaluate (skips candidate extraction)
uv run python -m benchmark \
  --work-dir output/exp1 \
  --yaml data/queries.yaml \
  --modes score evaluate \
  --force
```

### Debug failed cases

```bash
# View ranking details
jq .details.rank_list output/exp1/overall_metrics.json

# Check specific case
cat output/exp1/results/{query_id}/agent.log
cat output/exp1/results/{query_id}/score_table.json
```

### View real-time progress

```bash
# Terminal 1: Run benchmark
uv run python -m benchmark --yaml data/queries.yaml --work-dir output/exp1

# Terminal 2: Watch metrics update
watch -n 1 'jq .summary output/exp1/overall_metrics.json'
```

---

**For detailed documentation**, see [README_DEV.md](README_DEV.md)
