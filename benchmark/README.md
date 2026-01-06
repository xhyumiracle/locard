# BlockchainMAS Benchmark System

批量评估系统，支持 top-k 命中率计算、详细日志记录和断点续跑。

## 功能特性

1. **批量查询执行**：从 YAML 文件加载多个查询并批量执行
2. **Top-K 命中率计算**：自动计算 top-1, 3, 5, 10 的命中率
3. **详细日志记录**：每个查询的完整执行日志保存到文件
4. **断点续跑**：自动保存 checkpoint，支持中断后继续执行
5. **结构化输出**：所有结果以 JSON 格式保存，便于后续分析

## 快速开始

### 1. 准备查询文件

创建 YAML 文件，格式如下：

```yaml
queries:
  - query: "Your query here..."
    comment: "Ground Truth: EXPECTED_TXHASH"
    metadata:
      pair: BTC-DOGE
      time_diff: 166
```

参考 [data/benchmark_template.yaml](../../data/benchmark_template.yaml) 获取完整模板。

### 2. 运行 Benchmark

```bash
# 基本用法
python -m benchmark \
  --yaml data/benchmark_queries.yaml \
  --output benchmark_result/exp1

# 从特定查询开始（覆盖 checkpoint）
python -m benchmark \
  --yaml data/benchmark_queries.yaml \
  --output benchmark_result/exp1 \
  --start-from 10

# 只运行前 5 个查询
python -m benchmark \
  --yaml data/benchmark_queries.yaml \
  --output benchmark_result/exp1 \
  --limit 5

# Debug 模式（详细日志）
python -m benchmark \
  --yaml data/benchmark_queries.yaml \
  --output benchmark_result/exp1 \
  --debug
```

### 3. 查看结果

执行完成后，`output` 目录包含以下文件：

```
benchmark_result/exp1/
├── checkpoint.json      # 断点文件（中断后自动继续）
├── results.json         # 详细结果（每个查询的完整输出）
├── summary.json         # 指标汇总（top-k 命中率等）
└── execution.log        # 完整执行日志（用于 debug）
```

## 输出文件说明

### summary.json

汇总指标，包含：

```json
{
  "total_queries": 10,
  "successful_queries": 9,
  "queries_with_ground_truth": 8,
  "metrics": {
    "hit_rates": {
      "1": 0.75,    // Top-1 命中率 75%
      "3": 0.875,   // Top-3 命中率 87.5%
      "5": 0.875,
      "10": 1.0
    },
    "mrr": 0.8542,                      // Mean Reciprocal Rank
    "found_rate": 1.0,                  // Ground truth 被找到的比例
    "avg_initial_candidates": 12.3,     // 平均初始候选数（排除前）
    "avg_valid_candidates": 8.5         // 平均有效候选数（排除后）
  }
}
```

### results.json

每个查询的详细结果：

```json
{
  "results": [
    {
      "query_id": 1,
      "query": "trace source of ...",
      "ground_truth": "TXHASH123...",
      "success": true,
      "execution_time": 45.23,
      "score_table": {
        "status": "SUCCESS",
        "candidates": [...],
        "best_match": "link_id_123"
      },
      "metadata": {...},
      "timestamp": "2026-01-01T12:00:00"
    }
  ]
}
```

### checkpoint.json

断点信息，支持自动续跑：

```json
{
  "completed_queries": 5,
  "results": [...],
  "timestamp": "2026-01-01T12:30:00"
}
```

## 高级用法

### 1. 断点续跑

系统会自动保存 checkpoint。如果执行被中断（Ctrl+C、网络错误、系统重启等），只需重新运行相同的命令：

```bash
# 第一次运行（在第 5 个查询时中断）
python -m benchmark --yaml data/queries.yaml --output benchmark_result/exp1
# ^C (interrupted)

# 重新运行（自动从第 6 个查询继续）
python -m benchmark --yaml data/queries.yaml --output benchmark_result/exp1
# Resuming from checkpoint: 5 queries already completed
```

如果需要强制从头开始，删除 checkpoint 文件：

```bash
rm benchmark_result/exp1/checkpoint.json
```

### 2. 手动指定起始位置

使用 `--start-from` 可以覆盖 checkpoint，从指定位置开始：

```bash
# 从第 10 个查询开始（跳过前 9 个）
python -m benchmark \
  --yaml data/queries.yaml \
  --output benchmark_result/exp1 \
  --start-from 10
```

### 3. 分段执行

使用 `--start-from` 和 `--limit` 组合，可以只运行特定范围的查询：

```bash
# 只运行第 5-9 个查询（共 5 个）
python -m benchmark \
  --yaml data/queries.yaml \
  --output benchmark_result/exp1 \
  --start-from 5 \
  --limit 5
```

### 4. Debug 模式

开启 debug 模式可以获得更详细的日志：

```bash
python -m benchmark \
  --yaml data/queries.yaml \
  --output benchmark_result/exp1 \
  --debug
```

所有日志都会写入 `execution.log`，包括：
- 每个查询的完整执行过程
- LLM 调用日志
- Tool 调用日志
- 错误堆栈信息

## 指标说明

### Top-K Hit Rate

Top-K 命中率表示 ground truth 出现在前 K 个候选中的比例。

- **Top-1**：最佳匹配就是 ground truth 的比例（精确率）
- **Top-3**：ground truth 在前 3 个候选中的比例
- **Top-5/10**：同理

