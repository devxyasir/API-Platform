"""AES-256-GCM payload envelope for the dashboard/console APIs.

This obfuscates dashboard request/response bodies so the browser Network tab shows
opaque ciphertext instead of JSON. It is defense-in-depth on top of TLS and
server-side authorization, **not** a replacement for either: the per-user key is
handed to the browser at login, so a determined user with the running app can still
decrypt their own traffic. The real access boundary is the server's RBAC — an
encrypted request from a non-admin still hits ``require_permission`` and gets 403.

Wire format (base64, url-safe):  nonce(12 bytes) || ciphertext || tag(16 bytes)
Key derivation:  HKDF-free HMAC-SHA256(jwt_secret, "gw-envelope-v1:" + subject)[:32]
The key is deterministic per subject so the server can recompute it from the bearer
token on every request without any server-side session store.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_NONCE_BYTES = 12
_INFO = b"gw-envelope-v1:"


def derive_key(subject: str) -> bytes:
    """Deterministic 32-byte AES key for a token subject (user id)."""
    mac = hmac.new(settings.jwt_secret.encode("utf-8"), _INFO + subject.encode("utf-8"), hashlib.sha256)
    return mac.digest()  # 32 bytes


def client_key_b64(subject: str) -> str:
    """The key handed to the browser at login (base64, for WebCrypto importKey)."""
    return base64.b64encode(derive_key(subject)).decode("ascii")


def encrypt(subject: str, plaintext: bytes) -> str:
    key = derive_key(subject)
    nonce = _random_nonce()
    ct = AESGCM(key).encrypt(nonce, plaintext, None)
    return base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt(subject: str, token: str) -> bytes:
    key = derive_key(subject)
    raw = base64.urlsafe_b64decode(_pad(token))
    if len(raw) <= _NONCE_BYTES:
        raise ValueError("ciphertext too short")
    nonce, ct = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    return AESGCM(key).decrypt(nonce, ct, None)


def _random_nonce() -> bytes:
    # os.urandom is fine here; AES-GCM nonces only need to be unique per key, not secret.
    import os

    return os.urandom(_NONCE_BYTES)


def _pad(b64: str) -> bytes:
    s = b64.strip()
    return (s + "=" * (-len(s) % 4)).encode("ascii")
