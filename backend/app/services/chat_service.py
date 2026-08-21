"""Chat orchestration shared by the OpenAI (/v1/chat/completions) and Anthropic
(/v1/messages) endpoints.

Flow: resolve model → rate-limit check → concurrency guard → circuit breaker →
provider call → token accounting → request logging. Both public formats funnel
through the same provider abstraction.
"""
from __future__ import annotations

import math
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionLocal
from app.dependencies import AuthContext
from app.errors import (
    APIError,
    InvalidRequestError,
    NotFoundError,
    PermissionDeniedError,
    ProviderError,
    ProviderTimeoutError,
    QuotaExceededError,
    RateLimitError,
    ServiceUnavailableError,
    TokenQuotaExceededError,
)
from app.logging_config import get_logger
from app.models.enums import RequestStatus, TokenCountSource
from app.models.model import Model
from app.models.rate_limit import RateLimitEvent
from app.models.request_log import RequestLog
from app.providers import ChatRequest, ChatResult, StreamChunk, Usage, registry
from app.providers.errors import CircuitOpenError, UpstreamError, UpstreamTimeout, UpstreamUnavailable
from app.rate_limit import concurrency, limiter
from app.services import (
    credit_service,
    model_service,
    plan_service,
    pricing_service,
    quota_service,
    request_logger,
    tokenizer,
)
from app.utils.time import utcnow

logger = get_logger("app.services.chat")


@dataclass
class Prepared:
    chat_request: ChatRequest
    model: Model
    endpoint: str
    api_format: str
    request_id: str
    prompt_tokens_est: int
    started_at: datetime
    stream: bool
    ip_hash: str | None = None
    user_agent: str | None = None
    request_text: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def _translate_upstream(exc: Exception) -> APIError:
    if isinstance(exc, CircuitOpenError):
        return ServiceUnavailableError(
            "Upstream provider temporarily unavailable.", code="upstream_unavailable"
        )
    if isinstance(exc, UpstreamTimeout):
        return ProviderTimeoutError("Upstream provider timed out.", code="upstream_timeout")
    if isinstance(exc, UpstreamUnavailable):
        return ServiceUnavailableError(
            "Upstream provider unavailable.", code="upstream_unavailable"
        )
    if isinstance(exc, UpstreamError):
        status = exc.status_code or 502
        if status in (400, 422):
            return InvalidRequestError(exc.message, code=exc.code or "invalid_request")
        if status == 404:
            return NotFoundError(exc.message, code=exc.code or "not_found")
        if status in (401, 403):
            # Never leak that OUR upstream credential failed as a client auth error.
            return ProviderError("Upstream authorization failed.", code="upstream_auth_error")
        if status == 429:
            return ServiceUnavailableError(
                "Upstream provider is rate limiting requests.", code="upstream_rate_limited"
            )
        return ProviderError(exc.message or "Upstream provider error.", code="upstream_error")
    return ProviderError("Unexpected upstream error.", code="upstream_error")


