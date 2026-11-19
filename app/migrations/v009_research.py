"""Add research evaluation records (protocols, results, reference areas, plans, reports).

Additive only: five new tables, and nothing in `datasets`, `training_runs`,
`scene_analyses` or `fusion_runs` is altered. A project with no research records
simply has none.
"""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncConnection

from ..models import EvaluationProtocol, EvaluationResult, ReferenceArea, ResearchPlan, ResearchReport

TABLES = (
    EvaluationProtocol,
    EvaluationResult,
    ReferenceArea,
    ResearchPlan,
    ResearchReport,
)


async def upgrade(connection: AsyncConnection) -> None:
    names = set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
    if "projects" not in names:
        return
    for model in TABLES:
        await connection.run_sync(lambda sync, m=model: m.__table__.create(sync, checkfirst=True))
