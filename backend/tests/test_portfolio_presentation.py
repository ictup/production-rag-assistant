from pathlib import Path

PORTFOLIO_DOC_PATH = Path("docs/PORTFOLIO_PRESENTATION.md")
README_PATH = Path("README.md")


def test_portfolio_presentation_doc_covers_public_repo_setup() -> None:
    guide = PORTFOLIO_DOC_PATH.read_text(encoding="utf-8")

    required_sections = [
        "# Portfolio Presentation Guide",
        "## Recommended Name",
        "## GitHub About",
        "## Portfolio Positioning",
        "## What To Show First",
        "## Suggested Demo Assets",
        "## Resume Bullet",
        "## Interview Walkthrough",
        "## Maintenance Rules",
    ]
    missing_sections = [
        section
        for section in required_sections
        if section not in guide
    ]

    assert missing_sections == []


def test_portfolio_presentation_doc_has_actionable_about_fields() -> None:
    guide = PORTFOLIO_DOC_PATH.read_text(encoding="utf-8")

    required_snippets = [
        "Production RAG Assistant",
        "production-rag-assistant",
        "Production-ready RAG backend with FastAPI, pgvector",
        "https://github.com/ictup/Production_RAG_Assistant/releases/tag/v0.1.0",
        "retrieval-augmented-generation",
        "production-ready",
        "ai-engineering",
    ]
    missing_snippets = [
        snippet
        for snippet in required_snippets
        if snippet not in guide
    ]

    assert missing_snippets == []


def test_portfolio_presentation_doc_is_linked_from_readme() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    assert "docs/PORTFOLIO_PRESENTATION.md" in readme
