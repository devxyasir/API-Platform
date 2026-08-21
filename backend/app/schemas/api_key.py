"""API key schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(default="Default key", max_length=200)
    project_id: str | None = None
    scopes: list[str] | None = None
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    rpm_limit: int | None = None
    tpm_limit: int | None = None


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    key_prefix: str
    user_id: str
    project_id: str | None = None
    scopes: list[str]
    status: str
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class ApiKeyCreatedOut(ApiKeyOut):
    """Returned once at creation — includes the raw secret."""

    key: str = Field(..., description="The full API key. Shown only once — store it securely.")
