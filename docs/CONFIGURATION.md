# Configuration and Secrets Guide

This guide is the source of truth for runtime configuration. Keep `.env`
local-only, use `.env.example` as the template, and never commit real secrets.
For operational startup, verification, logging, and recovery steps, use
`docs/DEPLOYMENT_RUNBOOK.md`.

## Quick Start

Create local configuration:

```powershell
Copy-Item .env.example .env
```

Validate production compose without printing resolved environment values:

```powershell
docker compose -f docker-compose.prod.yml config --quiet
```

Do not use plain `docker compose config` when `.env` contains real secrets,
because it expands environment values into terminal output.

## Runtime Modes

### Local Development

Use these defaults when developing the backend directly on the host:

```text
ENV=local
EMBEDDING_PROVIDER=fake
GENERATOR_PROVIDER=fake
DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/rag
SYNC_DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag
```

If local PostgreSQL already uses port `5432`, change `POSTGRES_PORT`,
`DATABASE_URL`, and `SYNC_DATABASE_URL` together.

### Production-Style Compose

`docker-compose.prod.yml` overrides the API container database URLs so the API
uses the internal service name:

```text
DATABASE_URL=postgresql+asyncpg://rag:rag@postgres:5432/rag
SYNC_DATABASE_URL=postgresql+psycopg://rag:rag@postgres:5432/rag
```

`API_PORT` controls the host port only. The API still listens on port `8000`
inside the container.

### Real OpenAI Providers

Fake providers are the default and require no external key. To call OpenAI,
switch the relevant providers and set `OPENAI_API_KEY`:

```text
EMBEDDING_PROVIDER=openai
GENERATOR_PROVIDER=openai
OPENAI_API_KEY=<set in local .env or secret manager>
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
LLM_MODEL=gpt-5.4-nano
```

After changing embedding provider for an existing database, reindex stored
chunk embeddings so query vectors and stored vectors use the same model.

## Secrets Rules

- Never commit `.env`, real API keys, database passwords, or production tokens.
- Keep only placeholders in `.env.example`.
- Use `API_KEYS` for client authentication tokens; rotate them by updating the
  deployment secret and restarting the API.
- Use `OPENAI_API_KEY` only when OpenAI providers are enabled.
- Use a real secret manager for shared or production deployments. `.env` is
  acceptable only for local development.
- Prefer `docker compose -f docker-compose.prod.yml config --quiet` for
  validation so secrets are not printed.
- Before committing, run the repository secret scan command from this guide.

## Environment Variables

### Application

| Variable | Default | Required | Description |
| --- | --- | --- | --- |
| `APP_NAME` | `production-rag-assistant` | No | Service name used by config and logs. |
| `ENV` | `local` | No | Runtime environment label such as `local` or `production`. |
| `LOG_LEVEL` | `INFO` | No | Backend log level. |
| `API_KEYS` | `dev-key` | Yes | Comma-separated Bearer tokens accepted by API authentication. |

### Ports and Database

| Variable | Default | Required | Description |
| --- | --- | --- | --- |
| `POSTGRES_USER` | `rag` | Yes | PostgreSQL username used by Docker Compose. |
| `POSTGRES_PASSWORD` | `rag` | Yes | PostgreSQL password used by Docker Compose. Replace outside local development. |
| `POSTGRES_DB` | `rag` | Yes | PostgreSQL database name. |
| `POSTGRES_PORT` | `5432` | No | Host port for the local Postgres service. |
| `POSTGRES_LOG_MIN_DURATION_STATEMENT_MS` | `1000` | No | Slow query log threshold in milliseconds for Compose-managed Postgres. |
| `API_PORT` | `8000` | No | Host port published by production compose for the API service. |
| `DATABASE_URL` | local asyncpg URL | Yes | Async SQLAlchemy database URL for the API. |
| `SYNC_DATABASE_URL` | local psycopg URL | Yes | Sync database URL for Alembic migrations. |

