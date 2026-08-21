"""Your projects (``/account/projects``).

Strictly self-scoped: every lookup is constrained to ``owner_id == caller``. (Admins see
all projects via ``/admin/projects``.)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.admin import ProjectCreate, ProjectOut, ProjectUpdate
from app.schemas.common import OK
from app.services import project_service

router = APIRouter(tags=["Account Projects"], prefix="/projects")


@router.get("", response_model=list[ProjectOut], summary="List your projects")
async def list_projects(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    projects = await project_service.list_projects(session, owner_id=user.id)
    return [ProjectOut.model_validate(p) for p in projects]


@router.post("", response_model=ProjectOut, status_code=201, summary="Create a project")
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = await project_service.create_project(session, owner_id=user.id, **body.model_dump())
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut, summary="Get one of your projects")
async def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = await project_service.get_project_or_404(session, project_id, owner_id=user.id)
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut, summary="Update one of your projects")
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = await project_service.get_project_or_404(session, project_id, owner_id=user.id)
    project = await project_service.update_project(
        session, project, **body.model_dump(exclude_unset=True)
    )
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", response_model=OK, summary="Delete one of your projects")
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = await project_service.get_project_or_404(session, project_id, owner_id=user.id)
    await project_service.delete_project(session, project)
    return OK(detail="Project deleted.")
