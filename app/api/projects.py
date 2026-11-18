"""Project management endpoints (project-management capability)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..models import Project
from ..schemas import ProjectCreate, ProjectOut, ProjectUpdate, TaxonomyOut
from ..services.taxonomy_service import (
    TaxonomyError,
    build_taxonomy,
    describe,
)
from .deps import SessionDep, get_project

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_taxonomy(payload: ProjectCreate) -> dict | None:
    """The taxonomy snapshot a project opts into, or None for generic classes."""
    if payload.generic_classes:
        return None
    try:
        return build_taxonomy(
            aliases=payload.classification_config.label_aliases,
            binary_interpretation=payload.classification_config.binary_output_interpretation,
            source="default",
        )
    except TaxonomyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
        taxonomy=_project_taxonomy(payload),
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
    data.pop("generic_classes", None)
    if not data:
        raise HTTPException(status_code=422, detail="No fields to update")
    for field, value in data.items():
        if value is not None:
            setattr(project, field, value)

    # Re-derive the taxonomy whenever the class semantics may have changed. Prior
    # training runs keep their own snapshot, so this only affects future runs.
    config = payload.classification_config
    if config is not None or payload.generic_classes is not None or "classes" in data:
        if payload.generic_classes is True:
            project.taxonomy = None
        else:
            if project.classes != [c for c in ("open_water", "emergent_vegetation", "land")]:
                if payload.generic_classes is False:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "Cannot apply the water taxonomy to a project whose classes "
                            f"are {project.classes}; set classes to the water taxonomy first."
                        ),
                    )
                project.taxonomy = None
            else:
                from ..schemas import ClassificationConfig

                effective = config or ClassificationConfig.model_validate(
                    project.classification_config or {}
                )
                try:
                    project.taxonomy = build_taxonomy(
                        aliases=effective.label_aliases,
                        binary_interpretation=effective.binary_output_interpretation,
                        source="project",
                    )
                except TaxonomyError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                project.classification_config = effective.model_dump()
    elif project.taxonomy is not None and project.classes != list(
        ("open_water", "emergent_vegetation", "land")
    ):
        # Class list edited on its own: the water crosswalk no longer describes it.
        project.taxonomy = None
    await session.commit()
    await session.refresh(project)
    return project


@router.get("/{project_id}/taxonomy", response_model=TaxonomyOut)
async def read_taxonomy(project_id: int, session: SessionDep) -> TaxonomyOut:
    """Class semantics, aliases and the derived-binary plan for this project."""
    project = await get_project(session, project_id)
    return TaxonomyOut(**describe(project.classes, project.taxonomy))


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, session: SessionDep) -> None:
    project = await get_project(session, project_id)
    await session.delete(project)
    await session.commit()
