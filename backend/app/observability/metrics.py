import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
DEFAULT_LATENCY_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


def format_metric_value(value: float | int) -> str:
    return f"{value:.15g}" if isinstance(value, float) else str(value)


def escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def format_labels(labels: dict[str, str]) -> str:
    return ",".join(
        f'{key}="{escape_label_value(value)}"' for key, value in labels.items()
    )


class MetricsRegistry:
    def __init__(
        self,
        *,
        latency_buckets: Iterable[float] = DEFAULT_LATENCY_BUCKETS,
    ) -> None:
        self.latency_buckets = tuple(sorted(latency_buckets))
        self._lock = Lock()
        self._request_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        self._latency_bucket_counts: dict[tuple[str, str], list[int]] = defaultdict(
            lambda: [0] * len(self.latency_buckets)
        )
        self._latency_counts: dict[tuple[str, str], int] = defaultdict(int)
        self._latency_sums: dict[tuple[str, str], float] = defaultdict(float)

    def reset(self) -> None:
        with self._lock:
            self._request_counts.clear()
            self._latency_bucket_counts.clear()
            self._latency_counts.clear()
            self._latency_sums.clear()

    def observe_http_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        latency_seconds: float,
    ) -> None:
        route_key = (method, path)
        status_key = (method, path, str(status_code))

        with self._lock:
            self._request_counts[status_key] += 1
            self._latency_counts[route_key] += 1
            self._latency_sums[route_key] += latency_seconds

            bucket_counts = self._latency_bucket_counts[route_key]
            for index, upper_bound in enumerate(self.latency_buckets):
                if latency_seconds <= upper_bound:
                    bucket_counts[index] += 1

    def render_prometheus(self) -> str:
        with self._lock:
            request_counts = dict(self._request_counts)
            latency_bucket_counts = {
                key: list(value)
                for key, value in self._latency_bucket_counts.items()
            }
            latency_counts = dict(self._latency_counts)
            latency_sums = dict(self._latency_sums)

        lines = [
            "# HELP rag_requests_total Total HTTP requests.",
            "# TYPE rag_requests_total counter",
        ]
        for method, path, status_code in sorted(request_counts):
            labels = format_labels(
                {
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                }
            )
            lines.append(
                f"rag_requests_total{{{labels}}} "
                f"{request_counts[(method, path, status_code)]}"
            )

        lines.extend(
            [
                "# HELP rag_request_latency_seconds HTTP request latency.",
                "# TYPE rag_request_latency_seconds histogram",
            ]
        )
        for method, path in sorted(latency_counts):
            base_labels = {
                "method": method,
                "path": path,
            }
            for upper_bound, count in zip(
                self.latency_buckets,
                latency_bucket_counts[(method, path)],
                strict=True,
            ):
                labels = format_labels(
                    {
                        **base_labels,
                        "le": format_metric_value(upper_bound),
                    }
                )
                lines.append(
                    f"rag_request_latency_seconds_bucket{{{labels}}} {count}"
                )

            inf_labels = format_labels({**base_labels, "le": "+Inf"})
            lines.append(
                "rag_request_latency_seconds_bucket"
                f"{{{inf_labels}}} {latency_counts[(method, path)]}"
            )
            route_labels = format_labels(base_labels)
            lines.append(
                "rag_request_latency_seconds_count"
                f"{{{route_labels}}} {latency_counts[(method, path)]}"
            )
            lines.append(
                "rag_request_latency_seconds_sum"
                f"{{{route_labels}}} "
                f"{format_metric_value(latency_sums[(method, path)])}"
            )

        return "\n".join(lines) + "\n"


metrics_registry = MetricsRegistry()


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            metrics_registry.observe_http_request(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                latency_seconds=max(0.0, time.perf_counter() - started_at),
            )
