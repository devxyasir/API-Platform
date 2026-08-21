"""Organizations are the ownership entity for plans, subscriptions, credits, projects,
keys and usage (§4, §6). Every user gets an auto-created personal organization
(OpenAI-style), so single-user personal use "just works"; multi-member orgs are also
fully supported.

Account *provisioning* (personal org + subscription + opening credits + legacy-credit
conversion) is centralized in :func:`provision_account`, called from registration,
admin user-creation, and the bootstrap backfill."""
from __future__ import annotations

import re

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ConflictError, InvalidRequestError, NotFoundError
from app.logging_config import get_logger
from app.models.api_key import ApiKey
from app.models.enums import CreditTxnType, MemberStatus, OrgRole, OrgStatus
from app.models.organization import Organization, OrganizationMember
from app.models.project import Project
from app.models.usage import UsageRecord
from app.models.user import User
from app.services import credit_service, plan_service, subscription_service
from app.utils.ids import ulid

logger = get_logger("app.services.organization")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    base = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return base or "org"


async def _unique_slug(session: AsyncSession, desired: str) -> str:
    """A slug guaranteed free right now. Falls back to a random suffix on collision."""
    base = _slugify(desired)[:100]
    if (await session.execute(select(Organization.id).where(Organization.slug == base))).first() is None:
        return base
    # Append a short unique suffix (lower-cased ULID tail).
    return f"{base}-{ulid()[-6:].lower()}"


# --- reads -------------------------------------------------------------------
async def get_org(session: AsyncSession, organization_id: str) -> Organization | None:
    return await session.get(Organization, organization_id)


async def get_org_or_404(session: AsyncSession, organization_id: str) -> Organization:
    org = await get_org(session, organization_id)
    if org is None:
        raise NotFoundError("Organization not found.", code="organization_not_found")
    return org


async def get_by_slug(session: AsyncSession, slug: str) -> Organization | None:
    return (
        await session.execute(select(Organization).where(Organization.slug == slug))
    ).scalar_one_or_none()


