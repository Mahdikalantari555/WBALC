"""Shared API dependencies and lookup helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import Dataset, Label, Project, TrainingRun


async def get_session(request: Request):
    db = request.app.state.db
    async with db.session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_project(session: AsyncSession, project_id: int) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


async def get_dataset(session: AsyncSession, project_id: int, dataset_id: int) -> Dataset:
    dataset = await session.get(Dataset, dataset_id)
    if dataset is None or dataset.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found in project {project_id}")
    return dataset


async def latest_dataset(session: AsyncSession, project_id: int) -> Dataset | None:
    result = await session.execute(
        select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.id.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def require_dataset(session: AsyncSession, project_id: int, dataset_id: int | None) -> Dataset:
    if dataset_id is not None:
        return await get_dataset(session, project_id, dataset_id)
    dataset = await latest_dataset(session, project_id)
    if dataset is None:
        raise HTTPException(status_code=409, detail="Project has no dataset; upload a GeoTIFF first")
    return dataset


async def project_labels(session: AsyncSession, project_id: int) -> list[Label]:
    result = await session.execute(
        select(Label).where(Label.project_id == project_id).order_by(Label.id)
    )
    return list(result.scalars())


async def latest_run(
    session: AsyncSession, project_id: int, iteration: int | None = None
) -> TrainingRun | None:
    stmt = select(TrainingRun).where(TrainingRun.project_id == project_id)
    if iteration is not None:
        stmt = stmt.where(TrainingRun.iteration == iteration)
    stmt = stmt.order_by(TrainingRun.id.desc()).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
