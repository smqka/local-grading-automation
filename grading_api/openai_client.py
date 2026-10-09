"""OpenAI-compatible chat completions client for grading answer images."""

from __future__ import annotations

import base64
import binascii
import http.client
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Protocol

from .config import Settings
from .errors import UpstreamError
from .models import GradeRequest, ReferenceParseRequest


class GradingModelClient(Protocol):
    model_name: str

    def grade(self, request: GradeRequest) -> dict[str, Any]:
        ...

    def parse_reference(self, request: ReferenceParseRequest) -> dict[str, Any]:
        ...


SYSTEM_INSTRUCTIONS = """You are an AI grading assistant for math teachers.
You provide advisory scores only. The teacher is always the final grader.
Grade only from the cropped answer image and the teacher-confirmed text rubric.
Do not infer student identity. Do not claim the score has been submitted.
If the image is unclear, the rubric is ambiguous, or the answer cannot be read, set needs_review to true and lower confidence.
Never assign a score below 0 or above the max score.
All user-facing text in the JSON response must be Chinese."""

REFERENCE_PARSE_JSON_KEYS = (
    "standard_answer, grading_rules, deduction_rules, max_score, confidence, "
    "needs_review, review_reason, uncertain_factors"
)

DATA_URI_RE = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,(?P<data>[A-Za-z0-9+/=\s]+)$")


class OpenAIResponsesClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise UpstreamError("OPENAI_API_KEY is not configured.")
        self._settings = settings
        self.model_name = settings.openai_model

    def grade(self, request: GradeRequest) -> dict[str, Any]:
        response_payload = self._grade_with_chat_completions(request)
        return _parse_json_object_from_model(response_payload)

    def parse_reference(self, request: ReferenceParseRequest) -> dict[str, Any]:
        response_payload = self._parse_reference_with_chat_completions(request)
        return _parse_json_object_from_model(response_payload)

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    # 仅对 Qwen3.7-Flash 关闭深度思考
        if str(payload.get("model", "")).strip().lower() == "qwen3.7-flash":
            payload = {**payload, "enable_thinking": False}

        body_text = json.dumps(payload, ensure_ascii=False)

        attempts = 3
        for attempt in range(attempts):
            try:
                curl_path = _find_curl_executable()
                if curl_path:
                    response_body = self._post_json_with_curl(url, body_text, curl_path)
                else:
                    response_body = self._post_json_with_urllib(url, body_text.encode("utf-8"))
                break
            except UpstreamError:
                if attempt < attempts - 1:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                raise

        try:
            return json.loads(_extract_sse_json_text(response_body))
        except json.JSONDecodeError as exc:
            raise UpstreamError("OpenAI returned invalid JSON.") from exc

    def _post_json_with_urllib(self, url: str, body: bytes) -> str:
        http_request = urllib.request.Request(
            url,
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
                return response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            if isinstance(exc, urllib.error.HTTPError):
                raise
            raise UpstreamError(
                "Could not reach the model API. Check network, proxy, or OPENAI_BASE_URL.",
                details={"reason": str(exc.reason)},
            ) from exc
        except TimeoutError as exc:
            raise UpstreamError("Model API request timed out. Check network or proxy.") from exc
        except (http.client.HTTPException, OSError) as exc:
            raise UpstreamError(
                "Model API connection failed before a response was returned.",
                details={"reason": type(exc).__name__},
            ) from exc

    def _post_json_with_curl(self, url: str, body_text: str, curl_path: str) -> str:
        request_path = ""
        response_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix="grading-model-request-",
                suffix=".json",
                delete=False,
            ) as request_file:
                request_file.write(body_text)
                request_path = request_file.name
            with tempfile.NamedTemporaryFile(
                prefix="grading-model-response-",
                suffix=".json",
                delete=False,
            ) as response_file:
                response_path = response_file.name

            command = [
                curl_path,
                "--silent",
                "--show-error",
                "--request",
                "POST",
                url,
                "--header",
                f"Authorization: Bearer {self._settings.openai_api_key}",
                "--header",
                "Content-Type: application/json",
                "--data-binary",
                f"@{request_path}",
                "--output",
                response_path,
                "--write-out",
                "%{http_code}",
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self._settings.request_timeout_seconds,
                check=False,
            )
            try:
                with open(response_path, encoding="utf-8", errors="replace") as response_file:
                    response_body = response_file.read()
            except OSError:
                response_body = ""

            status_text = completed.stdout.strip()
            status = int(status_text) if status_text.isdigit() else 0
            if completed.returncode != 0:
                raise UpstreamError(
                    "Could not reach the model API. Check network, proxy, or OPENAI_BASE_URL.",
                    details={"transport": "curl", "reason": f"curl_exit_{completed.returncode}"},
                )
            if status < 200 or status >= 300:
                detail = _safe_model_error_detail(status, response_body)
                raise UpstreamError(_safe_upstream_message(detail), details=detail)
            return response_body
        except subprocess.TimeoutExpired as exc:
            raise UpstreamError("Model API request timed out. Check network or proxy.", details={"transport": "curl"}) from exc
        except OSError as exc:
            raise UpstreamError(
                "Model API connection failed before a response was returned.",
                details={"transport": "curl", "reason": type(exc).__name__},
            ) from exc
        finally:
            for path in (request_path, response_path):
                if not path:
                    continue
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _grade_with_chat_completions(
        self,
        request: GradeRequest,
    ) -> dict[str, Any]:
        try:
            return self._post_json(f"{self._settings.openai_base_url}/chat/completions", self._build_chat_payload(request))
        except urllib.error.HTTPError as exc:
            detail = _safe_error_detail(exc)
            raise UpstreamError(_safe_upstream_message(detail), details=detail) from exc
        except UpstreamError:
            raise
        except Exception as exc:
            detail = _fallback_error_detail(exc)
            raise UpstreamError(_safe_upstream_message(detail), details=detail) from exc

    def _parse_reference_with_chat_completions(
        self,
        request: ReferenceParseRequest,
    ) -> dict[str, Any]:
        try:
            return self._post_json(
                f"{self._settings.openai_base_url}/chat/completions",
                self._build_reference_chat_payload(request),
            )
        except urllib.error.HTTPError as exc:
            detail = _safe_error_detail(exc)
            raise UpstreamError(_safe_upstream_message(detail), details=detail) from exc
        except UpstreamError:
            raise
        except Exception as exc:
            detail = _fallback_error_detail(exc)
            raise UpstreamError(_safe_upstream_message(detail), details=detail) from exc

    def _build_chat_payload(self, request: GradeRequest) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    build_user_prompt(request)
                    + "\n\nReturn only a valid JSON object with these keys: "
                    "suggested_score, max_score, confidence, needs_review, review_reason, "
                    "deduction_points, student_answer_summary, uncertain_factors. "
                    "Return confidence as a number from 0 to 1, not as a percent."
                ),
            },
            self._chat_image_item(request.image.data_uri),
        ]

        return {
            "model": self._settings.openai_model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": content},
            ],
            "temperature": 0,
            "max_tokens": 450,
        }

    def _build_reference_chat_payload(self, request: ReferenceParseRequest) -> dict[str, Any]:
        return {
            "model": self._settings.openai_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": build_reference_parse_prompt(request),
                        },
                        self._chat_image_item(request.image.data_uri),
                    ],
                },
            ],
            "temperature": 0,
            "max_tokens": 500,
        }

    def _chat_image_item(self, data_uri: str) -> dict[str, Any]:
        return {
            "type": "image_url",
            "image_url": {"url": self._image_url_for_chat(data_uri)},
        }

    def _image_url_for_chat(self, data_uri: str) -> str:
        if not self._settings.image_upload_url:
            return data_uri
        return self._upload_image_for_url(data_uri)

    def _upload_image_for_url(self, data_uri: str) -> str:
        mime_type, image_bytes = _decode_data_uri(data_uri)
        extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime_type]
        filename = f"answer-{uuid.uuid4().hex}.{extension}"

        upload_errors: list[UpstreamError] = []
        for attempt in range(3):
            try:
                curl_path = _find_curl_executable()
                if curl_path:
                    response_body = self._upload_image_with_curl(
                        curl_path=curl_path,
                        image_bytes=image_bytes,
                        field_name=self._settings.image_upload_field,
                        filename=filename,
                        mime_type=mime_type,
                        extension=extension,
                    )
                else:
                    response_body = self._upload_image_with_urllib(
                        image_bytes=image_bytes,
                        field_name=self._settings.image_upload_field,
                        filename=filename,
                        mime_type=mime_type,
                    )
                break
            except UpstreamError as exc:
                upload_errors.append(exc)
                if attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                raise exc
        else:
            raise upload_errors[-1]

        url = self._extract_upload_url(response_body)

        if self._settings.image_upload_rewrite_from:
            url = url.replace(
                self._settings.image_upload_rewrite_from,
                self._settings.image_upload_rewrite_to,
                1,
            )
        return url

    def _upload_image_with_urllib(
        self,
        *,
        image_bytes: bytes,
        field_name: str,
        filename: str,
        mime_type: str,
    ) -> str:
        boundary = f"----grading-upload-{uuid.uuid4().hex}"
        body = _build_multipart_body(
            boundary=boundary,
            fields=self._settings.image_upload_extra_fields,
            field_name=field_name,
            filename=filename,
            mime_type=mime_type,
            content=image_bytes,
        )
        request = urllib.request.Request(
            self._settings.image_upload_url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self._settings.request_timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = _safe_error_detail(exc)
            raise UpstreamError("Image URL upload failed.", details=detail) from exc
        except urllib.error.URLError as exc:
            raise UpstreamError("Image URL service is unavailable.", details={"reason": str(exc.reason)}) from exc
        except TimeoutError as exc:
            raise UpstreamError("Image URL upload timed out.") from exc
        except (http.client.HTTPException, OSError) as exc:
            raise UpstreamError(
                "Image URL service connection failed.",
                details={"reason": type(exc).__name__},
            ) from exc
        return response_body

    def _upload_image_with_curl(
        self,
        *,
        curl_path: str,
        image_bytes: bytes,
        field_name: str,
        filename: str,
        mime_type: str,
        extension: str,
    ) -> str:
        image_path = ""
        response_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                prefix="grading-upload-",
                suffix=f".{extension}",
                delete=False,
            ) as image_file:
                image_file.write(image_bytes)
                image_path = image_file.name
            with tempfile.NamedTemporaryFile(
                prefix="grading-upload-response-",
                suffix=".txt",
                delete=False,
            ) as response_file:
                response_path = response_file.name

            command = [
                curl_path,
                "--silent",
                "--show-error",
                "--request",
                "POST",
                self._settings.image_upload_url or "",
                "--output",
                response_path,
                "--write-out",
                "%{http_code}",
            ]
            for name, value in self._settings.image_upload_extra_fields:
                command.extend(["--form", f"{name}={value}"])
            command.extend(["--form", f"{field_name}=@{image_path};filename={filename};type={mime_type}"])

            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self._settings.request_timeout_seconds,
                check=False,
            )
            try:
                with open(response_path, encoding="utf-8", errors="replace") as response_file:
                    response_body = response_file.read()
            except OSError:
                response_body = ""

            status_text = completed.stdout.strip()
            status = int(status_text) if status_text.isdigit() else 0
            if completed.returncode != 0:
                raise UpstreamError(
                    "Image URL service is unavailable.",
                    details={"transport": "curl", "reason": f"curl_exit_{completed.returncode}"},
                )
            if status < 200 or status >= 300:
                raise UpstreamError(
                    "Image URL upload failed.",
                    details=_safe_upload_error_detail(status, response_body),
                )
            return response_body
        except subprocess.TimeoutExpired as exc:
            raise UpstreamError("Image URL upload timed out.", details={"transport": "curl"}) from exc
        except OSError as exc:
            raise UpstreamError(
                "Image URL service connection failed.",
                details={"transport": "curl", "reason": type(exc).__name__},
            ) from exc
        finally:
            for path in (image_path, response_path):
                if not path:
                    continue
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _extract_upload_url(self, response_body: str) -> str:
        if self._settings.image_upload_response_format == "text":
            url = response_body.strip()
        else:
            try:
                payload = json.loads(response_body)
            except json.JSONDecodeError as exc:
                raise UpstreamError("Image URL service returned non-JSON response.") from exc
            response_paths = _image_upload_response_paths(
                upload_url=self._settings.image_upload_url,
                configured_path=self._settings.image_upload_response_path,
            )
            url = _get_first_path(payload, response_paths)

        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise UpstreamError("Image URL service did not return a usable image URL.")
        return url