async def prepare(
    session: AsyncSession,
    ctx: AuthContext,
    *,
    api_format: str,
    endpoint: str,
    payload: dict[str, Any],
    model_field: str,
    stream: bool,
    request_id: str,
    ip_hash: str | None,
    user_agent: str | None,
    request_text: str | None,
) -> Prepared:
    ctx.require_scope("chat:write")

    model = await model_service.resolve_model(session, model_field)
    if model is None:
        raise NotFoundError(f"The model '{model_field}' does not exist.", code="model_not_found")
    if not model.enabled:
        raise PermissionDeniedError(f"The model '{model_field}' is disabled.", code="model_disabled")
    if stream and not model.supports_streaming:
        raise InvalidRequestError(
            f"The model '{model_field}' does not support streaming.", code="streaming_unsupported"
        )
    if ctx.project and ctx.project.allowed_models and model.public_id not in ctx.project.allowed_models:
        raise PermissionDeniedError(
            f"This project is not allowed to use the model '{model_field}'.", code="model_forbidden"
        )

    # --- plan model access (§55): the subscribed plan may restrict the model catalogue.
    if ctx.plan_id and not await plan_service.model_allowed(session, ctx.plan_id, model.public_id):
        raise PermissionDeniedError(
            f"Your plan does not include access to the model '{model_field}'.",
            code="model_not_available",
        )

    prompt_est = tokenizer.count_messages(payload.get("messages", []), model.upstream_model)

    # --- token quota pre-flight (§54): a REAL gate on the plan's monthly/daily token
    # quota computed from append-only usage. The rate-limiter's tpm/tpd are soft/peek-only
    # (a single over-budget request still runs once), so quota cannot rely on them.
    if ctx.organization_id:
        try:
            await quota_service.check_tokens(
                session, organization_id=ctx.organization_id, plan_slug=ctx.plan_slug,
                user_id=ctx.user.id, incoming_tokens=prompt_est,
            )
        except TokenQuotaExceededError as exc:
            await _persist_quota_exceeded(
                ctx, model=model, endpoint=endpoint, api_format=api_format,
                request_id=request_id, stream=stream, ip_hash=ip_hash, user_agent=user_agent,
                err=exc,
            )
            raise

    # --- credit balance gate (optional; off for personal use). Credits are a SEPARATE
    # unit from tokens/money (§58); this only refuses when the org is out of credits.
    if settings.credits_enforced and ctx.organization_id:
        if not await credit_service.has_credits(session, ctx.organization_id, 1):
            raise QuotaExceededError(
                "Insufficient credit balance for this request.", code="insufficient_credits"
            )

    # --- rate limiting (per API key, using resolved plan/user/project/key limits) ---
    scope_id = ctx.api_key.id
    decision = await limiter.check_request(scope_id, ctx.limits)
    if not decision.allowed:
        # Persist the throttling event + request log in a FRESH, committed session:
        # the RateLimitError below propagates out of the route, and get_session
        # rolls the request-scoped session back on exception.
        await _persist_rate_limited(
            ctx, model=model, endpoint=endpoint, api_format=api_format,
            request_id=request_id, stream=stream, ip_hash=ip_hash, user_agent=user_agent,
            limit_type=decision.limit_type or "unknown", limit_value=decision.limit_value,
        )
        raise RateLimitError("Rate limit exceeded.", headers=decision.headers)

    chat_request = ChatRequest(
        model_public=model.public_id,
        model_upstream=model.upstream_model,
        payload=payload,
        stream=stream,
        meta={"request_id": request_id},
    )

    if stream:
        # Release the request session before streaming begins. A streaming response
        # finalizes accounting on its OWN session (see _finalize_stream), and holding
        # this session's transaction open for the whole stream deadlocks SQLite —
        # which permits only a single writer — against that finalize write.
        await session.commit()

    return Prepared(
        chat_request=chat_request,
        model=model,
        endpoint=endpoint,
        api_format=api_format,
        request_id=request_id,
        prompt_tokens_est=prompt_est,
        started_at=utcnow(),
        stream=stream,
        ip_hash=ip_hash,
        user_agent=user_agent,
        request_text=request_text,
    )


def _base_log(ctx: AuthContext, prep: Prepared) -> RequestLog:
    return RequestLog(
        id=prep.request_id,
        user_id=ctx.user.id,
        project_id=ctx.project.id if ctx.project else None,
        api_key_id=ctx.api_key.id,
        model=prep.model.public_id,
        upstream_model=prep.model.upstream_model,
        endpoint=prep.endpoint,
        api_format=prep.api_format,
        provider=prep.model.provider,
        stream=prep.stream,
        started_at=prep.started_at,
        ip_hash=prep.ip_hash,
        user_agent=prep.user_agent,
    )


# --- non-streaming -----------------------------------------------------------
async def complete(session: AsyncSession, ctx: AuthContext, prep: Prepared) -> ChatResult:
    provider = registry.get(prep.model.provider)
    breaker = registry.breaker(prep.model.provider)
    log = _base_log(ctx, prep)

    try:
        breaker.check()
        async with concurrency.guard(
            key_scope=ctx.api_key.id, key_limit=ctx.limits.concurrency,
            user_scope=ctx.user.id, user_limit=ctx.limits.concurrency,
            global_limit=None,
        ):
            result = await provider.chat(prep.chat_request)
        breaker.record_success()
    except RateLimitError:
        raise
    except Exception as exc:
        if isinstance(exc, (UpstreamError, CircuitOpenError)):
            breaker.record_failure()
        api_err = _translate_upstream(exc) if not isinstance(exc, APIError) else exc
        await _persist_error(ctx, prep, api_err)
        raise api_err

    await _finalize_success(session, ctx, prep, log, result)
    return result


