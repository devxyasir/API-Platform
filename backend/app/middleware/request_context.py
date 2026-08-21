"""Pure-ASGI request context middleware.

Implemented at the ASGI level (not ``BaseHTTPMiddleware``) so it never buffers
streaming/SSE responses. Responsibilities:
- assign a ``request_id`` and expose it via ``request.state``
- inject ``X-Request-Id`` + security headers on the response
- strip the real stack fingerprint and emit decoy Server/X-Powered-By headers (§ obfuscation)
- record a privacy-safe structured access log (hashed IP, no secrets)
"""
from __future__ import annotations

import os
import time

from app.config import settings
from app.logging_config import get_logger
from app.utils.ids import request_id as gen_request_id
from app.utils.redaction import hash_ip

logger = get_logger("app.access")

_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"x-xss-protection", b"0"),
]

# Response headers that would reveal the real stack (FastAPI/Starlette/uvicorn/Python).
# NOTE: uvicorn appends its own `server` header at the transport layer, AFTER this ASGI
# app runs, so it cannot be removed from here — run the app with `server_header=False`
# (see backend/run.py) so the decoy below is the only Server header the client sees.
_STRIP = {b"server", b"x-powered-by"}


def _decoy_headers(content_type: bytes) -> list[tuple[bytes, bytes]]:
    """Cloudflare/PHP-style decoys so the response fingerprint misleads scanners."""
    out = [
        (b"server", settings.decoy_server.encode("latin-1")),
        (b"x-powered-by", settings.decoy_powered_by.encode("latin-1")),
        (b"cf-ray", f"{os.urandom(8).hex()}-SIN".encode("latin-1")),
        (b"cf-cache-status", b"DYNAMIC"),
    ]
    # SSE sets its own no-cache/no-transform; only stamp no-store on ordinary responses.
    if b"text/event-stream" not in content_type:
        out.append((b"cache-control", b"no-store"))
    return out


class RequestContextMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = gen_request_id()
        state = scope.setdefault("state", {})
        state["request_id"] = rid

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        xff = headers.get("x-forwarded-for")
        client_ip = xff.split(",")[0].strip() if xff else (scope.get("client") or ("", 0))[0]
        state["ip_hash"] = hash_ip(client_ip)
        state["user_agent"] = headers.get("user-agent", "")[:400]

        start = time.perf_counter()
        status_holder = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                raw = [(k, v) for k, v in message.get("headers", []) if k.lower() not in _STRIP]
                content_type = b""
                for k, v in raw:
                    if k.lower() == b"content-type":
                        content_type = v
                        break
                raw.append((b"x-request-id", rid.encode()))
                raw.extend(_SECURITY_HEADERS)
                if settings.decoy_headers_enabled:
                    # Drop any caller-set cache-control if we're about to stamp our own.
                    decoys = _decoy_headers(content_type)
                    if any(k == b"cache-control" for k, _ in decoys):
                        raw = [(k, v) for k, v in raw if k.lower() != b"cache-control"]
                    raw.extend(decoys)
                message["headers"] = raw
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = (time.perf_counter() - start) * 1000
            logger.info(
                "http_access",
                extra={
                    "request_id": rid,
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_holder["code"],
                    "latency_ms": round(duration, 2),
                    "ip_hash": state["ip_hash"],
                },
            )
