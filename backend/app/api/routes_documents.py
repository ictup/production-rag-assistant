import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.security import require_api_key
from backend.app.db.repositories import DocumentRepository
from backend.app.db.session import get_db_session
from backend.app.schemas.documents import (
    DeleteDocumentResponse,
    DocumentDetailResponse,
    DocumentsResponse,
)

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


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document_detail(
    document_id: uuid.UUID,
    _api_key: Annotated[str, Depends(require_api_key)],
    repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> DocumentDetailResponse:
    normalized_workspace_id = normalize_workspace_id(workspace_id)
    result = await repository.get_document_detail(
        document_id=document_id,
        workspace_id=normalized_workspace_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document not found",
        )
    return DocumentDetailResponse.from_result(
        workspace_id=normalized_workspace_id,
        result=result,
    )


@router.delete("/documents/{document_id}", response_model=DeleteDocumentResponse)
async def delete_document(
    document_id: uuid.UUID,
    _api_key: Annotated[str, Depends(require_api_key)],
    repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> DeleteDocumentResponse:
    normalized_workspace_id = normalize_workspace_id(workspace_id)
    deleted = await repository.delete_document(
        document_id=document_id,
        workspace_id=normalized_workspace_id,
        commit=True,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document not found",
        )
    return DeleteDocumentResponse(
        workspace_id=normalized_workspace_id,
        document_id=str(document_id),
        deleted=True,
    )
