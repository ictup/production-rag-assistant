import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.rag.citations import Source, build_sources, validate_citations
from backend.app.rag.embeddings import EmbeddingClient, build_embedding_client
from backend.app.rag.fusion import reciprocal_rank_fusion
from backend.app.rag.generation import Generator, build_generator
from backend.app.rag.prompts import build_rag_prompt
from backend.app.rag.refusal import (
    REFUSAL_ANSWER,
    RefusalInfo,
    should_refuse,
    should_refuse_question,
)
from backend.app.rag.reranking import Reranker, build_reranker
from backend.app.rag.sparse_retrieval import SparseRetriever
from backend.app.rag.vector_retrieval import VectorRetriever


class ChatPipelineRequest(BaseModel):
    question: str
    workspace_id: str = "public"
    vector_top_k: int | None = Field(default=None, gt=0)
    sparse_top_k: int | None = Field(default=None, gt=0)
    fused_top_k: int | None = Field(default=None, gt=0)
    rerank_top_n: int | None = Field(default=None, gt=0)
    rerank: bool = True

    @field_validator("question", "workspace_id")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class RetrievalInfo(BaseModel):
    mode: str
    vector_top_k: int
    sparse_top_k: int
    fused_count: int
    used_count: int
    top_score: float | None


class UsageInfo(BaseModel):
    model: str
    embedding_model: str
    latency_ms: int
    generator_provider: str = "unknown"
    embedding_provider: str = "unknown"
    embedding_latency_ms: int = 0
    generation_latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class ChatPipelineResponse(BaseModel):
    answer: str
    sources: list[Source]
    retrieval: RetrievalInfo
    usage: UsageInfo
    citation_valid: bool | None
    refusal: RefusalInfo | None = None


@dataclass(frozen=True)
class ChatPipelineStreamEvent:
    event_type: str
    delta: str = ""
    response: ChatPipelineResponse | None = None


