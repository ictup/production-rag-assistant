# Deployment Runbook

This runbook describes how to bring up, verify, update, stop, and recover the
production-style local stack. Configuration details live in
`docs/CONFIGURATION.md`. Metrics, dashboard, and alert templates live in
`docs/OBSERVABILITY.md`. Postgres slow query monitoring lives in
`docs/DATABASE_OBSERVABILITY.md`. Production secret manager mapping lives in
`docs/SECRET_MANAGER_MAPPING.md`. Release gating lives in
`docs/RELEASE_CHECKLIST.md`.

## Scope

The current deployment target is a single-host Docker Compose stack:

- `postgres`: PostgreSQL with pgvector
- `migrate`: one-shot Alembic migration job
- `api`: FastAPI backend and static web UI
- `export-worker`: long-running asynchronous export worker

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
- Set `API_KEY_ROLES` to assign each token an `admin`, `operator`, or `viewer`
  role.
- Set `POSTGRES_PASSWORD` to a non-default value outside local development.
- Set `API_PORT` if host port `8000` is already in use.
- Keep fake providers unless real OpenAI calls are intended.
- If using OpenAI providers, set `OPENAI_API_KEY` in `.env` or a secret manager.
- Configure `CORS_ALLOWED_ORIGINS` when a browser frontend uses another origin.
- Enable `RATE_LIMIT_ENABLED=true` when the API is exposed beyond local use.

For shared staging or production, do not treat `.env` as the source of truth.
Use `docs/SECRET_MANAGER_MAPPING.md` to map `API_KEYS`, database URLs,
`OPENAI_API_KEY`, and other sensitive values into the deployment platform's
secret store. Keep non-secret tuning values as platform runtime configuration.

Validate Compose without printing resolved environment values:

```powershell
docker compose -f docker-compose.prod.yml config --quiet
```

Run production configuration preflight without printing secret values:

```powershell
uv run python -m backend.app.core.config_check --production
```

Fix any reported errors before deployment. Warnings identify configuration
choices that are acceptable for local production-style testing but should be
reviewed for shared or real production environments.

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
- `export-worker` is running and polling for pending export jobs.

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

Follow export worker logs:

```powershell
docker compose -f docker-compose.prod.yml logs -f export-worker
```

If a worker process exits after marking a job `running` but before completing
it, the next worker iteration resets the job to `pending` after
`EXPORT_JOB_RUNNING_TIMEOUT_SECONDS`. The default timeout is `3600` seconds.
The worker also deletes expired top-level `.jsonl` and `.csv` files from
`EXPORT_STORAGE_DIR` after `EXPORT_FILE_RETENTION_SECONDS`. The default
retention is `604800` seconds. Export job metadata remains available for audit;
downloads for removed files return `404 export file not found`.

View migration logs:

```powershell
docker compose -f docker-compose.prod.yml logs migrate
```

View Postgres logs:

```powershell
docker compose -f docker-compose.prod.yml logs postgres
```

Slow queries are logged by Postgres when they meet or exceed
`POSTGRES_LOG_MIN_DURATION_STATEMENT_MS`. For `pg_stat_statements` inspection
queries and troubleshooting workflow, see:

```text
docs/DATABASE_OBSERVABILITY.md
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
uv run python -m backend.app.core.config_check --production
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

Before promoting a change, run the full release checklist:

```text
docs/RELEASE_CHECKLIST.md
```

At minimum, run:

```powershell
uv run pytest
uv run ruff check .
uv run python -m backend.app.core.config_check --production
uv run python -m evals.run --format summary --fail-on-failure --no-output
docker compose -f docker-compose.prod.yml config --quiet
```
