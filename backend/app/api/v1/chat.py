"""OpenAI-compatible Chat Completions endpoint."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import AuthContext, get_api_context
from app.errors import APIError
from app.logging_config import get_logger
from app.schemas.openai import ChatCompletionRequest
from app.services import chat_service
from app.utils.time import to_epoch

logger = get_logger("app.api.chat")

router = APIRouter(tags=["Chat"])

SSE_HEADERS = {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
}


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _envelope(chat_id: str, created: int, model: str, *, choices: list[dict],
              usage: dict | None = None, system_fingerprint: str | None = None) -> dict:
    """Build one OpenAI ``chat.completion.chunk`` envelope.

    ``choices`` is whatever should appear on the wire — either upstream choices
    forwarded verbatim (preserving tool_calls / function_call / refusal / logprobs
    and n>1) or a single reconstructed delta. ``id`` and ``model`` always carry the
    gateway's public identifiers so the stream is self-consistent across models.
    """
    payload: dict = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": choices,
    }
    if system_fingerprint is not None:
        payload["system_fingerprint"] = system_fingerprint
    if usage is not None:
        payload["usage"] = usage
    return payload


@router.post(
    "/chat/completions",
    summary="Create chat completion",
    response_model=None,
    responses={
        200: {"description": "Chat completion (or an SSE stream when stream=true)."},
        401: {"description": "Authentication error"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def create_chat_completion(
    body: ChatCompletionRequest,
    request: Request,
    ctx: AuthContext = Depends(get_api_context),
    session: AsyncSession = Depends(get_session),
):
    rid = getattr(request.state, "request_id", None) or ""
    include_usage = bool(body.stream_options and body.stream_options.include_usage)

    prep = await chat_service.prepare(
        session, ctx,
        api_format="openai",
        endpoint="/v1/chat/completions",
        payload=body.to_upstream_payload(),
        model_field=body.model,
        stream=body.stream,
        request_id=rid,
        ip_hash=getattr(request.state, "ip_hash", None),
        user_agent=getattr(request.state, "user_agent", None),
        request_text=_summarize_prompt(body),
    )

    if not body.stream:
        result = await chat_service.complete(session, ctx, prep)
        response = {
            "id": f"chatcmpl-{rid}",
            "object": "chat.completion",
            "created": result.created,
            "model": result.model,
            "choices": result.choices,
            "usage": result.usage.as_dict() if result.usage else None,
        }
        return JSONResponse(content=response)

    chat_id = f"chatcmpl-{rid}"
    created = to_epoch(prep.started_at)
    model = prep.model.public_id

    async def event_stream() -> AsyncIterator[str]:
        role_sent = False
        try:
            async for chunk in chat_service.stream(ctx, prep):
                sfp = (chunk.raw or {}).get("system_fingerprint")
                if chunk.choices is not None:
                    # Verbatim pass-through: keeps tool_calls, function_call, refusal,
                    # logprobs and n>1 choices intact for every model. Only id + model
                    # are rewritten to the gateway's public identifiers.
                    if chunk.choices:
                        yield _sse(_envelope(chat_id, created, model,
                                             choices=chunk.choices, system_fingerprint=sfp))
                else:
                    # Fallback for providers that surface only role/content/finish.
                    delta: dict = {}
                    if chunk.role and not role_sent:
                        delta["role"] = chunk.role
                        role_sent = True
                    if chunk.delta:
                        if not role_sent:
                            delta["role"] = "assistant"
                            role_sent = True
                        delta["content"] = chunk.delta
                    if delta or chunk.finish_reason:
                        yield _sse(_envelope(
                            chat_id, created, model,
                            choices=[{"index": 0, "delta": delta,
                                      "finish_reason": chunk.finish_reason}],
                        ))
                if chunk.usage and include_usage:
                    yield _sse(_envelope(chat_id, created, model, choices=[],
                                         usage=chunk.usage.as_dict()))
            yield "data: [DONE]\n\n"
        except APIError as exc:
            # Surface a terminal error event, then close the stream.
            yield _sse(exc.to_body(rid))
        except Exception:  # pragma: no cover - defensive
            logger.exception("stream_unexpected", extra={"request_id": rid})
            yield 'data: {"error":{"message":"stream failed","type":"internal_error"}}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)


def _summarize_prompt(body: ChatCompletionRequest) -> str:
    """A compact textual view of the prompt (only stored if content logging is on)."""
    try:
        return json.dumps([m.model_dump(exclude_none=True) for m in body.messages])[:20000]
    except Exception:
        return ""
