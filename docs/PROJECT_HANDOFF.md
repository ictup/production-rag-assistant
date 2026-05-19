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

当前容器化入口：

```text
Dockerfile
.dockerignore
docker-compose.prod.yml
```

## 1. 当前项目状态

这是一个生产风格的 RAG assistant 后端项目。当前阶段已经完成了可本地运行、可 ingest、可检索、可回答、可记录日志、可评测、可 CI 回归的后端 MVP。

当前默认仍然使用 fake generator。embedding 和 generator 都可以在 fake 和 OpenAI 之间切换；只有把对应 provider 改为 `openai` 并配置 `OPENAI_API_KEY` 后才会发真实 OpenAI API 请求。

## 2. 已完成的主要工作

### 后端服务

- FastAPI 应用入口：`backend/app/main.py`
- 健康检查接口：`GET /health`
- RAG 聊天接口：`POST /chat`，支持可选 `session_id`
- RAG 流式聊天接口：`POST /chat/stream`
- 聊天日志查询接口：`GET /chat/logs`
- chat session 创建接口：`POST /chat/sessions`
- chat session 列表接口：`GET /chat/sessions`
- chat session 详情接口：`GET /chat/sessions/{session_id}`
- chat session 历史日志接口：`GET /chat/sessions/{session_id}/logs`
- 文档上传接口：`POST /documents`
- 文档列表接口：`GET /documents`
- 文档详情接口：`GET /documents/{document_id}`
- 文档删除接口：`DELETE /documents/{document_id}`
- 文档索引重建接口：`POST /documents/reindex`
- Prometheus 指标接口：`GET /metrics`
- API key 鉴权：`Authorization: Bearer dev-key`
- workspace 隔离头：`X-Workspace-ID`
- request id 中间件：支持客户端传入 `X-Request-ID`
- 结构化请求日志中间件
- 基础 rate limit 中间件：默认关闭，可按 API key 哈希或客户端 IP 限流
- HTTP 请求指标、RAG refusal 指标、无效 citation 指标、provider token/latency 指标
- OpenAI provider 错误会映射为结构化 API 错误、日志和 metrics
- Web UI：`GET /app/`，支持 session、history、SSE streaming chat、文档上传和 reindex

### 数据库与迁移

- Postgres + pgvector Docker Compose
- Alembic 迁移：
  - `0001_enable_pgvector.py`
  - `0002_create_document_tables.py`
  - `0003_create_chat_logs.py`
  - `0004_create_chat_sessions.py`
