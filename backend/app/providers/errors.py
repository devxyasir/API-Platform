"""Internal provider-layer exceptions (translated to API errors by the caller)."""
from __future__ import annotations


class UpstreamError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None,
                 code: str | None = None, retryable: bool = False,
                 provider_request_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.retryable = retryable
        self.provider_request_id = provider_request_id


class UpstreamTimeout(UpstreamError):
    def __init__(self, message: str = "Upstream provider timed out") -> None:
        super().__init__(message, code="upstream_timeout", retryable=True)


class UpstreamUnavailable(UpstreamError):
    def __init__(self, message: str = "Upstream provider unavailable") -> None:
        super().__init__(message, code="upstream_unavailable", retryable=True)


class CircuitOpenError(UpstreamError):
    def __init__(self, message: str = "Upstream circuit breaker is open") -> None:
        super().__init__(message, code="circuit_open", retryable=False)