def build_user_prompt(request: GradeRequest) -> str:
    equivalent = "allowed" if request.allow_equivalent_answers else "not allowed unless explicitly listed"
    step_scoring = "score by steps" if request.score_by_steps else "score by final answer only"
    deduction_rules = request.deduction_rules or "No extra deduction rules were provided."
    question_id = request.question_id or "not provided"
    rule_version = request.rule_version or "not provided"

    standard_answer = request.standard_answer
    grading_rules = request.grading_rules

    return f"""Grade the first cropped student answer image using only the teacher-provided references.

Question ID: {question_id}
Rule version: {rule_version}
Max score: {request.max_score}
Score precision: {request.score_precision}
Equivalent answers: {equivalent}
Scoring mode: {step_scoring}

Standard answer:
{standard_answer}

Grading rules:
{grading_rules}

Deduction rules:
{deduction_rules}

The teacher has already confirmed the text standard answer and grading rules.
Inspect the student image internally, but do not transcribe the visible steps.
Score only answers and steps that are clearly visible in the image.
Do not infer missing or unclear work from the standard answer or grading rules.
If a required answer or step is not clearly visible, treat it as not shown.
Return the suggested score directly with minimal Chinese text.
Keep student_answer_summary empty unless a short review note is necessary.
Set deduction_points and uncertain_factors to empty arrays unless teacher review is needed.
Return only the structured JSON requested by the schema. If uncertain, choose needs_review=true and explain why briefly."""


