"""Admin project management (platform-wide).

The admin control-plane view of **every** account's projects. Requires an admin-scoped
session and the ``projects.*`` RBAC permission — a user-scoped token is rejected. Users
manage their own projects via ``/account/projects``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_permission
from app.models.user import User
from app.schemas.admin import ProjectCreate, ProjectOut, ProjectUpdate
from app.schemas.common import OK
from app.services import audit_service, project_service

router = APIRouter(tags=["Projects"], prefix="/projects")


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


@router.get("", response_model=list[ProjectOut], summary="List projects (all accounts)")
async def list_projects(
    owner_id: str | None = Query(default=None, description="Filter to a single owner."),
    _admin: User = Depends(require_permission("projects.read")),
    session: AsyncSession = Depends(get_session),
):
    projects = await project_service.list_projects(session, owner_id=owner_id)
    return [ProjectOut.model_validate(p) for p in projects]


@router.post("", response_model=ProjectOut, status_code=201, summary="Create a project for an owner")
async def create_project(
    body: ProjectCreate,
    request: Request,
    owner_id: str = Query(..., description="Account that will own the project."),
    admin: User = Depends(require_permission("projects.write")),
    session: AsyncSession = Depends(get_session),
):
    project = await project_service.create_project(session, owner_id=owner_id, **body.model_dump())
    await audit_service.record_audit(
        session, action="project.created", actor_id=admin.id, actor_email=admin.email,
        target_type="project", target_id=project.id, meta={"owner_id": owner_id}, ip_hash=_ip(request),
    )
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut, summary="Get any project")
async def get_project(
    project_id: str,
    _admin: User = Depends(require_permission("projects.read")),
    session: AsyncSession = Depends(get_session),
):
    project = await project_service.get_project_or_404(session, project_id, owner_id=None)
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut, summary="Update any project")
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    request: Request,
    admin: User = Depends(require_permission("projects.write")),
    session: AsyncSession = Depends(get_session),
):
    project = await project_service.get_project_or_404(session, project_id, owner_id=None)
    project = await project_service.update_project(session, project, **body.model_dump(exclude_unset=True))
    await audit_service.record_audit(
        session, action="project.updated", actor_id=admin.id, actor_email=admin.email,
        target_type="project", target_id=project.id, ip_hash=_ip(request),
    )
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", response_model=OK, summary="Delete any project")
async def delete_project(
    project_id: str,
    request: Request,
    admin: User = Depends(require_permission("projects.write")),
    session: AsyncSession = Depends(get_session),
):
    project = await project_service.get_project_or_404(session, project_id, owner_id=None)
    await project_service.delete_project(session, project)
    await audit_service.record_audit(
        session, action="project.deleted", actor_id=admin.id, actor_email=admin.email,
        target_type="project", target_id=project_id, ip_hash=_ip(request),
    )
    return OK(detail="Project deleted.")
