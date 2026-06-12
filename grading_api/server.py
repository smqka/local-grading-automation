"""Small local HTTP server for the grading API."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import Settings, load_settings
from .errors import GradingApiError, UnauthorizedError
from .service import GradingService


class GradingRequestHandler(BaseHTTPRequestHandler):
    server_version = "GradingAPI/0.1"

    def do_OPTIONS(self) -> None:
        self._send_json({}, status=HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json({"status": "ok"})
            return
        self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/api/grade":
            self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            self._authorize()
            payload = self._read_json_body()
            response = self.server.grading_service.grade_payload(payload)  # type: ignore[attr-defined]
            self._send_json(response.to_json())
        except GradingApiError as exc:
            self._send_json(
                {"error": exc.error_code, "message": str(exc), "details": exc.details},
                status=exc.status_code,
            )
        except json.JSONDecodeError:
            self._send_json(
                {"error": "bad_request", "message": "Request body must be valid JSON.", "details": {}},
                status=HTTPStatus.BAD_REQUEST,
            )
        except Exception:
            self._send_json(
                {"error": "internal_error", "message": "Unexpected server error.", "details": {}},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, format: str, *args: Any) -> None:
        # Keep logs metadata-only; never print request bodies or image data.
        super().log_message(format, *args)

    def _authorize(self) -> None:
        token = self.server.settings.api_token  # type: ignore[attr-defined]
        if not token:
            return
        if self.headers.get("X-Grading-Api-Token") != token:
            raise UnauthorizedError("Missing or invalid API token.")

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            raise json.JSONDecodeError("invalid length", raw_length, 0)
        body = self.rfile.read(length)
        return json.loads(body.decode("utf-8"))

    def _send_json(self, payload: dict[str, Any], *, status: int | HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        if int(status) != HTTPStatus.NO_CONTENT:
            self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        settings = self.server.settings  # type: ignore[attr-defined]
        if origin and origin in settings.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Grading-Api-Token")


class GradingHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], settings: Settings) -> None:
        super().__init__(server_address, GradingRequestHandler)
        self.settings = settings
        self.grading_service = GradingService(settings)


def create_server(settings: Settings | None = None) -> GradingHTTPServer:
    settings = settings or load_settings()
    return GradingHTTPServer((settings.host, settings.port), settings)


def main() -> None:
    server = create_server()
    host, port = server.server_address
    print(f"Grading API listening on http://{host}:{port}")
    print("POST cropped answer images to /api/grade; health check is /health.")
    server.serve_forever()


if __name__ == "__main__":
    main()