# --- streaming ---------------------------------------------------------------
async def stream(ctx: AuthContext, prep: Prepared) -> AsyncIterator[StreamChunk]:
    """Yield normalized chunks; persist accounting when the stream ends.

    A FRESH DB session is used for the final write because the request-scoped
    session may already be torn down by the time streaming completes.
    """
    provider = registry.get(prep.model.provider)
    breaker = registry.breaker(prep.model.provider)

    collected: list[str] = []
    usage_reported = None
    finish_reason: str | None = None
    ttft_ms: float | None = None
    error: APIError | None = None

    try:
        breaker.check()
    except CircuitOpenError as exc:
        breaker.record_failure()
        raise _translate_upstream(exc)

    try:
        async with concurrency.guard(
            key_scope=ctx.api_key.id, key_limit=ctx.limits.concurrency,
            user_scope=ctx.user.id, user_limit=ctx.limits.concurrency,
            global_limit=None,
        ):
            async for chunk in provider.stream_chat(prep.chat_request):
                if ttft_ms is None and chunk.delta:
                    ttft_ms = (utcnow() - prep.started_at).total_seconds() * 1000
                if chunk.delta:
                    collected.append(chunk.delta)
                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason
                if chunk.usage:
                    usage_reported = chunk.usage
                yield chunk
        breaker.record_success()
    except Exception as exc:  # includes upstream + client disconnect (CancelledError)
        if isinstance(exc, (UpstreamError, CircuitOpenError)):
            breaker.record_failure()
        error = _translate_upstream(exc) if not isinstance(exc, APIError) else exc
        # Re-raise so the router can end the SSE stream; accounting still runs in finally.
        raise error
    finally:
        await _finalize_stream(
            ctx, prep, "".join(collected), usage_reported, finish_reason, ttft_ms, error
        )


# --- persistence helpers -----------------------------------------------------
async def _bill(
    session, ctx: AuthContext, prep: Prepared, pt: int, ctok: int, tt: int, *, success: bool
) -> tuple[float, int, float, float]:
    """Compute a completed request's billing fields against the price snapshot in effect
    now (§53) and, when credit enforcement is on for a successful request, consume credits
    via the ledger. Returns (cost_usd, credits_used, input_price_snapshot, output_price_snapshot).

    Credits are a SEPARATE unit from tokens/money (§58): credits_used is recorded on the
    usage row ONLY when it was actually consumed from the ledger, so the two never drift."""
    in_price, out_price = await pricing_service.snapshot_for(session, prep.model)
    cost_usd = pricing_service.compute_cost(in_price, out_price, pt, ctok)
    credits_used = 0
    if success and settings.credits_enforced and ctx.organization_id and tt > 0:
        credits_used = math.ceil(tt / max(1, settings.credit_tokens_per_unit))
        if credits_used > 0:
            await credit_service.consume(
                session, ctx.organization_id, credits_used,
                reason=f"Usage for request {prep.request_id} ({prep.model.public_id})",
                user_id=ctx.user.id, reference_id=prep.request_id,
            )
    return cost_usd, credits_used, in_price, out_price


async def _finalize_success(session, ctx, prep, log, result: ChatResult) -> None:
    completed = utcnow()
    if result.usage:
        pt, ctok, tt = result.usage.prompt_tokens, result.usage.completion_tokens, result.usage.total_tokens
        source = TokenCountSource.PROVIDER_REPORTED
    else:
        pt, ctok, tt, source = tokenizer.estimate_usage(
            prep.chat_request.messages, result.text, prep.model.upstream_model
        )
    log.status = RequestStatus.SUCCESS
    log.status_code = 200
    log.completed_at = completed
    log.latency_ms = (completed - prep.started_at).total_seconds() * 1000
    log.prompt_tokens, log.completion_tokens, log.total_tokens = pt, ctok, tt
    log.token_count_source = source
    log.provider_request_id = result.provider_request_id

    # Ensure the returned result always carries usage (estimated if upstream omitted it).
    if result.usage is None:
        result.usage = Usage(prompt_tokens=pt, completion_tokens=ctok, total_tokens=tt, source=source)

    await limiter.add_tokens(ctx.api_key.id, tt, ctx.limits)
    cost_usd, credits_used, in_price, out_price = await _bill(
        session, ctx, prep, pt, ctok, tt, success=True
    )
    await request_logger.persist_request(
        session, log,
        request_content=prep.request_text,
        response_content=result.text,
        cost_usd=cost_usd,
        organization_id=ctx.organization_id,
        credits_used=credits_used,
        input_price_snapshot=in_price,
        output_price_snapshot=out_price,
    )


async def _finalize_stream(ctx, prep, text, usage, finish_reason, ttft_ms, error) -> None:
    completed = utcnow()
    if usage:
        pt, ctok, tt = usage.prompt_tokens, usage.completion_tokens, usage.total_tokens
        source = TokenCountSource.PROVIDER_REPORTED
    else:
        pt, ctok, tt, source = tokenizer.estimate_usage(
            prep.chat_request.messages, text, prep.model.upstream_model
        )
    async with SessionLocal() as session:
        log = _base_log(ctx, prep)
        log.completed_at = completed
        log.latency_ms = (completed - prep.started_at).total_seconds() * 1000
        log.ttft_ms = ttft_ms
        log.prompt_tokens, log.completion_tokens, log.total_tokens = pt, ctok, tt
        log.token_count_source = source
        if error is not None:
            log.status = RequestStatus.ERROR
            log.status_code = error.status_code
            log.error_type = error.error_type
            log.error_code = error.code
            log.error_message = error.message
        else:
            log.status = RequestStatus.SUCCESS
            log.status_code = 200
        try:
            await limiter.add_tokens(ctx.api_key.id, tt, ctx.limits)
            cost_usd, credits_used, in_price, out_price = await _bill(
                session, ctx, prep, pt, ctok, tt, success=error is None
            )
            await request_logger.persist_request(
                session, log, request_content=prep.request_text, response_content=text,
                cost_usd=cost_usd,
                organization_id=ctx.organization_id,
                credits_used=credits_used,
                input_price_snapshot=in_price,
                output_price_snapshot=out_price,
            )
            await session.commit()
        except Exception:  # pragma: no cover
            await session.rollback()
            logger.exception("stream_finalize_failed", extra={"request_id": prep.request_id})


