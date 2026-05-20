# Production RAG Assistant 项目交接与快速上手

本文档用于迁移、交接和快速恢复开发环境。它总结目前已经完成的工作、当前架构、运行方式、验证方式，以及后续还需要实现的功能。

当前仓库路径约定：

```text
D:\Learning-2026\RAG-2026
```

当前 GitHub 仓库：

```text
https://github.com/ictup/production-rag-assistant.git
```

当前容器化入口：

```text
Dockerfile
.dockerignore
docker-compose.prod.yml
```

当前配置与 secrets 文档：

```text
docs/CONFIGURATION.md
```

当前部署 runbook：

```text
docs/DEPLOYMENT_RUNBOOK.md
```

当前生产 secret manager 映射文档：

```text
docs/SECRET_MANAGER_MAPPING.md
```

当前 release checklist：

```text
docs/RELEASE_CHECKLIST.md
```

当前 release notes：

```text
docs/releases/v0.1.0.md
```

当前 GitHub Release 发布正文：

```text
docs/releases/v0.1.0-github-release.md
```

当前可观测性文档：

```text
docs/OBSERVABILITY.md
```

当前数据库可观测性文档：

```text
docs/DATABASE_OBSERVABILITY.md
```

当前 eval 趋势文档：

```text
docs/EVAL_TRENDS.md
```

当前 Agentic RAG 扩展设计文档：

```text
docs/agentic_rag_extension.md
```

## 1. 当前项目状态

这是一个生产风格的 RAG assistant 后端项目。当前阶段已经完成了可本地运行、可 ingest、可检索、可回答、可记录日志、可评测、可 CI 回归的后端 MVP。

当前默认仍然使用 fake generator、no-op query rewriter 和 no-op reranker。embedding、query rewriter、generator 和 reranker 都可以在本地默认模式和 OpenAI 之间切换；只有把对应 provider 改为 `openai` 并配置 `OPENAI_API_KEY` 后才会发真实 OpenAI API 请求。`/chat` 和 `/chat/stream` 传入 `session_id` 时，会读取最近会话历史并传给 query rewrite，用于多轮 follow-up 检索上下文化。

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
- workspace 创建接口：`POST /workspaces`
- workspace 更新接口：`PATCH /workspaces/{workspace_id}`
- workspace 软归档接口：`POST /workspaces/{workspace_id}/archive`
- workspace 恢复接口：`POST /workspaces/{workspace_id}/restore`
- workspace 跨页批量预览接口：`GET /workspaces/bulk/preview`
- workspace 跨页批量归档确认执行接口：`POST /workspaces/bulk/archive-matching`
- workspace 跨页批量恢复确认执行接口：`POST /workspaces/bulk/restore-matching`
- workspace 批量软归档接口：`POST /workspaces/bulk/archive`
- workspace 批量恢复接口：`POST /workspaces/bulk/restore`
- workspace 操作审计写入：单个归档/恢复、当前页批量归档/恢复、跨页匹配批量归档/恢复会写入 `workspace_audit_logs`
- workspace 操作审计查询接口：`GET /workspaces/audit-logs`
- workspace 归档写保护：归档 workspace 仍可读，但写入型接口返回 `409 workspace archived`
- workspace 列表接口：`GET /workspaces`
- workspace 详情接口：`GET /workspaces/{workspace_id}`
- 文档上传接口：`POST /documents`
- 文档列表接口：`GET /documents`
- 文档详情接口：`GET /documents/{document_id}`
- 文档删除接口：`DELETE /documents/{document_id}`
- 文档索引重建接口：`POST /documents/reindex`
- export job 创建接口：`POST /exports/jobs`
- export job 列表接口：`GET /exports/jobs`
- export job 详情接口：`GET /exports/jobs/{job_id}`
- export job 重试接口：`POST /exports/jobs/{job_id}/retry`
- export job 下载接口：`GET /exports/jobs/{job_id}/download`
- Prometheus 指标接口：`GET /metrics`
- Agentic RAG support triage 接口：`POST /agent/support-triage`，
  当前低风险路径会执行分类、风险检查、RAG 检索、历史工单检索和确定性带引用回复草稿生成
- Agentic RAG 内部编排：当前通过无 LangGraph 依赖的 `AgentGraphRunner`
  顺序执行节点，并在响应中返回 `node_runs` 节点级执行记录
- Agentic RAG 审批持久化基础：`agent_approvals` 表和
  `AgentApprovalRepository` 已支持 pending/approved/rejected 状态流转
- Agentic RAG 审批 API 基础版：`GET /agent/approvals`、
  `GET /agent/approvals/{approval_id}` 和
  `POST /agent/approvals/{approval_id}/decision` 已支持 workspace 权限和
  API key role 检查
