"""Identifier helpers.

We use human-readable, time-sortable, prefixed IDs everywhere (e.g. ``req_01J...``)
rather than opaque UUIDs. This keeps IDs portable across SQLite/Postgres and makes
logs & the dashboard far easier to read.
"""
from __future__ import annotations

import os
import secrets
import time

# Crockford base32 alphabet (no I, L, O, U — avoids ambiguity).
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def ulid() -> str:
    """A ULID: 48-bit millisecond timestamp + 80 bits of randomness, base32 (26 chars).

    Lexicographically sortable by creation time.
    """
    ts = int(time.time() * 1000) & ((1 << 48) - 1)
    rand = secrets.randbits(80)
    return _encode(ts, 10) + _encode(rand, 16)


def new_id(prefix: str) -> str:
    """Return a prefixed identifier, e.g. ``new_id("req")`` -> ``req_01J...``."""
    return f"{prefix}_{ulid()}"


def request_id() -> str:
    return new_id("req")


def correlation_id() -> str:
    return new_id("corr")


def raw_api_key(live: bool = True) -> str:
    """Generate a fresh, high-entropy API key shown to the user exactly once.

    Format: ``sk_live_<43 url-safe chars>`` (256 bits of entropy).
    """
    env = "live" if live else "test"
    return f"sk_{env}_{secrets.token_urlsafe(32)}"


def key_prefix(raw: str) -> str:
    """The non-secret prefix we store & display (e.g. ``sk_live_a1b2c3d4``)."""
    parts = raw.split("_", 2)
    head = "_".join(parts[:2]) if len(parts) >= 2 else raw[:8]
    tail = parts[2][:8] if len(parts) == 3 else ""
    return f"{head}_{tail}" if tail else head