- 文档表、chunk 表、chat session 表、chat log 表
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
- embedding provider smoke CLI
- chunk embedding reindex CLI
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
- OpenAI Responses API generator
- generator provider smoke CLI
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
    static/           由 FastAPI 托管的最小 Web UI
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
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_RETRIES=2
OPENAI_RETRY_DELAY_SECONDS=0.25
OPENAI_MAX_OUTPUT_TOKENS=512
EMBEDDING_DIMENSION=1536
```

`text-embedding-3-small` 默认 1536 维，和当前 pgvector schema 匹配。

如果要启用 OpenAI generator，可以继续设置：

```text
GENERATOR_PROVIDER=openai
LLM_MODEL=gpt-5.4-nano
```

跨域访问默认关闭。只有当 API 和前端不在同一个 origin 时，才需要显式配置 CORS。例如本地 Vite 前端或生产前端域名：

```text
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://app.example.com
CORS_ALLOWED_ORIGIN_REGEX=
CORS_ALLOW_CREDENTIALS=false
```

默认 `CORS_ALLOW_CREDENTIALS=false`。当前 API 使用 `Authorization: Bearer ...`，通常不需要浏览器 cookie credential。

基础 rate limit 默认关闭。单实例部署或本地 production compose 可以先开启：

```text
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_EXCLUDED_PATHS=/health,/metrics,/app,/openapi.json,/docs,/redoc
```

限流身份优先使用 `Authorization: Bearer ...` 的 token 哈希；没有 token 时使用客户端 IP。当前实现是进程内滑动窗口，适合单实例保护。多副本部署时应迁移到 Redis、API gateway 或反向代理层限流。

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

聊天 UI 地址：

```text
http://127.0.0.1:8000/app/
```

### 6. 构建并运行后端镜像

构建 API 镜像：

```powershell
docker build -t production-rag-assistant:local .
```

运行 API 容器：

```powershell
docker run --rm --env-file .env -p 8000:8000 production-rag-assistant:local
```

注意：如果只单独运行 API 容器，并且需要连接宿主机上的 Postgres，`.env` 里的数据库 host 不能写 `localhost`，需要改成 `host.docker.internal`。

### 7. 启动 production-style 本地栈

production compose 会把 API、migration job 和 Postgres 放在同一个 Docker network 中。API 容器内部使用 `postgres:5432` 访问数据库，不再依赖宿主机 `localhost`。

首次运行前创建 `.env`：

```powershell
Copy-Item .env.example .env
```

如果本机 `8000` 端口已被占用，先把 `.env` 中的 `API_PORT` 改成空闲端口，例如：

```text
API_PORT=8002
```

校验 compose 配置：

```powershell
docker compose -f docker-compose.prod.yml config --quiet
```

启动完整栈：

```powershell
docker compose -f docker-compose.prod.yml up -d --build
```

查看 API 日志：

```powershell
docker compose -f docker-compose.prod.yml logs -f api
```

停止完整栈：

```powershell
docker compose -f docker-compose.prod.yml down
```

## 6. API 快速验证

### Web UI

启动 API 后，浏览器打开：

```text
http://127.0.0.1:8000/app/
```

默认本地 API key 使用 `dev-key`，workspace 使用 `public`。页面支持：

- 创建 chat session
- 刷新 session 列表
- 加载 session history
- 通过 `POST /chat/stream` 流式展示回答
- 展示回答 sources
- 粘贴或选择 Markdown 文件并调用 `POST /documents`
- 刷新文档列表
- 调用 `POST /documents/reindex` 执行 dry-run 或写入式 reindex

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
- `session_id`

如果要把本次问答挂到某个 chat session，先创建 session，再把返回的 `session.id` 放到 `/chat` 请求体：

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -H "X-Workspace-ID: public" `
  -d "{\"question\":\"What problem does FlashAttention solve?\",\"session_id\":\"<session_id>\"}"
```

如果 `session_id` 不存在，或者不属于当前 `X-Workspace-ID`，接口会返回 `404`，并且不会调用 RAG pipeline，也不会写入 chat log。

### Streaming Chat

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/chat/stream `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -H "X-Workspace-ID: public" `
  -d "{\"question\":\"What problem does FlashAttention solve?\",\"session_id\":\"<session_id>\"}"
```

当前 `POST /chat/stream` 是 SSE 兼容接口，事件顺序为：

- `metadata`
- `answer_delta`
- `final`
- `done`

它复用 `/chat` 的鉴权、workspace、session 校验、日志写入和 metrics。OpenAI generator 已接入 Responses API 的真实 streaming：请求会带 `stream: true`，并解析 `response.output_text.delta` 作为 `answer_delta` 输出。fake generator 也实现了同一套 stream 接口，方便本地测试。

如果 provider 在流式响应开始后失败，`/chat/stream` 会返回 `error` SSE 事件；普通 `/chat` 仍然返回结构化 HTTP 错误。

如果 OpenAI provider 失败，响应会包含结构化错误：

```json
{
  "detail": {
    "error": "provider_error",
    "provider": "openai",
    "category": "rate_limit",
    "retryable": true,
    "request_id": "..."
  }
}
```

### Chat Logs

```powershell
curl.exe http://127.0.0.1:8000/chat/logs `
  -H "Authorization: Bearer dev-key" `
  -H "X-Workspace-ID: public"
```

### Chat Sessions

创建会话：

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat/sessions `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -H "X-Workspace-ID: public" `
  -d "{\"title\":\"GPU systems questions\",\"metadata\":{\"topic\":\"systems\"}}"
```

查询会话列表：

```powershell
curl.exe "http://127.0.0.1:8000/chat/sessions?limit=20&offset=0" `
  -H "Authorization: Bearer dev-key" `
  -H "X-Workspace-ID: public"
```

查询会话详情：

```powershell
curl.exe http://127.0.0.1:8000/chat/sessions/<session_id> `
  -H "Authorization: Bearer dev-key" `
  -H "X-Workspace-ID: public"
```

查询某个会话下的对话历史，按 `created_at` 从旧到新返回：

