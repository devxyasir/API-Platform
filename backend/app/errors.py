"""Unified error system.

Every error the public API emits is normalized into an OpenAI/Anthropic-style
envelope::

    {
      "error": {
        "message": "...",
        "type": "rate_limit_error",
        "code": "rate_limit_exceeded",
        "request_id": "req_..."
      }
    }

Internal stack traces are NEVER exposed to API consumers.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_config import get_logger

logger = get_logger("app.errors")


class APIError(Exception):
    """Base class for all normalized API errors."""

    status_code: int = 500
    error_type: str = "internal_error"
    code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        error_type: str | None = None,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if error_type:
            self.error_type = error_type
        if status_code:
            self.status_code = status_code
        self.headers = headers or {}
        self.extra = extra or {}

    def to_body(self, request_id: str | None) -> dict[str, Any]:
        err: dict[str, Any] = {
            "message": self.message,
            "type": self.error_type,
            "code": self.code,
        }
        if request_id:
            err["request_id"] = request_id
        err.update(self.extra)
        return {"error": err}


# --- 4xx ---------------------------------------------------------------------
class InvalidRequestError(APIError):
    status_code = 400
    error_type = "invalid_request_error"
    code = "invalid_request"


class AuthenticationError(APIError):
    status_code = 401
    error_type = "authentication_error"
    code = "invalid_api_key"


class PermissionDeniedError(APIError):
    status_code = 403
    error_type = "permission_error"
    code = "permission_denied"


class NotFoundError(APIError):
    status_code = 404
    error_type = "not_found_error"
    code = "not_found"


class ConflictError(APIError):
    status_code = 409
    error_type = "conflict_error"
    code = "conflict"


class RequestTimeoutError(APIError):
    status_code = 408
    error_type = "timeout_error"
    code = "request_timeout"


class QuotaExceededError(APIError):
    status_code = 402
    error_type = "insufficient_quota"
    code = "insufficient_quota"


class TokenQuotaExceededError(APIError):
    """Longer-window token quota (monthly/daily) exhausted. Distinct from the 402
    credit/quota-balance error and from the sliding-window rate limiter: this is a
    429 telling the caller to retry in the next quota period (§54)."""

    status_code = 429
    error_type = "quota_exceeded"
    code = "token_quota_exceeded"


class RateLimitError(APIError):
    status_code = 429
    error_type = "rate_limit_error"
    code = "rate_limit_exceeded"


class ChatQuotaExceededError(APIError):
    """The first-party chat product's monthly message allowance (``monthly_chat_messages``)
    is exhausted for the current billing period. A 429 distinct from the rate limiter and
    the token quota so the chat UI can show a plan-specific "monthly message limit" prompt."""

    status_code = 429
    error_type = "quota_exceeded"
    code = "chat_message_quota_exceeded"


# --- 5xx ---------------------------------------------------------------------
class InternalError(APIError):
    status_code = 500
    error_type = "internal_error"
    code = "internal_error"


class ProviderError(APIError):
    status_code = 502
    error_type = "provider_error"
    code = "upstream_error"


class ServiceUnavailableError(APIError):
    status_code = 503
    error_type = "service_unavailable"
    code = "service_unavailable"


class ProviderTimeoutError(APIError):
    status_code = 504
    error_type = "provider_error"
    code = "upstream_timeout"


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def install_exception_handlers(app) -> None:
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)

    @app.exception_handler(APIError)
    async def _api_error(request: Request, exc: APIError):  # noqa: ANN202
        rid = _request_id(request)
        if exc.status_code >= 500:
            logger.error(
                "api_error",
                extra={"request_id": rid, "code": exc.code, "error_message": exc.message},
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_body(rid),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):  # noqa: ANN202
        rid = _request_id(request)
        # Compact, safe summary — never echo internal locations verbatim beyond field path.
        details = []
        for e in exc.errors():
            loc = ".".join(str(p) for p in e.get("loc", []) if p != "body")
            details.append(f"{loc}: {e.get('msg')}" if loc else str(e.get("msg")))
        message = "; ".join(details) or "Invalid request."
        body = InvalidRequestError(message).to_body(rid)
        return JSONResponse(status_code=400, content=body)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):  # noqa: ANN202
        rid = _request_id(request)
        mapping = {
            400: ("invalid_request_error", "invalid_request"),
            401: ("authentication_error", "invalid_api_key"),
            403: ("permission_error", "permission_denied"),
            404: ("not_found_error", "not_found"),
            405: ("invalid_request_error", "method_not_allowed"),
            429: ("rate_limit_error", "rate_limit_exceeded"),
        }
        etype, code = mapping.get(exc.status_code, ("api_error", "error"))
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        body = {"error": {"message": detail, "type": etype, "code": code}}
        if rid:
            body["error"]["request_id"] = rid
        return JSONResponse(status_code=exc.status_code, content=body, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # noqa: ANN202
        rid = _request_id(request)
        logger.exception("unhandled_exception", extra={"request_id": rid})
        body = InternalError("An unexpected error occurred.").to_body(rid)
        return JSONResponse(status_code=500, content=body)
