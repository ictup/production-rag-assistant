# Eval Trends

本文档说明如何把每次 RAG eval 的结果追加到本地 JSONL 趋势文件中，用于观察通过率、失败原因和不同数据集表现的变化。

## 适用场景

单次完整报告适合排查某一次失败：

```text
evals/reports/latest.json
```

趋势记录适合长期对比多次运行：

```text
evals/reports/trends.jsonl
```

`trends.jsonl` 是本地运行产物，已被 `.gitignore` 忽略，不应提交到仓库。

## 运行命令

本地 fake provider 趋势记录：

```powershell
uv run python -m evals.run --format summary --trend-output evals/reports/trends.jsonl
```

也可以使用 Makefile：

```powershell
make eval-trend
```

真实 OpenAI provider 趋势记录，不写完整 JSON 报告：

```powershell
uv run python -m evals.run --format summary --fail-on-failure --no-output --trend-output evals/reports/trends.jsonl --embedding-provider openai --generator-provider openai --llm-model gpt-5.4-nano
```

## 记录内容

每一行是一次 eval run 的 compact JSON，主要字段包括：

- `recorded_at`：记录时间。
- `run_id`：单次运行 ID。
- `total_cases`、`passed_cases`、`failed_cases`、`pass_rate`：整体结果。
- `datasets`：按数据集拆分的通过率。
- `failure_reasons`：失败原因计数，便于定位回归类型。
- `metadata`：本次运行的 provider、model、workspace、top-k 和 rerank 配置。

示例结构：

```json
{"datasets":[{"case_type":"rag","failed_cases":0,"name":"rag_eval_questions","pass_rate":1.0,"passed_cases":2,"total_cases":2}],"failed_cases":0,"failure_reasons":{},"metadata":{"embedding_provider":"fake","generator_provider":"fake","rerank":true,"workspace_id":"public"},"pass_rate":1.0,"passed_cases":6,"recorded_at":"2026-05-20T08:30:00Z","run_id":"...","total_cases":6}
```

## 查看最近记录

PowerShell：

```powershell
Get-Content evals/reports/trends.jsonl | Select-Object -Last 5
```

如果要进一步分析，可以把 JSONL 导入 notebook、BI 工具，或后续接入 CI artifact / metrics backend。

## 易错点

- `--trend-output` 是显式开启的；普通 `eval-gate` 不会自动追加趋势文件。
- 趋势文件只保存聚合信息，不保存完整 answer 和 source；排查单个 case 仍然看 `latest.json`。
- OpenAI eval 前要保证数据库中的 chunk embedding 和当前 `--embedding-provider` 属于同一向量空间，否则检索质量会失真。
- 趋势文件是本地产物，默认不入库、不入 Git；需要跨机器保留时应作为 artifact 上传或另行归档。
