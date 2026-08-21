"""User account operations: registration, authentication, lockout, management."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password, verify_password
from app.config import settings
from app.errors import AuthenticationError, ConflictError, NotFoundError, PermissionDeniedError
from app.logging_config import get_logger
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.utils.time import utcnow

logger = get_logger("app.services.user")

_MAX_FAILED = 5
_LOCK_MINUTES = 15


async def get_user(session: AsyncSession, user_id: str) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def count_users(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(User))
    return int(result.scalar() or 0)


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    name: str = "",
    role: str = UserRole.DEVELOPER,
    plan: str = "free",
    email_verified: bool = False,
) -> User:
    existing = await get_user_by_email(session, email)
    if existing is not None:
        raise ConflictError("A user with that email already exists.", code="email_taken")
    user = User(
        email=email.lower(),
        name=name,
        password_hash=hash_password(password),
        role=role,
        plan=plan,
        status=UserStatus.ACTIVE,
        email_verified=email_verified,
    )
    session.add(user)
    await session.flush()
    logger.info("user_created", extra={"user_id": user.id, "role": role})
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(session, email)
    if user is None:
        # Perform a dummy hash to keep timing roughly constant.
        verify_password(password, hash_password("dummy"))
        raise AuthenticationError("Invalid email or password.", code="invalid_credentials")

    now = utcnow()
    if user.locked_until and user.locked_until > now:
        raise PermissionDeniedError(
            "Account temporarily locked due to failed login attempts.",
            code="account_locked",
        )

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= _MAX_FAILED:
            user.locked_until = now + timedelta(minutes=_LOCK_MINUTES)
            user.failed_login_count = 0
            logger.warning("account_locked", extra={"user_id": user.id})
        await session.flush()
        raise AuthenticationError("Invalid email or password.", code="invalid_credentials")

    if user.status == UserStatus.SUSPENDED:
        raise PermissionDeniedError("This account has been suspended.", code="account_suspended")
    if user.status == UserStatus.DELETED:
        raise AuthenticationError("Invalid email or password.", code="invalid_credentials")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login = now
    await session.flush()
    return user


async def change_password(session: AsyncSession, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise AuthenticationError("Current password is incorrect.", code="invalid_credentials")
    user.password_hash = hash_password(new)
    await session.flush()


async def list_users(session: AsyncSession, *, limit: int = 50, offset: int = 0) -> tuple[list[User], int]:
    total = int((await session.execute(select(func.count()).select_from(User))).scalar() or 0)
    result = await session.execute(
        select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), total


async def get_user_or_404(session: AsyncSession, user_id: str) -> User:
    user = await get_user(session, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return user
