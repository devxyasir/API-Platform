"""Pure-ASGI AES-GCM payload envelope for the dashboard/console APIs.

When a dashboard client sends ``X-Enc: 1``:
- a request body (POST/PATCH/PUT) arrives as ciphertext and is decrypted to JSON
  before routing;
- the response body is buffered and encrypted, so the Network tab shows an opaque
  ``application/octet-stream`` blob with an ``X-Enc: 1`` marker.

Scope: only ``/admin`` and ``/account`` paths — the OpenAI/Anthropic ``/v1`` surface
and health/docs are always left as plain JSON so programmatic SDK clients keep working.
Non-opted-in requests pass through untouched, so the whole layer degrades gracefully.

This is obfuscation on top of TLS + server-side authz (see app/auth/envelope.py); it
is not the access boundary. RBAC still runs on the decrypted request.
"""
from __future__ import annotations

import json

import jwt

from app.auth import envelope
from app.auth.security import decode_token
from app.config import settings

_ENC_PREFIXES = ("/admin", "/account")
_ENC_HEADER = b"x-enc"


def _wants_envelope(scope) -> bool:
    if not settings.payload_encryption_enabled:
        return False
    path = scope.get("path", "")
    if not path.startswith(_ENC_PREFIXES):
        return False
    for k, v in scope.get("headers", []):
        if k == _ENC_HEADER and v == b"1":
            return True
    return False


def _bearer_subject(scope) -> str | None:
    for k, v in scope.get("headers", []):
        if k == b"authorization":
            val = v.decode("latin-1")
            if val.lower().startswith("bearer "):
                try:
                    return decode_token(val[7:].strip()).get("sub")
                except jwt.PyJWTError:
                    return None
    return None


class EnvelopeMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not _wants_envelope(scope):
            await self.app(scope, receive, send)
            return

        subject = _bearer_subject(scope)
        if not subject:
            # Opted into encryption but no resolvable session → refuse rather than leak.
            await self._send_plain(send, 401, {
                "error": {"message": "Authentication required.", "type": "authentication_error",
                          "code": "not_authenticated"}
            })
            return

        # --- decrypt request body (if any) ---
        body = await self._read_body(receive)
        replay = {"sent": False}
        if body:
            try:
                decrypted = envelope.decrypt(subject, body.decode("ascii"))
            except Exception:
                await self._send_plain(send, 400, {
                    "error": {"message": "Malformed encrypted payload.",
                              "type": "invalid_request_error", "code": "bad_envelope"}
                })
                return
            body = decrypted

        async def receive_replay():
            if not replay["sent"]:
                replay["sent"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        # --- encrypt response body ---
        start_msg: dict = {}
        chunks: list[bytes] = []

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                start_msg.update(message)
                return  # defer until we've buffered + encrypted the full body
            if message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
                if message.get("more_body"):
                    return
                await self._flush_encrypted(send, subject, start_msg, b"".join(chunks))
                return
            await send(message)

        await self.app(scope, receive_replay, send_wrapper)

    async def _read_body(self, receive) -> bytes:
        parts: list[bytes] = []
        while True:
            msg = await receive()
            if msg["type"] != "http.request":
                break
            parts.append(msg.get("body", b""))
            if not msg.get("more_body"):
                break
        return b"".join(parts)

    async def _flush_encrypted(self, send, subject: str, start_msg: dict, body: bytes) -> None:
        token = envelope.encrypt(subject, body).encode("ascii")
        headers = [
            (k, v) for k, v in start_msg.get("headers", [])
            if k.lower() not in (b"content-length", b"content-type", b"content-encoding")
        ]
        headers.append((b"content-type", b"application/octet-stream"))
        headers.append((b"content-length", str(len(token)).encode("ascii")))
        headers.append((_ENC_HEADER, b"1"))
        await send({"type": "http.response.start",
                    "status": start_msg.get("status", 200), "headers": headers})
        await send({"type": "http.response.body", "body": token, "more_body": False})

    async def _send_plain(self, send, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(data)).encode("ascii")),
        ]})
        await send({"type": "http.response.body", "body": data, "more_body": False})
