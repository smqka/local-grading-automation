"""Small local HTTP server for the grading API."""

from __future__ import annotations

import json
import ctypes
import math
import sys
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import Settings, load_settings
from .errors import BadRequestError, GradingApiError, MouseAutomationUnavailableError, UnauthorizedError
from .service import GradingService


MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


_DPI_AWARENESS_SET = False


def _user32() -> Any:
    if sys.platform != "win32" or not hasattr(ctypes, "windll"):
        raise MouseAutomationUnavailableError("Mouse automation is only available on Windows.")
    _set_process_dpi_aware()
    return ctypes.windll.user32


def _set_process_dpi_aware() -> None:
    global _DPI_AWARENESS_SET
    if _DPI_AWARENESS_SET or sys.platform != "win32" or not hasattr(ctypes, "windll"):
        return
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
    _DPI_AWARENESS_SET = True


def _virtual_screen_bounds() -> dict[str, int]:
    user32 = _user32()
    left = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
    top = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
    width = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
    height = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    if width <= 0 or height <= 0:
        raise MouseAutomationUnavailableError("Could not read the Windows screen bounds.")
    return {"left": left, "top": top, "width": width, "height": height}


def _read_coordinate(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise BadRequestError(f"{name} must be a finite number.")
    return int(round(float(value)))


def _read_point(payload: Any) -> dict[str, int]:
    if not isinstance(payload, dict):
        raise BadRequestError("Point must be a JSON object with x and y.")

    point = {"x": _read_coordinate(payload.get("x"), "x"), "y": _read_coordinate(payload.get("y"), "y")}
    bounds = _virtual_screen_bounds()
    right = bounds["left"] + bounds["width"]
    bottom = bounds["top"] + bounds["height"]
    if not (bounds["left"] <= point["x"] < right and bounds["top"] <= point["y"] < bottom):
        raise BadRequestError("Point is outside the current screen bounds.", details={"point": point, "bounds": bounds})
    return point


def _get_mouse_position() -> dict[str, Any]:
    user32 = _user32()
    point = POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise MouseAutomationUnavailableError("Could not read the current mouse position.")
    return {"x": int(point.x), "y": int(point.y), "screen": _virtual_screen_bounds()}


def _click_point(point: dict[str, int]) -> dict[str, int]:
    user32 = _user32()
    if not user32.SetCursorPos(point["x"], point["y"]):
        raise MouseAutomationUnavailableError("Could not move the mouse to the requested point.")
    time.sleep(0.04)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return point


def _read_delay_ms(payload: dict[str, Any]) -> int:
    raw_delay = payload.get("delay_ms", 300)
    if isinstance(raw_delay, bool) or not isinstance(raw_delay, (int, float)) or not math.isfinite(float(raw_delay)):
        raise BadRequestError("delay_ms must be a finite number.")
    return max(0, min(int(round(float(raw_delay))), 5000))


def _click_payload(payload: dict[str, Any]) -> dict[str, Any]:
    point = _read_point(payload)
    return {"ok": True, "clicked": [_click_point(point)]}


def _click_sequence_payload(payload: dict[str, Any]) -> dict[str, Any]:
    points = payload.get("points")
    if not isinstance(points, list) or not points:
        raise BadRequestError("points must be a non-empty list.")
    if len(points) > 10:
        raise BadRequestError("A click sequence can contain at most 10 points.")

    delay_ms = _read_delay_ms(payload)
    parsed_points = [_read_point(point) for point in points]
    clicked = []
    for index, point in enumerate(parsed_points):
        clicked.append(_click_point(point))
        if index < len(parsed_points) - 1 and delay_ms > 0:
            time.sleep(delay_ms / 1000)

    return {"ok": True, "clicked": clicked, "delay_ms": delay_ms}


class GradingRequestHandler(BaseHTTPRequestHandler):
    server_version = "GradingAPI/0.1"

    def do_OPTIONS(self) -> None:
        self._send_json({}, status=HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        try:
            if self.path == "/health":
                settings = self.server.settings  # type: ignore[attr-defined]
                self._send_json({"status": "ok", "has_openai_key": bool(settings.openai_api_key)})
                return
            if self.path == "/api/mouse-position":
                self._authorize()
                self._send_json(_get_mouse_position())
                return
            self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
        except GradingApiError as exc:
            self._send_json(
                {"error": exc.error_code, "message": str(exc), "details": exc.details},
                status=exc.status_code,
            )
        except Exception:
            traceback.print_exc()
            self._send_json(
                {"error": "internal_error", "message": "Unexpected server error.", "details": {}},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_POST(self) -> None:
        if self.path not in {"/api/grade", "/api/parse-reference", "/api/click", "/api/click-sequence"}:
            self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            self._authorize()
            payload = self._read_json_body()
            if self.path == "/api/parse-reference":
                response = self.server.grading_service.parse_reference_payload(payload)  # type: ignore[attr-defined]
                self._send_json(response.to_json())
            elif self.path == "/api/grade":
                response = self.server.grading_service.grade_payload(payload)  # type: ignore[attr-defined]
                self._send_json(response.to_json())
            elif self.path == "/api/click":
                self._send_json(_click_payload(payload))
            else:
                self._send_json(_click_sequence_payload(payload))
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
            # Log metadata-only traceback; request bodies can contain student images.
            traceback.print_exc()
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
