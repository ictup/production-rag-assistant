import pytest

from backend.app.core.config import Settings
from backend.app.rag.pipeline_smoke import build_pipeline_smoke_settings


def make_settings() -> Settings:
    return Settings(
        embedding_provider="fake",
        embedding_model="test-fake-embedding",
        generator_provider="fake",
        llm_model="fake-llm",
        openai_api_key="test-key",
        openai_max_output_tokens=512,
    )


def test_build_pipeline_smoke_settings_applies_runtime_overrides() -> None:
    settings = build_pipeline_smoke_settings(
        make_settings(),
        embedding_provider="openai",
        generator_provider="openai",
        llm_model="gpt-test",
        openai_max_output_tokens=123,
    )

    assert settings.embedding_provider == "openai"
    assert settings.generator_provider == "openai"
    assert settings.llm_model == "gpt-test"
    assert settings.openai_max_output_tokens == 123


def test_build_pipeline_smoke_settings_keeps_base_settings_without_overrides() -> None:
    base_settings = make_settings()

    settings = build_pipeline_smoke_settings(base_settings)

    assert settings is base_settings


def test_build_pipeline_smoke_settings_rejects_invalid_output_limit() -> None:
    with pytest.raises(ValueError, match="openai_max_output_tokens"):
        build_pipeline_smoke_settings(
            make_settings(),
            openai_max_output_tokens=0,
        )