```powershell
curl.exe "http://127.0.0.1:8000/chat/sessions/<session_id>/logs?limit=50&offset=0" `
  -H "Authorization: Bearer dev-key" `
  -H "X-Workspace-ID: public"
```

响应包含：

- `workspace_id`
- `session_id`
- `total`
- `count`
- `limit`
- `offset`
- `logs`

### Documents

上传 Markdown 文档：

```powershell
curl.exe -X POST http://127.0.0.1:8000/documents `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -H "X-Workspace-ID: public" `
  -d "{\"source_uri\":\"uploads/flashattention.md\",\"markdown\":\"# FlashAttention`n`nFlashAttention reduces HBM traffic.\"}"
```

响应会包含：

- `workspace_id`
- `document_id`
- `content_hash`
- `inserted`
- `chunks_inserted`
- `reason`

```powershell
curl.exe "http://127.0.0.1:8000/documents?limit=20&offset=0" `
  -H "Authorization: Bearer dev-key" `
  -H "X-Workspace-ID: public"
```

响应会包含：

- `workspace_id`
- `total`
- `count`
- `limit`
- `offset`
- `documents`

查询单个文档详情和 chunks：

```powershell
curl.exe http://127.0.0.1:8000/documents/<document_id> `
  -H "Authorization: Bearer dev-key" `
  -H "X-Workspace-ID: public"
```

响应会包含：

- `workspace_id`
- `document`
- `chunks`

删除文档及其 chunks：

```powershell
curl.exe -X DELETE http://127.0.0.1:8000/documents/<document_id> `
  -H "Authorization: Bearer dev-key" `
  -H "X-Workspace-ID: public"
```

响应会包含：

- `workspace_id`
- `document_id`
- `deleted`

重建当前 workspace 下的 chunk embeddings。默认是 dry-run，只统计不写入：

```powershell
curl.exe -X POST http://127.0.0.1:8000/documents/reindex `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -H "X-Workspace-ID: public" `
  -d "{\"dry_run\":true}"
```

确认后写入：

```powershell
curl.exe -X POST http://127.0.0.1:8000/documents/reindex `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -H "X-Workspace-ID: public" `
  -d "{\"dry_run\":false,\"batch_size\":32}"
```

响应会包含：

- `workspace_id`
- `source_uri`
- `model`
- `chunks_matched`
- `chunks_embedded`
- `chunks_updated`
- `dry_run`
- `elapsed_seconds`

### Metrics

```powershell
curl.exe http://127.0.0.1:8000/metrics
```

Provider 失败会暴露为：

```text
rag_provider_errors_total{provider="openai",operation="OpenAI response request",category="rate_limit"} 1
```

Provider 成功调用会暴露 token 和延迟指标：

```text
rag_provider_latency_seconds_count{provider="openai",operation="embedding",model="text-embedding-3-small"} 1
rag_provider_latency_seconds_count{provider="openai",operation="generation",model="gpt-5.4-nano"} 1
rag_provider_tokens_total{provider="openai",model="gpt-5.4-nano",token_type="input"} 1200
rag_provider_tokens_total{provider="openai",model="gpt-5.4-nano",token_type="output"} 240
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
311 passed
```

### Pipeline Smoke

```powershell
uv run python -m backend.app.rag.pipeline_smoke
```

真实 OpenAI 端到端 smoke，不修改 `.env`，临时覆盖 provider/model：

```powershell
uv run python -m backend.app.rag.pipeline_smoke --embedding-provider openai --generator-provider openai --llm-model gpt-5.4-nano
```

### Eval Gate

```powershell
uv run python -m evals.run --format summary --fail-on-failure
```

真实 OpenAI eval，不修改 `.env`，临时覆盖 provider/model：

