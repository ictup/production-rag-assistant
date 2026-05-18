from fastapi import APIRouter, Response

from backend.app.observability.metrics import (
    PROMETHEUS_CONTENT_TYPE,
    metrics_registry,
)

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(
        content=metrics_registry.render_prometheus(),
        media_type=PROMETHEUS_CONTENT_TYPE,
    )
