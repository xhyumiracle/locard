# Locard: The First Agentic Framework for Blockchain Forensics

**Locard** is the first agentic blockchain forensics (ABF) framework that leverages LLM-powered agents for investigation tasks.

- Autonomously orchestrates data retrieval, reasoning, and validation across heterogeneous blockchains
- Currently demonstrates its potential through *cross-chain transaction tracing*
- Built with *LangGraph* for agentic workflows


> *"Every contact leaves a trace."* — Edmond Locard


📄 **Paper**: *LOCARD: An Agentic Framework for Blockchain Forensics* [Under review]

## Installation

```bash
git clone https://github.com/xhyumiracle/locard.git
cd locard
uv sync  # or: pip install -e .
```

**Requirements**: Python ≥3.10

**Setup**: Copy `.env.example` to `.env` and configure API keys (OpenAI/Anthropic/tools).

## Usage

### Single Query

```bash
python -m src.main "What is the source transaction for this cross-chain DOGE output to DFtveSGy9MkgqKc2uvJnhy3bP9gyMaNTEQ in tx 75412AD04820CA91A9212C7E5F1842B0EB434A2592731C4891135FFCA6A32BA8 on DOGE, given that it originates from BTC on BTC?"
```

### Batch Processing

```bash
python -m src.main --batch data/thorchain/queries/sample.yaml

# With parameters
python -m src.main --batch queries.yaml \
  --param tracetx.search_time_offset=120 \
  --param tracetx.w_amount=0.7
```

**YAML format**:
```yaml
queries:
  - query: "What is the source transaction for this cross-chain DOGE output to DFtveSGy9MkgqKc2uvJnhy3bP9gyMaNTEQ in tx 75412AD04820CA91A9212C7E5F1842B0EB434A2592731C4891135FFCA6A32BA8 on DOGE, given that it originates from BTC on BTC?"
    groundtruth: "8F299E3F9738B9971E2CCFA68E1F8FFE6B16696EFB0B2F6C7720EF6285EC5AD3"
```
> only "query" goes to the agent, other fields won't

### Parameters

Configure via `--param KEY=VALUE`:

```bash
# TraceTx parameters
--param tracetx.search_time_offset=60    # Search window (minutes)
--param tracetx.max_time_delta=3600      # Max time difference (seconds)
--param tracetx.tau_time=600             # Time scoring parameter
--param tracetx.w_time=0.3               # Time weight
--param tracetx.w_amount=0.7             # Amount weight

# TraceGroupTx parameters
--param max_hops=1                       # Maximum ancestor trace depth
--param min_value=0.5                    # Minimum ancestor value
```

## Testing

```bash
uv run pytest tests/                     # All tests
uv run pytest tests/test_tool_*.py       # Tool tests
uv run pytest tests/test_workflow_*.py   # Workflow tests
```

## Benchmark

For evaluation, you can:
- Use [ThorChain-2025 dataset](data/thorchain/README.md) (benchmark dataset used in the paper)
- Use the [benchmark pipeline](benchmark/README.md) (benchmark framework)

### Reproduce Paper Results

Quick start with ThorChain-2025 dataset:

```bash
# 1. Download dataset
git submodule update --init data/thorchain

# 2. Generate queries
uv run python data/thorchain/script/process/gen_query.py \
  --batch \
  --input-dir data/thorchain-2025-high-fast-mini \
  --output-dir data/thorchain/queries/thorchain-2025-high-fast-mini

# 3. Run benchmark
uv run python -m benchmark \
  --yaml data/thorchain/queries/thorchain-2025-high-fast-mini/BTC-DOGE.yaml \
  --work-dir benchmark_output/btc_doge \
  -vv

# View results
cat benchmark_output/btc_doge/overall_metrics.json
```

**Metrics**: Hit@K (K=1,3,5,10,20,50), MRR, Found rate

### Benchmark Results

**Table: Benchmark results on Thor25HF-mini for single-transfer cross-chain tracing task**

| Pair     | Recall  | Hit@1  | Hit@3  | Hit@5  | Hit@10 | Hit@20  | Hit@50  |
| -------- | ------- | ------ | ------ | ------ | ------ | ------- | ------- |
| BTC→ETH  | **100** | 15     | 40     | 57     | 72     | 91      | **100** |
| BTC→DOGE | 96      | 15     | 34     | 46     | 66     | 86      | 95      |
| BTC→LTC  | 99      | 16     | 32     | 49     | 71     | 93      | 98      |
| ETH→BTC  | 96      | 4      | 12     | 24     | 43     | 66      | 93      |
| ETH→DOGE | 93      | 19     | 48     | 63     | 76     | 83      | 91      |
| ETH→LTC  | 98      | 31     | 60     | 67     | 84     | 95      | 98      |
| DOGE→BTC | **100** | 38     | 75     | **94** | **98** | **100** | **100** |
| DOGE→ETH | 97      | **62** | 88     | 93     | 95     | 96      | 97      |
| DOGE→LTC | 99      | 52     | **89** | **94** | **98** | 99      | 99      |
| LTC→BTC  | 96      | 8      | 17     | 30     | 63     | 83      | 94      |
| LTC→ETH  | 96      | 18     | 47     | 69     | 86     | 93      | 96      |
| LTC→DOGE | 98      | 27     | 54     | 68     | 80     | 93      | 98      |

## Architecture

```
locard/
├── src/
│   ├── node/          # LangGraph nodes (orchestrator, fetcher, validator, scorer)
│   ├── agents/        # LLM agent implementations
│   ├── graph/         # Subgraph definitions (TraceTx, TraceGroupTx)
│   ├── tools/         # Blockchain API tools (3xpl, Bitquery, Blockchair)
│   └── state/         # State definitions
├── tests/             # Test suite
├── benchmark/         # Evaluation pipeline
└── data/              # Datasets and queries
```