示例：
```
Top-1: 75%   → 10 个查询中，7 个的最佳匹配是正确的
Top-3: 87.5% → 10 个查询中，8.75 个的正确答案在前 3 中
```

### Mean Reciprocal Rank (MRR)

衡量正确答案排名的倒数平均值。

计算方式：
- 如果 ground truth 排第 1，得分 1.0
- 如果排第 2，得分 0.5
- 如果排第 3，得分 0.333
- 如果未找到，得分 0.0

MRR = 所有查询得分的平均值

### Found Rate

Ground truth 被找到（出现在候选列表中）的比例，不考虑排名。

## 典型工作流程

### 实验 1：基线评估

```bash
# 1. 准备查询集
cp data/benchmark_template.yaml data/exp1_queries.yaml
# 编辑 exp1_queries.yaml，添加 20 个查询

# 2. 运行 benchmark
python -m benchmark \
  --yaml data/exp1_queries.yaml \
  --output benchmark_result/exp1_baseline

# 3. 查看结果
cat benchmark_result/exp1_baseline/summary.json
```

### 实验 2：调整参数后对比

```bash
# 1. 修改 config.py 中的参数
# 例如：调整 SCORING_W_TIME 和 SCORING_W_VALUE

# 2. 用相同查询集重新测试
python -m benchmark \
  --yaml data/exp1_queries.yaml \
  --output benchmark_result/exp2_adjusted

# 3. 对比结果
diff <(jq .metrics benchmark_result/exp1_baseline/summary.json) \
     <(jq .metrics benchmark_result/exp2_adjusted/summary.json)
```

### 实验 3：Debug 特定失败案例

```bash
# 1. 从 results.json 中找到失败的查询 ID

# 2. 只运行该查询，开启 debug
python -m benchmark \
  --yaml data/exp1_queries.yaml \
  --output benchmark_result/debug_q5 \
  --start-from 5 \
  --limit 1 \
  --debug

# 3. 查看详细日志
tail -f benchmark_result/debug_q5/execution.log
```

## Ground Truth 提取规则

系统会自动从 `comment` 字段提取 ground truth：

支持的格式：
```yaml
comment: "Ground Truth: TXHASH123"
comment: "Expected: TXHASH123"
comment: "Answer: TXHASH123"
```

提取逻辑：
1. 找到关键词后的第一个单词
2. 去除标点符号
3. 转换为大写
4. 长度必须 > 20（合理的 hash 长度）

## 常见问题

### Q: Checkpoint 机制如何工作？

A: 每完成一个查询后，系统会自动保存 checkpoint。重新运行时，系统会检测到 checkpoint 并自动继续。

### Q: 如何强制重新运行？

A: 删除 checkpoint 文件或使用 `--start-from 1`。

### Q: 为什么有些查询没有命中率？

A: 只有包含 ground truth 的查询才会计算命中率。确保 YAML 文件中的 `comment` 字段包含正确的格式。

### Q: 如何并行运行多个实验？

A: 使用不同的 `--output` 目录即可并行运行：

```bash
python -m benchmark --yaml data/queries1.yaml --output benchmark_result/exp1 &
python -m benchmark --yaml data/queries2.yaml --output benchmark_result/exp2 &
```

### Q: 如何分析 score_table？

A: `results.json` 中包含每个查询的完整 `score_table`，可以用 Python 脚本进一步分析：

```python
import json

with open('benchmark_result/exp1/results.json') as f:
    data = json.load(f)

for result in data['results']:
    table = result['score_table']
    print(f"Query {result['query_id']}: {table['status']}")
    for i, cand in enumerate(table['candidates'][:5], 1):
        print(f"  {i}. confidence={cand['confidence']:.4f}")
```

## 扩展开发

### 添加自定义指标

编辑 [metrics.py](./metrics.py)，在 `aggregate_metrics()` 中添加新指标：

```python
def aggregate_metrics(results: List[MetricResult]) -> Dict[str, Any]:
    # ... 现有代码 ...

    # 添加自定义指标
    custom_metric = calculate_custom_metric(results)

    return {
        # ... 现有指标 ...
        "custom_metric": custom_metric
    }
```

### 修改 checkpoint 间隔

在 `BenchmarkRunner` 初始化时修改：

```python
runner = BenchmarkRunner(
    output_dir=Path(output_dir),
    checkpoint_interval=5,  # 每 5 个查询保存一次
    verbose=True
)
```

## 技术架构

```
benchmark/
├── __init__.py       # 模块初始化
├── __main__.py       # CLI 入口
├── runner.py         # 核心执行逻辑
│   ├── BenchmarkRunner   # 批量执行器
│   ├── QueryResult       # 单个查询结果
│   └── run_benchmark()   # 便捷函数
├── metrics.py        # 指标计算
│   ├── calculate_hit_rate()   # 单查询命中率
│   ├── aggregate_metrics()    # 汇总指标
│   └── normalize_txhash()     # Hash 标准化
└── README.md         # 本文档
```

关键设计：
1. **直接 invoke subgraph**：`SUBGRAPH_MAP["tracetx"].invoke(state)`
2. **JSON checkpoint**：轻量级断点机制
3. **结构化输出**：直接访问 `ScoreTable` 对象
4. **单进程执行**：所有日志在同一个进程，便于 debug
