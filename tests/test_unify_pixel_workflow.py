"""unify-pixel-workflow-and-map-fields spec scenarios.

Covers: newest-first run listing with server-owned iterations, scene ↔ dataset
linkage (fresh registration + legacy backfill), and pixel-granular query pools.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from .conftest import point_label


def train(client, project_id: str, **payload) -> dict:
    resp = client.post(
        f"/projects/{project_id}/train",
        json={"model_type": "rf", "params": {"n_estimators": 10}, **payload},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestRunOrderingAndIteration:
    def test_runs_are_listed_newest_first(self, client, project, dataset, labeled):
        pid = project["id"]
        first = train(client, pid)
        second = train(client, pid)
        assert second["iteration"] == first["iteration"] + 1
        runs = client.get(f"/projects/{pid}/runs").json()
        assert [run["iteration"] for run in runs] == sorted(
            (run["iteration"] for run in runs), reverse=True
        )
        assert runs[0]["id"] == second["id"]

    def test_client_iteration_is_ignored(self, client, project, dataset, labeled):
        pid = project["id"]
        # A repeated client value must not collide: the engine derives its own.
        first = train(client, pid, iteration=3)
        second = train(client, pid, iteration=3)
        assert first["iteration"] == 0
        assert second["iteration"] == 1
        runs = client.get(f"/projects/{pid}/runs").json()
        assert sorted(run["iteration"] for run in runs) == [0, 1]


class TestSceneDatasetLink:
    def _register_scene(self, client, project_id: int, filename: str = "scene-a.tif") -> dict:
        buf = io.BytesIO()
        h = w = 16
        data = np.zeros((2, h, w), dtype="uint16")
        with rasterio.open(
            buf, "w", driver="GTiff", height=h, width=w, count=2, dtype="uint16",
            crs="EPSG:32631", transform=from_origin(500000, 4649776, 10, 10),
        ) as dst:
            dst.write(data)
        resp = client.post(
            f"/projects/{project_id}/scenes",
            files={"file": (filename, buf.getvalue(), "image/tiff")},
            data={
                "sensor": "Sentinel-1",
                "acquisition_datetime": "2025-04-01T00:00:00Z",
                "band_names": "vv,vh",
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_registration_links_the_derived_dataset(self, client, project):
        scene = self._register_scene(client, project["id"])
        assert scene["dataset_id"] is not None
        datasets = client.get(f"/projects/{project['id']}/dataset").json()
        linked = next(item for item in datasets if item["id"] == scene["dataset_id"])
        assert linked["origin"] == "scene"

    def test_dataset_deletion_nulls_the_scene_link(self, client, project):
        scene = self._register_scene(client, project["id"])
        dataset_id = scene["dataset_id"]
        resp = client.delete(f"/projects/{project['id']}/dataset/{dataset_id}")
        assert resp.status_code == 204
        fresh = client.get(f"/projects/{project['id']}/scenes/{scene['id']}").json()
        assert fresh["dataset_id"] is None


class TestPixelQueryPools:
    def _pixel_project(self, client, project, dataset) -> str:
        labels = []
        for row in range(8):
            for col in range(8):
                x, y = col * 8 + 4, row * 8 + 4
                cls = "water" if col < 4 else "vegetation"
                labels.append(point_label(x, y, cls))
        resp = client.post(f"/projects/{project['id']}/labels", json={"labels": labels})
        assert resp.status_code == 201, resp.text
        return train(client, project["id"], resolution="pixel")["id"]

    def test_uncertainty_ranks_a_pixel_pool(self, client, project, dataset, labeled):
        run_id = self._pixel_project(client, project, dataset)
        resp = client.post(
            f"/projects/{project['id']}/query",
            json={"strategy": "uncertainty", "batch_size": 5},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Pool granularity recorded structurally and in prose.
        assert body["pool"]["patch_size"] == 1
        assert any("pixel" in note for note in body["notes"])
        assert body["model_iteration"] is not None
        assert body["training_run_id"] == run_id
        samples = body["samples"]
        assert len(samples) == 5
        for sample in samples:
            assert sample["prediction"] in {"water", "vegetation"}
            assert sample["confidence"] is not None
            # One pixel per candidate: a 1×1 window in the raw coords.
            coords = sample["coords"]
            assert coords["x1"] - coords["x0"] == 1
            assert coords["y1"] - coords["y0"] == 1

    def test_diversity_on_a_pixel_pool_is_model_free(self, client, project, dataset, labeled):
        self._pixel_project(client, project, dataset)
        resp = client.post(
            f"/projects/{project['id']}/query",
            json={"strategy": "diversity", "batch_size": 4},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["pool"]["patch_size"] == 1
        assert body["model_iteration"] is None
        assert body["training_run_id"] is None
        assert len(body["samples"]) == 4

    def test_granularity_mismatch_is_refused(self, client, project, dataset, labeled):
        self._pixel_project(client, project, dataset)
        resp = client.post(
            f"/projects/{project['id']}/query",
            json={"strategy": "uncertainty", "sample_resolution": "patch"},
        )
        assert resp.status_code == 409, resp.text
        assert "pixel" in resp.json()["detail"] and "patch" in resp.json()["detail"]

    def test_patch_checkpoint_behaviour_is_unchanged(self, client, project, dataset, labeled):
        train(client, project["id"])  # patch resolution default
        resp = client.post(
            f"/projects/{project['id']}/query",
            json={"strategy": "uncertainty", "batch_size": 3},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["pool"]["patch_size"] == 8  # the test settings' patch size
        assert body["model_iteration"] is not None


class TestLegacyBackfill:
    def test_migration_links_scenes_by_content_digest(self, tmp_path: Path):
        """A v011-era database (no link columns) is linked by the migration."""
        import asyncio

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.migrations.v012_scene_dataset_link import upgrade as upgrade_v12

        async def migrate() -> tuple[list, dict]:
            engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
            async with engine.begin() as conn:
                # A pre-v012 database: the two tables carry no link/origin columns.
                await conn.execute(
                    text(
                        "CREATE TABLE datasets (id INTEGER PRIMARY KEY, project_id INTEGER, "
                        "filename TEXT, content_sha256 TEXT)"
                    )
                )
                await conn.execute(
                    text(
                        "CREATE TABLE scenes (id INTEGER PRIMARY KEY, project_id INTEGER, "
                        "content_sha256 TEXT, source_filename TEXT)"
                    )
                )
                await conn.execute(
                    text(
                        "INSERT INTO datasets (id, project_id, filename, content_sha256) VALUES "
                        "(1, 1, 'Sentinel-1 2025-04-01 · scene-a.tif', 'abc'), "
                        "(2, 1, 'training.tif', NULL)"
                    )
                )
                await conn.execute(
                    text(
                        "INSERT INTO scenes (id, project_id, content_sha256, source_filename) VALUES "
                        "(1, 1, 'abc', 'scene-a.tif'), (2, 1, NULL, 'legacy.tif')"
                    )
                )
                await upgrade_v12(conn)
                scene_links = (
                    await conn.execute(text("SELECT id, dataset_id FROM scenes ORDER BY id"))
                ).all()
                origins = dict(
                    (await conn.execute(text("SELECT id, origin FROM datasets ORDER BY id"))).all()
                )
            await engine.dispose()
            return scene_links, origins

        scene_links, origins = asyncio.run(migrate())

        # Digest match links scene 1 → dataset 1 and marks it scene-derived;
        # the digest-less legacy scene stays unlinked rather than guessed.
        assert scene_links == [(1, 1), (2, None)]
        assert origins == {1: "scene", 2: "upload"}
