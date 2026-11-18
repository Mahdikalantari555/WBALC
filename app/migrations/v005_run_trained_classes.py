"""Record which classes a training run actually learned.

Additive only: existing runs keep `trained_classes = NULL`. Readers fall back to
the run's class list (the pre-Phase-1 assumption), and never infer a binary
mapping for a class the model may not have seen.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection


async def upgrade(connection: AsyncConnection) -> None:
    table_names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    if "training_runs" not in table_names:
        return
    existing = await connection.run_sync(
        lambda sync: {column["name"] for column in inspect(sync).get_columns("training_runs")}
    )
    if "trained_classes" not in existing:
        await connection.execute(text("ALTER TABLE training_runs ADD COLUMN trained_classes JSON"))
