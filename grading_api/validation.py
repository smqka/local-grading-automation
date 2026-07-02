"""Input and output validation for grading requests."""

from __future__ import annotations

import base64
import binascii
import math
import re
from typing import Any

from .errors import BadRequestError
from .models import GradeRequest, ImagePayload, ModelGradeResult, ReferenceParseRequest, ReferenceParseResult, ScorePrecision

DATA_URI_RE = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,(?P<data>[A-Za-z0-9+/=\s]+)$")
SUPPORTED_PRECISIONS: tuple[ScorePrecision, ...] = ("integer", "0.5", "0.1")


def parse_grade_request(payload: dict[str, Any], *, max_image_bytes: int) -> GradeRequest:
    if not isinstance(payload, dict):
        raise BadRequestError("Request body must be a JSON object.")

    image = _parse_image(payload, "image", max_image_bytes=max_image_bytes)
    max_score = _parse_number(payload.get("max_score"), "max_score")
    if max_score <= 0:
        raise BadRequestError("max_score must be greater than 0.")
    if max_score > 100:
        raise BadRequestError("max_score is unexpectedly large.", details={"limit": 100})

    standard_answer = _optional_text(payload.get("standard_answer"), "standard_answer")
    if not standard_answer:
        raise BadRequestError("Provide confirmed standard_answer text before grading.")

    grading_rules = _optional_text(payload.get("grading_rules"), "grading_rules")
    if not grading_rules:
        raise BadRequestError("Provide confirmed grading_rules text before grading.")

    deduction_rules = _optional_text(payload.get("deduction_rules"))
    score_precision = _parse_precision(payload.get("score_precision", "0.5"))

    return GradeRequest(
        image=image,
        max_score=max_score,
        standard_answer=standard_answer,
        grading_rules=grading_rules,
        deduction_rules=deduction_rules,
        allow_equivalent_answers=_parse_bool(payload.get("allow_equivalent_answers", True), "allow_equivalent_answers"),
        score_by_steps=_parse_bool(payload.get("score_by_steps", True), "score_by_steps"),
        score_precision=score_precision,
        question_id=_optional_text(payload.get("question_id")) or None,
        rule_version=_optional_text(payload.get("rule_version")) or None,
    )


def parse_reference_parse_request(payload: dict[str, Any], *, max_image_bytes: int) -> ReferenceParseRequest:
    if not isinstance(payload, dict):
        raise BadRequestError("Request body must be a JSON object.")

    return ReferenceParseRequest(
        image=_parse_image(payload, "image", max_image_bytes=max_image_bytes),
        question_id=_optional_text(payload.get("question_id")) or None,
        rule_version=_optional_text(payload.get("rule_version")) or None,
    )


def validate_reference_parse_result(raw: dict[str, Any]) -> ReferenceParseResult:
    if not isinstance(raw, dict):
        return ReferenceParseResult(
            standard_answer="",
            grading_rules="",
            deduction_rules="",
            max_score=None,
            confidence=0.0,
            needs_review=True,
            review_reason="Model output was not a JSON object.",
            uncertain_factors=[],
            raw={},
        )

    confidence = raw.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(float(confidence)):
        confidence_value = 0.0
    else:
        confidence_value = max(0.0, min(float(confidence), 1.0))

    max_score = raw.get("max_score")
    max_score_value = None
    if not isinstance(max_score, bool) and isinstance(max_score, (int, float)) and math.isfinite(float(max_score)):
        max_score_value = float(max_score)

    standard_answer = _coerce_reference_text(raw.get("standard_answer"))
    grading_rules = _coerce_reference_text(raw.get("grading_rules"))
    deduction_rules = _coerce_reference_text(raw.get("deduction_rules"))
    review_reason = _coerce_reference_text(raw.get("review_reason"))
    needs_review = bool(raw.get("needs_review", False))
    uncertain_factors = _string_list(raw.get("uncertain_factors"))

    missing = []
    if not standard_answer:
        missing.append("standard_answer")
    if not grading_rules:
        missing.append("grading_rules")
    if missing:
        needs_review = True
        review_reason = review_reason or f"Missing parsed fields: {', '.join(missing)}."
    elif confidence_value < 0.8:
        needs_review = True
        review_reason = review_reason or "Reference parse confidence is below 0.80; teacher review is required."

    return ReferenceParseResult(
        standard_answer=standard_answer,
        grading_rules=grading_rules,
        deduction_rules=deduction_rules,
        max_score=max_score_value,
        confidence=round(confidence_value, 4),
        needs_review=needs_review,
        review_reason=review_reason,
        uncertain_factors=uncertain_factors,
        raw=raw,
    )


