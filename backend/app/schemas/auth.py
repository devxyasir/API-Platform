"""Auth & user schemas (dashboard)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=200)
    name: str = Field(default="", max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    scope: str = "user"
    # Per-session AES key (base64) for the optional payload envelope. Delivered here over
    # TLS; the client uses it to encrypt/decrypt dashboard bodies. Obfuscation only.
    enc_key: str | None = None
    user: "UserOut"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    role: str
    status: str
    plan: str
    account_type: str
    admin_role: str | None = None
    admin_permissions: list[str] = Field(default_factory=list)
    primary_org_id: str | None = None
    quota_tokens: int | None = None
    credits: int
    email_verified: bool
    last_login: datetime | None = None
    created_at: datetime


class UserCreateAdmin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str = ""
    role: str = "developer"
    plan: str = "free"


class UserUpdateAdmin(BaseModel):
    name: str | None = None
    role: str | None = None
    status: str | None = None
    plan: str | None = None
    account_type: str | None = None
    quota_tokens: int | None = None


TokenResponse.model_rebuild()
