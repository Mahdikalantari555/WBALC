"""Add lineage columns, artifact hashes and the experiments table.

Additive only. Existing datasets/scenes keep `content_sha256 = NULL`, which is how
a legacy input says "my bytes were never hashed at registration time" — the API
reports that as incomplete instead of hashing today and pretending it was always
known. Existing runs keep `manifest = NULL` and are marked legacy/incomplete.

The one deliberately defensive choice: a column that already exists is skipped,
so a database that was created by an older build and a fresh one converge.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..models import Experiment

_ADDITIONS: dict[str, list[tuple[str, str]]] = {
    "datasets": [
        ("content_sha256", "VARCHAR(64)"),
        ("size_bytes", "INTEGER"),
    ],
    "scenes": [
        ("content_sha256", "VARCHAR(64)"),
        ("size_bytes", "INTEGER"),
    ],
    "exports": [
        ("sha256", "VARCHAR(64)"),
        ("size_bytes", "INTEGER"),
    ],
    "training_runs": [
        ("manifest", "JSON"),
        ("checkpoint_sha256", "VARCHAR(64)"),
        ("experiment_id", "INTEGER"),
    ],
}


async def upgrade(connection: AsyncConnection) -> None:
    table_names = set(
        await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    )
    for table, columns in _ADDITIONS.items():
        if table not in table_names:
            continue
        existing = await connection.run_sync(
            lambda sync, name=table: {
                column["name"] for column in inspect(sync).get_columns(name)
            }
        )
        for name, sql_type in columns:
            if name not in existing:
                await connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                )

    if "projects" in table_names:
        await connection.run_sync(
            lambda sync: Experiment.__table__.create(sync, checkfirst=True)
        )
