from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EvalCaseType = Literal["rag", "refusal", "security"]


class EvalCase(BaseModel):
    id: str
    question: str
    case_type: EvalCaseType
    expected_sources: list[str] = Field(default_factory=list)
    expected_keywords: list[str] = Field(default_factory=list)
    must_cite: bool = False
    should_refuse: bool = False
    attack_type: str | None = None
    should_not_follow_retrieved_instruction: bool = False

    @field_validator("id", "question")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("expected_sources", "expected_keywords")
    @classmethod
    def normalize_string_list(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]

    @field_validator("attack_type")
    @classmethod
    def normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_case_contract(self) -> "EvalCase":
        if self.case_type == "rag":
            if not self.expected_sources:
                raise ValueError("rag eval cases require expected_sources")
            if not self.expected_keywords:
                raise ValueError("rag eval cases require expected_keywords")
            if self.should_refuse:
                raise ValueError("rag eval cases must not set should_refuse")

        if self.case_type == "refusal" and not self.should_refuse:
            raise ValueError("refusal eval cases require should_refuse=true")

        if self.case_type == "security":
            if self.attack_type is None:
                raise ValueError("security eval cases require attack_type")
            if (
                not self.should_refuse
                and not self.should_not_follow_retrieved_instruction
            ):
                raise ValueError("security eval cases require a security expectation")

        return self


class EvalDataset(BaseModel):
    name: str
    case_type: EvalCaseType
    path: Path
    cases: list[EvalCase]


class EvalSuite(BaseModel):
    datasets: list[EvalDataset]

    @property
    def total_cases(self) -> int:
        return sum(len(dataset.cases) for dataset in self.datasets)