class RagPipeline:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings | None = None,
        embedding_client: EmbeddingClient | None = None,
        reranker: Reranker | None = None,
        generator: Generator | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.embedding_client = embedding_client or build_embedding_client(
            self.settings
        )
        self.reranker = reranker or build_reranker(self.settings)
        self.generator = generator or build_generator(self.settings)

    async def answer_question(
        self,
        request: ChatPipelineRequest,
    ) -> ChatPipelineResponse:
        started_at = time.perf_counter()
        vector_top_k = request.vector_top_k or self.settings.vector_top_k
        sparse_top_k = request.sparse_top_k or self.settings.sparse_top_k
        fused_top_k = request.fused_top_k or self.settings.fused_top_k
        rerank_top_n = request.rerank_top_n or self.settings.rerank_top_n

        question_refusal = should_refuse_question(request.question)
        if question_refusal is not None:
            return build_refusal_response(
                refusal=question_refusal,
                mode="question_guard",
                vector_top_k=vector_top_k,
                sparse_top_k=sparse_top_k,
                fused_count=0,
                top_score=None,
                model=self.generator.model_name,
                generator_provider=self.generator.provider_name,
                embedding_model=self.embedding_client.model_name,
                embedding_provider=self.embedding_client.provider_name,
                started_at=started_at,
            )

        embedding_started_at = time.perf_counter()
        query_embedding = await self.embedding_client.embed_query(request.question)
        embedding_latency_ms = max(
            0,
            int((time.perf_counter() - embedding_started_at) * 1000),
        )
        vector_results = await VectorRetriever(self.session).retrieve(
            query_embedding=query_embedding,
            top_k=vector_top_k,
            workspace_id=request.workspace_id,
        )
        sparse_results = await SparseRetriever(self.session).retrieve(
            query=request.question,
            top_k=sparse_top_k,
            workspace_id=request.workspace_id,
        )
        fused_results = reciprocal_rank_fusion(
            [vector_results, sparse_results],
            k=self.settings.rrf_k,
            top_n=fused_top_k,
        )

        refusal = should_refuse(
            fused_results,
            threshold=self.settings.refusal_score_threshold,
        )
        if refusal is not None:
            return build_refusal_response(
                refusal=refusal,
                mode="hybrid_rrf",
                vector_top_k=vector_top_k,
                sparse_top_k=sparse_top_k,
                fused_count=len(fused_results),
                top_score=refusal.top_score,
                model=self.generator.model_name,
                generator_provider=self.generator.provider_name,
                embedding_model=self.embedding_client.model_name,
                embedding_provider=self.embedding_client.provider_name,
                started_at=started_at,
                embedding_latency_ms=embedding_latency_ms,
            )

        used_chunks = (
            await self.reranker.rerank(
                query=request.question,
                chunks=fused_results,
                top_n=rerank_top_n,
            )
            if request.rerank
            else fused_results[:rerank_top_n]
        )
        prompt = build_rag_prompt(request.question, used_chunks)
        generation_started_at = time.perf_counter()
        generated = await self.generator.generate(prompt)
        generation_latency_ms = max(
            0,
            int((time.perf_counter() - generation_started_at) * 1000),
        )
        sources = build_sources(used_chunks)
        citation_valid = validate_citations(generated.answer, len(sources))

        return ChatPipelineResponse(
            answer=generated.answer,
            sources=sources,
            retrieval=build_retrieval_info(
                mode="hybrid_rrf_rerank" if request.rerank else "hybrid_rrf",
                vector_top_k=vector_top_k,
                sparse_top_k=sparse_top_k,
                fused_count=len(fused_results),
                used_count=len(used_chunks),
                top_score=fused_results[0].score if fused_results else None,
            ),
            usage=build_usage_info(
                model=generated.model,
                generator_provider=self.generator.provider_name,
                embedding_model=self.embedding_client.model_name,
                embedding_provider=self.embedding_client.provider_name,
                started_at=started_at,
                input_tokens=generated.input_tokens,
                output_tokens=generated.output_tokens,
                embedding_latency_ms=embedding_latency_ms,
                generation_latency_ms=generation_latency_ms,
            ),
            citation_valid=citation_valid,
            refusal=None,
        )

    async def stream_answer(
        self,
        request: ChatPipelineRequest,
    ) -> AsyncIterator[ChatPipelineStreamEvent]:
        started_at = time.perf_counter()
        vector_top_k = request.vector_top_k or self.settings.vector_top_k
        sparse_top_k = request.sparse_top_k or self.settings.sparse_top_k
        fused_top_k = request.fused_top_k or self.settings.fused_top_k
        rerank_top_n = request.rerank_top_n or self.settings.rerank_top_n

        question_refusal = should_refuse_question(request.question)
        if question_refusal is not None:
            response = build_refusal_response(
                refusal=question_refusal,
                mode="question_guard",
                vector_top_k=vector_top_k,
                sparse_top_k=sparse_top_k,
                fused_count=0,
                top_score=None,
                model=self.generator.model_name,
                generator_provider=self.generator.provider_name,
                embedding_model=self.embedding_client.model_name,
                embedding_provider=self.embedding_client.provider_name,
                started_at=started_at,
            )
            yield ChatPipelineStreamEvent(event_type="delta", delta=response.answer)
            yield ChatPipelineStreamEvent(event_type="completed", response=response)
            return

        embedding_started_at = time.perf_counter()
        query_embedding = await self.embedding_client.embed_query(request.question)
        embedding_latency_ms = max(
            0,
            int((time.perf_counter() - embedding_started_at) * 1000),
        )
        vector_results = await VectorRetriever(self.session).retrieve(
            query_embedding=query_embedding,
            top_k=vector_top_k,
            workspace_id=request.workspace_id,
        )
        sparse_results = await SparseRetriever(self.session).retrieve(
            query=request.question,
            top_k=sparse_top_k,
            workspace_id=request.workspace_id,
        )
        fused_results = reciprocal_rank_fusion(
            [vector_results, sparse_results],
            k=self.settings.rrf_k,
            top_n=fused_top_k,
        )

        refusal = should_refuse(
            fused_results,
            threshold=self.settings.refusal_score_threshold,
        )
        if refusal is not None:
            response = build_refusal_response(
                refusal=refusal,
                mode="hybrid_rrf",
                vector_top_k=vector_top_k,
                sparse_top_k=sparse_top_k,
                fused_count=len(fused_results),
                top_score=refusal.top_score,
                model=self.generator.model_name,
                generator_provider=self.generator.provider_name,
                embedding_model=self.embedding_client.model_name,
                embedding_provider=self.embedding_client.provider_name,
                started_at=started_at,
                embedding_latency_ms=embedding_latency_ms,
            )
            yield ChatPipelineStreamEvent(event_type="delta", delta=response.answer)
            yield ChatPipelineStreamEvent(event_type="completed", response=response)
            return

        used_chunks = (
            await self.reranker.rerank(
                query=request.question,
                chunks=fused_results,
                top_n=rerank_top_n,
            )
            if request.rerank
            else fused_results[:rerank_top_n]
        )
        prompt = build_rag_prompt(request.question, used_chunks)
        generation_started_at = time.perf_counter()
        answer_parts: list[str] = []
        generated_model = self.generator.model_name
        input_tokens = 0
        output_tokens = 0

        async for generated_event in self.generator.stream(prompt):
            if generated_event.event_type == "delta" and generated_event.delta:
                answer_parts.append(generated_event.delta)
                yield ChatPipelineStreamEvent(
                    event_type="delta",
                    delta=generated_event.delta,
                )
                continue

            if generated_event.event_type == "completed":
                if generated_event.answer is not None:
                    answer_parts = [generated_event.answer]
                if generated_event.model is not None:
                    generated_model = generated_event.model
                input_tokens = generated_event.input_tokens or 0
                output_tokens = generated_event.output_tokens or 0

        generation_latency_ms = max(
            0,
            int((time.perf_counter() - generation_started_at) * 1000),
        )
        answer = "".join(answer_parts).strip()
        sources = build_sources(used_chunks)
        citation_valid = validate_citations(answer, len(sources))
        response = ChatPipelineResponse(
            answer=answer,
            sources=sources,
            retrieval=build_retrieval_info(
                mode="hybrid_rrf_rerank" if request.rerank else "hybrid_rrf",
                vector_top_k=vector_top_k,
                sparse_top_k=sparse_top_k,
                fused_count=len(fused_results),
                used_count=len(used_chunks),
                top_score=fused_results[0].score if fused_results else None,
            ),
            usage=build_usage_info(
                model=generated_model,
                generator_provider=self.generator.provider_name,
                embedding_model=self.embedding_client.model_name,
                embedding_provider=self.embedding_client.provider_name,
                started_at=started_at,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                embedding_latency_ms=embedding_latency_ms,
                generation_latency_ms=generation_latency_ms,
            ),
            citation_valid=citation_valid,
            refusal=None,
        )
        yield ChatPipelineStreamEvent(event_type="completed", response=response)