- API key 鉴权：`Authorization: Bearer dev-key`
- workspace 隔离头：`X-Workspace-ID`
- API key workspace 访问控制：`API_KEY_WORKSPACE_ACCESS`
- request id 中间件：支持客户端传入 `X-Request-ID`
- trace context 中间件：支持客户端传入 `X-Trace-ID`，并返回 `X-Trace-ID`
- 结构化请求日志中间件
- 结构化 trace/span 日志：`backend.trace`
- 基础 rate limit 中间件：默认关闭，可按 API key 哈希或客户端 IP 限流
- HTTP 请求指标、RAG refusal 指标、无效 citation 指标、provider token/latency/cost 指标
- OpenAI provider 错误会映射为结构化 API 错误、日志和 metrics
- 异步导出 job 基础模型、API、worker 与下载接口：`export_jobs` 表和 `ExportJobRepository` 已支持 pending/running/succeeded/failed 状态流转，`/exports/jobs` 已支持创建、列表、详情、重试和下载查询，`python -m backend.app.exporting.worker` 可执行一个 pending chat log 导出任务，`python -m backend.app.exporting.worker --loop` 可作为常驻 worker 轮询并落地 JSONL/CSV 文件；worker 会按 `EXPORT_JOB_RUNNING_TIMEOUT_SECONDS` 恢复长时间停留在 running 的任务，并按 `EXPORT_FILE_RETENTION_SECONDS` 清理过期导出文件
- Web UI：`GET /app/`，支持 session、history、SSE streaming chat、文档上传、reindex、workspace 创建、编辑、归档、恢复、workspace 搜索、分页、状态过滤、当前页批量归档/恢复和跨页匹配批量预览/确认、归档 workspace 写入控件禁用、只读 admin overview、chat log audit filters、chat log async export job creation/poll/download、chat log audit details、workspace operation audit filters 和 workspace operation audit details

### 数据库与迁移

- Postgres + pgvector Docker Compose
- Alembic 迁移：
  - `0001_enable_pgvector.py`
  - `0002_create_document_tables.py`
  - `0003_create_chat_logs.py`
  - `0004_create_chat_sessions.py`
  - `0005_enable_pg_stat_statements.py`
  - `0006_create_workspaces.py`
  - `0007_add_workspace_foreign_keys.py`
  - `0008_add_workspace_archive_fields.py`
  - `0009_create_workspace_audit_logs.py`
  - `0010_create_export_jobs.py`
  - `0011_create_support_tickets.py`
  - `0012_create_agent_approvals.py`
- 文档表、chunk 表、chat session 表、chat log 表
- workspace 表，包含 `archived_at` 和 `archived_reason` 软归档字段
- workspace 操作审计表 `workspace_audit_logs`，记录 request id、API key hash、action、workspace ids 和操作 metadata
- 异步导出任务表 `export_jobs`，记录 workspace、request id、actor hash、export type、format、filters、status、结果 URI、错误信息和生命周期时间戳
- 历史支持工单表 `support_tickets`，用于 Agentic RAG 工作流按 workspace、
  category、query 和 tags 检索相似案例
- Agentic RAG 审批表 `agent_approvals`，记录高风险 run 的草稿、
  风险原因、tool/node 执行上下文、审批状态和人工反馈
- `pg_stat_statements` 扩展和 Compose 慢查询日志配置
- async SQLAlchemy session
- repository 层封装文档 ingest、聊天日志写入/查询、export job 状态流转和
  agent approval 状态流转

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
- no-op query rewriter
- OpenAI Responses API query rewriter
- session history query contextualization for query rewrite
- vector retrieval
- sparse retrieval
- metadata filter for vector/sparse retrieval
- reciprocal rank fusion
- no-op reranker
- OpenAI Responses API listwise reranker
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
- eval JSONL trend record
- `eval-gate` 失败门禁
- 默认本地报告：`evals/reports/latest.json`
- 默认本地趋势文件：`evals/reports/trends.jsonl`
- CI 报告：`evals/reports/ci.json`

### CI

- GitHub Actions workflow：`.github/workflows/ci.yml`
- 远端 GitHub Actions 已确认会在 `main` push 后运行。
- 最近一次已完成核验：
  - workflow：`CI`
  - event：`push`
  - branch：`main`
  - commit：`2d39e63e8a6e3dfc3a4afd999456e38602a27930`
  - run：`https://github.com/ictup/production-rag-assistant/actions/runs/26154936552`
  - status：`completed`
  - conclusion：`success`
  - created_at：`2026-05-20T09:51:04Z`
  - updated_at：`2026-05-20T09:51:56Z`
  - job：`Backend checks`
  - job conclusion：`success`
- CI 步骤包括：
  - `uv sync --frozen`
  - `uv run ruff check .`
  - `uv run pytest`
  - `uv run alembic upgrade head`
  - seed document ingest
  - ingestion inspect
  - pipeline smoke
  - document-management smoke
  - eval gate
  - eval report artifact 上传

## 3. 当前目录结构

```text
backend/
  app/
    api/              FastAPI routes、API security、workspace routes
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
  trends.py           eval JSONL 趋势记录
  run.py              eval CLI

data/raw/
  llm_systems/        当前 seed Markdown 文档

.github/workflows/
  ci.yml              GitHub Actions CI

monitoring/
  grafana/            Grafana dashboard 模板
  prometheus/         Prometheus alert rule 模板
```

## 4. 本地环境准备

完整配置清单、运行模式和 secrets 规则见：

```text
docs/CONFIGURATION.md
```

生产部署平台 secret manager 映射见：

```text
docs/SECRET_MANAGER_MAPPING.md
```

部署前可以运行不会打印 secret 值的配置预检：

```powershell
uv run python -m backend.app.core.config_check
uv run python -m backend.app.core.config_check --production
```

部署启动、验证、日志、停服和恢复步骤见：

```text
docs/DEPLOYMENT_RUNBOOK.md
```

最终发布门禁见：

```text
docs/RELEASE_CHECKLIST.md
```

指标、dashboard 和 alert 模板见：

```text
docs/OBSERVABILITY.md
```

Postgres 慢查询日志和 `pg_stat_statements` 排查流程见：

