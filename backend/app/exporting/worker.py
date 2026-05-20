import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from backend.app.core.config import Settings, get_settings
from backend.app.db.models import ExportJob
from backend.app.db.repositories import ChatLogRepository, ExportJobRepository
from backend.app.db.session import get_sessionmaker
from backend.app.exporting.chat_logs import (
    serialize_chat_logs_csv,
    serialize_chat_logs_jsonl,
)
from backend.app.schemas.export_jobs import ChatLogExportFilters

EXPORT_MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "jsonl": "application/x-ndjson; charset=utf-8",
}


@dataclass(frozen=True)
class ExportJobExecutionResult:
    job: ExportJob
    result_path: Path | None = None


async def execute_next_export_job(
    *,
    export_job_repository: ExportJobRepository,
    chat_log_repository: ChatLogRepository,
    settings: Settings,
) -> ExportJobExecutionResult | None:
    export_job = await export_job_repository.claim_next_pending_export_job(
        commit=True,
    )
    if export_job is None:
        return None
    return await execute_export_job(
        export_job=export_job,
        export_job_repository=export_job_repository,
        chat_log_repository=chat_log_repository,
        settings=settings,
    )


async def execute_export_job(
    *,
    export_job: ExportJob,
    export_job_repository: ExportJobRepository,
    chat_log_repository: ChatLogRepository,
    settings: Settings,
) -> ExportJobExecutionResult:
    try:
        result_path = await write_export_job_file(
            export_job=export_job,
            chat_log_repository=chat_log_repository,
            storage_dir=Path(settings.export_storage_dir),
        )
        payload_size = result_path.stat().st_size
        completed_job = await export_job_repository.complete_export_job(
            job_id=export_job.id,
            result_uri=result_path.resolve().as_uri(),
            result_media_type=media_type_for_format(export_job.format),
            result_size_bytes=payload_size,
            commit=True,
        )
        return ExportJobExecutionResult(
            job=completed_job or export_job,
            result_path=result_path,
        )
    except Exception as exc:
        failed_job = await export_job_repository.fail_export_job(
            job_id=export_job.id,
            error_message=str(exc),
            commit=True,
        )
        return ExportJobExecutionResult(job=failed_job or export_job)


async def write_export_job_file(
    *,
    export_job: ExportJob,
    chat_log_repository: ChatLogRepository,
    storage_dir: Path,
) -> Path:
    if export_job.export_type != "chat_logs":
        raise ValueError(f"unsupported export type: {export_job.export_type}")

    filters = ChatLogExportFilters.model_validate(dict(export_job.filters_))
    logs = await chat_log_repository.list_recent_chat_logs(
        workspace_id=export_job.workspace_id,
        limit=filters.limit,
        offset=filters.offset,
        session_id=filters.session_id,
        request_id=filters.request_id,
        refusal_only=filters.refusal_only,
        citation_valid=filters.citation_valid,
    )

    if export_job.format == "csv":
        payload = serialize_chat_logs_csv(logs).encode("utf-8")
    elif export_job.format == "jsonl":
        payload = serialize_chat_logs_jsonl(logs).encode("utf-8")
    else:
        raise ValueError(f"unsupported export format: {export_job.format}")

    storage_dir.mkdir(parents=True, exist_ok=True)
    result_path = storage_dir / build_export_job_filename(export_job)
    result_path.write_bytes(payload)
    return result_path


def media_type_for_format(export_format: str) -> str:
    try:
        return EXPORT_MEDIA_TYPES[export_format]
    except KeyError as exc:
        raise ValueError(f"unsupported export format: {export_format}") from exc


def build_export_job_filename(export_job: ExportJob) -> str:
    workspace = safe_filename_part(export_job.workspace_id)
    export_type = safe_filename_part(export_job.export_type)
    export_format = safe_filename_part(export_job.format)
    return f"{export_type}-{workspace}-{export_job.id}.{export_format}"


def safe_filename_part(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip())
    return normalized.strip(".-") or "export"


async def run_export_worker_once(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    async with get_sessionmaker()() as session:
        result = await execute_next_export_job(
            export_job_repository=ExportJobRepository(session=session),
            chat_log_repository=ChatLogRepository(session=session),
            settings=settings,
        )
    if result is None:
        return "no pending export job"
    if result.result_path is None:
        return f"export job {result.job.id} failed"
    return f"export job {result.job.id} wrote {result.result_path}"


def main() -> None:
    print(asyncio.run(run_export_worker_once()))


if __name__ == "__main__":
    main()
