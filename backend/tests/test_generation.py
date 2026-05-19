import uuid

import httpx
import pytest

from backend.app.core.config import Settings
from backend.app.rag.citations import validate_citations
from backend.app.rag.generation import (
    FakeGenerator,
    GeneratedAnswer,
    Generator,
    OpenAIGenerationError,
    OpenAIResponsesGenerator,
    build_fake_answer,
    build_generator,
    build_relevant_context_snippet,
    extract_first_context_text,
    extract_openai_response_text,
    extract_question,
    extract_question_terms,
    first_sentence,
    score_sentence,
    select_relevant_sentences,
    split_sentences,
)
from backend.app.rag.generator_smoke import run_generator_smoke
from backend.app.rag.prompts import build_rag_prompt
from backend.app.rag.retrieval_models import RetrievedChunk


def make_chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=str(uuid.uuid4()),
        document_id=str(uuid.uuid4()),
        text=text,
        title="FlashAttention Notes",
        section_title="FlashAttention",
        source_uri="llm_systems/flashattention.md",
        score=1.0,
        rank=1,
        retrieval_mode="hybrid_rrf",
        metadata={},
    )


class RecordingGenerator:
    provider_name = "recording"
    model_name = "recording-model"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(self, prompt: str):
        self.prompts.append(prompt)
        return GeneratedAnswer(
            answer="FlashAttention reduces memory traffic. [1]",
            model=self.model_name,
            input_tokens=10,
            output_tokens=5,
        )


@pytest.mark.asyncio
async def test_fake_generator_returns_cited_answer_and_usage() -> None:
    prompt = build_rag_prompt(
        "What problem does FlashAttention solve?",
        [
            make_chunk(
                "FlashAttention reduces memory traffic between HBM and SRAM. "
                "It tiles exact attention."
            )
        ],
    )
    generator = FakeGenerator(model_name="test-fake")

    generated = await generator.generate(prompt)

    assert generated.model == "test-fake"
    assert "FlashAttention reduces memory traffic" in generated.answer
    assert generated.answer.endswith("[1]")
    assert generated.input_tokens > 0
    assert generated.output_tokens > 0
    assert validate_citations(generated.answer, num_sources=1) is True


@pytest.mark.asyncio
async def test_fake_generator_rejects_blank_prompt() -> None:
    generator = FakeGenerator()

    with pytest.raises(ValueError, match="prompt"):
        await generator.generate("  ")


@pytest.mark.asyncio
async def test_openai_responses_generator_sends_expected_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url == "https://api.openai.test/v1/responses"
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = request.read()
        assert b'"model":"gpt-test"' in payload
        assert b'"max_output_tokens":123' in payload
        assert b'"store":false' in payload
        assert b"FlashAttention" in payload
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "FlashAttention reduces memory traffic. [1]",
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 42,
                    "output_tokens": 7,
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as http_client:
        generator = OpenAIResponsesGenerator(
            api_key="test-key",
            model_name="gpt-test",
            base_url="https://api.openai.test/v1",
            max_output_tokens=123,
            http_client=http_client,
        )

        generated = await generator.generate(
            "Context: FlashAttention\n\nQuestion: Why?"
        )

    assert generated.answer == "FlashAttention reduces memory traffic. [1]"
    assert generated.model == "gpt-test"
    assert generated.input_tokens == 42
    assert generated.output_tokens == 7
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_openai_responses_generator_rejects_http_errors() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(429, text="rate limited")
        )
    ) as http_client:
        generator = OpenAIResponsesGenerator(
            api_key="test-key",
            model_name="gpt-test",
            http_client=http_client,
        )

        with pytest.raises(OpenAIGenerationError, match="status 429"):
            await generator.generate("Context: FlashAttention\n\nQuestion: Why?")


def test_extract_openai_response_text_prefers_output_text_property() -> None:
    assert (
        extract_openai_response_text({"output_text": " Direct answer. [1] "})
        == "Direct answer. [1]"
    )


def test_extract_openai_response_text_rejects_missing_text() -> None:
    with pytest.raises(OpenAIGenerationError, match="output"):
        extract_openai_response_text({"output": []})