```powershell
uv run python -m evals.run --format summary --fail-on-failure --no-output --embedding-provider openai --generator-provider openai --llm-model gpt-5.4-nano
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

### Embedding Provider Smoke

启用 OpenAI embedding 后，先确认 key、模型和维度可用：

```powershell
uv run python -m backend.app.rag.embedding_smoke --expected-dimension 1536
```

### Generator Provider Smoke

默认使用 `.env` 中的 `GENERATOR_PROVIDER` 和 `LLM_MODEL`：

```powershell
uv run python -m backend.app.rag.generator_smoke
```

也可以只对本次 smoke 临时覆盖 provider 和 model，不修改 `.env`：

```powershell
uv run python -m backend.app.rag.generator_smoke --provider openai --model gpt-5.4-nano
```

### 重建已有 Chunk Embedding

如果数据库中已有 chunk 是用 fake provider 写入的，切换到 OpenAI embedding 后必须重建 chunk embedding，否则 query embedding 和库内 embedding 不在同一向量空间，vector retrieval 质量会不可靠。

先 dry-run 统计会影响多少 chunk，不会调用 OpenAI，也不会写库：

```powershell
uv run python -m backend.app.rag.reindex_embeddings --workspace-id public
```

确认后再写入：

```powershell
uv run python -m backend.app.rag.reindex_embeddings --workspace-id public --write
```

可以用 `--limit` 做小批量 smoke：

```powershell
uv run python -m backend.app.rag.reindex_embeddings --workspace-id public --limit 2 --write
```

## 8. Makefile 命令速查

```text
make db-up              启动 Postgres/pgvector
make db-down            停止 Docker Compose 服务
make db-logs            查看 Postgres 日志
make prod-config        静默校验 production compose 配置
make prod-build         构建 production API 镜像
make prod-up            启动 production-style 本地栈
make prod-down          停止 production-style 本地栈
make prod-logs          查看 production API 日志
make migrate            执行 Alembic 迁移
make ingest             导入 data/raw
make ingest-dry-run     只解析和 embedding，不写库
make reindex-embeddings-dry-run
                        统计当前 workspace 下待重建 embedding 的 chunk
make reindex-embeddings 用当前 provider 重建并写入 chunk embedding
make inspect-ingestion  检查文档/chunk 数量
make inspect-chat-logs  检查 chat_logs
make inspect-evals      检查 eval 数据集格式
make run-evals          运行 eval summary
make eval-gate          eval 失败时返回非零退出码
make eval-gate-openai   用 OpenAI embedding/generator 运行真实 eval gate
make embedding-smoke    验证当前 embedding provider 能返回正确维度
make generator-smoke    验证当前 generator provider 能返回非空答案
make pipeline-smoke     端到端 pipeline smoke
make pipeline-smoke-openai
                        用 OpenAI embedding/generator 跑真实端到端 smoke
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
    M --> N["Generator provider (fake or OpenAI)"]
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

- OpenAI embedding provider 已有代码、mock 测试和联网 smoke CLI。
- OpenAI generator provider 已有代码和 smoke CLI。
- OpenAI provider 超时、有限重试和错误分类。
- OpenAI provider API 错误响应、结构化日志和 metrics。
- provider API key 配置校验目前覆盖 OpenAI embedding 和 OpenAI generator。
- provider token 统计和 embedding/generation latency 细分指标。
- OpenAI Responses API streaming 已接入 generator 和 `/chat/stream`。
- provider 真实美元成本估算还未实现；建议后续用配置化价格表，不要把频繁变化的官方价格写死在代码里。

### 检索质量

- 真实 reranker。
- 更大的文档集合。
- 更完整的 metadata filter。
- 更强的 query rewrite。
- 多轮对话里的 query contextualization。

### 产品 API

- 文档列表 API 已完成：`GET /documents`。
- 文档详情 API 已完成：`GET /documents/{document_id}`。
- 文档删除 API 已完成：`DELETE /documents/{document_id}`。
- 文档上传 API 已完成：`POST /documents`。
- 文档重新索引 API 已完成：`POST /documents/reindex`。
- 当前已有 CLI 和 API 两种 chunk embedding reindex 入口。
- chat session 表和 `chat_logs.session_id` 迁移已完成。
- chat session repository 和基础 API 已完成：`POST /chat/sessions`、`GET /chat/sessions`、`GET /chat/sessions/{session_id}`。
- workspace 管理 API。
- `/chat` 已支持可选 `session_id`，并会把 chat log 挂到对应会话。
- conversation history API 已完成：`GET /chat/sessions/{session_id}/logs`。
- streaming chat API 已完成：`POST /chat/stream`。
- 底层 OpenAI Responses 真 token streaming 已完成。

### 前端与体验

- 最小 Web UI 已完成：`GET /app/`。
- 聊天 UI 已支持 session 创建、session 列表、history 加载和 SSE streaming。
- 文档 UI 已支持 Markdown 上传、文档列表、reindex dry-run 和 write。
- 没有管理后台。
- 聊天页面还没有更完整的错误恢复体验。

