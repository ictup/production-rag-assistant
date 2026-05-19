import re
from typing import Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, Field

from backend.app.core.config import Settings, get_settings
from ingestion.chunking import count_tokens

OPENAI_RESPONSES_PATH = "/responses"
QUESTION_PATTERN = re.compile(r"\n\nQuestion:\n(?P<question>.+)\s*\Z", re.DOTALL)
FIRST_CONTEXT_TEXT_PATTERN = re.compile(
    r"\[1\]\n.*?Text:\n(?P<text>.*?)(?:\n\n\[\d+\]|\n\nQuestion:)",
    re.DOTALL,
)
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "does",
    "for",
    "how",
    "is",
    "it",
    "of",
    "the",
    "to",
    "what",
}
DEFAULT_ANSWER_SENTENCE_COUNT = 3
OPENAI_RAG_INSTRUCTIONS = (
    "You are a production RAG answer generator. Answer using only the provided "
    "context. Preserve citation markers like [1] and [2]. If the context is "
    "insufficient, say that you do not know based on the provided documents."
)


class OpenAIGenerationError(RuntimeError):
    pass


class GeneratedAnswer(BaseModel):
    answer: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


@runtime_checkable
class Generator(Protocol):
    provider_name: str
    model_name: str

    async def generate(self, prompt: str) -> GeneratedAnswer:
        pass


class FakeGenerator:
    provider_name = "fake"

    def __init__(self, *, model_name: str = "fake-llm") -> None:
        self.model_name = model_name

    async def generate(self, prompt: str) -> GeneratedAnswer:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt must not be blank")

        question = extract_question(prompt)
        context_text = extract_first_context_text(prompt)
        answer = build_fake_answer(question=question, context_text=context_text)

        return GeneratedAnswer(
            answer=answer,
            model=self.model_name,
            input_tokens=count_tokens(prompt),
            output_tokens=count_tokens(answer),
        )


class OpenAIResponsesGenerator:
    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        max_output_tokens: int = 512,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise ValueError("api_key must not be blank")
        if not model_name.strip():
            raise ValueError("model_name must not be blank")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than zero")

        self.api_key = api_key
        self.model_name = model_name.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.http_client = http_client

    async def generate(self, prompt: str) -> GeneratedAnswer:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt must not be blank")

        payload = {
            "model": self.model_name,
            "instructions": OPENAI_RAG_INSTRUCTIONS,
            "input": prompt,
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }
        response_data = await self._create_response(payload)
        answer = extract_openai_response_text(response_data)
        usage = extract_openai_response_usage(response_data)

        return GeneratedAnswer(
            answer=answer,
            model=self.model_name,
            input_tokens=usage.get("input_tokens", count_tokens(prompt)),
            output_tokens=usage.get("output_tokens", count_tokens(answer)),
        )

    async def _create_response(self, payload: dict) -> dict:
        if self.http_client is not None:
            return await self._post_response(self.http_client, payload)

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await self._post_response(client, payload)

    async def _post_response(
        self,
        client: httpx.AsyncClient,
        payload: dict,
    ) -> dict:
        try:
            response = await client.post(
                f"{self.base_url}{OPENAI_RESPONSES_PATH}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenAIGenerationError(
                "OpenAI response request failed with "
                f"status {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenAIGenerationError(
                f"OpenAI response request failed: {exc}"
            ) from exc

        try:
            response_data = response.json()
        except ValueError as exc:
            raise OpenAIGenerationError(
                "OpenAI response was not valid JSON"
            ) from exc
        if not isinstance(response_data, dict):
            raise OpenAIGenerationError("OpenAI response must be an object")
        return response_data


def extract_openai_response_text(response_data: dict) -> str:
    output_text = response_data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output_items = response_data.get("output")
    if not isinstance(output_items, list):
        raise OpenAIGenerationError("OpenAI response missing output list")

    text_parts: list[str] = []
    for item in output_items:
        if not isinstance(item, dict):
            continue
        content_items = item.get("content")
        if not isinstance(content_items, list):
            continue
        for content_item in content_items:
            if not isinstance(content_item, dict):
                continue
            if content_item.get("type") != "output_text":
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())

    answer = "\n".join(text_parts).strip()
    if not answer:
        raise OpenAIGenerationError("OpenAI response did not include output text")
    return answer


