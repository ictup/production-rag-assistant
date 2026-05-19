from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.app.db.repositories import (
    DocumentChunkSummary,
    DocumentDetailResult,
    DocumentListResult,
    DocumentSummary,
)


class DocumentItem(BaseModel):
    id: str
    workspace_id: str
    source_type: str
    source_uri: str
    title: str
    author: str | None
    visibility: str
    metadata: dict[str, Any]
    chunk_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_summary(cls, document: DocumentSummary) -> "DocumentItem":
        return cls(
            id=str(document.id),
            workspace_id=document.workspace_id,
            source_type=document.source_type,
            source_uri=document.source_uri,
            title=document.title,
            author=document.author,
            visibility=document.visibility,
            metadata=dict(document.metadata),
            chunk_count=document.chunk_count,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )


class DocumentsResponse(BaseModel):
    workspace_id: str
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)
    documents: list[DocumentItem]

    @classmethod
    def from_result(
        cls,
        *,
        workspace_id: str,
        limit: int,
        offset: int,
        result: DocumentListResult,
    ) -> "DocumentsResponse":
        documents = [
            DocumentItem.from_summary(document) for document in result.documents
        ]
        return cls(
            workspace_id=workspace_id,
            total=result.total,
            count=len(documents),
            limit=limit,
            offset=offset,
            documents=documents,
        )


class DocumentChunkItem(BaseModel):
    id: str
    document_id: str
    workspace_id: str
    chunk_index: int = Field(ge=0)
    text: str
    token_count: int = Field(ge=0)
    section_title: str | None
    page_number: int | None
    source_uri: str
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_summary(cls, chunk: DocumentChunkSummary) -> "DocumentChunkItem":
        return cls(
            id=str(chunk.id),
            document_id=str(chunk.document_id),
            workspace_id=chunk.workspace_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            token_count=chunk.token_count,
            section_title=chunk.section_title,
            page_number=chunk.page_number,
            source_uri=chunk.source_uri,
            metadata=dict(chunk.metadata),
            created_at=chunk.created_at,
        )


class DocumentDetailResponse(BaseModel):
    workspace_id: str
    document: DocumentItem
    chunks: list[DocumentChunkItem]

    @classmethod
    def from_result(
        cls,
        *,
        workspace_id: str,
        result: DocumentDetailResult,
    ) -> "DocumentDetailResponse":
        return cls(
            workspace_id=workspace_id,
            document=DocumentItem.from_summary(result.document),
            chunks=[DocumentChunkItem.from_summary(chunk) for chunk in result.chunks],
        )


class DeleteDocumentResponse(BaseModel):
    workspace_id: str
    document_id: str
    deleted: bool
