"""Project operations."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.models.project import Project


async def create_project(session: AsyncSession, *, owner_id: str, **fields) -> Project:
    clean = {k: v for k, v in fields.items() if v is not None}
    project = Project(owner_id=owner_id, **clean)
    session.add(project)
    await session.flush()
    return project


async def list_projects(session: AsyncSession, *, owner_id: str | None = None) -> list[Project]:
    stmt = select(Project).order_by(Project.created_at.desc())
    if owner_id:
        stmt = stmt.where(Project.owner_id == owner_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_project_or_404(session: AsyncSession, project_id: str, *, owner_id: str | None = None) -> Project:
    project = await session.get(Project, project_id)
    if project is None or (owner_id is not None and project.owner_id != owner_id):
        raise NotFoundError("Project not found.")
    return project


async def update_project(session: AsyncSession, project: Project, **fields) -> Project:
    for key, value in fields.items():
        if value is not None:
            setattr(project, key, value)
    await session.flush()
    return project


async def delete_project(session: AsyncSession, project: Project) -> None:
    await session.delete(project)
    await session.flush()
