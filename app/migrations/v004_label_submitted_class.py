"""Keep the label text an annotator actually submitted.

Additive only: existing rows keep `submitted_class_name = NULL`, which means "the
stored class_name is what was submitted". Nothing is rewritten.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection


async def upgrade(connection: AsyncConnection) -> None:
    table_names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    if "labels" not in table_names:
        return
    existing = await connection.run_sync(
        lambda sync: {column["name"] for column in inspect(sync).get_columns("labels")}
    )
    if "submitted_class_name" not in existing:
        await connection.execute(text("ALTER TABLE labels ADD COLUMN submitted_class_name VARCHAR(255)"))