async def list_orgs(
    session: AsyncSession,
    *,
    status: str | None = None,
    include_personal: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Organization], int]:
    conds = []
    if status is not None:
        conds.append(Organization.status == status)
    if not include_personal:
        conds.append(Organization.is_personal.is_(False))
    total = int(
        (await session.execute(select(func.count()).select_from(Organization).where(*conds))).scalar() or 0
    )
    rows = (
        await session.execute(
            select(Organization).where(*conds)
            .order_by(Organization.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return list(rows), total


async def count_orgs(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(Organization))).scalar() or 0)


# --- creation ----------------------------------------------------------------
async def create_org(
    session: AsyncSession,
    *,
    name: str,
    owner: User,
    is_personal: bool = False,
    slug: str | None = None,
) -> Organization:
    """Create an organization and add ``owner`` as its OWNER member."""
    if not name or not name.strip():
        raise InvalidRequestError("Organization name is required.", code="org_name_required")
    org = Organization(
        name=name.strip(),
        slug=await _unique_slug(session, slug or name),
        owner_id=owner.id,
        status=OrgStatus.ACTIVE,
        is_personal=is_personal,
        credit_balance=0,
    )
    session.add(org)
    await session.flush()
    session.add(
        OrganizationMember(
            organization_id=org.id, user_id=owner.id,
            role=OrgRole.OWNER, status=MemberStatus.ACTIVE,
        )
    )
    await session.flush()
    logger.info("organization_created",
                extra={"organization_id": org.id, "is_personal": is_personal, "owner_id": owner.id})
    return org


async def get_personal_org(session: AsyncSession, user: User) -> Organization | None:
    if user.primary_org_id:
        org = await get_org(session, user.primary_org_id)
        if org is not None:
            return org
    return (
        await session.execute(
            select(Organization)
            .where(Organization.owner_id == user.id, Organization.is_personal.is_(True))
            .order_by(Organization.created_at)
        )
    ).scalars().first()


async def create_personal_org(session: AsyncSession, user: User) -> Organization:
    """Create the user's personal org (idempotent) and point ``primary_org_id`` at it."""
    existing = await get_personal_org(session, user)
    if existing is not None:
        if user.primary_org_id != existing.id:
            user.primary_org_id = existing.id
            await session.flush()
        return existing
    label = (user.name or user.email or "Personal").strip()
    org = await create_org(
        session, name=f"{label}'s Organization", owner=user,
        is_personal=True, slug=(user.email.split("@")[0] if user.email else label),
    )
    user.primary_org_id = org.id
    await session.flush()
    return org


async def provision_account(
    session: AsyncSession,
    user: User,
    *,
    plan_slug: str | None = None,
    actor_id: str | None = None,
    trial: bool | None = None,
) -> Organization:
    """Full account setup for a user (§4, §14, §31): personal org + subscription to the
    chosen plan + opening credits, plus a one-time conversion of any legacy
    ``user.credits`` into an org credit-ledger grant. Idempotent: if the user already
    has a subscription, only the personal org is ensured."""
    org = await create_personal_org(session, user)

    existing_sub = await subscription_service.get_active_subscription(session, org.id)
    if existing_sub is not None:
        return org  # already provisioned

    plan = (
        await plan_service.get_plan_by_slug(session, plan_slug) if plan_slug else None
    ) or await plan_service.default_plan(session)
    if plan is None:
        # No plans seeded (shouldn't happen post-bootstrap) — leave org without a sub.
        logger.warning("provision_account_no_plan", extra={"organization_id": org.id})
        return org

    # Keep the user's coarse fields in step with the provisioned plan.
    user.plan = plan.slug
    await subscription_service.create_subscription(
        session, organization_id=org.id, plan=plan, actor_id=actor_id,
        user_id=user.id, trial=trial, reason="account provisioning",
    )

    # One-time legacy credit conversion (user.credits -> org ledger). Zero the legacy
    # mirror afterward so re-running never double-counts.
    if user.credits and user.credits > 0:
        await credit_service.grant(
            session, org.id, int(user.credits), type=CreditTxnType.GRANT,
            reason="Converted from legacy per-user credits", user_id=user.id,
            created_by=actor_id,
        )
        user.credits = 0
    await session.flush()
    logger.info("account_provisioned",
                extra={"user_id": user.id, "organization_id": org.id, "plan": plan.slug})
    return org


# --- membership --------------------------------------------------------------
async def list_members(session: AsyncSession, organization_id: str) -> list[OrganizationMember]:
    return list(
        (
            await session.execute(
                select(OrganizationMember)
                .where(OrganizationMember.organization_id == organization_id)
                .order_by(OrganizationMember.joined_at)
            )
        ).scalars().all()
    )


async def get_member(
    session: AsyncSession, organization_id: str, user_id: str
) -> OrganizationMember | None:
    return (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def add_member(
    session: AsyncSession,
    *,
    organization_id: str,
    user_id: str,
    role: str = OrgRole.DEVELOPER,
    status: str = MemberStatus.ACTIVE,
) -> OrganizationMember:
    if await get_member(session, organization_id, user_id) is not None:
        raise ConflictError("User is already a member of this organization.",
                            code="member_exists")
    member = OrganizationMember(
        organization_id=organization_id, user_id=user_id, role=role, status=status
    )
    session.add(member)
    await session.flush()
    return member


async def update_member_role(
    session: AsyncSession, member: OrganizationMember, role: str
) -> OrganizationMember:
    member.role = role
    await session.flush()
    return member


async def remove_member(session: AsyncSession, member: OrganizationMember) -> None:
    """Remove a member. The organization owner cannot be removed (transfer first)."""
    org = await get_org(session, member.organization_id)
    if org is not None and org.owner_id == member.user_id:
        raise InvalidRequestError("Cannot remove the organization owner.", code="cannot_remove_owner")
    member.status = MemberStatus.REMOVED
    await session.delete(member)
    await session.flush()


async def set_status(session: AsyncSession, org: Organization, status: str) -> Organization:
    org.status = status
    await session.flush()
    logger.info("organization_status_changed",
                extra={"organization_id": org.id, "status": status})
    return org


# --- backfill (bootstrap / migration) ----------------------------------------
async def backfill_personal_orgs(session: AsyncSession, *, actor_id: str | None = None) -> int:
    """Provision a personal org + subscription for every user that lacks one. Returns
    the number of users provisioned. Idempotent."""
    users = (await session.execute(select(User))).scalars().all()
    provisioned = 0
    for user in users:
        sub_before = None
        if user.primary_org_id:
            sub_before = await subscription_service.get_active_subscription(session, user.primary_org_id)
        if sub_before is not None:
            continue
        await provision_account(session, user, plan_slug=user.plan, actor_id=actor_id)
        provisioned += 1
    return provisioned


async def backfill_org_ids(session: AsyncSession) -> None:
    """Stamp ``organization_id`` onto projects, api_keys, and usage_records that predate
    organizations, using each owning user's ``primary_org_id`` (correlated subquery —
    portable across SQLite/Postgres)."""
    proj_org = select(User.primary_org_id).where(User.id == Project.owner_id).scalar_subquery()
    await session.execute(
        update(Project).where(Project.organization_id.is_(None)).values(organization_id=proj_org)
    )
    key_org = select(User.primary_org_id).where(User.id == ApiKey.user_id).scalar_subquery()
    await session.execute(
        update(ApiKey).where(ApiKey.organization_id.is_(None)).values(organization_id=key_org)
    )
    use_org = select(User.primary_org_id).where(User.id == UsageRecord.user_id).scalar_subquery()
    await session.execute(
        update(UsageRecord).where(UsageRecord.organization_id.is_(None)).values(organization_id=use_org)
    )
    await session.flush()
