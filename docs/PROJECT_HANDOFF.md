# Production RAG Assistant 项目交接与快速上手

本文档用于迁移、交接和快速恢复开发环境。它总结目前已经完成的工作、当前架构、运行方式、验证方式，以及后续还需要实现的功能。

当前仓库路径约定：

```text
D:\Learning-2026\RAG-2026
```

当前 GitHub 仓库：

```text
https://github.com/ictup/Production_RAG_Assistant.git
```

## 1. 当前项目状态

这是一个生产风格的 RAG assistant 后端项目。当前阶段已经完成了可本地运行、可 ingest、可检索、可回答、可记录日志、可评测、可 CI 回归的后端 MVP。

当前默认仍然使用 fake embedding provider 和 fake generator，因此本地和 CI 暂时不需要真实模型 API key。OpenAI embedding provider 的代码已经接入，但默认关闭；只有把 `EMBEDDING_PROVIDER=openai` 并配置 `OPENAI_API_KEY` 后才会发真实 API 请求。

## 2. 已完成的主要工作

### 后端服务

- FastAPI 应用入口：`backend/app/main.py`
- 健康检查接口：`GET /health`
- RAG 聊天接口：`POST /chat`
- 聊天日志查询接口：`GET /chat/logs`
- Prometheus 指标接口：`GET /metrics`
- API key 鉴权：`Authorization: Bearer dev-key`
- workspace 隔离头：`X-Workspace-ID`
- request id 中间件：支持客户端传入 `X-Request-ID`
- 结构化请求日志中间件
- HTTP 请求指标、RAG refusal 指标、无效 citation 指标

### 数据库与迁移

- Postgres + pgvector Docker Compose
- Alembic 迁移：
  - `0001_enable_pgvector.py`
  - `0002_create_document_tables.py`
  - `0003_create_chat_logs.py`
- 文档表、chunk 表、chat log 表
- async SQLAlchemy session
- repository 层封装文档 ingest 和聊天日志写入/查询

### Ingestion

- Markdown 文件发现和解析
- YAML frontmatter 元数据解析
- 文本清洗
- Markdown section chunking
- token 计数
- content hash 去重
- fake embedding 生成
- OpenAI-compatible embedding client
- ingest CLI
- ingestion inspect CLI

### RAG Pipeline

- fake embedding client
- OpenAI embedding client
- vector retrieval
- sparse retrieval
- reciprocal rank fusion
- no-op reranker
- prompt 构造
- fake generator
- citation 构建和校验
- retrieval-confidence refusal
- question-level refusal guard
- pipeline smoke CLI

### 安全与拒答

- 检索前问题级 guard
- prompt injection 样式问题拒答
- 明显越界问题拒答
- 无检索结果拒答
- 低检索置信度拒答
- refusal reason 会写入响应、日志和 metrics

### 评测系统

- JSONL eval 数据集
- RAG / refusal / security 三类 case
- eval dataset loader
- deterministic eval runner
- eval summary 和 JSON report
- `eval-gate` 失败门禁
- 默认本地报告：`evals/reports/latest.json`
- CI 报告：`evals/reports/ci.json`

### CI

- GitHub Actions workflow：`.github/workflows/ci.yml`
- CI 步骤包括：
  - `uv sync --frozen`
  - `uv run ruff check .`
  - `uv run pytest`
  - `uv run alembic upgrade head`
  - seed document ingest
  - ingestion inspect
  - pipeline smoke
  - eval gate
  - eval report artifact 上传

## 3. 当前目录结构

```text
backend/
  app/
    api/              FastAPI routes 和 API security
    core/             config、logging、request id
    db/               models、repositories、session、migrations
    observability/    Prometheus metrics middleware 和 registry
    rag/              retrieval、fusion、rerank、prompt、generation、pipeline
  tests/              后端单元测试和集成风格测试

ingestion/
  clean_text.py       文本清洗
  chunking.py         Markdown chunking 和 token 计数
  hashing.py          内容 hash
  ingest.py           Markdown ingest CLI
  inspect_ingestion.py
  parse_markdown.py

evals/
  datasets/           JSONL eval 数据集
  reports/            本地/CI eval 运行报告目录
  loaders.py          eval dataset loader
  models.py           eval 数据模型
  runner.py           deterministic eval runner
  run.py              eval CLI

data/raw/
  llm_systems/        当前 seed Markdown 文档

.github/workflows/
  ci.yml              GitHub Actions CI
```

## 4. 本地环境准备

### 必需工具

- Python 3.11
- uv
- Docker Desktop
- PostgreSQL 客户端可选，但不是必须

### 安装依赖

```powershell
uv sync --frozen
```

如果本机 uv 全局缓存遇到权限问题，可以先确认是否是本机缓存目录问题。CI 中会重新创建干净环境。

### 创建 `.env`

```powershell
Copy-Item .env.example .env
```

默认 `.env.example` 使用 Postgres 端口 `5432`。如果本机已经安装了 PostgreSQL 并占用了 5432，可以把 `.env` 改成：

