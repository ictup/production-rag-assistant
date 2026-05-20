import csv
from io import StringIO
from json import dumps as json_dumps

from backend.app.db.models import ChatLog

CHAT_LOG_EXPORT_FIELDS = (
    "id",
    "request_id",
    "workspace_id",
    "session_id",
    "question",
    "answer",
    "sources",
    "retrieval",
    "usage",
    "refusal",
    "citation_valid",
    "latency_ms",
    "created_at",
)


def build_chat_log_export_record(chat_log: ChatLog) -> dict[str, object]:
    return {
        "id": str(chat_log.id),
        "request_id": chat_log.request_id,
        "workspace_id": chat_log.workspace_id,
        "session_id": str(chat_log.session_id) if chat_log.session_id else None,
        "question": chat_log.question,
        "answer": chat_log.answer,
        "sources": list(chat_log.sources),
        "retrieval": dict(chat_log.retrieval),
        "usage": dict(chat_log.usage),
        "refusal": dict(chat_log.refusal) if chat_log.refusal is not None else None,
        "citation_valid": chat_log.citation_valid,
        "latency_ms": chat_log.latency_ms,
        "created_at": chat_log.created_at.isoformat(),
    }


def serialize_chat_logs_jsonl(logs: list[ChatLog]) -> str:
    lines = [
        json_dumps(
            build_chat_log_export_record(chat_log),
            ensure_ascii=False,
            default=str,
        )
        for chat_log in logs
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def serialize_csv_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json_dumps(value, ensure_ascii=False, default=str)
    return str(value)


def serialize_chat_logs_csv(logs: list[ChatLog]) -> str:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CHAT_LOG_EXPORT_FIELDS)
    writer.writeheader()
    for chat_log in logs:
        record = build_chat_log_export_record(chat_log)
        writer.writerow(
            {
                field: serialize_csv_cell(record[field])
                for field in CHAT_LOG_EXPORT_FIELDS
            }
        )
    return output.getvalue()
