# Deployment Runbook

This runbook describes how to bring up, verify, update, stop, and recover the
production-style local stack. Configuration details live in
`docs/CONFIGURATION.md`.

## Scope

The current deployment target is a single-host Docker Compose stack:

- `postgres`: PostgreSQL with pgvector
- `migrate`: one-shot Alembic migration job
- `api`: FastAPI backend and static web UI

For multi-host or multi-replica production, move secrets to a managed secret
store and replace in-process rate limiting with Redis, an API gateway, or a
reverse proxy layer.

## Prerequisites

- Docker Desktop or Docker Engine with Compose v2
- Git
- PowerShell
- Access to this repository
- A local `.env` file created from `.env.example`

Confirm Docker is available:

```powershell
docker info
docker compose version
```

## Initial Setup

Clone or update the repository:

```powershell
git clone https://github.com/ictup/Production_RAG_Assistant.git
Set-Location Production_RAG_Assistant
```

Create local configuration:

```powershell
Copy-Item .env.example .env
```

Edit `.env` before starting the stack:

- Set `API_KEYS` to one or more real client tokens.
- Set `POSTGRES_PASSWORD` to a non-default value outside local development.
- Set `API_PORT` if host port `8000` is already in use.
- Keep fake providers unless real OpenAI calls are intended.
- If using OpenAI providers, set `OPENAI_API_KEY` in `.env` or a secret manager.
- Configure `CORS_ALLOWED_ORIGINS` when a browser frontend uses another origin.
- Enable `RATE_LIMIT_ENABLED=true` when the API is exposed beyond local use.

Validate Compose without printing resolved environment values:

```powershell
docker compose -f docker-compose.prod.yml config --quiet
```

## First Deployment

Build and start the stack:

```powershell
docker compose -f docker-compose.prod.yml up -d --build
```

Check container status:

```powershell
docker compose -f docker-compose.prod.yml ps
```

Expected state:

- `postgres` is healthy.
- `migrate` exits successfully with code `0`.
- `api` is running and becomes healthy.

## Verification

Health check:

```powershell
curl.exe http://127.0.0.1:8000/health
```

If `API_PORT` is not `8000`, replace the port in the URL.

Metrics endpoint:

```powershell
curl.exe http://127.0.0.1:8000/metrics
```

Static web UI:

```text
http://127.0.0.1:8000/app/
```

Authenticated API smoke:

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat `
  -H "Authorization: Bearer dev-key" `
  -H "Content-Type: application/json" `
  -H "X-Workspace-ID: public" `
  -d "{\"question\":\"What is FlashAttention?\"}"
```

Replace `dev-key` with the token configured in `API_KEYS`.

## Logs and Inspection

Follow API logs:

```powershell
docker compose -f docker-compose.prod.yml logs -f api
```

View migration logs:

```powershell
docker compose -f docker-compose.prod.yml logs migrate
```

View Postgres logs:

```powershell
docker compose -f docker-compose.prod.yml logs postgres
```

Inspect service status:

```powershell
docker compose -f docker-compose.prod.yml ps
```

## Update Procedure

Fetch the latest code:

```powershell
git fetch origin main
git pull --ff-only origin main
```

Validate configuration:

```powershell
docker compose -f docker-compose.prod.yml config --quiet
```

Rebuild and restart:

```powershell
docker compose -f docker-compose.prod.yml up -d --build
```

The `migrate` job runs before the API starts, so schema migrations are applied
as part of the restart.

## Stop and Restart

Stop the stack while keeping the Postgres volume:

```powershell
docker compose -f docker-compose.prod.yml down
```

Start again:

```powershell
docker compose -f docker-compose.prod.yml up -d
```

Do not delete Docker volumes unless the data can be discarded or restored from
a backup.

## Backup and Recovery

Create a logical database backup:

```powershell
docker compose -f docker-compose.prod.yml exec postgres pg_dump `
  -U rag `
  -d rag `
  -Fc `
  -f /tmp/rag.dump
```

Copy the backup to the host:

```powershell
docker compose -f docker-compose.prod.yml cp postgres:/tmp/rag.dump .\rag.dump
```

Restore into an empty database:

```powershell
docker compose -f docker-compose.prod.yml cp .\rag.dump postgres:/tmp/rag.dump
docker compose -f docker-compose.prod.yml exec postgres pg_restore `
  -U rag `
  -d rag `
  --clean `
  --if-exists `
  /tmp/rag.dump
```

After restore, restart the API:

```powershell
docker compose -f docker-compose.prod.yml up -d api
```

## Common Failures

### Port Already in Use

Symptom: the API cannot bind host port `8000`.

Fix: set a different host port in `.env`:

```text
API_PORT=8002
```

Then restart:

```powershell
docker compose -f docker-compose.prod.yml up -d --build
```

### Invalid API Key

Symptom: API returns `401` with `invalid api key`.

Fix: verify `API_KEYS` in `.env` and use the same value in the
`Authorization: Bearer ...` header.

### OpenAI Provider Fails

Symptom: provider errors appear in API responses, logs, or metrics.

Fix:

- Confirm `OPENAI_API_KEY` is set in the runtime environment.
- Confirm the selected model names are available for the configured provider.
- Run provider smoke tests from the project handoff document.

### Empty Retrieval Results

Symptom: chat refuses because no useful chunks are retrieved.

Fix:

- Confirm documents were ingested or uploaded.
- Confirm `X-Workspace-ID` matches the workspace used during ingestion.
- If embedding provider changed, run chunk embedding reindex.

### Migration Job Fails

Symptom: `migrate` exits non-zero and `api` does not start.

Fix:

```powershell
docker compose -f docker-compose.prod.yml logs migrate
docker compose -f docker-compose.prod.yml logs postgres
```

Resolve the migration or database issue, then restart:

```powershell
docker compose -f docker-compose.prod.yml up -d --build
```

## Final Pre-Release Check

Before promoting a change, run:

```powershell
uv run pytest
uv run ruff check .
uv run python -m evals.run --format summary --fail-on-failure --no-output
docker compose -f docker-compose.prod.yml config --quiet
```
