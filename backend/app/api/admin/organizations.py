"""Organization administration (§4-7): organizations, their status, and members.

Organizations are the ownership entity for plans, subscriptions, credits, projects,
keys and usage. Every user has an auto-created personal org; admins may also create and
manage multi-member organizations here."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_permission
from app.errors import InvalidRequestError, NotFoundError
from app.models.enums import MemberStatus, OrgRole, OrgStatus
from app.models.user import User
from app.schemas.admin import (
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
    OrgMemberAdd,
    OrgMemberOut,
    OrgMemberUpdate,
    OrgStatusUpdate,
)
from app.schemas.common import OK, Page
from app.services import audit_service, organization_service, user_service

router = APIRouter(tags=["Organizations"], prefix="/organizations")

_VALID_ORG_STATUS = {s.value for s in OrgStatus}
_VALID_ORG_ROLE = {r.value for r in OrgRole}


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


@router.get("", response_model=Page[OrganizationOut], summary="List organizations")
async def list_organizations(
    status: str | None = Query(default=None),
    include_personal: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_permission("orgs.read")),
    session: AsyncSession = Depends(get_session),
):
    orgs, total = await organization_service.list_orgs(
        session, status=status, include_personal=include_personal, limit=limit, offset=offset
    )
    return Page[OrganizationOut](
        items=[OrganizationOut.model_validate(o) for o in orgs], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=OrganizationOut, status_code=201, summary="Create an organization")
async def create_organization(
    body: OrganizationCreate,
    request: Request,
    admin: User = Depends(require_permission("orgs.write")),
    session: AsyncSession = Depends(get_session),
):
    owner = await user_service.get_user_or_404(session, body.owner_id)
    org = await organization_service.create_org(
        session, name=body.name, owner=owner, is_personal=False, slug=body.slug
    )
    await audit_service.record_audit(
        session, action="organization.created", actor_id=admin.id, actor_email=admin.email,
        target_type="organization", target_id=org.id,
        meta={"owner_id": owner.id}, ip_hash=_ip(request),
    )
    return OrganizationOut.model_validate(org)


@router.get("/{org_id}", response_model=OrganizationOut, summary="Get an organization")
async def get_organization(
    org_id: str,
    _admin: User = Depends(require_permission("orgs.read")),
    session: AsyncSession = Depends(get_session),
):
    org = await organization_service.get_org_or_404(session, org_id)
    return OrganizationOut.model_validate(org)


@router.patch("/{org_id}", response_model=OrganizationOut, summary="Update an organization")
async def update_organization(
    org_id: str,
    body: OrganizationUpdate,
    request: Request,
    admin: User = Depends(require_permission("orgs.write")),
    session: AsyncSession = Depends(get_session),
):
    org = await organization_service.get_org_or_404(session, org_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(org, key, value)
    await session.flush()
    await audit_service.record_audit(
        session, action="organization.updated", actor_id=admin.id, actor_email=admin.email,
        target_type="organization", target_id=org.id,
        meta={"changes": list(changes)}, ip_hash=_ip(request),
    )
    return OrganizationOut.model_validate(org)


@router.post("/{org_id}/status", response_model=OrganizationOut, summary="Set organization status")
async def set_organization_status(
    org_id: str,
    body: OrgStatusUpdate,
    request: Request,
    admin: User = Depends(require_permission("orgs.write")),
    session: AsyncSession = Depends(get_session),
):
    if body.status not in _VALID_ORG_STATUS:
        raise InvalidRequestError(
            f"Invalid organization status. Choose one of: {', '.join(sorted(_VALID_ORG_STATUS))}.",
            code="invalid_status",
        )
    org = await organization_service.get_org_or_404(session, org_id)
    if org.is_personal and body.status == OrgStatus.DELETED:
        raise InvalidRequestError(
            "A personal organization cannot be deleted while its user exists.",
            code="cannot_delete_personal_org",
        )
    org = await organization_service.set_status(session, org, body.status)
    await audit_service.record_audit(
        session, action="organization.status_changed", actor_id=admin.id, actor_email=admin.email,
        target_type="organization", target_id=org.id,
        meta={"status": body.status, "reason": body.reason}, ip_hash=_ip(request),
    )
    return OrganizationOut.model_validate(org)


# --- members ----------------------------------------------------------------
@router.get("/{org_id}/members", response_model=list[OrgMemberOut], summary="List members")
async def list_members(
    org_id: str,
    _admin: User = Depends(require_permission("orgs.read")),
    session: AsyncSession = Depends(get_session),
):
    await organization_service.get_org_or_404(session, org_id)
    members = await organization_service.list_members(session, org_id)
    return [OrgMemberOut.model_validate(m) for m in members]


@router.post("/{org_id}/members", response_model=OrgMemberOut, status_code=201, summary="Add a member")
async def add_member(
    org_id: str,
    body: OrgMemberAdd,
    request: Request,
    admin: User = Depends(require_permission("orgs.write")),
    session: AsyncSession = Depends(get_session),
):
    if body.role not in _VALID_ORG_ROLE:
        raise InvalidRequestError("Invalid organization role.", code="invalid_role")
    await organization_service.get_org_or_404(session, org_id)
    await user_service.get_user_or_404(session, body.user_id)
    member = await organization_service.add_member(
        session, organization_id=org_id, user_id=body.user_id, role=body.role,
        status=MemberStatus.ACTIVE,
    )
    await audit_service.record_audit(
        session, action="organization.member_added", actor_id=admin.id, actor_email=admin.email,
        target_type="organization", target_id=org_id,
        meta={"user_id": body.user_id, "role": body.role}, ip_hash=_ip(request),
    )
    return OrgMemberOut.model_validate(member)


@router.patch("/{org_id}/members/{user_id}", response_model=OrgMemberOut, summary="Update a member's role")
async def update_member(
    org_id: str,
    user_id: str,
    body: OrgMemberUpdate,
    request: Request,
    admin: User = Depends(require_permission("orgs.write")),
    session: AsyncSession = Depends(get_session),
):
    if body.role not in _VALID_ORG_ROLE:
        raise InvalidRequestError("Invalid organization role.", code="invalid_role")
    member = await organization_service.get_member(session, org_id, user_id)
    if member is None:
        raise NotFoundError("Organization member not found.", code="member_not_found")
    member = await organization_service.update_member_role(session, member, body.role)
    await audit_service.record_audit(
        session, action="organization.member_updated", actor_id=admin.id, actor_email=admin.email,
        target_type="organization", target_id=org_id,
        meta={"user_id": user_id, "role": body.role}, ip_hash=_ip(request),
    )
    return OrgMemberOut.model_validate(member)


@router.delete("/{org_id}/members/{user_id}", response_model=OK, summary="Remove a member")
async def remove_member(
    org_id: str,
    user_id: str,
    request: Request,
    admin: User = Depends(require_permission("orgs.write")),
    session: AsyncSession = Depends(get_session),
):
    member = await organization_service.get_member(session, org_id, user_id)
    if member is None:
        raise NotFoundError("Organization member not found.", code="member_not_found")
    await organization_service.remove_member(session, member)
    await audit_service.record_audit(
        session, action="organization.member_removed", actor_id=admin.id, actor_email=admin.email,
        target_type="organization", target_id=org_id,
        meta={"user_id": user_id}, ip_hash=_ip(request),
    )
    return OK(detail="Member removed.")
