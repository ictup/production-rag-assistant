import math

import httpx
import pytest

from backend.app.core.config import Settings
from backend.app.rag.embeddings import (
    EmbeddingClient,
    EmbeddingDimensionError,
    FakeEmbeddingClient,
    OpenAIEmbeddingClient,
    OpenAIEmbeddingError,
    build_embedding_client,
    normalize_embedding_inputs,
    parse_openai_embeddings_response,
    validate_embedding_batch,
    validate_embedding_dimension,
)


@pytest.mark.asyncio
async def test_fake_embedding_client_returns_deterministic_vectors() -> None:
    client = FakeEmbeddingClient(dimension=8)

    first = await client.embed_query("FlashAttention reduces HBM traffic")
    second = await client.embed_query("FlashAttention reduces HBM traffic")

    assert first == second
    assert len(first) == 8
    assert math.isclose(sum(value * value for value in first), 1.0)


@pytest.mark.asyncio
async def test_fake_embedding_client_preserves_input_order() -> None:
    client = FakeEmbeddingClient(dimension=6)

    embeddings = await client.embed_texts(["KV cache", "PagedAttention", "KV cache"])

    assert len(embeddings) == 3
    assert embeddings[0] == embeddings[2]
    assert embeddings[0] != embeddings[1]


@pytest.mark.asyncio
async def test_fake_embedding_client_rejects_blank_text() -> None:
    client = FakeEmbeddingClient(dimension=4)

    with pytest.raises(ValueError, match="must not be blank"):
        await client.embed_query("   ")


def test_normalize_embedding_inputs_collapses_whitespace() -> None:
    assert normalize_embedding_inputs(["  KV\ncache  "]) == ["KV cache"]


def test_normalize_embedding_inputs_rejects_blank_text() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        normalize_embedding_inputs(["FlashAttention", "   "])


@pytest.mark.asyncio
async def test_openai_embedding_client_sends_expected_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.url == "https://api.openai.test/v1/embeddings"
        payload = json_from_request(request)
        assert payload == {
            "model": "text-embedding-3-small",
            "input": ["FlashAttention", "PagedAttention"],
            "encoding_format": "float",
            "dimensions": 3,
        }
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.4, 0.5, 0.6]},
                    {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedding_client = OpenAIEmbeddingClient(
            api_key="test-key",
            model_name="text-embedding-3-small",
            dimension=3,
            base_url="https://api.openai.test/v1/",
            http_client=client,
        )

        embeddings = await embedding_client.embed_texts(
            ["FlashAttention", "PagedAttention"]
        )

    assert embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_openai_embedding_client_rejects_http_errors() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid api key")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedding_client = OpenAIEmbeddingClient(
            api_key="test-key",
            dimension=3,
            base_url="https://api.openai.test/v1",
            http_client=client,
        )

        with pytest.raises(OpenAIEmbeddingError, match="status 401"):
            await embedding_client.embed_query("FlashAttention")


def test_openai_embedding_client_rejects_blank_api_key() -> None:
    with pytest.raises(ValueError, match="api_key"):
        OpenAIEmbeddingClient(api_key=" ")


def test_parse_openai_embeddings_response_rejects_missing_indexes() -> None:
    with pytest.raises(OpenAIEmbeddingError, match="indexes"):
        parse_openai_embeddings_response(
            {"data": [{"index": 1, "embedding": [0.1]}]},
            expected_count=1,
        )


def test_parse_openai_embeddings_response_rejects_missing_data() -> None:
    with pytest.raises(OpenAIEmbeddingError, match="data list"):
        parse_openai_embeddings_response({}, expected_count=1)


def test_validate_embedding_dimension_rejects_wrong_size() -> None:
    with pytest.raises(EmbeddingDimensionError, match="does not match"):
        validate_embedding_dimension([0.1, 0.2], expected_dimension=3)


def test_validate_embedding_dimension_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite numeric"):
        validate_embedding_dimension([0.1, float("nan")], expected_dimension=2)


def test_validate_embedding_batch_reports_failing_index() -> None:
    with pytest.raises(EmbeddingDimensionError, match=r"embedding\[1\]"):
        validate_embedding_batch([[0.1, 0.2], [0.3]], expected_dimension=2)


def test_build_embedding_client_uses_settings() -> None:
    client = build_embedding_client(
        Settings(
            embedding_provider="fake",
            embedding_model="test-fake",
            embedding_dimension=12,
        )
    )

    assert isinstance(client, EmbeddingClient)
    assert client.model_name == "test-fake"
    assert client.dimension == 12


def test_build_embedding_client_requires_openai_api_key() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_embedding_client(Settings(embedding_provider="openai"))


def test_build_embedding_client_rejects_blank_openai_api_key() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_embedding_client(
            Settings(embedding_provider="openai", openai_api_key=" ")
        )


def test_build_embedding_client_uses_openai_settings() -> None:
    client = build_embedding_client(
        Settings(
            embedding_provider="openai",
            embedding_dimension=1536,
            openai_api_key="test-key",
            openai_base_url="https://api.openai.test/v1",
            openai_embedding_model="text-embedding-3-small",
        )
    )

    assert isinstance(client, EmbeddingClient)
    assert client.model_name == "text-embedding-3-small"
    assert client.dimension == 1536


def json_from_request(request: httpx.Request) -> dict:
    import json

    return json.loads(request.content.decode("utf-8"))