### 生产部署

- backend Dockerfile 已完成：`Dockerfile`。
- `.dockerignore` 已完成，排除 `.env`、`.venv`、缓存和本地报告。
- production docker-compose 已完成：`docker-compose.prod.yml`。
- 部署说明。
- CORS 策略已完成：默认关闭，通过 `CORS_ALLOWED_ORIGINS` 或 `CORS_ALLOWED_ORIGIN_REGEX` 显式开启。
- rate limit 已完成：默认关闭，通过 `RATE_LIMIT_ENABLED` 显式开启。
- 更完整的认证和权限模型。
- secrets 管理。

### 可观测性

- trace/span 集成。
- dashboard 模板。
- 慢查询监控。
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

1. 用真实 `OPENAI_API_KEY` 跑一轮 OpenAI embedding smoke。
2. 对已有 chunk 执行 embedding reindex，确保库内向量和 query 向量来自同一 provider。
3. 用 OpenAI generator 跑 pipeline smoke。
4. 用 OpenAI generator 跑 eval gate。
5. 增加 provider 超时、重试和错误分类。
6. 增加 provider API 错误响应和 metrics。
7. 根据业务需要增加配置化 provider price table，把 token usage 转成成本估算。

需要你提供：

```text
OPENAI_API_KEY
```

如果不用 OpenAI，需要提供目标 provider，例如 Azure OpenAI、Ollama、本地 vLLM。

### 阶段 C：文档管理能力

目标：从 CLI ingest 升级为 API 驱动。

建议步骤：

1. `GET /documents` 查询文档。
2. `GET /documents/{id}` 查询文档详情和 chunks。
3. `DELETE /documents/{id}` 删除文档和 chunks。
4. `POST /documents` 上传文档。
5. `POST /documents/reindex` 重建索引。

### 阶段 D：多轮和前端

目标：形成可演示的完整 assistant。

建议步骤：

1. chat session 表。
2. chat session repository 和基础 API。
3. `/chat` 挂载 session。
4. conversation history。
5. streaming response。
6. 底层 OpenAI Responses 真 token streaming。
7. 简单前端聊天 UI。
8. 文档上传 UI。

### 阶段 E：生产化

目标：部署和长期维护。

建议步骤：

1. backend Dockerfile。已完成。
2. production compose。已完成。
3. CORS。已完成。
4. rate limit。已完成。
5. 环境变量和 secrets 文档。
6. dashboard 和 alert。

## 14. 当前优先级建议

建议下一步优先做：

```text
生产化配置收口：环境变量和 secrets 文档
```

原因：

- OpenAI embedding provider 已经过真实 smoke 验证。
- chunk embedding 已可用 reindex CLI 重建。
- OpenAI generator 已可单独 smoke。
- 真实端到端 pipeline smoke 已可通过 provider/model override 运行。
- OpenAI generator 已可纳入 eval runner。
- OpenAI provider 已有超时、有限重试和错误分类。
- OpenAI provider 错误已可映射到 API 响应、日志和 metrics。
- provider token 统计和 embedding/generation latency 细分已完成，可以支持基础成本估算和性能观察。
- chat session 表、repository、基础 API、`/chat` 的 `session_id` 挂载、conversation history API、API 层 SSE streaming、底层 OpenAI Responses token streaming、最小聊天 UI、文档上传/reindex UI、backend Dockerfile、production compose、CORS 和基础 rate limit 都已完成，下一步系统整理环境变量、secrets 和生产配置说明。

启用 OpenAI embedding 后可以先跑：

```powershell
uv run python -m backend.app.rag.embedding_smoke --expected-dimension 1536
```

然后重建 chunk embedding：

```powershell
uv run python -m backend.app.rag.reindex_embeddings --workspace-id public --write
```

之后验证 generator：

```powershell
uv run python -m backend.app.rag.generator_smoke --provider openai --model gpt-5.4-nano
```

真实端到端 smoke：

```powershell
uv run python -m backend.app.rag.pipeline_smoke --embedding-provider openai --generator-provider openai --llm-model gpt-5.4-nano
```

真实 eval gate：

```powershell
uv run python -m evals.run --format summary --fail-on-failure --no-output --embedding-provider openai --generator-provider openai --llm-model gpt-5.4-nano
```

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
