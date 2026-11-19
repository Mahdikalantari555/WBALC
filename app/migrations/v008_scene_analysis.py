"""Add scene-level analysis and late-fusion records.

Additive only: both tables are new, and existing datasets/scenes/exports are
untouched. A project with no scene analyses simply has none.
"""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncConnection

from ..models import FusionRun, SceneAnalysis


async def upgrade(connection: AsyncConnection) -> None:
    table_names = set(
        await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    )
    if "projects" not in table_names:
        return
    await connection.run_sync(
        lambda sync: SceneAnalysis.__table__.create(sync, checkfirst=True)
    )
    await connection.run_sync(lambda sync: FusionRun.__table__.create(sync, checkfirst=True))