def build_retrieval_info(
    *,
    mode: str,
    vector_top_k: int,
    sparse_top_k: int,
    fused_count: int,
    used_count: int,
    top_score: float | None,
) -> RetrievalInfo:
    return RetrievalInfo(
        mode=mode,
        vector_top_k=vector_top_k,
        sparse_top_k=sparse_top_k,
        fused_count=fused_count,
        used_count=used_count,
        top_score=top_score,
    )


def build_refusal_response(
    *,
    refusal: RefusalInfo,
    mode: str,
    vector_top_k: int,
    sparse_top_k: int,
    fused_count: int,
    top_score: float | None,
    model: str,
    embedding_model: str,
    generator_provider: str = "unknown",
    embedding_provider: str = "unknown",
    started_at: float,
    embedding_latency_ms: int = 0,
) -> ChatPipelineResponse:
    return ChatPipelineResponse(
        answer=REFUSAL_ANSWER,
        sources=[],
        retrieval=build_retrieval_info(
            mode=mode,
            vector_top_k=vector_top_k,
            sparse_top_k=sparse_top_k,
            fused_count=fused_count,
            used_count=0,
            top_score=top_score,
        ),
        usage=build_usage_info(
            model=model,
            generator_provider=generator_provider,
            embedding_model=embedding_model,
            embedding_provider=embedding_provider,
            started_at=started_at,
            embedding_latency_ms=embedding_latency_ms,
        ),
        citation_valid=None,
        refusal=refusal,
    )


def build_usage_info(
    *,
    model: str,
    embedding_model: str,
    started_at: float,
    generator_provider: str = "unknown",
    embedding_provider: str = "unknown",
    input_tokens: int = 0,
    output_tokens: int = 0,
    embedding_latency_ms: int = 0,
    generation_latency_ms: int = 0,
) -> UsageInfo:
    return UsageInfo(
        model=model,
        embedding_model=embedding_model,
        generator_provider=generator_provider,
        embedding_provider=embedding_provider,
        latency_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
        embedding_latency_ms=embedding_latency_ms,
        generation_latency_ms=generation_latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