async def _persist_error(ctx, prep, err: APIError) -> None:
    """Persist a failed request in a fresh, committed session.

    The request-scoped session is rolled back by ``get_session`` when the API
    error propagates out of the route, so error logs must be written independently.
    """
    completed = utcnow()
    async with SessionLocal() as session:
        log = _base_log(ctx, prep)
        log.status = RequestStatus.TIMEOUT if err.status_code == 504 else RequestStatus.ERROR
        log.status_code = err.status_code
        log.completed_at = completed
        log.latency_ms = (completed - prep.started_at).total_seconds() * 1000
        log.error_type = err.error_type
        log.error_code = err.code
        log.error_message = err.message
        log.prompt_tokens = prep.prompt_tokens_est
        log.total_tokens = prep.prompt_tokens_est
        log.token_count_source = TokenCountSource.TOKENIZER_ESTIMATED
        try:
            await request_logger.persist_request(session, log, request_content=prep.request_text)
            await session.commit()
        except Exception:  # pragma: no cover
            await session.rollback()
            logger.exception("error_persist_failed", extra={"request_id": prep.request_id})


async def _persist_rate_limited(ctx, *, model, endpoint, api_format, request_id,
                                stream, ip_hash, user_agent, limit_type, limit_value) -> None:
    now = utcnow()
    async with SessionLocal() as session:
        session.add(
            RateLimitEvent(
                user_id=ctx.user.id,
                project_id=ctx.project.id if ctx.project else None,
                api_key_id=ctx.api_key.id,
                limit_type=limit_type,
                scope="api_key",
                limit_value=limit_value,
            )
        )
        log = RequestLog(
            id=request_id,
            user_id=ctx.user.id,
            project_id=ctx.project.id if ctx.project else None,
            api_key_id=ctx.api_key.id,
            model=model.public_id,
            upstream_model=model.upstream_model,
            endpoint=endpoint,
            api_format=api_format,
            provider=model.provider,
            stream=stream,
            started_at=now,
            completed_at=now,
            status=RequestStatus.RATE_LIMITED,
            status_code=429,
            error_type="rate_limit_error",
            error_code="rate_limit_exceeded",
            ip_hash=ip_hash,
            user_agent=user_agent,
        )
        try:
            await request_logger.persist_request(session, log)
            await session.commit()
        except Exception:  # pragma: no cover
            await session.rollback()
            logger.exception("rate_limit_persist_failed", extra={"request_id": request_id})


async def _persist_quota_exceeded(ctx, *, model, endpoint, api_format, request_id,
                                  stream, ip_hash, user_agent, err: APIError) -> None:
    """Persist a token-quota rejection (429) in a FRESH, committed session.

    The TokenQuotaExceededError propagates out of the route and ``get_session`` rolls the
    request-scoped session back, so the log must be written independently — mirrors
    :func:`_persist_rate_limited`. The usage row is stamped ``status=error`` (0 tokens), so
    it is excluded from quota/billing aggregates (which count only successful usage)."""
    now = utcnow()
    async with SessionLocal() as session:
        log = RequestLog(
            id=request_id,
            user_id=ctx.user.id,
            project_id=ctx.project.id if ctx.project else None,
            api_key_id=ctx.api_key.id,
            model=model.public_id,
            upstream_model=model.upstream_model,
            endpoint=endpoint,
            api_format=api_format,
            provider=model.provider,
            stream=stream,
            started_at=now,
            completed_at=now,
            status=RequestStatus.ERROR,
            status_code=err.status_code,
            error_type=err.error_type,
            error_code=err.code,
            error_message=err.message,
            ip_hash=ip_hash,
            user_agent=user_agent,
        )
        try:
            await request_logger.persist_request(session, log, organization_id=ctx.organization_id)
            await session.commit()
        except Exception:  # pragma: no cover
            await session.rollback()
            logger.exception("quota_persist_failed", extra={"request_id": request_id})