```text
POSTGRES_PORT=5433
DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5433/rag
SYNC_DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5433/rag
```

当前阶段不需要真实模型 key：

```text
EMBEDDING_PROVIDER=fake
GENERATOR_PROVIDER=fake
RERANKER_PROVIDER=none
API_KEYS=dev-key
```

如果要启用 OpenAI embeddings，需要改成：

```text
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536
```

`text-embedding-3-small` 默认 1536 维，和当前 pgvector schema 匹配。

## 5. 本地启动流程

### 1. 启动数据库

```powershell
make db-up
```

如果 Windows 上没有 make，也可以直接运行：

```powershell
docker compose up -d postgres
```

### 2. 执行数据库迁移

```powershell
uv run alembic upgrade head
```

### 3. 导入 seed 文档

```powershell
uv run python -m ingestion.ingest --input data/raw --workspace-id public
```

### 4. 检查导入结果

```powershell
uv run python -m ingestion.inspect_ingestion --min-documents 2 --min-chunks 2
```

### 5. 启动 API

```powershell
uv run uvicorn backend.app.main:app --reload
```

默认地址：

```text
http://127.0.0.1:8000
```

## 6. API 快速验证

### Health

```powershell
curl.exe http://127.0.0.1:8000/health
```

预期：

```json
{"status":"ok"}
```

### Chat

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -H "X-Workspace-ID: public" `
  -d "{\"question\":\"What problem does FlashAttention solve?\"}"
```

响应应包含：

- `answer`
- `sources`
- `retrieval`
- `usage`
- `citation_valid`
- `request_id`

### Chat Logs

```powershell
curl.exe http://127.0.0.1:8000/chat/logs `
  -H "Authorization: Bearer dev-key" `
  -H "X-Workspace-ID: public"
```

### Metrics

```powershell
curl.exe http://127.0.0.1:8000/metrics
```

## 7. 常用验证命令

### Lint

```powershell
uv run ruff check .
```

### 全量测试

```powershell
uv run pytest
```

当前最近一次本地通过结果：

```text
180 passed
```

### Pipeline Smoke

```powershell
uv run python -m backend.app.rag.pipeline_smoke
```

### Eval Gate

```powershell
uv run python -m evals.run --format summary --fail-on-failure
```

当前 eval 基线：

```text
eval cases: 6/6 passed (100.0%)
- rag_eval_questions: 2/2 passed (100.0%)
- refusal_questions: 2/2 passed (100.0%)
- security_questions: 2/2 passed (100.0%)
```

### 生成 eval JSON 报告

默认写入：

```text
evals/reports/latest.json
```

命令：

```powershell
uv run python -m evals.run --format summary
```

只看终端、不写报告：

```powershell
uv run python -m evals.run --format summary --no-output
```

## 8. Makefile 命令速查

```text
make db-up              启动 Postgres/pgvector
make db-down            停止 Docker Compose 服务
make db-logs            查看 Postgres 日志
make migrate            执行 Alembic 迁移
make ingest             导入 data/raw
make ingest-dry-run     只解析和 embedding，不写库
make inspect-ingestion  检查文档/chunk 数量
make inspect-chat-logs  检查 chat_logs
make inspect-evals      检查 eval 数据集格式
make run-evals          运行 eval summary
make eval-gate          eval 失败时返回非零退出码
make pipeline-smoke     端到端 pipeline smoke
```

## 9. 当前架构流程

```mermaid
flowchart TD
    A["Markdown files in data/raw"] --> B["ingestion.ingest"]
    B --> C["Document and chunk tables"]
    C --> D["Embeddings stored in pgvector"]
    E["POST /chat"] --> F["API key and workspace"]
    F --> G["Question-level refusal guard"]
    G --> H["Vector retrieval"]
    G --> I["Sparse retrieval"]
    H --> J["RRF fusion"]
    I --> J
    J --> K["Retrieval confidence refusal"]
    K --> L["Reranker"]
    L --> M["Prompt builder"]
    M --> N["Fake generator"]
    N --> O["Citation validation"]
    O --> P["Chat response"]
    P --> Q["Chat log persistence"]
    P --> R["Metrics"]
    S["evals.run"] --> E
```

## 10. 迁移到新机器的步骤

1. Clone 仓库。

```powershell
git clone https://github.com/ictup/Production_RAG_Assistant.git
cd Production_RAG_Assistant
```

2. 安装依赖。

```powershell
uv sync --frozen
```

3. 创建 `.env`。

```powershell
Copy-Item .env.example .env
```

4. 如果本机 5432 已被占用，修改 `.env` 使用 5433。

5. 启动数据库。

```powershell
docker compose up -d postgres
```

6. 执行迁移。

```powershell
uv run alembic upgrade head
```

7. 导入 seed 文档。

```powershell
uv run python -m ingestion.ingest --input data/raw --workspace-id public
```

8. 跑验证。

```powershell
uv run ruff check .
uv run pytest
uv run python -m backend.app.rag.pipeline_smoke
uv run python -m evals.run --format summary --fail-on-failure
```

