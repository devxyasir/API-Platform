"""Provider registry, shared HTTP client, and circuit breaker."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.logging_config import get_logger
from app.providers.base import LLMProvider
from app.providers.errors import CircuitOpenError
from app.providers.openai_provider import OpenAIProvider
from app.providers.notrack_provider import NotrackProvider

logger = get_logger("app.providers.registry")


@dataclass
class CircuitBreaker:
    """Trips open after ``threshold`` consecutive failures; recovers after ``cooldown``."""

    threshold: int = 5
    cooldown: float = 30.0
    failures: int = 0
    opened_at: float | None = field(default=None)

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if time.monotonic() - self.opened_at >= self.cooldown:
            return "half_open"
        return "open"

    def check(self) -> None:
        if self.state == "open":
            raise CircuitOpenError()

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold and self.opened_at is None:
            self.opened_at = time.monotonic()
            logger.error("circuit_opened", extra={"failures": self.failures})


class ProviderRegistry:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._providers: dict[str, LLMProvider] = {}
        self._breakers: dict[str, CircuitBreaker] = {}

    def startup(self) -> None:
        limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
        timeout = httpx.Timeout(settings.upstream_timeout, connect=10.0)
        self._client = httpx.AsyncClient(limits=limits, timeout=timeout)
        self._providers["openai"] = OpenAIProvider(self._client)
        self._breakers["openai"] = CircuitBreaker()
        self._providers["notrack"] = NotrackProvider(self._client)
        self._breakers["notrack"] = CircuitBreaker()
        logger.info("provider_registry_started", extra={"providers": list(self._providers)})

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def get(self, name: str = "openai") -> LLMProvider:
        provider = self._providers.get(name)
        if provider is None:
            # Fall back to the default provider for unknown names.
            provider = self._providers.get("openai")
        if provider is None:
            raise RuntimeError("Provider registry not initialized")
        return provider

    @property
    def provider_names(self) -> list[str]:
        return sorted(self._providers)

    def breaker(self, name: str = "openai") -> CircuitBreaker:
        return self._breakers.setdefault(name, CircuitBreaker())

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Provider registry not initialized")
        return self._client


# Singleton used across the app.
registry = ProviderRegistry()
