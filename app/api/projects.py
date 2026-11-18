"""Project management endpoints (project-management capability)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..models import Project
from ..schemas import ProjectCreate, ProjectOut, ProjectUpdate
from .deps import SessionDep, get_project

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(payload: ProjectCreate, session: SessionDep) -> Project:
    project = Project(
        name=payload.name,
        classes=payload.classes or payload.classification_config.internal_classes,
        description=payload.description,
        status=payload.status,
        study_area_geometry=payload.study_area_geometry,
        study_area_crs=payload.study_area_crs,
        classification_config=payload.classification_config.model_dump(),
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(session: SessionDep) -> list[Project]:
    result = await session.execute(select(Project).order_by(Project.id))
    return list(result.scalars())


@router.get("/{project_id}", response_model=ProjectOut)
async def read_project(project_id: int, session: SessionDep) -> Project:
    return await get_project(session, project_id)


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, payload: ProjectUpdate, session: SessionDep) -> Project:
    project = await get_project(session, project_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="No fields to update")
    for field, value in data.items():
        if value is not None:
            setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, session: SessionDep) -> None:
    project = await get_project(session, project_id)
    await session.delete(project)
    await session.commit()