def build_reference_parse_prompt(request: ReferenceParseRequest) -> str:
    return (
        "Read this teacher reference image. "
        "Return JSON only with keys: "
        f"{REFERENCE_PARSE_JSON_KEYS}."
    ).strip()


def extract_output_text(response_payload: dict[str, Any]) -> str:
    direct_output = response_payload.get("output_text")
    if isinstance(direct_output, str):
        return direct_output

    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = first_choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()
                if isinstance(content, list):
                    chunks = [
                        item.get("text", "")
                        for item in content
                        if isinstance(item, dict) and isinstance(item.get("text"), str)
                    ]
                    return "".join(chunks).strip()

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


def _parse_json_object_from_model(response_payload: dict[str, Any]) -> dict[str, Any]:
    output_text = extract_output_text(response_payload)
    if not output_text:
        raise UpstreamError("Model response did not include output text.")

    try:
        parsed = json.loads(_extract_json_object_text(output_text))
    except json.JSONDecodeError as exc:
        raise UpstreamError("Model output was not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise UpstreamError("Model output JSON was not an object.")
    return parsed


def _extract_json_object_text(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _decode_data_uri(data_uri: str) -> tuple[str, bytes]:
    match = DATA_URI_RE.match(data_uri)
    if not match:
        raise UpstreamError("Image URL upload only supports PNG, JPEG, or WebP data URIs.")
    mime_type = match.group(1)
    normalized = "".join(match.group("data").split())
    try:
        return mime_type, base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise UpstreamError("Image URL upload received invalid image base64.") from exc


def _build_multipart_body(
    *,
    boundary: str,
    fields: tuple[tuple[str, str], ...],
    field_name: str,
    filename: str,
    mime_type: str,
    content: bytes,
) -> bytes:
    parts: list[bytes] = []
    for name, value in fields:
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )

    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8")
    suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
    parts.append(prefix + content + suffix)
    return b"".join(parts)


def _get_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return None
    return current


def _get_first_path(payload: dict[str, Any], paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = _get_path(payload, path)
        if value is not None:
            return value
    return None


def _image_upload_response_paths(*, upload_url: str | None, configured_path: str) -> tuple[str, ...]:
    paths = [configured_path]
    if upload_url and "api.imgbb.com/1/upload" in upload_url:
        paths.extend(["data.medium.url", "data.thumb.url", "data.display_url", "data.url"])
    return tuple(dict.fromkeys(path for path in paths if path))


def _find_curl_executable() -> str | None:
    return shutil.which("curl.exe") or shutil.which("curl")


def _safe_upload_error_detail(status: int, response_body: str) -> dict[str, Any]:
    detail: dict[str, Any] = {"status": status, "transport": "curl"}
    try:
        parsed = json.loads(response_body)
    except Exception:
        return detail
    if not isinstance(parsed, dict):
        return detail
    error = parsed.get("error")
    if isinstance(error, dict):
        for key in ("type", "code"):
            if isinstance(error.get(key), str):
                detail[key] = error[key]
    if isinstance(parsed.get("status_code"), int):
        detail["provider_status"] = parsed["status_code"]
    return detail


def _safe_model_error_detail(status: int, response_body: str) -> dict[str, Any]:
    detail: dict[str, Any] = {"status": status, "transport": "curl"}
    try:
        parsed = json.loads(_extract_sse_json_text(response_body))
    except Exception:
        return detail
    error = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(error, dict):
        for key in ("type", "code"):
            if isinstance(error.get(key), str):
                detail[key] = error[key]
    return detail


def _extract_sse_json_text(response_body: str) -> str:
    text = response_body.strip()
    if text.startswith("{"):
        return text

    chunks: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if data and data != "[DONE]":
            chunks.append(data)
    if len(chunks) == 1:
        return chunks[0]
    return text


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


def _fallback_error_detail(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, urllib.error.HTTPError):
        return _safe_error_detail(exc)
    if isinstance(exc, UpstreamError):
        return exc.details or {"reason": type(exc).__name__}
    return {"reason": type(exc).__name__}


def _safe_upstream_message(detail: dict[str, Any]) -> str:
    if detail.get("status") in {401, 403} or detail.get("code") in {"invalid_api_key", "insufficient_quota"}:
        return "Model API credentials are invalid or not authorized."
    return "Model API request failed. Check whether the gateway supports chat/completions image_url."
