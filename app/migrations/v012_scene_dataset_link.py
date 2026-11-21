"""Link every Scene to the queryable Dataset row it spawned.

Adds `scenes.dataset_id` and `datasets.origin`, then backfills both from the
shared content digest: a scene and its derived dataset carry the same
`content_sha256` of the same immutable upload. Idempotent and additive.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

# Scene display names use "SENSOR date · file" — the separator marks a
# scene-derived dataset row when several rows share one digest.
_DISPLAY_SEPARATOR = " · "


async def upgrade(connection: AsyncConnection) -> None:
    scene_columns = await connection.run_sync(
        lambda sync: {c["name"] for c in inspect(sync).get_columns("scenes")}
    )
    if "dataset_id" not in scene_columns:
        await connection.execute(
            text("ALTER TABLE scenes ADD COLUMN dataset_id INTEGER REFERENCES datasets(id) ON DELETE SET NULL")
        )

    dataset_columns = await connection.run_sync(
        lambda sync: {c["name"] for c in inspect(sync).get_columns("datasets")}
    )
    if "origin" not in dataset_columns:
        await connection.execute(
            text("ALTER TABLE datasets ADD COLUMN origin VARCHAR(10) NOT NULL DEFAULT 'upload'")
        )

    # Backfill: link scene -> dataset by (project, content_sha256), preferring
    # the display-name form when several dataset rows share a digest. Rows with
    # no digest (legacy uploads) stay unlinked; nothing is guessed.
    scenes = (
        await connection.execute(
            text(
                "SELECT id, project_id, content_sha256, source_filename FROM scenes "
                "WHERE dataset_id IS NULL AND content_sha256 IS NOT NULL"
            )
        )
    ).mappings().all()
    for scene in scenes:
        rows = (
            await connection.execute(
                text(
                    "SELECT id, filename FROM datasets WHERE project_id = :pid "
                    "AND content_sha256 = :sha ORDER BY id"
                ),
                {"pid": scene["project_id"], "sha": scene["content_sha256"]},
            )
        ).mappings().all()
        if not rows:
            continue
        exact = [
            row
            for row in rows
            if row["filename"] == scene["source_filename"]
            or _DISPLAY_SEPARATOR in str(row["filename"])
        ]
        chosen = (exact or rows)[0]
        await connection.execute(
            text("UPDATE scenes SET dataset_id = :did WHERE id = :sid"),
            {"did": chosen["id"], "sid": scene["id"]},
        )
        await connection.execute(
            text("UPDATE datasets SET origin = 'scene' WHERE id = :did"),
            {"did": chosen["id"]},
        )