def validate_model_result(raw: dict[str, Any], request: GradeRequest) -> ModelGradeResult:
    if not isinstance(raw, dict):
        return _review_result(request, "Model output was not a JSON object.", raw={})

    errors: list[str] = []
    suggested_score = _maybe_number(raw.get("suggested_score"), "suggested_score", errors)
    confidence = _maybe_number(raw.get("confidence"), "confidence", errors)
    max_score = _maybe_number(raw.get("max_score"), "max_score", errors)

    if suggested_score is not None:
        if suggested_score < 0 or suggested_score > request.max_score:
            errors.append("suggested_score must be between 0 and max_score")
        if not _matches_precision(suggested_score, request.score_precision):
            errors.append(f"suggested_score must match {request.score_precision} precision")

    if confidence is None:
        confidence = 0.0
    elif confidence < 0 or confidence > 1:
        errors.append("confidence must be between 0 and 1")

    if max_score is None:
        max_score = request.max_score
    elif not math.isclose(max_score, request.max_score, rel_tol=0, abs_tol=0.0001):
        errors.append("model max_score must match request max_score")

    deduction_points = _string_list(raw.get("deduction_points"))
    uncertain_factors = _string_list(raw.get("uncertain_factors"))
    summary = _text_or_empty(raw.get("student_answer_summary"))
    review_reason = _text_or_empty(raw.get("review_reason"))
    needs_review = bool(raw.get("needs_review", False))

    if confidence < 0.9:
        needs_review = True
        if not review_reason:
            review_reason = _confidence_review_reason(confidence)

    if errors:
        needs_review = True
        suggested_score = None
        review_reason = "; ".join(errors)

    return ModelGradeResult(
        suggested_score=suggested_score,
        max_score=request.max_score,
        confidence=round(confidence, 4),
        needs_review=needs_review,
        review_reason=review_reason,
        deduction_points=deduction_points,
        student_answer_summary=summary,
        uncertain_factors=uncertain_factors,
        raw=raw,
    )


def _parse_image(payload: dict[str, Any], name: str, *, max_image_bytes: int) -> ImagePayload:
    image = payload.get(name)
    mime_type = payload.get(f"{name}_mime_type")
    if name == "image" and not mime_type:
        mime_type = payload.get("mime_type")

    if isinstance(image, str) and image.startswith("data:"):
        return _parse_data_uri(image, name, max_image_bytes=max_image_bytes)

    base64_name = f"{name}_base64"
    if isinstance(payload.get(base64_name), str):
        image_base64 = payload[base64_name]
        if not isinstance(mime_type, str) or mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise BadRequestError(f"{name}_mime_type must be image/png, image/jpeg, or image/webp.")
        normalized = "".join(image_base64.split())
        size = _decoded_size(normalized, name, max_image_bytes=max_image_bytes)
        return ImagePayload(
            data_uri=f"data:{mime_type};base64,{normalized}",
            mime_type=mime_type,
            size_bytes=size,
        )

    if name == "image":
        raise BadRequestError("Provide image as a data URI or image_base64 with image_mime_type.")
    raise BadRequestError(f"Provide {name} as a data URI or {base64_name} with {name}_mime_type.")


def _parse_optional_image(payload: dict[str, Any], name: str, *, max_image_bytes: int) -> ImagePayload | None:
    if not payload.get(name) and not payload.get(f"{name}_base64"):
        return None
    return _parse_image(payload, name, max_image_bytes=max_image_bytes)


def _parse_data_uri(data_uri: str, name: str, *, max_image_bytes: int) -> ImagePayload:
    match = DATA_URI_RE.match(data_uri)
    if not match:
        raise BadRequestError(f"{name} must be a base64 data URI for png, jpeg, or webp.")
    mime_type = match.group(1)
    normalized = "".join(match.group("data").split())
    size = _decoded_size(normalized, name, max_image_bytes=max_image_bytes)
    return ImagePayload(
        data_uri=f"data:{mime_type};base64,{normalized}",
        mime_type=mime_type,
        size_bytes=size,
    )


def _decoded_size(value: str, name: str, *, max_image_bytes: int) -> int:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BadRequestError(f"{name} base64 is invalid.") from exc
    size = len(decoded)
    if size == 0:
        raise BadRequestError(f"{name} must not be empty.")
    if size > max_image_bytes:
        raise BadRequestError(f"{name} is too large.", details={"max_image_bytes": max_image_bytes})
    return size


def _parse_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BadRequestError(f"{name} must be a number.")
    if not math.isfinite(value):
        raise BadRequestError(f"{name} must be finite.")
    return float(value)


def _maybe_number(value: Any, name: str, errors: list[str]) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        errors.append(f"{name} must be a finite number")
        return None
    return float(value)


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BadRequestError(f"{name} is required.")
    return value.strip()


def _optional_text(value: Any, name: str = "Optional text field") -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise BadRequestError(f"{name} must be a string.")
    return value.strip()


def _parse_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise BadRequestError(f"{name} must be a boolean.")
    return value


def _parse_precision(value: Any) -> ScorePrecision:
    if value not in SUPPORTED_PRECISIONS:
        raise BadRequestError("score_precision must be one of integer, 0.5, or 0.1.")
    return value


def _matches_precision(score: float, precision: ScorePrecision) -> bool:
    if precision == "integer":
        step = 1.0
    elif precision == "0.5":
        step = 0.5
    else:
        step = 0.1
    return math.isclose(score / step, round(score / step), rel_tol=0, abs_tol=0.0001)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _coerce_reference_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return str(value)
    if isinstance(value, list):
        parts = [_coerce_reference_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            text = _coerce_reference_text(item)
            if text:
                lines.append(f"{key}: {text}")
        return "\n".join(lines)
    return ""


def _text_or_empty(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _confidence_review_reason(confidence: float) -> str:
    if confidence < 0.7:
        return "Confidence is below 0.70; teacher review is required."
    return "Confidence is below 0.90; teacher review is recommended."


def _review_result(request: GradeRequest, reason: str, raw: dict[str, Any]) -> ModelGradeResult:
    return ModelGradeResult(
        suggested_score=None,
        max_score=request.max_score,
        confidence=0.0,
        needs_review=True,
        review_reason=reason,
        deduction_points=[],
        student_answer_summary="",
        uncertain_factors=[],
        raw=raw,
    )
