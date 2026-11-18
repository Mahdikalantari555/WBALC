"""Add WBALC study configuration; scene table comes from ORM metadata."""

from __future__ import annotations

from sqlalchemy import JSON, Column, MetaData, Table, inspect, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from ..models import Scene

DEFAULT_CLASSIFICATION = {
    "internal_classes": ["open_water", "emergent_vegetation", "land"],
    "binary_output_interpretation": "water_vs_non_water",
}


async def upgrade(connection: AsyncConnection) -> None:
    table_names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    if "projects" not in table_names:
        return
    existing = await connection.run_sync(
        lambda sync: {column["name"] for column in inspect(sync).get_columns("projects")}
    )
    if "study_area_geometry" not in existing:
        await connection.execute(text("ALTER TABLE projects ADD COLUMN study_area_geometry JSON"))
    if "study_area_crs" not in existing:
        await connection.execute(text("ALTER TABLE projects ADD COLUMN study_area_crs VARCHAR(255)"))
    if "classification_config" not in existing:
        await connection.execute(text("ALTER TABLE projects ADD COLUMN classification_config JSON"))

    table = Table(
        "projects",
        MetaData(),
        Column("id"),
        Column("classification_config", JSON),
    )
    await connection.execute(
        update(table)
        .where(table.c.classification_config.is_(None))
        .values(classification_config=DEFAULT_CLASSIFICATION)
    )
    # Explicitly create the new domain table as part of the versioned migration.
    await connection.run_sync(lambda sync: Scene.__table__.create(sync, checkfirst=True))
