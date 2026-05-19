import json
from pathlib import Path

import yaml

ALERTS_PATH = Path("monitoring/prometheus/rag-alerts.yml")
DASHBOARD_PATH = Path("monitoring/grafana/rag-dashboard.json")
OBSERVABILITY_DOC_PATH = Path("docs/OBSERVABILITY.md")
README_PATH = Path("README.md")
HANDOFF_PATH = Path("docs/PROJECT_HANDOFF.md")
RUNBOOK_PATH = Path("docs/DEPLOYMENT_RUNBOOK.md")

CORE_METRICS = {
    "rag_requests_total",
    "rag_request_latency_seconds_bucket",
    "rag_refusals_total",
    "rag_citation_invalid_total",
    "rag_provider_latency_seconds_bucket",
    "rag_provider_tokens_total",
    "rag_provider_errors_total",
}


def load_alert_rules() -> dict:
    return yaml.safe_load(ALERTS_PATH.read_text(encoding="utf-8"))


def load_dashboard() -> dict:
    return json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))


def collect_dashboard_exprs(dashboard: dict) -> str:
    expressions: list[str] = []

    for panel in dashboard["panels"]:
        for target in panel.get("targets", []):
            expressions.append(target["expr"])

    return "\n".join(expressions)


def test_prometheus_alert_rules_parse_and_cover_core_alerts() -> None:
    alerts = load_alert_rules()
    rules = alerts["groups"][0]["rules"]
    alert_names = {rule["alert"] for rule in rules}

    assert alert_names == {
        "RAGHigh5xxRate",
        "RAGHighRateLimitRate",
        "RAGHighHttpLatencyP95",
        "RAGProviderErrors",
        "RAGHighProviderLatencyP95",
        "RAGInvalidCitations",
        "RAGNoRetrievalRefusalsSpike",
    }


def test_prometheus_alert_rules_reference_existing_metrics() -> None:
    alerts = load_alert_rules()
    expressions = "\n".join(
        rule["expr"]
        for group in alerts["groups"]
        for rule in group["rules"]
    )

    for metric in CORE_METRICS - {"rag_provider_tokens_total"}:
        assert metric in expressions


def test_grafana_dashboard_json_references_existing_metrics() -> None:
    dashboard = load_dashboard()
    expressions = collect_dashboard_exprs(dashboard)

    assert dashboard["title"] == "Production RAG Assistant"
    assert len(dashboard["panels"]) >= 6
    for metric in CORE_METRICS:
        assert metric in expressions


def test_observability_doc_links_templates_and_metrics_endpoint() -> None:
    doc = OBSERVABILITY_DOC_PATH.read_text(encoding="utf-8")

    assert "monitoring/grafana/rag-dashboard.json" in doc
    assert "monitoring/prometheus/rag-alerts.yml" in doc
    assert "curl.exe http://127.0.0.1:8000/metrics" in doc
    for metric in CORE_METRICS:
        base_metric = metric.removesuffix("_bucket")
        assert base_metric in doc


def test_observability_doc_is_linked_from_entry_documents() -> None:
    expected_link = "docs/OBSERVABILITY.md"

    assert expected_link in README_PATH.read_text(encoding="utf-8")
    assert expected_link in HANDOFF_PATH.read_text(encoding="utf-8")
    assert expected_link in RUNBOOK_PATH.read_text(encoding="utf-8")