9. 启动 API。

```powershell
uv run uvicorn backend.app.main:app --reload
```

## 11. GitHub Actions 注意事项

CI 文件：

```text
.github/workflows/ci.yml
```

CI 当前不需要任何 secrets，因为使用 fake provider。推送后如果 GitHub 没有出现 workflow run，需要在 GitHub 仓库页面检查：

```text
Repository -> Actions
Repository -> Settings -> Actions -> General
```

确认 Actions 已启用。

## 12. 当前还没有实现的功能

### 模型与 provider

- OpenAI embedding provider 已有代码和 mock 测试，但还没有用真实 `OPENAI_API_KEY` 做联网 smoke。
- 真实 LLM generator，例如 OpenAI chat/completions。
- provider 超时、重试、错误分类。
- provider API key 配置校验目前只覆盖 OpenAI embedding。
- provider usage/token/cost 统计。

### 检索质量

- 真实 reranker。
- 更大的文档集合。
- 更完整的 metadata filter。
- 更强的 query rewrite。
- 多轮对话里的 query contextualization。

### 产品 API

- 文档上传 API。
- 文档删除 API。
- 文档重新索引 API。
- workspace 管理 API。
- chat session / conversation API。
- streaming chat API。

### 前端与体验

- 当前没有前端 UI。
- 没有管理后台。
- 没有文档上传页面。
- 没有聊天页面。

### 生产部署

- backend Dockerfile。
- production docker-compose。
- 部署说明。
- CORS 策略。
- rate limit。
- 更完整的认证和权限模型。
- secrets 管理。

### 可观测性

- trace/span 集成。
- dashboard 模板。
- 慢查询监控。
- provider latency 细分指标。
- eval 趋势记录。

## 13. 推荐后续路线

### 阶段 A：文档和迁移收尾

目标：让任何新机器可以按文档跑起来。

建议步骤：

1. 扩展 README，让它成为项目主页。
2. 增加 `.env.example` 中真实 provider 的占位配置。
3. 确认 GitHub Actions 在远端实际运行。

### 阶段 B：接入真实模型

目标：从 fake RAG 变成真实 RAG。

建议步骤：

1. 用真实 `OPENAI_API_KEY` 跑一轮 OpenAI embedding ingest smoke。
2. 增加 OpenAI generator provider。
3. 增加 provider 超时、重试和错误分类测试。
4. 用真实 key 跑一轮 ingest 和 eval。

需要你提供：

```text
OPENAI_API_KEY
```

如果不用 OpenAI，需要提供目标 provider，例如 Azure OpenAI、Ollama、本地 vLLM。

### 阶段 C：文档管理能力

目标：从 CLI ingest 升级为 API 驱动。

建议步骤：

1. `POST /documents` 上传文档。
2. `GET /documents` 查询文档。
3. `DELETE /documents/{id}` 删除文档和 chunks。
4. `POST /documents/reindex` 重建索引。

### 阶段 D：多轮和前端

目标：形成可演示的完整 assistant。

建议步骤：

1. chat session 表。
2. conversation history。
3. streaming response。
4. 简单前端聊天 UI。
5. 文档上传 UI。

### 阶段 E：生产化

目标：部署和长期维护。

建议步骤：

1. backend Dockerfile。
2. production compose。
3. 环境变量和 secrets 文档。
4. rate limit。
5. CORS。
6. dashboard 和 alert。

## 14. 当前优先级建议

建议下一步优先做：

```text
用真实 OPENAI_API_KEY 验证 OpenAI embedding provider
```

原因：

- OpenAI embedding client 已经有 mock 测试，但还没经过真实 API 验证。
- embedding provider 是 RAG 质量的第一关键依赖。
- 完成真实 embedding smoke 后，后续接 OpenAI generator 会更稳。

然后再做：

```text
接入真实 LLM generator
```

这样项目就会从“本地教学型 RAG”进入“真实模型驱动 RAG”的阶段。

## 15. 快速故障排查

### 端口 5432 被占用

修改 `.env`：

```text
POSTGRES_PORT=5433
DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5433/rag
SYNC_DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5433/rag
```

然后重启 Docker Compose：

```powershell
docker compose down
docker compose up -d postgres
```

### pipeline smoke 无 sources

通常是没有执行 ingest，或者数据库不是当前 `.env` 指向的数据库。

检查：

```powershell
uv run python -m ingestion.inspect_ingestion --min-documents 1 --min-chunks 1
```

### eval gate 失败

先看报告：

```text
evals/reports/latest.json
```

常见失败类型：

- `missing_expected_sources`
- `missing_expected_keywords`
- `expected_valid_citation`
- `expected_refusal`
- `runner_error`

### `/chat` 返回 401

确认 header：

```text
Authorization: Bearer dev-key
```

如果 `.env` 修改了 `API_KEYS`，请求里的 Bearer token 也要同步修改。

### GitHub Actions 没有运行

检查仓库 Actions 设置是否启用。CI 文件已经在仓库内，但 GitHub 可能需要手动允许 Actions。
