# Production RAG Assistant

Production-style RAG assistant backend with FastAPI, Postgres/pgvector,
deterministic evals, and CI gate.

Start here:

- [Project handoff and quick start](docs/PROJECT_HANDOFF.md)
- [Configuration and secrets guide](docs/CONFIGURATION.md)
- [Deployment runbook](docs/DEPLOYMENT_RUNBOOK.md)
- [Observability guide](docs/OBSERVABILITY.md)
- [Database observability guide](docs/DATABASE_OBSERVABILITY.md)
- [Eval trends guide](docs/EVAL_TRENDS.md)

Local web UI after starting the API:

- http://127.0.0.1:8000/app/

Build the backend image:

```powershell
docker build -t production-rag-assistant:local .
```

Run the production-style local stack:

```powershell
Copy-Item .env.example .env
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml up -d --build
```

If port 8000 is already in use, set `API_PORT` in `.env` before starting the
stack.
