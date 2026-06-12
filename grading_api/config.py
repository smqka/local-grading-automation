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
        if key and key not in os.environ:
            os.environ[key] = value


def load_settings(*, env_path: str | os.PathLike[str] | None = None) -> Settings:
    load_dotenv(env_path)

    return Settings(
        host=os.getenv("GRADING_API_HOST", "127.0.0.1"),
        port=_get_int("GRADING_API_PORT", 8765),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
        prompt_version=os.getenv("GRADING_PROMPT_VERSION", "grading-api-v1"),
        request_timeout_seconds=_get_float("GRADING_REQUEST_TIMEOUT_SECONDS", 30.0),
        max_image_bytes=_get_int("GRADING_MAX_IMAGE_BYTES", 5 * 1024 * 1024),
        api_token=os.getenv("GRADING_API_TOKEN") or None,
        allowed_origins=_get_origins(),
    )