```text
docs/DATABASE_OBSERVABILITY.md
```

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
QUERY_REWRITER_PROVIDER=none
QUERY_REWRITE_MODEL=gpt-5.4-nano
QUERY_REWRITE_MAX_OUTPUT_TOKENS=64
QUERY_CONTEXT_HISTORY_LIMIT=4
RERANKER_PROVIDER=none
RERANKER_MODEL=gpt-5.4-nano
API_KEYS=dev-key
API_KEY_ROLES=
API_KEY_WORKSPACE_ACCESS=
```

`API_KEY_ROLES` 为空时，为了兼容本地开发，所有已配置 API key 都拥有
`admin` 权限。生产环境应显式配置：

```text
API_KEY_ROLES=admin-key=admin;operator-key=operator;viewer-key=viewer
```

角色边界：

- `viewer`：读取 workspace、documents、chat logs、audit logs 和 export job。
- `operator`：包含 viewer，并可 chat、创建 session、上传/删除/reindex 文档、创建和重试 export job。
- `admin`：包含 operator，并可创建/更新 workspace、归档/恢复和执行 workspace 批量操作。

`API_KEY_WORKSPACE_ACCESS` 为空时，所有已配置 API key 都可以访问所有 workspace。配置后格式为：

```text
API_KEY_WORKSPACE_ACCESS=dev-key=*;tenant-key=tenant-a|tenant-b
```

如果该变量非空，没有出现在映射里的 API key 不能访问任何 workspace；访问未授权 workspace 会返回 `403 workspace access denied`。

如果要启用 OpenAI embeddings，需要改成：

```text
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=<set locally only>
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_RETRIES=2
OPENAI_RETRY_DELAY_SECONDS=0.25
OPENAI_MAX_OUTPUT_TOKENS=512
EMBEDDING_DIMENSION=1536
```

如果要启用 provider 成本估算，设置每 100 万 token 的输入/输出价格：

```text
PROVIDER_PRICE_TABLE=openai:gpt-example:input=0.00,output=0.00;openai:text-embedding-example:input=0.00,output=0
```

当前基础版会估算 generation token 成本和 OpenAI embedding input token 成本，并输出到响应 `usage`、chat log `usage` 和 Prometheus `rag_provider_cost_usd_total`。embedding 模型没有 output token 计费时，把 `output=0`。真实价格会变化，应放在部署配置或 secret manager 中维护，不写死在代码里。

`text-embedding-3-small` 默认 1536 维，和当前 pgvector schema 匹配。

如果要启用 OpenAI generator，可以继续设置：

```text
GENERATOR_PROVIDER=openai
LLM_MODEL=gpt-5.4-nano
```

如果要启用 OpenAI query rewrite，可以继续设置：

```text
QUERY_REWRITER_PROVIDER=openai
QUERY_REWRITE_MODEL=gpt-5.4-nano
QUERY_REWRITE_MAX_OUTPUT_TOKENS=64
QUERY_CONTEXT_HISTORY_LIMIT=4
```

OpenAI query rewriter 会在 question guard 之后、embedding/sparse retrieval 之前调用 Responses API，把用户原始问题改写成更适合检索的短查询；默认 `QUERY_REWRITER_PROVIDER=none` 不会产生额外外部请求。如果请求带 `session_id`，API 会读取最近 `QUERY_CONTEXT_HISTORY_LIMIT` 条历史问答，并把它们传入 query rewrite prompt，让 “它/这个/刚才那个” 这类追问先变成独立检索 query。设置 `QUERY_CONTEXT_HISTORY_LIMIT=0` 可以关闭历史加载。

如果要启用 OpenAI reranker，可以继续设置：

```text
RERANKER_PROVIDER=openai
RERANKER_MODEL=gpt-5.4-nano
```

OpenAI reranker 会在 RRF fusion 之后、prompt 构造之前调用 Responses API，让模型根据 query 对候选 chunk 返回 JSON 排名；默认 `RERANKER_PROVIDER=none` 不会产生额外外部请求。

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
uv run python -m ingestion.inspect_ingestion --min-documents 3 --min-chunks 3
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

production compose 会把 API、export worker、migration job 和 Postgres 放在同一个 Docker network 中。API 和 worker 容器内部使用 `postgres:5432` 访问数据库，不再依赖宿主机 `localhost`。API 与 `export-worker` 共享 `export_prod_data:/app/exports`，用于下载 worker 写出的异步导出文件。

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

查看 export worker 日志：

```powershell
docker compose -f docker-compose.prod.yml logs -f export-worker
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

默认本地 API key 使用 `dev-key`，workspace 使用 `public`。如果配置了 `API_KEY_WORKSPACE_ACCESS`，页面填写的 API key 也必须被允许访问当前 workspace。页面支持：

- 创建 chat session
- 刷新 session 列表
- 加载 session history
- 通过 `POST /chat/stream` 流式展示回答
- 展示回答 sources
- 粘贴或选择 Markdown 文件并调用 `POST /documents`
- 刷新文档列表
- 调用 `POST /documents/reindex` 执行 dry-run 或写入式 reindex
- 调用 `POST /workspaces` 创建 workspace，并在成功后切换当前 workspace
- 调用 `PATCH /workspaces/{workspace_id}` 更新当前 workspace 的 name、description 和 metadata
- 调用 `POST /workspaces/{workspace_id}/archive` 和 `POST /workspaces/{workspace_id}/restore` 归档或恢复当前 workspace
- workspace 列表支持 Previous/Next 分页，并可在当前页内按 All / Active / Archived 过滤
- 当前 workspace 已归档时，页面会显示只读提示，并禁用 chat、session 创建、document upload 和 reindex 写入控件
- 查看可访问 workspace 列表和当前 workspace 最近 chat logs
- 按 request id、session id、refusal only、citation valid/invalid 过滤当前 workspace 的 chat logs，并用 Previous/Next 做基础翻页
- 按当前 chat log 过滤条件导出 JSONL 或 CSV
- 展开 chat log audit details，查看 session、request、citation、refusal、retrieval、query rewrite、usage 和 cost 字段

