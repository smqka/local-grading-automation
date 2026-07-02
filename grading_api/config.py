"""Runtime configuration for the local grading API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    openai_api_key: str | None
    openai_base_url: str
    openai_model: str
    prompt_version: str
    request_timeout_seconds: float
    max_image_bytes: int
    api_token: str | None
    allowed_origins: tuple[str, ...]
    image_upload_url: str | None = None
    image_upload_field: str = "file"
    image_upload_response_path: str = "data.url"
    image_upload_response_format: str = "json"
    image_upload_extra_fields: tuple[tuple[str, str], ...] = ()
    image_upload_rewrite_from: str | None = None
    image_upload_rewrite_to: str = ""


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _get_origins() -> tuple[str, ...]:
    raw = os.getenv("GRADING_ALLOWED_ORIGINS", "")
    origins = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
    if origins:
        return origins
    return (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )


def _get_extra_fields() -> tuple[tuple[str, str], ...]:
    raw = os.getenv("GRADING_IMAGE_UPLOAD_EXTRA_FIELDS", "")
    fields: list[tuple[str, str]] = []
    for item in raw.split("&"):
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if key:
            fields.append((key, value.strip()))
    return tuple(fields)


def load_dotenv(path: str | os.PathLike[str] | None = None) -> None:
    env_path = Path(path) if path is not None else Path(__file__).resolve().parents[1] / ".env"
    try:
        content = env_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and not os.environ.get(key, "").strip():
            os.environ[key] = value


def load_settings(*, env_path: str | os.PathLike[str] | None = None) -> Settings:
    load_dotenv(env_path)

    image_upload_url = os.getenv("GRADING_IMAGE_UPLOAD_URL") or None
    image_url_mode = os.getenv("GRADING_IMAGE_URL_MODE", "").strip().lower()
    if not image_upload_url and image_url_mode == "tmpfiles":
        image_upload_url = "https://tmpfiles.org/api/v1/upload"
    elif not image_upload_url and image_url_mode == "uguu":
        image_upload_url = "https://uguu.se/upload.php"
    elif not image_upload_url and image_url_mode == "litterbox":
        image_upload_url = "https://litterbox.catbox.moe/resources/internals/api.php"
    elif not image_upload_url and image_url_mode == "imgbb" and os.getenv("IMGBB_API_KEY"):
        expiration = os.getenv("IMGBB_EXPIRATION_SECONDS", "600")
        image_upload_url = f"https://api.imgbb.com/1/upload?expiration={expiration}&key={os.getenv('IMGBB_API_KEY')}"

    upload_field = os.getenv("GRADING_IMAGE_UPLOAD_FIELD", "file")
    upload_response_path_env = os.getenv("GRADING_IMAGE_UPLOAD_RESPONSE_PATH")
    upload_response_path = upload_response_path_env or "data.url"
    upload_response_format = os.getenv("GRADING_IMAGE_UPLOAD_RESPONSE_FORMAT", "json")
    upload_extra_fields = _get_extra_fields()

    if image_url_mode == "uguu":
        upload_field = os.getenv("GRADING_IMAGE_UPLOAD_FIELD", "files[]")
        upload_response_path = os.getenv("GRADING_IMAGE_UPLOAD_RESPONSE_PATH", "files.0.url")
    elif image_url_mode == "litterbox":
        upload_field = os.getenv("GRADING_IMAGE_UPLOAD_FIELD", "fileToUpload")
        upload_response_format = os.getenv("GRADING_IMAGE_UPLOAD_RESPONSE_FORMAT", "text")
        upload_extra_fields = upload_extra_fields or (("reqtype", "fileupload"), ("time", "1h"))
    elif image_url_mode == "imgbb":
        upload_field = os.getenv("GRADING_IMAGE_UPLOAD_FIELD", "image")
        upload_response_path = upload_response_path_env or "data.medium.url"

    return Settings(
        host=os.getenv("GRADING_API_HOST", "127.0.0.1"),
        port=_get_int("GRADING_API_PORT", 8765),
        openai_api_key=os.getenv("OPENAI_API_KEY")
        or os.getenv("AI_KEY_TEST_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or None,
        openai_base_url=(
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("AI_KEY_TEST_BASE_URL")
            or os.getenv("DEEPSEEK_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/"),
        openai_model=os.getenv("OPENAI_MODEL")
        or os.getenv("AI_KEY_TEST_MODEL")
        or os.getenv("DEEPSEEK_TEXT_MODEL")
        or os.getenv("DEEPSEEK_DRAFT_MODEL")
        or "gpt-4.1",
        prompt_version=os.getenv("GRADING_PROMPT_VERSION", "grading-api-v1"),
        request_timeout_seconds=_get_float("GRADING_REQUEST_TIMEOUT_SECONDS", 30.0),
        max_image_bytes=_get_int("GRADING_MAX_IMAGE_BYTES", 5 * 1024 * 1024),
        api_token=os.getenv("GRADING_API_TOKEN") or None,
        allowed_origins=_get_origins(),
        image_upload_url=image_upload_url,
        image_upload_field=upload_field,
        image_upload_response_path=upload_response_path,
        image_upload_response_format=upload_response_format,
        image_upload_extra_fields=upload_extra_fields,
        image_upload_rewrite_from=os.getenv("GRADING_IMAGE_UPLOAD_REWRITE_FROM")
        or ("https://tmpfiles.org/" if image_url_mode == "tmpfiles" else None),
        image_upload_rewrite_to=os.getenv("GRADING_IMAGE_UPLOAD_REWRITE_TO")
        or ("https://tmpfiles.org/dl/" if image_url_mode == "tmpfiles" else ""),
    )
