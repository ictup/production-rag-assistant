import math
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from hashlib import sha256
from threading import Lock

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.app.core.config import Settings
from backend.app.core.request_id import REQUEST_ID_HEADER, get_request_id


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int
    reset_after_seconds: int


class SlidingWindowRateLimiter:
    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> RateLimitDecision:
        now = self.clock()
        window_start = now - self.window_seconds

        with self._lock:
            timestamps = self._requests[key]
            while timestamps and timestamps[0] <= window_start:
                timestamps.popleft()

            if len(timestamps) >= self.limit:
                retry_after_seconds = max(
                    1,
                    math.ceil(timestamps[0] + self.window_seconds - now),
                )
                return RateLimitDecision(
                    allowed=False,
                    limit=self.limit,
                    remaining=0,
                    retry_after_seconds=retry_after_seconds,
                    reset_after_seconds=retry_after_seconds,
                )

            timestamps.append(now)
            reset_after_seconds = max(
                1,
                math.ceil(timestamps[0] + self.window_seconds - now),
            )
            return RateLimitDecision(
                allowed=True,
                limit=self.limit,
                remaining=max(0, self.limit - len(timestamps)),
                retry_after_seconds=0,
                reset_after_seconds=reset_after_seconds,
            )


def parse_rate_limit_excluded_paths(raw_paths: str) -> list[str]:
    return [
        path.strip()
        for path in raw_paths.split(",")
        if path.strip()
    ]


def path_matches_prefix(path: str, prefix: str) -> bool:
    normalized_prefix = prefix.rstrip("/")
    if normalized_prefix == "":
        return path == "/"
    return path == normalized_prefix or path.startswith(f"{normalized_prefix}/")


def is_rate_limit_excluded(path: str, excluded_paths: list[str]) -> bool:
    return any(path_matches_prefix(path, prefix) for prefix in excluded_paths)


def build_rate_limit_key(request: Request) -> str:
    authorization = request.headers.get("authorization")
    if authorization is not None:
        scheme, separator, token = authorization.partition(" ")
        if separator and scheme.lower() == "bearer" and token.strip():
            token_hash = sha256(token.strip().encode("utf-8")).hexdigest()
            return f"api_key:{token_hash}"

    if request.client is not None and request.client.host:
        return f"ip:{request.client.host}"

    return "ip:unknown"


def add_rate_limit_headers(
    response: Response,
    decision: RateLimitDecision,
) -> None:
    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    response.headers["X-RateLimit-Reset"] = str(decision.reset_after_seconds)
    if not decision.allowed:
        response.headers["Retry-After"] = str(decision.retry_after_seconds)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        limiter: SlidingWindowRateLimiter,
        excluded_paths: list[str],
    ) -> None:
        super().__init__(app)
        self.limiter = limiter
        self.excluded_paths = excluded_paths

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if is_rate_limit_excluded(request.url.path, self.excluded_paths):
            return await call_next(request)

        decision = self.limiter.check(build_rate_limit_key(request))
        if not decision.allowed:
            request_id = get_request_id(request)
            response = JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded"},
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            add_rate_limit_headers(response, decision)
            return response

        response = await call_next(request)
        add_rate_limit_headers(response, decision)
        return response


def add_rate_limit_middleware(app: FastAPI, settings: Settings) -> None:
    if not settings.rate_limit_enabled:
        return

    app.add_middleware(
        RateLimitMiddleware,
        limiter=SlidingWindowRateLimiter(
            limit=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        ),
        excluded_paths=parse_rate_limit_excluded_paths(
            settings.rate_limit_excluded_paths
        ),
    )