### Health

```powershell
curl.exe http://127.0.0.1:8000/health
```

预期：

```json
{"status":"ok"}
```

### Workspaces

创建 workspace：

```powershell
curl.exe -X POST http://127.0.0.1:8000/workspaces `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -d "{\"id\":\"tenant-a\",\"name\":\"Tenant A\",\"description\":\"GPU systems team\",\"metadata\":{\"tier\":\"internal\"}}"
```

查询可访问 workspace 列表：

```powershell
curl.exe "http://127.0.0.1:8000/workspaces?limit=20&offset=0" `
  -H "Authorization: Bearer dev-key"
```

按状态过滤 workspace：

```powershell
curl.exe "http://127.0.0.1:8000/workspaces?limit=20&offset=0&status=active" `
  -H "Authorization: Bearer dev-key"
```

按 ID、名称或描述搜索 workspace：

```powershell
curl.exe "http://127.0.0.1:8000/workspaces?limit=20&offset=0&q=tenant" `
  -H "Authorization: Bearer dev-key"
```

查询 workspace 详情：

```powershell
curl.exe http://127.0.0.1:8000/workspaces/tenant-a `
  -H "Authorization: Bearer dev-key"
```

软归档 workspace：

```powershell
curl.exe -X POST http://127.0.0.1:8000/workspaces/tenant-a/archive `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -d "{\"reason\":\"temporary tenant cleanup\"}"
```

恢复 workspace：

```powershell
curl.exe -X POST http://127.0.0.1:8000/workspaces/tenant-a/restore `
  -H "Authorization: Bearer dev-key"
```

批量软归档 workspace：

```powershell
curl.exe "http://127.0.0.1:8000/workspaces/bulk/preview?status=active&q=tenant&sample_limit=20" `
  -H "Authorization: Bearer dev-key"

curl.exe -X POST http://127.0.0.1:8000/workspaces/bulk/archive-matching `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -d "{\"q\":\"tenant\",\"status\":\"active\",\"expected_total\":2,\"confirm\":true,\"reason\":\"temporary cleanup\"}"

curl.exe -X POST http://127.0.0.1:8000/workspaces/bulk/archive `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -d "{\"ids\":[\"tenant-a\",\"tenant-b\"],\"reason\":\"temporary cleanup\"}"
```

批量恢复 workspace：

```powershell
curl.exe -X POST http://127.0.0.1:8000/workspaces/bulk/restore `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -d "{\"ids\":[\"tenant-a\",\"tenant-b\"]}"
```

归档 workspace 仍可用于查询、审计和恢复，但写入型接口会返回 `409 workspace archived`。当前受保护的写入路径包括：

- `POST /chat`
- `POST /chat/stream`
- `POST /chat/sessions`
- `POST /documents`
- `POST /documents/reindex`
- `DELETE /documents/{document_id}`

如果 `API_KEY_WORKSPACE_ACCESS` 限制了当前 API key，`GET /workspaces` 只返回该 key 可访问的 workspace；访问未授权 workspace 会返回 `403`。

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

可以在 `/chat` 和 `/chat/stream` 请求体里传 `metadata_filter`，按 chunk metadata 做 JSONB exact-containment 过滤。文档上传时传入的 metadata 会复制到 chunks，因此常见用法是按 `topic`、`difficulty`、`source_family` 等字段缩小检索候选：

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -H "X-Workspace-ID: public" `
  -d "{\"question\":\"What problem does FlashAttention solve?\",\"metadata_filter\":{\"topic\":\"attention\"}}"
```

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
671 passed
```

### Pipeline Smoke

```powershell
uv run python -m backend.app.rag.pipeline_smoke
```

### Document Management Smoke

```powershell
uv run python -m evals.document_management_smoke
```

该 smoke 会通过真实 FastAPI app 和数据库执行文档上传、列表、详情、
reindex dry-run、删除和删除后 404 校验。上传时强制使用 fake embedding
client，不会调用外部 provider。

真实 OpenAI 端到端 smoke，不修改 `.env`，临时覆盖 provider/model：

```powershell
uv run python -m backend.app.rag.pipeline_smoke --embedding-provider openai --generator-provider openai --llm-model gpt-5.4-nano
```

如果还要把真实 reranker 纳入端到端 smoke，可以继续加 reranker override：

```powershell
uv run python -m backend.app.rag.pipeline_smoke --embedding-provider openai --generator-provider openai --reranker-provider openai --llm-model gpt-5.4-nano --reranker-model gpt-5.4-nano
```

如果还要把真实 query rewrite 纳入端到端 smoke，可以继续加 query rewrite override：

```powershell
uv run python -m backend.app.rag.pipeline_smoke --embedding-provider openai --generator-provider openai --query-rewriter-provider openai --llm-model gpt-5.4-nano --query-rewrite-model gpt-5.4-nano
```

### Eval Gate

```powershell
uv run python -m evals.run --format summary --fail-on-failure
```

真实 OpenAI eval，不修改 `.env`，临时覆盖 provider/model：

