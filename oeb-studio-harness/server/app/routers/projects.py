from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
import uuid

from app.database import get_db
from app.auth import require_admin
from app.models.project import Project
from app.models.audit import AuditEvent
from app.schemas.project import ProjectCreateRequest, ProjectSummary

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
async def create_project(body: ProjectCreateRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Project).where(Project.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slug already exists")

    project = Project(
        name=body.name,
        slug=body.slug,
        description=body.description,
    )
    db.add(project)
    db.add(AuditEvent(
        event_type="project.created",
        actor_type="user",
        actor_id="admin",
        resource_type="project",
        resource_id=str(project.id),
        details={"slug": project.slug},
    ))
    await db.commit()
    await db.refresh(project)
    return ProjectSummary.model_validate(project)


@router.get("", response_model=list[ProjectSummary], dependencies=[Depends(require_admin)])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project).where(Project.status == "active").order_by(Project.name)
    )
    return [ProjectSummary.model_validate(p) for p in result.scalars().all()]


@router.get("/{project_id}", response_model=ProjectSummary, dependencies=[Depends(require_admin)])
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectSummary.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_admin)])
async def archive_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.status = "archived"
    project.updated_at = datetime.now(timezone.utc)
    db.add(AuditEvent(
        event_type="project.archived",
        actor_type="user",
        actor_id="admin",
        resource_type="project",
        resource_id=str(project.id),
    ))
    await db.commit()