### Embeddings

| Variable | Default | Required | Description |
| --- | --- | --- | --- |
| `EMBEDDING_PROVIDER` | `fake` | Yes | Embedding provider. Supported values: `fake`, `openai`. |
| `EMBEDDING_MODEL` | `fake-embedding` | Yes | Logical embedding model name recorded with chunks. |
| `EMBEDDING_DIMENSION` | `1536` | Yes | Vector dimension expected by pgvector schema. |

### OpenAI

| Variable | Default | Required | Description |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | empty | When OpenAI providers are used | OpenAI API key. Keep only in local `.env` or secret manager. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | No | OpenAI-compatible API base URL. |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Yes for OpenAI embeddings | Embedding model used by OpenAI embedding provider. |
| `OPENAI_TIMEOUT_SECONDS` | `30` | No | HTTP timeout for OpenAI-compatible calls. |
| `OPENAI_MAX_RETRIES` | `2` | No | Maximum retry attempts for retryable provider failures. |
| `OPENAI_RETRY_DELAY_SECONDS` | `0.25` | No | Base retry delay for provider calls. |
| `OPENAI_MAX_OUTPUT_TOKENS` | `512` | No | Maximum generated output tokens for OpenAI generation. |

### Browser Boundary

| Variable | Default | Required | Description |
| --- | --- | --- | --- |
| `CORS_ALLOWED_ORIGINS` | empty | No | Comma-separated explicit browser origins allowed to call the API. |
| `CORS_ALLOWED_ORIGIN_REGEX` | empty | No | Optional regex for allowed browser origins. |
| `CORS_ALLOW_CREDENTIALS` | `false` | No | Whether browser credentials are allowed. Usually keep `false` for Bearer token APIs. |

### Rate Limit

| Variable | Default | Required | Description |
| --- | --- | --- | --- |
| `RATE_LIMIT_ENABLED` | `false` | No | Enables in-process sliding-window API rate limiting. |
| `RATE_LIMIT_REQUESTS` | `60` | No | Number of requests allowed per identity in each window. |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | No | Sliding window length in seconds. |
| `RATE_LIMIT_EXCLUDED_PATHS` | `/health,/metrics,/app,/openapi.json,/docs,/redoc` | No | Comma-separated path prefixes excluded from rate limiting. |

### Retrieval and Ranking

| Variable | Default | Required | Description |
| --- | --- | --- | --- |
| `RERANKER_PROVIDER` | `none` | Yes | Reranker provider. Current supported value: `none`. |
| `RERANK_TOP_N` | `5` | No | Number of fused chunks retained after reranking. |
| `VECTOR_TOP_K` | `20` | No | Number of vector retrieval candidates. |
| `SPARSE_TOP_K` | `20` | No | Number of sparse retrieval candidates. |
| `FUSED_TOP_K` | `20` | No | Number of candidates retained after RRF fusion. |
| `RRF_K` | `60` | No | RRF smoothing constant. |

### Generation and Refusal

| Variable | Default | Required | Description |
| --- | --- | --- | --- |
| `GENERATOR_PROVIDER` | `fake` | Yes | Generator provider. Supported values: `fake`, `openai`. |
| `LLM_MODEL` | `fake-llm` | Yes | Generator model name. |
| `REFUSAL_SCORE_THRESHOLD` | `0.01` | No | Retrieval confidence threshold below which the assistant refuses to answer. |

## Validation Commands

Run before committing configuration changes:

```powershell
uv run pytest backend/tests/test_configuration_docs.py backend/tests/test_config.py
uv run ruff check .
docker compose -f docker-compose.prod.yml config --quiet
rg -n "s[k]-" backend docs .github ingestion evals pyproject.toml README.md Makefile docker-compose.yml docker-compose.prod.yml .env.example Dockerfile .dockerignore
```

The secret scan should only match intentional placeholders, not real keys.