```powershell
uv run python -m evals.run --format summary --fail-on-failure --no-output --embedding-provider openai --generator-provider openai --llm-model gpt-5.4-nano
```

真实 OpenAI eval 加真实 reranker：

```powershell
uv run python -m evals.run --format summary --fail-on-failure --no-output --embedding-provider openai --generator-provider openai --reranker-provider openai --llm-model gpt-5.4-nano --reranker-model gpt-5.4-nano
```

真实 OpenAI eval 加真实 query rewrite：

```powershell
uv run python -m evals.run --format summary --fail-on-failure --no-output --embedding-provider openai --generator-provider openai --query-rewriter-provider openai --llm-model gpt-5.4-nano --query-rewrite-model gpt-5.4-nano
```

当前 eval 基线：

```text
eval cases: 9/9 passed (100.0%)
- rag_eval_questions: 5/5 passed (100.0%)
- refusal_questions: 2/2 passed (100.0%)
- security_questions: 2/2 passed (100.0%)
```

最近一次真实 OpenAI 端到端验证也已通过：

```text
embedding smoke: text-embedding-3-small, 1536 dimensions, passed
reindex public: 6 chunks matched, 6 embedded, 6 updated
generator smoke: openai / gpt-5.4-nano, passed
pipeline smoke: openai embedding + openai generator, passed
pipeline smoke: openai query rewrite + reranker + embedding + generator, passed
OpenAI eval gate: 9/9 passed (100.0%)
```

`rag_005` 的 expected keywords 已从实现细节词收敛为 `KV` 和 `paged`，
用于稳定验证 metadata filter 命中 PagedAttention/kv-cache 语义，同时兼容
fake generator 和真实 OpenAI generator 的不同表述。

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

### 追加 eval JSONL 趋势记录

默认建议写入：

```text
evals/reports/trends.jsonl
```

命令：

```powershell
uv run python -m evals.run --format summary --trend-output evals/reports/trends.jsonl
```

该文件是本地运行产物，已被 `.gitignore` 忽略。详细字段见 `docs/EVAL_TRENDS.md`。

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

### Reranker Provider Smoke

默认使用 `.env` 中的 `RERANKER_PROVIDER` 和 `RERANKER_MODEL`：

```powershell
uv run python -m backend.app.rag.rerank_smoke
```

也可以只对本次 smoke 临时启用 OpenAI reranker：