def extract_openai_response_usage(response_data: dict) -> dict[str, int]:
    usage = response_data.get("usage")
    if not isinstance(usage, dict):
        return {}

    parsed_usage: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and value >= 0:
            parsed_usage[key] = value
    return parsed_usage


def extract_question(prompt: str) -> str:
    match = QUESTION_PATTERN.search(prompt)
    if match is None:
        raise ValueError("prompt must contain a Question section")

    question = match.group("question").strip()
    if not question:
        raise ValueError("question must not be blank")
    return question


def extract_first_context_text(prompt: str) -> str:
    match = FIRST_CONTEXT_TEXT_PATTERN.search(prompt)
    if match is None:
        raise ValueError("prompt must contain a [1] context block with Text")

    text = match.group("text").strip()
    if not text:
        raise ValueError("first context block text must not be blank")
    return text


def first_sentence(text: str) -> str:
    sentences = split_sentences(text)
    if sentences:
        return sentences[0]
    return ""


def split_sentences(text: str) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []

    sentences = re.findall(r".+?(?:[.!?])(?:\s|$)", normalized)
    consumed_length = sum(len(sentence) for sentence in sentences)
    remainder = normalized[consumed_length:].strip()
    if remainder:
        sentences.append(remainder)

    return [sentence.strip() for sentence in sentences if sentence.strip()]


def extract_question_terms(question: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(question.casefold())
        if len(token) > 1 and token not in STOPWORDS
    }


def score_sentence(sentence: str, question_terms: set[str]) -> int:
    if not question_terms:
        return 0

    sentence_terms = set(TOKEN_PATTERN.findall(sentence.casefold()))
    return len(sentence_terms & question_terms)


def select_relevant_sentences(
    *,
    question: str,
    context_text: str,
    max_sentences: int = DEFAULT_ANSWER_SENTENCE_COUNT,
) -> list[str]:
    if max_sentences <= 0:
        raise ValueError("max_sentences must be greater than zero")

    sentences = split_sentences(context_text)
    if not sentences:
        return []

    question_terms = extract_question_terms(question)
    scored_indexes = [
        (score_sentence(sentence, question_terms), index)
        for index, sentence in enumerate(sentences)
    ]
    _, best_index = max(scored_indexes, key=lambda item: (item[0], -item[1]))

    start_index = max(0, best_index - 1)
    end_index = min(len(sentences), start_index + max_sentences)
    if end_index - start_index < max_sentences:
        start_index = max(0, end_index - max_sentences)

    return sentences[start_index:end_index]


def build_relevant_context_snippet(*, question: str, context_text: str) -> str:
    sentences = select_relevant_sentences(
        question=question,
        context_text=context_text,
    )
    if not sentences:
        raise ValueError("context_text must not be blank")
    return " ".join(sentences)


def build_fake_answer(*, question: str, context_text: str) -> str:
    snippet = build_relevant_context_snippet(
        question=question,
        context_text=context_text,
    )
    return (
        "Based on the provided documents, the relevant answer is: "
        f"{snippet} [1]"
    )


def build_generator(settings: Settings | None = None) -> Generator:
    settings = settings or get_settings()

    if settings.generator_provider == "fake":
        return FakeGenerator(model_name=settings.llm_model)

    if settings.generator_provider == "openai":
        if settings.openai_api_key is None or not settings.openai_api_key.strip():
            raise ValueError("OPENAI_API_KEY is required for OpenAI generation")
        return OpenAIResponsesGenerator(
            api_key=settings.openai_api_key,
            model_name=settings.llm_model,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.openai_timeout_seconds,
            max_output_tokens=settings.openai_max_output_tokens,
        )

    raise ValueError(f"unsupported generator provider: {settings.generator_provider}")
