# Database Observability Guide

This guide covers PostgreSQL slow query visibility for the Docker Compose
deployment.

## What Is Enabled

The local and production-style Compose files start Postgres with:

```text
shared_preload_libraries=pg_stat_statements
pg_stat_statements.track=all
track_io_timing=on
log_min_duration_statement=${POSTGRES_LOG_MIN_DURATION_STATEMENT_MS:-1000}
```

Alembic migration `0005_enable_pg_stat_statements` creates the
`pg_stat_statements` extension.

`POSTGRES_LOG_MIN_DURATION_STATEMENT_MS` controls the slow query log threshold.
The default is `1000`, which means statements taking at least one second are
written to Postgres logs.

## Restart Requirement

`shared_preload_libraries` is read at Postgres process start. If you change the
Compose command or `POSTGRES_LOG_MIN_DURATION_STATEMENT_MS`, restart Postgres:

```powershell
docker compose down
docker compose up -d postgres
```

For the production-style stack:

```powershell
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
```

## View Slow Query Logs

Local Compose:

```powershell
docker compose logs -f postgres
```

Production-style Compose:

```powershell
docker compose -f docker-compose.prod.yml logs -f postgres
```

Look for log lines containing `duration:`. Those are statements whose runtime
met or exceeded `log_min_duration_statement`.

## Inspect pg_stat_statements

Production-style Compose:

```powershell
docker compose -f docker-compose.prod.yml exec postgres psql `
  -U rag `
  -d rag `
  -c "SELECT query, calls, total_exec_time, mean_exec_time, rows FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;"
```

Local Compose:

```powershell
docker compose exec postgres psql `
  -U rag `
  -d rag `
  -c "SELECT query, calls, total_exec_time, mean_exec_time, rows FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 20;"
```

Useful columns:

- `calls`: how many times the normalized statement ran.
- `total_exec_time`: total time spent in the statement.
- `mean_exec_time`: average execution time.
- `rows`: rows returned or affected.
- `shared_blks_read`: blocks read from disk or OS cache.
- `shared_blks_hit`: blocks served from shared buffers.

## Reset Statement Statistics

Reset after a deployment or after collecting a baseline:

```powershell
docker compose -f docker-compose.prod.yml exec postgres psql `
  -U rag `
  -d rag `
  -c "SELECT pg_stat_statements_reset();"
```

## Investigation Workflow

1. Check API symptoms first: high latency, 5xx, or slow trace spans.
2. Check Postgres logs for `duration:` lines.
3. Query `pg_stat_statements` ordered by `total_exec_time`.
4. Query `pg_stat_statements` ordered by `mean_exec_time`.
5. Match slow statement shapes to code paths, not raw parameter values.
6. Use `EXPLAIN (ANALYZE, BUFFERS)` on a representative query in a safe
   non-production environment.
7. Fix with a targeted index, query shape change, or pagination limit.
8. Rerun the same workload and compare `pg_stat_statements` before and after.

## Common Causes

- Missing workspace or timestamp indexes.
- Large unbounded document or chat log scans.
- Vector retrieval asking for too many candidates.
- Sparse retrieval over a large corpus without appropriate GIN indexes.
- Reindex jobs competing with online traffic.
- Running with a stale query plan after major data volume changes.

## Safety Notes

- Slow query logs can include SQL text. Avoid logging sensitive parameter
  values in application-generated SQL.
- Do not paste production query text containing user data into tickets or chat.
- `pg_stat_statements` normalizes constants, which is safer for sharing than
  raw slow query logs.
- Keep `POSTGRES_LOG_MIN_DURATION_STATEMENT_MS` conservative in production to
  avoid excessive log volume.