```powershell
uv run python -m backend.app.rag.rerank_smoke --reranker-provider openai --reranker-model gpt-5.4-nano
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
make config-check       校验当前运行配置，不打印 secret 值
make prod-config-check  按 production 规则校验配置，不打印 secret 值
make prod-config        静默校验 production compose 配置
make prod-build         构建 production API 镜像
make prod-up            启动 production-style 本地栈
make prod-down          停止 production-style 本地栈
make prod-logs          查看 production API 日志
make prod-worker-logs   查看 production export worker 日志
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
make eval-trend         运行 eval summary 并追加 JSONL 趋势记录
make document-management-smoke
                        验证文档管理 API 上传、查询、reindex dry-run 和删除
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
    F --> HIST["Optional session history"]
    HIST --> G["Question-level refusal guard"]
    G --> QR["Optional query rewrite/contextualization"]
    QR --> MF["Optional metadata_filter"]
    MF --> H["Vector retrieval"]
    MF --> I["Sparse retrieval"]
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
git clone https://github.com/ictup/production-rag-assistant.git
cd production-rag-assistant
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

当前远端 Actions 已验证可运行。最近一次已完成核验的 `main` push CI：

```text
Run: https://github.com/ictup/production-rag-assistant/actions/runs/26154936552
Commit: 2d39e63e8a6e3dfc3a4afd999456e38602a27930
Workflow: CI
Job: Backend checks
Status: completed
Conclusion: success
Created: 2026-05-20T09:51:04Z
Completed: 2026-05-20T09:51:56Z
```

## 12. 当前还没有实现的功能

### 模型与 provider

- OpenAI embedding provider 已有代码、mock 测试和联网 smoke CLI。
- OpenAI generator provider 已有代码和 smoke CLI。
- OpenAI provider 超时、有限重试和错误分类。
- OpenAI provider API 错误响应、结构化日志和 metrics。
- provider API key 配置校验目前覆盖 OpenAI embedding、OpenAI generator、OpenAI query rewriter 和 OpenAI reranker。
- provider token 统计和 embedding/generation latency 细分指标。
- OpenAI Responses API streaming 已接入 generator 和 `/chat/stream`。
- OpenAI Responses API query rewriter 已完成，默认仍为 no-op，可用 `QUERY_REWRITER_PROVIDER=openai` 启用。
- 多轮 query contextualization 已完成：带 `session_id` 的 `/chat` 和 `/chat/stream` 会读取最近 session logs，并传给 query rewrite prompt。
- OpenAI Responses API listwise reranker 已完成，默认仍为 no-op，可用 `RERANKER_PROVIDER=openai` 启用。
- metadata filter 基础版已接入 `/chat` 和 `/chat/stream`，会应用到 vector/sparse retrieval 的 `document_chunks.metadata @>` 条件。
- provider generation token 和 OpenAI embedding token 成本估算基础版已完成：`PROVIDER_PRICE_TABLE`、响应 usage cost 字段、Prometheus `rag_provider_cost_usd_total`。
- 真实 OpenAI 端到端验证已完成：OpenAI embedding smoke、public workspace chunk reindex、OpenAI generator smoke、OpenAI eval gate，以及包含 query rewrite/reranker 的 pipeline smoke 均通过。

### 检索质量

- seed 文档集合已从 2 篇扩到 3 篇，并新增 speculative decoding 和 metadata-filter 检索 eval；更大的业务文档集合仍需继续补充。

### 产品 API

- 文档列表 API 已完成：`GET /documents`。
- 文档详情 API 已完成：`GET /documents/{document_id}`。
- 文档删除 API 已完成：`DELETE /documents/{document_id}`。
- 文档上传 API 已完成：`POST /documents`。
- 文档重新索引 API 已完成：`POST /documents/reindex`。
- 当前已有 CLI 和 API 两种 chunk embedding reindex 入口。
- document-management smoke 已完成，覆盖上传、列表、详情、reindex dry-run、删除和删除后 404。
- chat session 表和 `chat_logs.session_id` 迁移已完成。
- chat session repository 和基础 API 已完成：`POST /chat/sessions`、`GET /chat/sessions`、`GET /chat/sessions/{session_id}`。
- workspace registry 表、repository 和基础 API 已完成：`POST /workspaces`、`GET /workspaces`、`GET /workspaces/{workspace_id}`。
- workspace 更新和软归档 API 已完成：`PATCH /workspaces/{workspace_id}`、`POST /workspaces/{workspace_id}/archive`、`POST /workspaces/{workspace_id}/restore`。
- workspace 归档写保护已完成：归档 workspace 可读，但 chat、session 创建、document 上传/删除/reindex 等写入路径会返回 `409 workspace archived`。
- documents/chat sessions/chat logs 已通过 workspace 外键收紧；写入路径会先校验 workspace 是否存在。
- `/chat` 已支持可选 `session_id`，并会把 chat log 挂到对应会话。
- conversation history API 已完成：`GET /chat/sessions/{session_id}/logs`。
- streaming chat API 已完成：`POST /chat/stream`。
- 底层 OpenAI Responses 真 token streaming 已完成。

### 前端与体验

- 最小 Web UI 已完成：`GET /app/`。
- 聊天 UI 已支持 session 创建、session 列表、history 加载和 SSE streaming。
- 文档 UI 已支持 Markdown 上传、文档列表、reindex dry-run 和 write。
- 聊天错误恢复体验已完成基础版：provider/HTTP 错误会在 assistant 消息内展示分类、request id、retryable 状态和 Retry 按钮。
- 管理后台基础版已完成：右侧 Admin overview 可刷新可访问 workspace 列表和当前 workspace 最近 chat logs，并可从 workspace 列表切换当前 workspace。
- workspace 管理操作基础版已完成：Admin overview 可调用 `POST /workspaces` 创建 workspace，成功后自动切换当前 workspace 并刷新会话、文档和管理概览。
- workspace 编辑基础版已完成：`PATCH /workspaces/{workspace_id}` 可更新 name、description、metadata，Admin overview 可编辑当前 workspace。
- workspace 归档/恢复 UI 基础版已完成：Admin overview 可展示归档状态，并调用 archive/restore API 更新当前 workspace。
- workspace 归档状态 UX guard 已完成：当前 workspace 已归档时，Web UI 会显示只读提示，并禁用 chat、session 创建、document upload 和 reindex 写入控件。
- workspace 列表状态过滤已完成：`GET /workspaces?status=all|active|archived` 会按 `archived_at` 做后端过滤，Admin overview 支持 All / Active / Archived 全量过滤。
- workspace 列表分页基础版已完成：Admin overview 使用 `/workspaces?limit&offset` 做 Previous/Next 翻页。
- workspace 搜索基础版已完成：`GET /workspaces?q=...` 会按 workspace ID、name 和 description 过滤，Admin overview 可搜索并重置分页。
- workspace 批量操作 API 基础版已完成：`POST /workspaces/bulk/archive` 和 `POST /workspaces/bulk/restore` 支持一次请求处理多个 workspace，缺失 workspace 会返回 missing id 列表。
- workspace 批量操作 UI 基础版已完成：Admin overview 支持当前页多选 workspace，并调用 bulk archive / restore API。
- workspace 跨页批量预览基础版已完成：`GET /workspaces/bulk/preview` 会按当前 `q`、`status` 和 API key 权限返回匹配总数与样本 workspace，用于后续确认流。
- workspace 跨页批量确认执行基础版已完成：`POST /workspaces/bulk/archive-matching` 和 `POST /workspaces/bulk/restore-matching` 要求 `confirm=true` 与 `expected_total` 匹配当前查询总数后才执行。
- workspace 跨页批量 UI 确认流已完成：Admin overview 可按当前 status/search 预览匹配总数和样本，再带 `expected_total` 与 `confirm=true` 调用 archive-matching / restore-matching。
- workspace 操作审计写入基础版已完成：单个 archive/restore、当前页 bulk archive/restore、跨页 matching archive/restore 会在同一事务写入 `workspace_audit_logs`，审计中保存 request id、API key hash、action、workspace ids 和操作 metadata。
- workspace 操作审计查询 API 已完成：`GET /workspaces/audit-logs` 支持 `limit`、`offset`、`action`、`workspace_id`、`request_id`、`created_from` 和 `created_to`，并按 API key workspace 权限过滤。
- workspace 操作审计 UI 已完成：Admin overview 会展示 `GET /workspaces/audit-logs` 返回的记录，支持 action、workspace id、request id、created from 和 created to 过滤，支持 Previous/Next 分页，并可展开查看 audit id、actor hash、metadata 等详情。
- chat log 审计过滤基础版已完成：`GET /chat/logs` 支持 `offset`、`session_id`、`request_id`、`refusal_only`、`citation_valid`，Admin overview 支持对应筛选和 Previous/Next 翻页。
- chat log 审计导出基础版已完成：`GET /chat/logs/export` 支持同一组过滤参数，可导出 JSONL 或 CSV，Admin overview 可按当前过滤条件触发下载。
- chat log 审计详情基础版已完成：每条最近日志可展开查看 session、request、citation、sources、refusal、retrieval、query rewrite、metadata filter、usage 和 cost。
- export job 基础模型已完成：新增 `export_jobs` 表、`ExportJobRepository`、pending -> running -> succeeded/failed 状态流转和 worker claim 入口。
- export job API 已完成：`POST /exports/jobs` 可按当前 `X-Workspace-ID` 创建 chat log 导出任务，`GET /exports/jobs` 支持 status/export_type 分页查询，`GET /exports/jobs/{job_id}` 可按 workspace 读取任务详情，`POST /exports/jobs/{job_id}/retry` 可把当前 workspace 下 failed job 重置为 pending；现有 `/chat/logs/export` 仍保持同步。
- export worker 基础版已完成：`backend.app.exporting.worker` 会 claim 一个 pending job，按 filters 查询 chat logs，复用同步导出的 JSONL/CSV 序列化，写入 `EXPORT_STORAGE_DIR`，并将 job 标记为 succeeded/failed。
- export 下载接口和前端轮询已完成：`GET /exports/jobs/{job_id}/download` 只允许下载当前 workspace 下 succeeded job 的 `EXPORT_STORAGE_DIR` 内部文件，Admin export JSONL/CSV 按钮会创建 job、轮询详情并在 succeeded 后触发下载。
- export worker 常驻服务和 production compose 编排已完成：`--loop` 模式按 `EXPORT_WORKER_POLL_INTERVAL_SECONDS` 轮询，`docker-compose.prod.yml` 增加 `export-worker` 服务，并让 API/worker 共享 `export_prod_data`。
- export job running 超时恢复基础版已完成：worker 每轮 claim 前会按 `EXPORT_JOB_RUNNING_TIMEOUT_SECONDS` 将超时 running job 重置为 pending，便于 worker 崩溃或中断后的自动恢复。
- export 文件过期清理基础版已完成：worker 每轮 claim 前会按 `EXPORT_FILE_RETENTION_SECONDS` 删除 `EXPORT_STORAGE_DIR` 顶层过期 `.jsonl` 和 `.csv` 文件，job metadata 保留用于审计。
- export failed job 手动重试基础版已完成：`POST /exports/jobs/{job_id}/retry` 只允许重试 failed job，按 API key workspace 权限过滤，重试后由 worker 正常 claim。
- 完整管理后台仍未完成：还缺少用户/角色/组织管理、更完整的批量运维操作和权限分层 UI。

### 生产部署

- backend Dockerfile 已完成：`Dockerfile`。
- `.dockerignore` 已完成，排除 `.env`、`.venv`、缓存和本地报告。
- production docker-compose 已完成：`docker-compose.prod.yml`。
- production export worker 服务已完成：`export-worker` 使用同一镜像运行 `python -m backend.app.exporting.worker --loop`，并与 API 共享导出文件 volume。
- 环境变量和 secrets 文档已完成：`docs/CONFIGURATION.md`。
- 配置预检 CLI 已完成：`python -m backend.app.core.config_check` 和 `--production` 会在不打印 secret 值的情况下检查 OpenAI key、生产 API key、CORS credential 边界、workspace scoping、rate limit 和本地数据库 URL 风险。
- 生产部署平台 secret manager 映射已完成：`docs/SECRET_MANAGER_MAPPING.md` 明确了 managed secrets、plain runtime config、注入模式和轮换流程。
- 部署 runbook 已完成：`docs/DEPLOYMENT_RUNBOOK.md`。
- CORS 策略已完成：默认关闭，通过 `CORS_ALLOWED_ORIGINS` 或 `CORS_ALLOWED_ORIGIN_REGEX` 显式开启。
- rate limit 已完成：默认关闭，通过 `RATE_LIMIT_ENABLED` 显式开启。
- API key 到 workspace 的访问控制已完成：`API_KEY_WORKSPACE_ACCESS`、`ApiPrincipal`、越权返回 403。
- API key 角色分层基础版已完成：`API_KEY_ROLES` 支持 `admin`、`operator`、`viewer`，并保护 workspace 管理、文档写入、chat/session 写入和 export job 写入路径。
- 更完整的用户/角色/组织模型。
- secret manager 基础映射文档已完成；真实部署时仍需要把对应变量填入目标平台的 secret/config UI 或 CLI。
- release checklist 已完成：`docs/RELEASE_CHECKLIST.md` 覆盖本地验证、生产配置门禁、secret scan、CI gate、dry run、tag、release notes 和 rollback readiness。

### 可观测性

- trace/span 集成已完成：HTTP request span、RAG pipeline 关键阶段 span、`X-Trace-ID` 关联。
- dashboard 和 alert 模板已完成：`docs/OBSERVABILITY.md`、`monitoring/grafana/rag-dashboard.json`、`monitoring/prometheus/rag-alerts.yml`。
- 慢查询监控方案已完成：`docs/DATABASE_OBSERVABILITY.md`、`pg_stat_statements`、`log_min_duration_statement`。
- eval 趋势记录已完成：`docs/EVAL_TRENDS.md`、`evals/trends.py`、`--trend-output`。

## 13. 推荐后续路线

### 阶段 A：文档和迁移收尾

目标：让任何新机器可以按文档跑起来。

建议步骤：

1. 扩展 README，让它成为项目主页。已完成。
2. 增加 `.env.example` 中真实 provider 的占位配置。已完成。
3. 确认 GitHub Actions 在远端实际运行。已完成。

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
8. 接入真实 OpenAI reranker。已完成。
9. 接入真实 OpenAI query rewrite。已完成。

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
9. 多轮 query contextualization。已完成。
10. chat error recovery UX。已完成。

### 阶段 E：生产化

目标：部署和长期维护。

建议步骤：

1. backend Dockerfile。已完成。
2. production compose。已完成。
3. CORS。已完成。
4. rate limit。已完成。
5. 环境变量和 secrets 文档。已完成。
6. 部署 runbook。已完成。
7. dashboard 和 alert。已完成。
8. eval 趋势记录。已完成。
9. API key workspace 访问控制。已完成。
10. workspace 管理 API。已完成。
11. workspace 存在性校验和外键收紧。已完成。
12. provider 成本估算基础版。已完成。
13. 真实 OpenAI reranker。已完成。
14. workspace 软归档 API。已完成。
15. workspace 归档/恢复 UI。已完成。
16. workspace 归档写保护。已完成。
17. workspace 归档状态前端写入禁用。已完成。
18. workspace 列表状态过滤。已完成。
19. workspace 列表分页基础版。已完成。
20. workspace 搜索基础版。已完成。
21. workspace 后端状态过滤。已完成。
22. workspace 批量操作 API 基础版。已完成。
23. workspace 批量操作 UI 基础版。已完成。
24. workspace 跨页批量预览基础版。已完成。
25. workspace 跨页批量确认执行基础版。已完成。
26. workspace 跨页批量 UI 确认流。已完成。
27. workspace 批量操作审计记录。已完成。
28. workspace 操作审计查询 API。已完成。
29. workspace 操作审计 UI。已完成。
30. 导出任务异步化：job 表和后台执行模型。已完成。
31. 导出任务异步化：创建/查询 job API。已完成。
32. 导出任务异步化：worker 执行和文件落地。已完成。
33. 导出任务异步化：下载接口和前端轮询。已完成。
34. 导出 worker 常驻服务和 production compose 编排。已完成。
35. 导出任务运维补强：running 超时恢复。已完成。
36. 导出任务运维补强：过期导出文件清理。已完成。
37. 导出任务运维补强：失败任务手动重试。已完成。
38. 真实 OpenAI 端到端验证。已完成。
39. 生产配置和 secrets 收紧：配置预检 CLI。已完成。
40. 生产部署平台 secrets 接入说明。已完成。
41. 管理后台权限分层基础版：API key roles。已完成。
42. 最终 release 收口：release checklist。已完成。

## 14. 当前优先级建议

建议下一步优先做：

```text
正式创建 release tag 和 release notes
```

原因：

- export job 表、迁移、repository、状态流转、创建/查询 API、worker 执行、文件落地、下载接口、前端轮询、常驻 worker、production compose 编排、running 超时恢复、过期文件清理、失败任务手动重试、真实 OpenAI 端到端验证、配置预检 CLI、secret manager 映射文档、API key 角色分层基础版和 release checklist 已完成。
- 下一步可以在你确认版本号后创建正式 release tag 和 release notes。

以下命令是后续需要真实 provider 时的验证入口：

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

验证 reranker：

```powershell
uv run python -m backend.app.rag.rerank_smoke --reranker-provider openai --reranker-model gpt-5.4-nano
```

验证 query rewrite 需要通过 pipeline 或 eval 临时启用：

```powershell
uv run python -m backend.app.rag.pipeline_smoke --embedding-provider openai --generator-provider openai --query-rewriter-provider openai --llm-model gpt-5.4-nano --query-rewrite-model gpt-5.4-nano
```

真实端到端 smoke：

```powershell
uv run python -m backend.app.rag.pipeline_smoke --embedding-provider openai --generator-provider openai --llm-model gpt-5.4-nano
```

真实端到端 smoke 加 reranker：

```powershell
uv run python -m backend.app.rag.pipeline_smoke --embedding-provider openai --generator-provider openai --reranker-provider openai --llm-model gpt-5.4-nano --reranker-model gpt-5.4-nano
```

真实端到端 smoke 加 query rewrite 和 reranker：

```powershell
uv run python -m backend.app.rag.pipeline_smoke --embedding-provider openai --generator-provider openai --query-rewriter-provider openai --reranker-provider openai --llm-model gpt-5.4-nano --query-rewrite-model gpt-5.4-nano --reranker-model gpt-5.4-nano
```

真实 eval gate：

```powershell
uv run python -m evals.run --format summary --fail-on-failure --no-output --embedding-provider openai --generator-provider openai --llm-model gpt-5.4-nano
```

真实 eval gate 加 reranker：

```powershell
uv run python -m evals.run --format summary --fail-on-failure --no-output --embedding-provider openai --generator-provider openai --reranker-provider openai --llm-model gpt-5.4-nano --reranker-model gpt-5.4-nano
```

真实 eval gate 加 query rewrite 和 reranker：

```powershell
uv run python -m evals.run --format summary --fail-on-failure --no-output --embedding-provider openai --generator-provider openai --query-rewriter-provider openai --reranker-provider openai --llm-model gpt-5.4-nano --query-rewrite-model gpt-5.4-nano --reranker-model gpt-5.4-nano
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
