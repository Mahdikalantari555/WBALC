"""Add an explicit water-body taxonomy to projects.

Additive only: existing rows keep `taxonomy = NULL`, which this application
interprets as "generic/legacy project, no water crosswalk configured". A NULL is
never backfilled into the WBALC taxonomy, because that would relabel somebody
else's existing classes after the fact.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection


async def upgrade(connection: AsyncConnection) -> None:
    table_names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    if "projects" not in table_names:
        return
    existing = await connection.run_sync(
        lambda sync: {column["name"] for column in inspect(sync).get_columns("projects")}
    )
    if "taxonomy" not in existing:
        await connection.execute(text("ALTER TABLE projects ADD COLUMN taxonomy JSON"))
