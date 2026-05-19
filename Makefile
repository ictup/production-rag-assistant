.PHONY: db-up db-down db-logs migrate ingest ingest-dry-run reindex-embeddings-dry-run reindex-embeddings inspect-ingestion inspect-chat-logs inspect-evals run-evals eval-gate embedding-smoke generator-smoke vector-smoke sparse-smoke hybrid-smoke rerank-smoke pipeline-smoke

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres

migrate:
	uv run alembic upgrade head

ingest:
	uv run python -m ingestion.ingest --input data/raw --workspace-id public

ingest-dry-run:
	uv run python -m ingestion.ingest --input data/raw --workspace-id public --dry-run

reindex-embeddings-dry-run:
	uv run python -m backend.app.rag.reindex_embeddings --workspace-id public

reindex-embeddings:
	uv run python -m backend.app.rag.reindex_embeddings --workspace-id public --write

inspect-ingestion:
	uv run python -m ingestion.inspect_ingestion --min-documents 1 --min-chunks 1

inspect-chat-logs:
	uv run python -m backend.app.db.inspect_chat_logs --workspace-id public --min-logs 1

inspect-evals:
	uv run python -m evals.inspect_datasets --min-total-cases 6

run-evals:
	uv run python -m evals.run --format summary

eval-gate:
	uv run python -m evals.run --format summary --fail-on-failure

embedding-smoke:
	uv run python -m backend.app.rag.embedding_smoke --expected-dimension 1536

generator-smoke:
	uv run python -m backend.app.rag.generator_smoke

vector-smoke:
	uv run python -m backend.app.rag.vector_smoke

sparse-smoke:
	uv run python -m backend.app.rag.sparse_smoke

hybrid-smoke:
	uv run python -m backend.app.rag.hybrid_smoke

rerank-smoke:
	uv run python -m backend.app.rag.rerank_smoke

pipeline-smoke:
	uv run python -m backend.app.rag.pipeline_smoke
