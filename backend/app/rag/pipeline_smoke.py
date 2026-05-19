import argparse
import asyncio
from typing import Literal

from backend.app.core.config import Settings, get_settings
from backend.app.db.session import get_sessionmaker
from backend.app.rag.pipeline import ChatPipelineRequest, RagPipeline

ProviderName = Literal["fake", "openai"]


async def run_pipeline_smoke(
    *,
    question: str,
    workspace_id: str,
    settings: Settings | None = None,
) -> int:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        pipeline = RagPipeline(session=session, settings=settings)
        response = await pipeline.answer_question(
            ChatPipelineRequest(
                question=question,
                workspace_id=workspace_id,
                vector_top_k=5,
                sparse_top_k=5,
                fused_top_k=5,
                rerank_top_n=2,
            )
        )

    print(f"answer: {response.answer}")
    print(f"citation_valid: {response.citation_valid}")
    print(f"refusal: {response.refusal}")
    print(f"retrieval: {response.retrieval.model_dump()}")
    print(f"usage: {response.usage.model_dump()}")
    print("sources:")
    for source in response.sources:
        print(f"- [{source.source_id}] {source.source_uri} {source.section}")

    if response.refusal is not None:
        raise SystemExit("pipeline smoke failed: unexpected refusal")
    if not response.citation_valid:
        raise SystemExit("pipeline smoke failed: invalid citations")
    if not response.sources:
        raise SystemExit("pipeline smoke failed: no sources")

    print("pipeline smoke passed")
    return 0


def build_pipeline_smoke_settings(
    settings: Settings | None = None,
    *,
    embedding_provider: ProviderName | None = None,
    generator_provider: ProviderName | None = None,
    llm_model: str | None = None,
    openai_max_output_tokens: int | None = None,
) -> Settings:
    settings = settings or get_settings()
    updates = {}
    if embedding_provider is not None:
        updates["embedding_provider"] = embedding_provider
    if generator_provider is not None:
        updates["generator_provider"] = generator_provider
    if llm_model is not None:
        updates["llm_model"] = llm_model
    if openai_max_output_tokens is not None:
        if openai_max_output_tokens <= 0:
            raise ValueError("openai_max_output_tokens must be greater than zero")
        updates["openai_max_output_tokens"] = openai_max_output_tokens

    if not updates:
        return settings
    return Settings(**{**settings.model_dump(), **updates})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a full RAG pipeline smoke test.")
    parser.add_argument(
        "--question",
        default="What problem does FlashAttention solve?",
    )
    parser.add_argument("--workspace-id", default="public")
    parser.add_argument(
        "--embedding-provider",
        choices=["fake", "openai"],
        default=None,
        help="Override EMBEDDING_PROVIDER for this smoke run.",
    )
    parser.add_argument(
        "--generator-provider",
        choices=["fake", "openai"],
        default=None,
        help="Override GENERATOR_PROVIDER for this smoke run.",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="Override LLM_MODEL for this smoke run.",
    )
    parser.add_argument(
        "--openai-max-output-tokens",
        type=int,
        default=None,
        help="Override OPENAI_MAX_OUTPUT_TOKENS for this smoke run.",
    )
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = build_pipeline_smoke_settings(
        embedding_provider=args.embedding_provider,
        generator_provider=args.generator_provider,
        llm_model=args.llm_model,
        openai_max_output_tokens=args.openai_max_output_tokens,
    )
    return await run_pipeline_smoke(
        question=args.question,
        workspace_id=args.workspace_id,
        settings=settings,
    )


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
