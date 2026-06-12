"""OpenAI Responses API client for grading answer images."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from .config import Settings
from .errors import UpstreamError
from .models import GradeRequest


class GradingModelClient(Protocol):
    model_name: str

    def grade(self, request: GradeRequest) -> dict[str, Any]:
        ...


GRADING_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "suggested_score": {
            "type": "number",
            "description": "Suggested score for the answer. Must be between 0 and max_score.",
        },
        "max_score": {"type": "number"},
        "confidence": {
            "type": "number",
            "description": "A confidence value from 0 to 1.",
        },
        "needs_review": {
            "type": "boolean",
            "description": "True when the teacher should manually review before using this suggestion.",
        },
        "review_reason": {"type": "string"},
        "deduction_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Main reasons for score deductions.",
        },
        "student_answer_summary": {
            "type": "string",
            "description": "Brief summary of the visible student answer.",
        },
        "uncertain_factors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Image, handwriting, ambiguity, or rule issues that reduce certainty.",
        },
    },
    "required": [
        "suggested_score",
        "max_score",
        "confidence",
        "needs_review",
        "review_reason",
        "deduction_points",
        "student_answer_summary",
        "uncertain_factors",
    ],
    "additionalProperties": False,
}


SYSTEM_INSTRUCTIONS = """You are an AI grading assistant for math teachers.
You provide advisory scores only. The teacher is always the final grader.
Grade only from the cropped answer image and the teacher-provided rubric.
Do not infer student identity. Do not claim the score has been submitted.
If the image is unclear, the rubric is ambiguous, or the answer cannot be read, set needs_review to true and lower confidence.
Never assign a score below 0 or above the max score."""


class OpenAIResponsesClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise UpstreamError("OPENAI_API_KEY is not configured.")
        self._settings = settings
        self.model_name = settings.openai_model

    def grade(self, request: GradeRequest) -> dict[str, Any]:
        payload = self._build_payload(request)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = urllib.request.Request(
            f"{self._settings.openai_base_url}/responses",
            data=body,
            headers={
                "Authorization": f"Bearer {self._settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                http_request,
                timeout=self._settings.request_timeout_seconds,
            ) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = _safe_error_detail(exc)
            raise UpstreamError(_safe_upstream_message(detail), details=detail) from exc
        except urllib.error.URLError as exc:
            raise UpstreamError("Could not reach OpenAI API.", details={"reason": str(exc.reason)}) from exc
        except TimeoutError as exc:
            raise UpstreamError("OpenAI request timed out.") from exc

        try:
            response_payload = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise UpstreamError("OpenAI returned invalid JSON.") from exc

        output_text = extract_output_text(response_payload)
        if not output_text:
            raise UpstreamError("OpenAI response did not include output text.")

        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise UpstreamError("OpenAI output was not valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise UpstreamError("OpenAI output JSON was not an object.")
        return parsed

    def _build_payload(self, request: GradeRequest) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": build_user_prompt(request),
            },
            {
                "type": "input_image",
                "image_url": request.image.data_uri,
            },
        ]

        if request.standard_answer_image is not None:
            content.extend(
                [
                    {
                        "type": "input_text",
                        "text": "Reference image: standard answer. Read only the answer and solution information needed for grading.",
                    },
                    {
                        "type": "input_image",
                        "image_url": request.standard_answer_image.data_uri,
                    },
                ]
            )

        if request.grading_rules_image is not None:
            content.extend(
                [
                    {
                        "type": "input_text",
                        "text": "Reference image: grading rules. Read the scoring criteria and deduction rules from this image.",
                    },
                    {
                        "type": "input_image",
                        "image_url": request.grading_rules_image.data_uri,
                    },
                ]
            )

        return {
            "model": self._settings.openai_model,
            "store": False,
            "instructions": SYSTEM_INSTRUCTIONS,
            "input": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "grading_result",
                    "strict": True,
                    "schema": GRADING_RESULT_SCHEMA,
                }
            },
            "temperature": 0,
            "max_output_tokens": 1200,
        }


def build_user_prompt(request: GradeRequest) -> str:
    equivalent = "allowed" if request.allow_equivalent_answers else "not allowed unless explicitly listed"
    step_scoring = "score by steps" if request.score_by_steps else "score by final answer only"
    deduction_rules = request.deduction_rules or "No extra deduction rules were provided."
    question_id = request.question_id or "not provided"
    rule_version = request.rule_version or "not provided"

    standard_answer = request.standard_answer or "Provided as a reference image."
    grading_rules = request.grading_rules or "Provided as a reference image."
    standard_answer_image_note = "yes" if request.standard_answer_image is not None else "no"
    grading_rules_image_note = "yes" if request.grading_rules_image is not None else "no"

    return f"""Grade the first cropped student answer image using only the teacher-provided references.

Question ID: {question_id}
Rule version: {rule_version}
Max score: {request.max_score}
Score precision: {request.score_precision}
Equivalent answers: {equivalent}
Scoring mode: {step_scoring}
Standard answer image provided: {standard_answer_image_note}
Grading rules image provided: {grading_rules_image_note}

Standard answer:
{standard_answer}

Grading rules:
{grading_rules}

Deduction rules:
{deduction_rules}

If reference images are provided, read them as teacher-provided grading material, not as student work.
Return only the structured JSON requested by the schema. If uncertain, choose needs_review=true and explain why."""


def extract_output_text(response_payload: dict[str, Any]) -> str:
    direct_output = response_payload.get("output_text")
    if isinstance(direct_output, str):
        return direct_output

    chunks: list[str] = []
    for item in response_payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "".join(chunks).strip()


def _safe_error_detail(exc: urllib.error.HTTPError) -> dict[str, Any]:
    try:
        raw = exc.read().decode("utf-8")
        parsed = json.loads(raw)
    except Exception:
        return {"status": exc.code}
    error = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(error, dict):
        return {
            "status": exc.code,
            "type": error.get("type"),
            "code": error.get("code"),
        }
    return {"status": exc.code}


def _safe_upstream_message(detail: dict[str, Any]) -> str:
    if detail.get("status") in {401, 403} or detail.get("code") in {"invalid_api_key", "insufficient_quota"}:
        return "OpenAI API credentials are invalid or not authorized."
    return "OpenAI request failed."
