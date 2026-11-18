"""Numbered, idempotent database migrations for WBALC."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .v001_scene_foundation import upgrade as upgrade_v1

MIGRATIONS = [(1, upgrade_v1)]


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
