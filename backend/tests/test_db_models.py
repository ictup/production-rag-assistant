from pgvector.sqlalchemy import Vector

from backend.app.db.models import (
    EMBEDDING_DIMENSION,
    Base,
    ChatLog,
    ChatSession,
    Document,
    DocumentChunk,
)


def test_base_metadata_contains_core_document_tables() -> None:
    assert set(Base.metadata.tables) == {
        "documents",
        "document_chunks",
        "chat_sessions",
        "chat_logs",
    }


def test_document_metadata_column_uses_safe_python_attribute_name() -> None:
    assert Document.metadata_.name == "metadata"
    assert Document.__table__.c["metadata"] is Document.metadata_.property.columns[0]


def test_document_chunk_embedding_column_uses_expected_dimension() -> None:
    embedding_type = DocumentChunk.__table__.c.embedding.type

    assert isinstance(embedding_type, Vector)
    assert embedding_type.dim == EMBEDDING_DIMENSION


def test_document_chunk_has_access_and_search_indexes() -> None:
    index_names = {index.name for index in DocumentChunk.__table__.indexes}

    assert "document_chunks_embedding_hnsw" in index_names
    assert "document_chunks_search_vector_idx" in index_names
    assert "document_chunks_metadata_idx" in index_names
    assert "document_chunks_workspace_idx" in index_names


def test_document_chunk_cascades_when_document_is_deleted() -> None:
    foreign_keys = list(DocumentChunk.__table__.c.document_id.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "CASCADE"


def test_chat_log_has_request_and_workspace_indexes() -> None:
    constraints = {constraint.name for constraint in ChatLog.__table__.constraints}
    index_names = {index.name for index in ChatLog.__table__.indexes}

    assert "chat_logs_request_id_key" in constraints
    assert "chat_logs_workspace_created_at_idx" in index_names


def test_chat_session_metadata_column_uses_safe_python_attribute_name() -> None:
    assert ChatSession.metadata_.name == "metadata"
    assert (
        ChatSession.__table__.c["metadata"]
        is ChatSession.metadata_.property.columns[0]
    )


def test_chat_session_has_workspace_updated_at_index() -> None:
    index_names = {index.name for index in ChatSession.__table__.indexes}

    assert "chat_sessions_workspace_updated_at_idx" in index_names


def test_chat_log_can_attach_to_session_without_requiring_it() -> None:
    assert ChatLog.__table__.c.session_id.nullable is True

    foreign_keys = list(ChatLog.__table__.c.session_id.foreign_keys)
    index_names = {index.name for index in ChatLog.__table__.indexes}

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "SET NULL"
    assert "chat_logs_session_created_at_idx" in index_names


def test_chat_log_json_columns_use_expected_names() -> None:
    assert ChatLog.__table__.c.sources.name == "sources"
    assert ChatLog.__table__.c.retrieval.name == "retrieval"
    assert ChatLog.__table__.c.usage.name == "usage"
