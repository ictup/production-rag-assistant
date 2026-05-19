# Observability Guide

The API exposes Prometheus metrics at `/metrics`. This guide maps those
metrics to dashboard panels and alert rules.

## Templates

- Grafana dashboard: `monitoring/grafana/rag-dashboard.json`
- Prometheus alert rules: `monitoring/prometheus/rag-alerts.yml`

Import the Grafana dashboard and point `${DS_PROMETHEUS}` at your Prometheus
datasource. Load the Prometheus rule file into your Prometheus or compatible
alerting system.

## Metric Catalog

| Metric | Type | Purpose |
| --- | --- | --- |
| `rag_requests_total` | Counter | HTTP request volume by method, path, and status code. |
| `rag_request_latency_seconds` | Histogram | HTTP request latency by method and path. |
| `rag_refusals_total` | Counter | RAG refusal count by refusal reason. |
| `rag_citation_invalid_total` | Counter | Responses that failed citation validation. |
| `rag_provider_latency_seconds` | Histogram | Upstream embedding and generation provider latency. |
| `rag_provider_tokens_total` | Counter | Upstream provider token usage by provider, model, and token type. |
| `rag_provider_errors_total` | Counter | Upstream provider errors by provider, operation, and category. |

## Dashboard Panels

The dashboard focuses on the first questions an operator needs to answer:

- Is the API receiving traffic?
- Are 5xx or 429 responses increasing?
- Is API latency rising?
- Are upstream providers slow or failing?
- Are token rates changing unexpectedly?
- Are refusals or invalid citations increasing?

The dashboard intentionally uses only metrics already emitted by the API. It
does not require new runtime services beyond Prometheus and Grafana.

## Alert Rules

The alert template includes:

- `RAGHigh5xxRate`: more than 5% of requests return 5xx for 10 minutes.
- `RAGHighRateLimitRate`: more than 20% of requests return 429 for 10 minutes.
- `RAGHighHttpLatencyP95`: API p95 latency above 2 seconds for 15 minutes.
- `RAGProviderErrors`: provider errors observed for 5 minutes.
- `RAGHighProviderLatencyP95`: provider p95 latency above 5 seconds.
- `RAGInvalidCitations`: at least one invalid citation in 15 minutes.
- `RAGNoRetrievalRefusalsSpike`: more than five no-retrieval refusals in 15 minutes.

Tune thresholds after observing real traffic. The defaults are intentionally
conservative starting points, not final service-level objectives.

## Local Verification

Start the production-style stack:

```powershell
docker compose -f docker-compose.prod.yml up -d --build
```

Confirm metrics are exposed:

```powershell
curl.exe http://127.0.0.1:8000/metrics
```

If `API_PORT` is not `8000`, replace the port in the URL.

## Operational Notes

- A high 429 rate usually means `RATE_LIMIT_REQUESTS` is too low for current
  traffic or a client is retrying aggressively.
- Provider errors should be correlated with API logs and provider status.
- Invalid citation alerts should be treated as answer quality regressions.
- Refusal spikes can mean ingestion failed, workspace IDs do not match, or
  embeddings were not reindexed after provider changes.
