"""Cryptographic primitives: password hashing, JWTs, and API-key hashing.

- Passwords: bcrypt (with a SHA-256 pre-hash to sidestep bcrypt's 72-byte limit).
- API keys: SHA-256 over ``pepper + raw`` — fast, constant-time compared. Raw keys
  are high-entropy (256 bits) so a slow hash isn't required, and constant-time
  comparison prevents timing attacks.
- JWTs: HS256 via PyJWT for dashboard sessions.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import timedelta
from typing import Any

import bcrypt
import jwt

from app.config import settings
from app.utils.time import utcnow


# --- Passwords ---------------------------------------------------------------
def _prepare_password(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare_password(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare_password(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --- API keys ----------------------------------------------------------------
def hash_api_key(raw_key: str) -> str:
    mac = hmac.new(settings.api_key_pepper.encode("utf-8"), raw_key.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw_key), stored_hash)


# --- JWTs --------------------------------------------------------------------
def create_access_token(subject: str, *, extra: dict[str, Any] | None = None,
                        expires_minutes: int | None = None) -> str:
    now = utcnow()
    exp = now + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Decode & verify a JWT. Raises ``jwt.PyJWTError`` on failure."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
