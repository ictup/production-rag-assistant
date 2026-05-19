import argparse
import asyncio

from backend.app.core.config import Settings, get_settings
from backend.app.rag.generation import Generator, build_generator
from backend.app.rag.prompts import build_rag_prompt
from backend.app.rag.retrieval_models import RetrievedChunk


def build_smoke_prompt() -> str:
    chunk = RetrievedChunk(
        chunk_id="generator-smoke-chunk",
        document_id="generator-smoke-document",
        text=(
            "FlashAttention is an IO-aware exact attention algorithm. "
            "It reduces memory traffic between high-bandwidth memory and "
            "on-chip SRAM by tiling attention computation."
        ),
        title="FlashAttention Notes",
        section_title="FlashAttention",
        source_uri="llm_systems/flashattention.md",
        score=1.0,
        rank=1,
        retrieval_mode="hybrid_rrf",
        metadata={},
    )
    return build_rag_prompt(
        "What problem does FlashAttention solve?",
        [chunk],
    )


async def run_generator_smoke(
    *,
    generator: Generator | None = None,
    settings: Settings | None = None,
) -> int:
    resolved_generator = generator or build_generator(settings)
    generated = await resolved_generator.generate(build_smoke_prompt())
    answer = generated.answer.strip()
    if not answer:
        raise SystemExit("generator smoke failed: blank answer")

    print(f"provider: {resolved_generator.provider_name}")
    print(f"model: {generated.model}")
    print(f"input_tokens: {generated.input_tokens}")
    print(f"output_tokens: {generated.output_tokens}")
    print(f"answer: {answer}")
    print("generator smoke passed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a generator provider smoke test.")
    parser.add_argument(
        "--provider",
        choices=["fake", "openai"],
        default=None,
        help="Override GENERATOR_PROVIDER for this smoke run.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override LLM_MODEL for this smoke run.",
    )
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    updates = {}
    if args.provider is not None:
        updates["generator_provider"] = args.provider
    if args.model is not None:
        updates["llm_model"] = args.model

    if updates:
        settings = settings.model_copy(update=updates)

    return await run_generator_smoke(settings=settings)


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
