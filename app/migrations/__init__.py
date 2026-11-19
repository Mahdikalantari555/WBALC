"""Numbered, idempotent database migrations for WBALC."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .v001_scene_foundation import upgrade as upgrade_v1
from .v002_dataset_band_schema import upgrade as upgrade_v2
from .v003_project_taxonomy import upgrade as upgrade_v3
from .v004_label_submitted_class import upgrade as upgrade_v4
from .v005_run_trained_classes import upgrade as upgrade_v5
from .v006_query_batches import upgrade as upgrade_v6
from .v007_lineage import upgrade as upgrade_v7

MIGRATIONS = [
    (1, upgrade_v1),
    (2, upgrade_v2),
    (3, upgrade_v3),
    (4, upgrade_v4),
    (5, upgrade_v5),
    (6, upgrade_v6),
    (7, upgrade_v7),
]


async def run_migrations(connection: AsyncConnection) -> None:
    """Run additive migrations once, safely supporting existing RSAL databases."""
    await connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
    )
    applied = set((await connection.execute(text("SELECT version FROM schema_migrations"))).scalars())
    for version, upgrade in MIGRATIONS:
        if version in applied:
            continue
        await upgrade(connection)
        await connection.execute(
            text("INSERT INTO schema_migrations (version) VALUES (:version)"),
            {"version": version},
        )
