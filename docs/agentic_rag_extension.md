# Agentic RAG Support Workflow

This document tracks the V3 extension of Production RAG Assistant. The goal is
to turn the existing RAG backend into a controlled, observable, evaluable
support triage workflow.

The extension is not an unrestricted autonomous agent. It is a backend-owned
state machine with explicit tools, schemas, risk policies, human approval for
high-risk paths, tracing, metrics, and evals.

## Target Workflow

```text
support ticket
-> classify ticket
-> retrieve grounded knowledge
-> search historical support cases
-> draft cited response
-> run risk check
-> route high-risk drafts to human approval
-> finalize safe responses
```

## Current Foundation

The repository already provides the production RAG layer that this workflow can
reuse:

- FastAPI API surface.
- Workspace isolation and API key roles.
- Postgres and pgvector data model.
- Hybrid vector and sparse retrieval.
- Query rewrite, reranking, citation validation, and refusal guards.
- Chat logs, export jobs, audit logs, metrics, evals, Docker, and CI.

## Step 1 Scope

The first implementation step adds only the stable contracts for the future
workflow:

- `backend.app.agent.state.AgentState`
- `backend.app.schemas.agent.SupportTicketRequest`
- rule-based ticket classification policy
- rule-based support risk policy
- MCP-style tool specs and tool call records

This step intentionally does not add LangGraph, new database tables, or public
agent endpoints. Those will be added after the contracts are tested.

## Tool Registry

The MVP workflow will use these backend-controlled tools:

| Tool | Purpose | Risk |
| --- | --- | --- |
| `classify_ticket_tool` | Classify the incoming support ticket | low |
| `rag_search_tool` | Search the internal RAG knowledge base | low |
| `ticket_lookup_tool` | Find similar historical support tickets | low |
| `draft_response_tool` | Draft a cited support response | medium |
| `risk_check_tool` | Classify risk and approval need | low |
| `human_approval_tool` | Create an internal approval request | high |

Tools must have explicit input and output schemas. The workflow must not execute
arbitrary code, run unrestricted SQL, send external messages, or call tools that
are not registered by the backend.

## Risk Policy

High-risk requests require human approval before finalization. Examples:

- deleting or exporting customer data
- handling private customer prompts or PII
- secrets, credentials, API keys, or prompt injection attempts
- refunds or account state changes
- production-impacting actions on urgent or high-priority tickets

Medium-risk requests can be drafted without approval but should remain careful
and auditable. Examples include deployment guidance, rate-limit tuning,
migration advice, and latency troubleshooting.

## Planned Next Steps

1. Create the next release tag and release notes.

## Step 2 Scope

The second implementation step adds the first public API entrypoint:

```text
POST /agent/support-triage
```

The route accepts a `SupportTicketRequest`, enforces API key workspace access,
runs the current rule-based classification and risk policies, and returns an
`AgentTriageResponse`. It is still a skeleton: no LangGraph, no historical
ticket lookup, no cited response drafting, and no approval table are used yet.

## Step 3 Scope

The third implementation step adds the first real workflow tool:

```text
rag_search_tool
```

Low-risk tickets now call the existing RAG retriever through
`RagPipeline.retrieve_context()`. The tool returns grounded sources, formatted
retrieval context, top score, refusal recommendation, and retrieval metadata.
High-risk tickets still stop before retrieval and return `approval_required`.

## Step 4 Scope

The fourth implementation step adds historical support ticket lookup:

```text
ticket_lookup_tool
```

The database now has a `support_tickets` table for historical cases. The lookup
repository filters by workspace, category, query text, and optional tags. The
agent low-risk path now calls `ticket_lookup_tool` after `rag_search_tool` and
returns `historical_cases` in `AgentTriageResponse`. No write API is exposed for
support tickets yet.

## Step 5 Scope

The fifth implementation step adds deterministic cited draft generation:

```text
draft_response_tool
```

The tool builds a customer-facing support draft from retrieved RAG sources,
retrieval context, and historical cases. It returns the draft, cited source IDs,
cited historical case IDs, and a citation validation boolean. The low-risk
agent path now calls `draft_response_tool` after `ticket_lookup_tool`, returns
the draft as the finalized response, and records citation metrics. This step
does not call an external LLM and does not create approval records yet.

## Step 6 Scope

The sixth implementation step adds a graph runner abstraction without adding
LangGraph as a runtime dependency:

```text
AgentGraphRunner
AgentGraphNode
AgentNodeRunRecord
```

The support triage API still follows the same behavior, but the internal
workflow is now executed as named nodes: `classify_ticket`, `risk_check`,
`rag_search`, `ticket_lookup`, and `draft_response`. High-risk requests stop
after `risk_check`. Responses now include `node_runs`, and metrics include
`node_count`, making the workflow easier to observe and replace with a real
graph engine later.

## Step 7 Scope

The seventh implementation step adds the approval persistence foundation:

```text
agent_approvals
AgentApprovalRepository
```

The database now has an `agent_approvals` table for pending, approved, and
rejected human approval records. The repository can create pending approvals,
load approvals by ID or run ID, list approvals by workspace and status, and
apply an approved or rejected decision with optional human feedback. No approval
API endpoints are exposed yet, and the support triage workflow does not create
approval rows until the API and high-risk workflow wiring are added.

## Step 8 Scope

The eighth implementation step exposes the approval API foundation:

```text
GET /agent/approvals
GET /agent/approvals/{approval_id}
POST /agent/approvals/{approval_id}/decision
```

The list and detail endpoints require an operator role and enforce workspace
access. The decision endpoint requires an admin role and accepts only
`approved` or `rejected` decisions with optional human feedback. The endpoints
read and update existing `agent_approvals` rows. At this step, the support
triage workflow did not create approval rows automatically; that wiring was
added in Step 9.

## Step 9 Scope

The ninth implementation step connects high-risk support triage runs to pending
approval creation:

```text
POST /agent/support-triage
-> risk_check
-> AgentApprovalRepository.create_agent_approval
```

When a request requires human approval, the workflow now creates a pending
`agent_approvals` row containing the run ID, ticket ID, workspace ID, request
ID, actor hash, category, risk reason, customer message, draft answer,
tool calls, node runs, and request metadata. The API response returns the
created `approval_id`. Low-risk finalized requests do not create approval rows.

## Step 10 Scope

The tenth implementation step adds Agent-specific Prometheus metrics:

```text
rag_agent_triage_requests_total
rag_agent_approvals_created_total
rag_agent_node_runs_total
rag_agent_node_latency_seconds
```

`POST /agent/support-triage` now records triage outcomes, approval creation,
node execution counts, and node latency histograms after the workflow returns.
Labels intentionally stay low cardinality: status, category, risk level,
approval-required boolean, node name, and node success. Run IDs, ticket IDs,
workspace IDs, request IDs, and actor hashes are not emitted as metric labels.

## Step 11 Scope

The eleventh implementation step adds deterministic Agent support triage evals:

```text
evals/datasets/agent_support_triage.jsonl
python -m evals.agent_run
```

The dataset contains 30 support cases across `rag_failure`, `evaluation`,
`serving_latency`, `rate_limit`, `deployment`, `unknown`, `data_privacy`, and
`security`. The runner executes the real support triage workflow with fake RAG,
fake historical ticket lookup, and fake approval persistence, then scores the
response status, category, risk level, approval requirement, node sequence, tool
sequence, citation validity, answer keywords, and approval reason keywords. CI
now runs this Agent eval gate and uploads the JSON report artifact.
