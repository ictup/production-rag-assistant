from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.app.core.config import Settings, get_settings
from backend.app.core.rate_limit import (
    SlidingWindowRateLimiter,
    build_rate_limit_key,
    is_rate_limit_excluded,
    parse_rate_limit_excluded_paths,
)
from backend.app.main import create_app
from backend.app.observability.metrics import metrics_registry


def test_parse_rate_limit_excluded_paths_ignores_blanks() -> None:
    assert parse_rate_limit_excluded_paths("/health, ,/metrics") == [
        "/health",
        "/metrics",
    ]


def test_is_rate_limit_excluded_matches_prefix_boundaries() -> None:
    excluded_paths = ["/health", "/app"]

    assert is_rate_limit_excluded("/health", excluded_paths)
    assert is_rate_limit_excluded("/app/assets/app.js", excluded_paths)
    assert not is_rate_limit_excluded("/healthz", excluded_paths)


def test_rate_limit_key_hashes_bearer_token() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/chat",
            "headers": [(b"authorization", b"Bearer secret-token")],
            "client": ("127.0.0.1", 12345),
        }
    )

    key = build_rate_limit_key(request)

    assert key.startswith("api_key:")
    assert "secret-token" not in key


def test_sliding_window_limiter_resets_after_window() -> None:
    now = 100.0

    def clock() -> float:
        return now

    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=10, clock=clock)

    first_decision = limiter.check("client")
    second_decision = limiter.check("client")
    now = 111.0
    third_decision = limiter.check("client")

    assert first_decision.allowed is True
    assert second_decision.allowed is False
    assert second_decision.retry_after_seconds == 10
    assert third_decision.allowed is True


def test_rate_limit_is_disabled_by_default() -> None:
    client = TestClient(create_app(Settings(rate_limit_enabled=False)))

    responses = [client.get("/missing") for _ in range(3)]

    assert [response.status_code for response in responses] == [404, 404, 404]
    assert all("x-ratelimit-limit" not in response.headers for response in responses)


def test_rate_limit_returns_429_after_configured_limit() -> None:
    client = TestClient(
        create_app(
            Settings(
                rate_limit_enabled=True,
                rate_limit_requests=2,
                rate_limit_window_seconds=60,
                rate_limit_excluded_paths="/health,/metrics",
            )
        )
    )

    first_response = client.get("/missing", headers={"X-Request-ID": "req-1"})
    second_response = client.get("/missing", headers={"X-Request-ID": "req-2"})
    third_response = client.get("/missing", headers={"X-Request-ID": "req-3"})

    assert first_response.status_code == 404
    assert first_response.headers["x-ratelimit-remaining"] == "1"
    assert second_response.status_code == 404
    assert second_response.headers["x-ratelimit-remaining"] == "0"
    assert third_response.status_code == 429
    assert third_response.json() == {"detail": "rate limit exceeded"}
    assert third_response.headers["retry-after"] == "60"
    assert third_response.headers["x-request-id"] == "req-3"


def test_rate_limit_uses_bearer_token_as_identity() -> None:
    client = TestClient(
        create_app(
            Settings(
                rate_limit_enabled=True,
                rate_limit_requests=1,
                rate_limit_window_seconds=60,
            )
        )
    )

    first_token_response = client.get(
        "/missing",
        headers={"Authorization": "Bearer first-token"},
    )
    second_token_response = client.get(
        "/missing",
        headers={"Authorization": "Bearer second-token"},
    )
    repeated_first_token_response = client.get(
        "/missing",
        headers={"Authorization": "Bearer first-token"},
    )

    assert first_token_response.status_code == 404
    assert second_token_response.status_code == 404
    assert repeated_first_token_response.status_code == 429


def test_rate_limit_skips_excluded_paths() -> None:
    client = TestClient(
        create_app(
            Settings(
                rate_limit_enabled=True,
                rate_limit_requests=1,
                rate_limit_window_seconds=60,
                rate_limit_excluded_paths="/health",
            )
        )
    )

    responses = [client.get("/health") for _ in range(3)]

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert all("x-ratelimit-limit" not in response.headers for response in responses)


def test_rate_limited_requests_are_recorded_by_metrics() -> None:
    metrics_registry.reset()
    client = TestClient(
        create_app(
            Settings(
                rate_limit_enabled=True,
                rate_limit_requests=1,
                rate_limit_window_seconds=60,
                rate_limit_excluded_paths="/metrics",
            )
        )
    )

    first_response = client.get("/missing")
    second_response = client.get("/missing")
    metrics_response = client.get("/metrics")

    assert first_response.status_code == 404
    assert second_response.status_code == 429
    assert (
        'rag_requests_total{method="GET",path="/missing",status_code="429"} 1'
        in metrics_response.text
    )

    metrics_registry.reset()


def test_settings_load_rate_limit_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "10")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "30")
    monkeypatch.setenv("RATE_LIMIT_EXCLUDED_PATHS", "/health,/metrics")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.rate_limit_enabled is True
    assert settings.rate_limit_requests == 10
    assert settings.rate_limit_window_seconds == 30
    assert settings.rate_limit_excluded_paths == "/health,/metrics"

    get_settings.cache_clear()
