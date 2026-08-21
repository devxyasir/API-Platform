"""Persist request logs and usage records (the analytics source of truth)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging_config import get_logger
from app.models.request_log import RequestLog
from app.models.usage import UsageRecord
from app.utils.redaction import redact_secrets

logger = get_logger("app.request")


async def persist_request(session: AsyncSession, log: RequestLog, *,
                          request_content: str | None = None,
                          response_content: str | None = None,
                          cost_usd: float = 0.0,
                          organization_id: str | None = None,
                          credits_used: int = 0,
                          input_price_snapshot: float = 0.0,
                          output_price_snapshot: float = 0.0) -> None:
    """Save a completed request + its usage record.

    Request/response bodies are stored ONLY when ``LOG_REQUEST_CONTENT`` is enabled,
    and are always run through secret redaction first. The usage record carries the
    billing fields (org, credits, and the price snapshot used to compute ``cost_usd``)
    so historical billing never re-prices with today's rates (§53).
    """
    if settings.log_request_content:
        log.request_content = redact_secrets(request_content)
        log.response_content = redact_secrets(response_content)

    session.add(log)

    usage = UsageRecord(
        request_id=log.id,
        user_id=log.user_id,
        organization_id=organization_id,
        project_id=log.project_id,
        api_key_id=log.api_key_id,
        model=log.model,
        prompt_tokens=log.prompt_tokens,
        completion_tokens=log.completion_tokens,
        total_tokens=log.total_tokens,
        cost_usd=cost_usd,
        credits_used=credits_used,
        status=str(log.status) if log.status else "success",
        input_price_snapshot=input_price_snapshot,
        output_price_snapshot=output_price_snapshot,
        ts=log.started_at,
    )
    session.add(usage)
    await session.flush()

    # Structured log line (never contains secrets).
    logger.info(
        "request_completed",
        extra={
            "request_id": log.id,
            "user_id": log.user_id,
            "project_id": log.project_id,
            "endpoint": log.endpoint,
            "model": log.model,
            "status": log.status,
            "status_code": log.status_code,
            "latency_ms": round(log.latency_ms, 2),
            "total_tokens": log.total_tokens,
            "stream": log.stream,
        },
    )
