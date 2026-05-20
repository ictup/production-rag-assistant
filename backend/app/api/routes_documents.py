import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.security import ApiPrincipal, require_api_key, resolve_workspace_id
from backend.app.api.workspace_validation import (
    get_workspace_repository,
    require_active_workspace,
)
from backend.app.db.repositories import DocumentRepository, WorkspaceRepository
from backend.app.db.session import get_db_session
from backend.app.rag.embedding_pipeline import embed_chunks
from backend.app.rag.embeddings import EmbeddingClient, build_embedding_client
from backend.app.rag.reindex_embeddings import (
    ReindexEmbeddingsStats,
    reindex_embeddings,
)
from backend.app.schemas.documents import (
    CreateDocumentRequest,
    CreateDocumentResponse,
    DeleteDocumentResponse,
    DocumentDetailResponse,
    DocumentsResponse,
    ReindexDocumentsRequest,
    ReindexDocumentsResponse,
)
from ingestion.chunking import chunk_document
from ingestion.hashing import compute_content_hash
from ingestion.parse_markdown import load_markdown_text

router = APIRouter(tags=["documents"])
ReindexRunner = Callable[..., Awaitable[ReindexEmbeddingsStats]]


async def get_document_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentRepository:
    return DocumentRepository(session=session)


async def get_embedding_client() -> EmbeddingClient:
    return build_embedding_client()


async def get_reindex_runner() -> ReindexRunner:
    return reindex_embeddings


@router.get("/documents", response_model=DocumentsResponse)
async def list_documents(
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentsResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
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


@router.post("/documents", response_model=CreateDocumentResponse)
async def create_document(
    request: CreateDocumentRequest,
    response: Response,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    workspace_repository: Annotated[
        WorkspaceRepository,
        Depends(get_workspace_repository),
    ],
    embedding_client: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> CreateDocumentResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
    await require_active_workspace(
        workspace_id=normalized_workspace_id,
        repository=workspace_repository,
    )
    try:
        raw_document = load_markdown_text(
            request.markdown,
            source_uri=request.source_uri,
            default_workspace_id=normalized_workspace_id,
            title=request.title,
            author=request.author,
            visibility=request.visibility,
            metadata=request.metadata,
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    content_hash = compute_content_hash(raw_document.text)
    existing_document_id = await repository.get_document_id_by_hash(content_hash)
    if existing_document_id is not None:
        return CreateDocumentResponse(
            workspace_id=normalized_workspace_id,
            document_id=str(existing_document_id),
            content_hash=content_hash,
            inserted=False,
            chunks_inserted=0,
            reason="duplicate_content_hash",
        )

    try:
        chunks = chunk_document(
            raw_document,
            chunk_size_tokens=request.chunk_size_tokens,
            chunk_overlap_tokens=request.chunk_overlap_tokens,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="document must produce at least one chunk",
        )

    chunk_embeddings = await embed_chunks(chunks, embedding_client)
    result = await repository.ingest_document(
        raw_document,
        chunks,
        content_hash=content_hash,
        chunk_embeddings=chunk_embeddings,
        commit=True,
    )
    if result.inserted:
        response.status_code = status.HTTP_201_CREATED

    return CreateDocumentResponse(
        workspace_id=normalized_workspace_id,
        document_id=str(result.document_id),
        content_hash=result.content_hash,
        inserted=result.inserted,
        chunks_inserted=result.chunks_inserted,
        reason=result.reason,
    )


@router.post("/documents/reindex", response_model=ReindexDocumentsResponse)
async def reindex_documents(
    request: ReindexDocumentsRequest,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    runner: Annotated[ReindexRunner, Depends(get_reindex_runner)],
    workspace_repository: Annotated[
        WorkspaceRepository,
        Depends(get_workspace_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> ReindexDocumentsResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
    await require_active_workspace(
        workspace_id=normalized_workspace_id,
        repository=workspace_repository,
    )
    try:
        stats = await runner(
            workspace_id=normalized_workspace_id,
            source_uri=request.source_uri,
            batch_size=request.batch_size,
            limit=request.limit,
            dry_run=request.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return ReindexDocumentsResponse.from_stats(stats)


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document_detail(
    document_id: uuid.UUID,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> DocumentDetailResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
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
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    workspace_repository: Annotated[
        WorkspaceRepository,
        Depends(get_workspace_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> DeleteDocumentResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
    await require_active_workspace(
        workspace_id=normalized_workspace_id,
        repository=workspace_repository,
    )
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
