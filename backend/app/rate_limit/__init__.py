"""Shared rate-limit singletons."""
from app.rate_limit.backends import RateBackend, build_backend
from app.rate_limit.concurrency import ConcurrencyGuard
from app.rate_limit.limiter import Decision, LimitSet, RateLimiter

backend: RateBackend = build_backend()
limiter = RateLimiter(backend)
concurrency = ConcurrencyGuard(backend)

__all__ = [
    "backend",
    "limiter",
    "concurrency",
    "RateLimiter",
    "ConcurrencyGuard",
    "LimitSet",
    "Decision",
]
