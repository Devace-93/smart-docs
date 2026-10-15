"""Domain errors. The API and the MCP server map these to status codes and structured errors."""

from __future__ import annotations


class SDError(Exception):
    code = "error"
    status = 400
    hint = ""

    def __init__(self, message: str, *, hint: str | None = None):
        super().__init__(message)
        self.message = message
        if hint is not None:
            self.hint = hint

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "hint": self.hint}


class NotFound(SDError):
    code = "not_found"
    status = 404
    hint = "Call list_tree to see what exists."


class Conflict(SDError):
    code = "conflict"
    status = 409
    hint = "Read the current version and send it as expected_version."


class Invalid(SDError):
    code = "invalid"
    status = 422


class Forbidden(SDError):
    code = "forbidden"
    status = 403


class Unauthorized(SDError):
    code = "unauthorized"
    status = 401
    hint = "Send a bearer token or an API key."


class RateLimited(SDError):
    code = "rate_limited"
    status = 429
    hint = "Wait for Retry-After seconds, or check GET /api/v1/me/usage before spending quota."

    def __init__(self, message: str, *, retry_after: int, limit: int, remaining: int, reset: int):
        super().__init__(message)
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.reset = reset

    def headers(self) -> dict[str, str]:
        return {
            "Retry-After": str(self.retry_after),
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset),
        }
