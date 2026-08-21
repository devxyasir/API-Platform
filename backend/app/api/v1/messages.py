"""Anthropic-compatible Messages endpoint (/v1/messages)."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.chat import SSE_HEADERS
from app.database import get_session
from app.dependencies import AuthContext, get_api_context
from app.errors import APIError
from app.logging_config import get_logger
from app.schemas.anthropic import (
    AnthropicMessagesRequest,
    anthropic_to_openai_payload,
    openai_finish_to_anthropic,
    result_to_anthropic,
)
from app.services import chat_service

logger = get_logger("app.api.messages")

router = APIRouter(tags=["Messages"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/messages", summary="Create a message (Anthropic-compatible)", response_model=None)
async def create_message(
    body: AnthropicMessagesRequest,
    request: Request,
    ctx: AuthContext = Depends(get_api_context),
    session: AsyncSession = Depends(get_session),
):
    rid = getattr(request.state, "request_id", None) or ""
    payload = anthropic_to_openai_payload(body)

    prep = await chat_service.prepare(
        session, ctx,
        api_format="anthropic",
        endpoint="/v1/messages",
        payload=payload,
        model_field=body.model,
        stream=body.stream,
        request_id=rid,
        ip_hash=getattr(request.state, "ip_hash", None),
        user_agent=getattr(request.state, "user_agent", None),
        request_text=json.dumps(payload.get("messages", []))[:20000],
    )

    if not body.stream:
        result = await chat_service.complete(session, ctx, prep)
        return JSONResponse(content=result_to_anthropic(result))

    msg_id = f"msg_{rid}"
    model = prep.model.public_id
    input_tokens_est = prep.prompt_tokens_est

    async def event_stream() -> AsyncIterator[str]:
        finish_reason = None
        output_tokens = 0
        usage = None
        try:
            yield _sse("message_start", {
                "type": "message_start",
                "message": {
                    "id": msg_id, "type": "message", "role": "assistant", "model": model,
                    "content": [], "stop_reason": None, "stop_sequence": None,
                    "usage": {"input_tokens": input_tokens_est, "output_tokens": 0},
                },
            })
            yield _sse("content_block_start", {
                "type": "content_block_start", "index": 0,
                "content_block": {"type": "text", "text": ""},
            })
            async for chunk in chat_service.stream(ctx, prep):
                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason
                if chunk.usage:
                    usage = chunk.usage
                if chunk.delta:
                    yield _sse("content_block_delta", {
                        "type": "content_block_delta", "index": 0,
                        "delta": {"type": "text_delta", "text": chunk.delta},
                    })
            yield _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
            output_tokens = usage.completion_tokens if usage else 0
            yield _sse("message_delta", {
                "type": "message_delta",
                "delta": {"stop_reason": openai_finish_to_anthropic(finish_reason), "stop_sequence": None},
                "usage": {"output_tokens": output_tokens},
            })
            yield _sse("message_stop", {"type": "message_stop"})
        except APIError as exc:
            yield _sse("error", {"type": "error", "error": exc.to_body(rid)["error"]})
        except Exception:  # pragma: no cover
            logger.exception("anthropic_stream_failed", extra={"request_id": rid})
            yield _sse("error", {"type": "error", "error": {"type": "internal_error", "message": "stream failed"}})

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)
