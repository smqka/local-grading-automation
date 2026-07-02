"""Data structures used by the grading service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ScorePrecision = Literal["integer", "0.5", "0.1"]


@dataclass(frozen=True)
class ImagePayload:
    data_uri: str
    mime_type: str
    size_bytes: int


@dataclass(frozen=True)
class GradeRequest:
    image: ImagePayload
    max_score: float
    standard_answer: str
    grading_rules: str
    deduction_rules: str
    allow_equivalent_answers: bool
    score_by_steps: bool
    score_precision: ScorePrecision
    question_id: str | None
    rule_version: str | None


@dataclass(frozen=True)
class ReferenceParseRequest:
    image: ImagePayload
    question_id: str | None
    rule_version: str | None


@dataclass(frozen=True)
class ReferenceParseResult:
    standard_answer: str
    grading_rules: str
    deduction_rules: str
    max_score: float | None
    confidence: float
    needs_review: bool
    review_reason: str
    uncertain_factors: list[str]
    raw: dict[str, Any]


@dataclass(frozen=True)
class ModelGradeResult:
    suggested_score: float | None
    max_score: float
    confidence: float
    needs_review: bool
    review_reason: str
    deduction_points: list[str]
    student_answer_summary: str
    uncertain_factors: list[str]
    raw: dict[str, Any]


@dataclass(frozen=True)
class GradeResponse:
    suggested_score: float | None
    max_score: float
    confidence: float
    needs_review: bool
    review_reason: str
    deduction_points: list[str]
    student_answer_summary: str
    uncertain_factors: list[str]
    model: str
    prompt_version: str
    rule_version: str | None
    question_id: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "suggested_score": self.suggested_score,
            "max_score": self.max_score,
            "confidence": self.confidence,
            "needs_review": self.needs_review,
            "review_reason": self.review_reason,
            "deduction_points": self.deduction_points,
            "student_answer_summary": self.student_answer_summary,
            "uncertain_factors": self.uncertain_factors,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "rule_version": self.rule_version,
            "question_id": self.question_id,
        }


@dataclass(frozen=True)
class ReferenceParseResponse:
    standard_answer: str
    grading_rules: str
    deduction_rules: str
    max_score: float | None
    confidence: float
    needs_review: bool
    review_reason: str
    uncertain_factors: list[str]
    model: str
    prompt_version: str
    rule_version: str | None
    question_id: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "standard_answer": self.standard_answer,
            "grading_rules": self.grading_rules,
            "deduction_rules": self.deduction_rules,
            "max_score": self.max_score,
            "confidence": self.confidence,
            "needs_review": self.needs_review,
            "review_reason": self.review_reason,
            "uncertain_factors": self.uncertain_factors,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "rule_version": self.rule_version,
            "question_id": self.question_id,
        }
