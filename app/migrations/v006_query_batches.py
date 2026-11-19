"""Add durable query batches and their items; also link labels to a query item.

Additive only. Both tables are created with `checkfirst`, so an existing
database gains them without touching current rows, and existing labels simply
have no `query_batch_id` (their provenance is reported as manual/legacy).
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..models import QueryBatch, QueryItem


async def upgrade(connection: AsyncConnection) -> None:
    table_names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    if "projects" in table_names:
        await connection.run_sync(
            lambda sync: QueryBatch.__table__.create(sync, checkfirst=True)
        )
        await connection.run_sync(lambda sync: QueryItem.__table__.create(sync, checkfirst=True))

    if "labels" not in table_names:
        return
    existing = await connection.run_sync(
        lambda sync: {column["name"] for column in inspect(sync).get_columns("labels")}
    )
    # Which batch/item a label version came from. NULL = typed or imported
    # directly, i.e. manual provenance — never backfilled with a guess.
    if "query_batch_id" not in existing:
        await connection.execute(text("ALTER TABLE labels ADD COLUMN query_batch_id INTEGER"))
    if "query_item_id" not in existing:
        await connection.execute(text("ALTER TABLE labels ADD COLUMN query_item_id INTEGER"))
