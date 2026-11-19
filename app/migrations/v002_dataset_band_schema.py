"""Add declarable band identity to prepared datasets.

Additive only: existing rows keep `band_schema = NULL`, which this application
interprets as "no declared identity". Nothing is backfilled from filenames or
sensor defaults, because a guessed schema is worse than an absent one.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection


async def upgrade(connection: AsyncConnection) -> None:
    table_names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    if "datasets" not in table_names:
        return
    existing = await connection.run_sync(
        lambda sync: {column["name"] for column in inspect(sync).get_columns("datasets")}
    )
    if "band_schema" not in existing:
        await connection.execute(text("ALTER TABLE datasets ADD COLUMN band_schema JSON"))
