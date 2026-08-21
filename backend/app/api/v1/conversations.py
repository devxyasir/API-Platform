"""Conversation management for API consumers (/v1/conversations)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import AuthContext, get_api_context, require_scope
from app.schemas.admin import ConversationCreate, ConversationDetailOut, ConversationOut
from app.schemas.common import OK
from app.services import conversation_service

router = APIRouter(tags=["Conversations"], prefix="/conversations")


@router.post("", response_model=ConversationOut, status_code=201, summary="Create conversation")
async def create_conversation(
    body: ConversationCreate,
    ctx: AuthContext = Depends(require_scope("conversations:write")),
    session: AsyncSession = Depends(get_session),
):
    conv = await conversation_service.create_conversation(
        session, user_id=ctx.user.id, title=body.title,
        project_id=body.project_id or (ctx.project.id if ctx.project else None),
        model=body.model,
    )
    return ConversationOut.model_validate(conv)


@router.get("", response_model=list[ConversationOut], summary="List conversations")
async def list_conversations(
    ctx: AuthContext = Depends(require_scope("conversations:read")),
    session: AsyncSession = Depends(get_session),
):
    convs = await conversation_service.list_conversations(session, user_id=ctx.user.id)
    return [ConversationOut.model_validate(c) for c in convs]


@router.get("/{conversation_id}", response_model=ConversationDetailOut, summary="Get conversation")
async def get_conversation(
    conversation_id: str,
    ctx: AuthContext = Depends(require_scope("conversations:read")),
    session: AsyncSession = Depends(get_session),
):
    conv = await conversation_service.get_conversation(
        session, conversation_id, user_id=ctx.user.id, with_messages=True
    )
    return ConversationDetailOut.model_validate(conv)


@router.delete("/{conversation_id}", response_model=OK, summary="Delete conversation")
async def delete_conversation(
    conversation_id: str,
    ctx: AuthContext = Depends(require_scope("conversations:write")),
    session: AsyncSession = Depends(get_session),
):
    conv = await conversation_service.get_conversation(session, conversation_id, user_id=ctx.user.id)
    await conversation_service.delete_conversation(session, conv)
    return OK(detail="Conversation deleted.")
