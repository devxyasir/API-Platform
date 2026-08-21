"""Shared schema helpers."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class Message(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    message: str
    type: str
    code: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class OK(BaseModel):
    ok: bool = True
    detail: str | None = None
