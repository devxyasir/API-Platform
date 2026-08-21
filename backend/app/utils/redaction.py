"""Privacy helpers: hash IPs and redact secrets before logging/storage."""
from __future__ import annotations

import hashlib
import re

from app.config import settings

# Header names that must never be logged/stored.
SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "proxy-authorization",
    "openai-api-key",
    "anthropic-api-key",
}

_SECRET_PATTERNS = [
    re.compile(r"sk_(live|test)_[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
]


def hash_ip(ip: str | None) -> str | None:
    """Return a privacy-safe, salted hash of a client IP (never store raw IPs)."""
    if not ip:
        return None
    digest = hashlib.sha256(f"{settings.ip_hash_salt}:{ip}".encode()).hexdigest()
    return f"ip_{digest[:24]}"


def redact_secrets(text: str | None) -> str | None:
    if not text:
        return text
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def scrub_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        k: ("[REDACTED]" if k.lower() in SENSITIVE_HEADERS else v)
        for k, v in headers.items()
    }
