from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.security import require_api_key
from backend.app.db.repositories import DocumentRepository
from backend.app.db.session import get_db_session
from backend.app.schemas.documents import DocumentsResponse

router = APIRouter(tags=["documents"])


async def get_document_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentRepository:
    return DocumentRepository(session=session)


def normalize_workspace_id(workspace_id: str | None) -> str:
    if workspace_id is None:
        return "public"

    normalized = workspace_id.strip()
    return normalized or "public"


@router.get("/documents", response_model=DocumentsResponse)
async def list_documents(
    _api_key: Annotated[str, Depends(require_api_key)],
    repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentsResponse:
    normalized_workspace_id = normalize_workspace_id(workspace_id)
    result = await repository.list_documents(
        workspace_id=normalized_workspace_id,
        limit=limit,
        offset=offset,
    )
    return DocumentsResponse.from_result(
        workspace_id=normalized_workspace_id,
        limit=limit,
        offset=offset,
        result=result,
    )