def test_extract_question_reads_question_section() -> None:
    assert extract_question("Context:\n[1]\n\nQuestion:\nWhat is RAG?") == (
        "What is RAG?"
    )


def test_extract_first_context_text_reads_first_numbered_block() -> None:
    prompt = (
        "[1]\nTitle: A\nText:\nFirst context.\n\n"
        "[2]\nTitle: B\nText:\nSecond context.\n\n"
        "Question:\nWhat matters?"
    )

    assert extract_first_context_text(prompt) == "First context."


def test_first_sentence_prefers_sentence_boundary() -> None:
    assert first_sentence("First sentence. Second sentence.") == "First sentence."


def test_split_sentences_preserves_markdown_heading_context() -> None:
    assert split_sentences(
        "# FlashAttention\n\nFlashAttention is IO-aware. It reduces memory."
    ) == [
        "# FlashAttention FlashAttention is IO-aware.",
        "It reduces memory.",
    ]


def test_extract_question_terms_removes_stopwords() -> None:
    assert extract_question_terms(
        "How does PagedAttention improve KV cache memory management?"
    ) == {
        "pagedattention",
        "improve",
        "kv",
        "cache",
        "memory",
        "management",
    }


def test_score_sentence_counts_question_term_overlap() -> None:
    question_terms = {"pagedattention", "kv", "cache", "memory"}

    assert (
        score_sentence(
            "PagedAttention stores the KV cache in virtual memory pages.",
            question_terms,
        )
        == 4
    )


def test_select_relevant_sentences_includes_neighboring_evidence() -> None:
    sentences = select_relevant_sentences(
        question="How does PagedAttention improve KV cache memory management?",
        context_text=(
            "During autoregressive decoding, each sequence grows token by token. "
            "Without a paged layout, KV-cache memory can become fragmented. "
            "Paging improves utilization."
        ),
    )

    assert sentences == [
        "During autoregressive decoding, each sequence grows token by token.",
        "Without a paged layout, KV-cache memory can become fragmented.",
        "Paging improves utilization.",
    ]


def test_build_relevant_context_snippet_keeps_keywords_for_eval() -> None:
    snippet = build_relevant_context_snippet(
        question="What problem does FlashAttention solve?",
        context_text=(
            "# FlashAttention\n\n"
            "FlashAttention is an IO-aware exact attention algorithm. "
            "It reduces memory traffic by tiling attention computation."
        ),
    )

    assert "IO-aware" in snippet
    assert "memory" in snippet
    assert "attention" in snippet


def test_build_fake_answer_adds_relevant_context_and_first_citation() -> None:
    answer = build_fake_answer(
        question="What is FlashAttention?",
        context_text="FlashAttention is IO-aware. Extra detail.",
    )

    assert answer == (
        "Based on the provided documents, the relevant answer is: "
        "FlashAttention is IO-aware. Extra detail. [1]"
    )


def test_build_generator_uses_settings() -> None:
    generator = build_generator(
        Settings(
            generator_provider="fake",
            llm_model="test-fake-llm",
        )
    )

    assert isinstance(generator, Generator)
    assert generator.model_name == "test-fake-llm"


def test_build_generator_requires_openai_api_key() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_generator(
            Settings(
                generator_provider="openai",
                llm_model="gpt-test",
                openai_api_key=None,
            )
        )


def test_build_generator_uses_openai_settings() -> None:
    generator = build_generator(
        Settings(
            generator_provider="openai",
            llm_model="gpt-test",
            openai_api_key="test-key",
            openai_base_url="https://api.openai.test/v1",
            openai_timeout_seconds=3,
            openai_max_output_tokens=123,
        )
    )

    assert isinstance(generator, OpenAIResponsesGenerator)
    assert generator.model_name == "gpt-test"
    assert generator.max_output_tokens == 123


@pytest.mark.asyncio
async def test_generator_smoke_uses_generator(capsys) -> None:
    generator = RecordingGenerator()

    exit_code = await run_generator_smoke(generator=generator)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert generator.prompts
    assert "provider: recording" in output
    assert "model: recording-model" in output
    assert "generator smoke passed" in output
