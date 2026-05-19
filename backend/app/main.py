from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api import (
    routes_chat,
    routes_chat_sessions,
    routes_documents,
    routes_health,
    routes_metrics,
)
from backend.app.core.config import Settings, get_settings
from backend.app.core.cors import add_cors_middleware
from backend.app.core.logging import RequestLoggingMiddleware, configure_logging
from backend.app.core.rate_limit import add_rate_limit_middleware
from backend.app.core.request_id import RequestIDMiddleware
from backend.app.observability.metrics import RequestMetricsMiddleware

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Production RAG Assistant",
        version=settings.app_version,
    )
    app.state.settings = settings
    add_rate_limit_middleware(app, settings)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RequestMetricsMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    add_cors_middleware(app, settings)

    app.include_router(routes_health.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_chat_sessions.router)
    app.include_router(routes_documents.router)
    app.include_router(routes_metrics.router)
    app.mount("/app", StaticFiles(directory=STATIC_DIR, html=True), name="app")

    @app.get("/", include_in_schema=False)
    async def redirect_to_app() -> RedirectResponse:
        return RedirectResponse(url="/app/")

    return app


app = create_app()
