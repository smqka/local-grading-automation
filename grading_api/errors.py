"""Domain errors rendered by the HTTP API."""

from __future__ import annotations


class GradingApiError(Exception):
    status_code = 500
    error_code = "internal_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class BadRequestError(GradingApiError):
    status_code = 400
    error_code = "bad_request"


class UnauthorizedError(GradingApiError):
    status_code = 401
    error_code = "unauthorized"


class UpstreamError(GradingApiError):
    status_code = 502
    error_code = "upstream_error"


class MouseAutomationUnavailableError(GradingApiError):
    status_code = 503
    error_code = "mouse_automation_unavailable"
