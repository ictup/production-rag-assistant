# Portfolio Presentation Guide

This document keeps the public-facing project positioning in one place. It is
meant for GitHub About settings, portfolio pages, resumes, interview
walkthroughs, and future README updates.

## Recommended Name

Use this display name:

```text
Production RAG Assistant
```

The current repository name, `Production_RAG_Assistant`, is understandable and
safe to keep. If the repository is ever renamed, prefer the lowercase GitHub
style:

```text
production-rag-assistant
```

Avoid a vague product name unless the project becomes a standalone product with
branding, hosted docs, and a real demo environment. For a portfolio repository,
the clear name is stronger because it tells reviewers the architecture category
immediately.

## GitHub About

Use this repository description:

```text
Production-ready RAG backend with FastAPI, pgvector, hybrid retrieval, eval gates, observability, RBAC, async exports, and OpenAI providers.
```

Use this website link while no hosted demo exists:

```text
https://github.com/ictup/Production_RAG_Assistant/releases/tag/v0.1.0
```

Recommended topics:

```text
rag
retrieval-augmented-generation
llm
fastapi
postgresql
pgvector
vector-search
hybrid-search
semantic-search
openai
docker
alembic
prometheus
observability
evals
rbac
sse
python
production-ready
ai-engineering
```

## Portfolio Positioning

Use this short positioning line:

```text
Built as a production-style AI backend project to demonstrate RAG architecture, retrieval quality, API design, security boundaries, eval gates, observability, and deployment readiness.
```

The strongest narrative is:

```text
This project shows the engineering layer around RAG: not only prompting and retrieval, but also tenancy, API design, database migrations, async exports, operational checks, metrics, docs, and release discipline.
```

## What To Show First

For portfolio reviewers, lead with these signals:

- The README first screen: badges, one-sentence purpose, project highlights,
  release status, and quick start.
- The `v0.1.0` release notes and GitHub Actions CI result.
- The architecture diagram in README.
- The validation checklist showing tests, evals, smoke tests, Compose config,
  and secret scan.
- The browser UI at `/app/` if running locally.

## Suggested Demo Assets

Add these screenshots or GIFs when available:

- Workspace and document management screen.
- Streaming chat with citations.
- Admin overview with chat logs, workspace audit logs, and export jobs.
- Terminal screenshot of the validation checklist passing.

Keep demo assets focused on real product behavior. Avoid generic AI artwork or
stock-style images because the project is being judged as backend and AI systems
engineering work.

## Resume Bullet

Use or adapt this resume bullet:

```text
Built a production-style RAG backend with FastAPI, Postgres/pgvector, hybrid retrieval, streaming chat, workspace isolation, RBAC-style API keys, async export jobs, OpenAI provider integrations, Prometheus metrics, Docker deployment, CI, and deterministic eval gates.
```

## Interview Walkthrough

Use this order when explaining the project:

1. Problem: a RAG system needs more than retrieval and prompting to be usable.
2. Architecture: FastAPI API, Postgres/pgvector data layer, retrieval pipeline,
   provider layer, evals, observability, and Docker runtime.
3. Retrieval: vector plus sparse search, RRF fusion, optional query rewrite and
   reranking, citation validation, and refusal guards.
4. Production concerns: workspaces, API keys, roles, archive write protection,
   audit logs, async export worker, config preflight, secret mapping, and release
   checklist.
5. Quality: tests, deterministic eval gate, smoke tests, CI, and release notes.

## Maintenance Rules

- Keep README public-facing and concise near the top.
- Put long operational details in `docs/`.
- Update the local test baseline after adding or removing tests.
- Do not include real API keys, private data, or local-only screenshots with
  secrets visible.
- Keep the GitHub About description aligned with the README first paragraph.
