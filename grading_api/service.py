"""Application service layer for the grading API."""

from __future__ import annotations

from .config import Settings
from .models import GradeResponse, ReferenceParseResponse
from .openai_client import GradingModelClient, OpenAIResponsesClient
from .validation import parse_grade_request, parse_reference_parse_request, validate_model_result, validate_reference_parse_result


class GradingService:
    def __init__(self, settings: Settings, model_client: GradingModelClient | None = None) -> None:
        self._settings = settings
        self._model_client = model_client

    def grade_payload(self, payload: dict) -> GradeResponse:
        request = parse_grade_request(payload, max_image_bytes=self._settings.max_image_bytes)
        model_client = self._get_model_client()
        model_raw = model_client.grade(request)
        result = validate_model_result(model_raw, request)
        return GradeResponse(
            suggested_score=result.suggested_score,
            max_score=result.max_score,
            confidence=result.confidence,
            needs_review=result.needs_review,
            review_reason=result.review_reason,
            deduction_points=result.deduction_points,
            student_answer_summary=result.student_answer_summary,
            uncertain_factors=result.uncertain_factors,
            model=model_client.model_name,
            prompt_version=self._settings.prompt_version,
            rule_version=request.rule_version,
            question_id=request.question_id,
        )

    def parse_reference_payload(self, payload: dict) -> ReferenceParseResponse:
        request = parse_reference_parse_request(payload, max_image_bytes=self._settings.max_image_bytes)
        model_client = self._get_model_client()
        model_raw = model_client.parse_reference(request)
        result = validate_reference_parse_result(model_raw)
        return ReferenceParseResponse(
            standard_answer=result.standard_answer,
            grading_rules=result.grading_rules,
            deduction_rules=result.deduction_rules,
            max_score=result.max_score,
            confidence=result.confidence,
            needs_review=result.needs_review,
            review_reason=result.review_reason,
            uncertain_factors=result.uncertain_factors,
            model=model_client.model_name,
            prompt_version=self._settings.prompt_version,
            rule_version=request.rule_version,
            question_id=request.question_id,
        )

    def _get_model_client(self) -> GradingModelClient:
        if self._model_client is None:
            self._model_client = OpenAIResponsesClient(self._settings)
        return self._model_client
