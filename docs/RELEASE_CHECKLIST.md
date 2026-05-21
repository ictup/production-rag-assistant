# Release Checklist

This checklist is the release gate for promoting Production RAG Assistant from
local development into a shared staging or production-style environment.

Use it before creating a Git tag or publishing release notes. It assumes the
runtime behavior is already covered by the deployment runbook and configuration
guides.

## Release Scope

Before release, write down:

- Target version or tag, for example `v0.1.0`.
- Commit SHA being promoted.
- Target environment: local production-style, shared staging, or production.
- Provider mode: fake providers, OpenAI embeddings only, or full OpenAI RAG.
- Database target and backup location.
- Operator responsible for rollback.

## Local Verification

Run from the repository root:

```powershell
uv run ruff check .
uv run pytest
uv run python -m backend.app.core.config_check
uv run python -m evals.agent_run --format summary --fail-on-failure --no-output
docker compose -f docker-compose.prod.yml config --quiet
```

Then run smoke tests that match the provider mode.

For the default local fake-provider path:

```powershell
uv run python -m backend.app.rag.pipeline_smoke --embedding-provider fake --generator-provider fake
uv run python -m evals.document_management_smoke
```

For a real OpenAI release, also run the provider-specific verification commands
from `docs/PROJECT_HANDOFF.md` after confirming `OPENAI_API_KEY` is present in
the runtime environment.

## Production Configuration Gate

Run the production preflight in an environment that sees the same variables as
the runtime process:

```powershell
uv run python -m backend.app.core.config_check --production
```

The preflight must have zero errors. Warnings require explicit review before
promotion.

Confirm these production settings are intentionally configured:

- `API_KEYS` uses long non-placeholder tokens.
- `API_KEY_ROLES` maps each token to `admin`, `operator`, or `viewer`.
- `API_KEY_WORKSPACE_ACCESS` scopes tokens to allowed workspaces.
- `DATABASE_URL` and `SYNC_DATABASE_URL` point at the intended database.
- `RATE_LIMIT_ENABLED=true` when exposed beyond local use.
- `CORS_ALLOWED_ORIGINS` contains only trusted browser origins.
- `OPENAI_API_KEY` exists when any OpenAI provider is enabled.

## Secret Scan

Run the repository secret scan before committing or tagging:

```powershell
rg -n "s[k]-" . -g "!*.lock" -g "!.env" -g "!.venv/**" -g "!.git/**" -g "!.uv-cache/**"
```

The command should return no real secrets. If it returns intentional test text,
make the placeholder less key-like instead of weakening the scan.

## CI Gate

After pushing the release candidate commit to `main`, confirm the GitHub Actions
`CI` workflow completed successfully for the same commit SHA.

The CI workflow must include:

- `uv sync --frozen`
- `uv run ruff check .`
- `uv run pytest`
- `uv run alembic upgrade head`
- seed document ingest and ingestion inspection
- pipeline smoke
- document-management smoke
- eval gate
- agent eval gate
- eval report artifact upload
- agent eval report artifact upload

Do not tag a release from a commit whose CI status is missing, pending, failed,
or for a different SHA.

## Deployment Dry Run

For production-style Compose, validate the stack before promotion:

```powershell
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl.exe http://127.0.0.1:8000/health
```

If the stack is already running, follow the update procedure in
`docs/DEPLOYMENT_RUNBOOK.md` instead of manually restarting individual
containers.

## Release Tag

After local verification, production configuration preflight, secret scan, and
CI gate all pass, create an annotated tag:

```powershell
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

Use the actual version chosen in the release scope. Do not reuse or move a tag
after it has been pushed unless the release is explicitly declared invalid.

## Release Notes

Release notes should include:

- Commit SHA and tag.
- Provider mode verified.
- Database migration status.
- New or changed environment variables.
- Security changes, especially API key roles and secret handling.
- Known limitations and operational follow-ups.
- Rollback instructions.

## Rollback Readiness

Before production promotion, confirm:

- Database backup exists and restore instructions are available.
- Previous deployable image or commit SHA is known.
- The previous environment variable set can be restored.
- Export storage volume retention is understood.
- The operator can run the stop/restart and backup/restore commands in
  `docs/DEPLOYMENT_RUNBOOK.md`.

If a migration cannot be safely rolled back, treat the release as a forward-only
deployment and document the recovery path before promotion.
