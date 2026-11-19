"""Phase 3: content identity, reproducibility manifests, artifact integrity, experiments.

Synthetic fixtures only. The theme of every assertion: the engine reports what it
can *prove* and says "unavailable" for the rest — it never back-fills provenance
it did not record, and it never lets a comparison look like a control.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
import rasterio

from app.services.lineage_service import (
    IntegrityError,
    canonical_bytes,
    dataset_manifest,
    digest,
    label_snapshot,
    scrub,
    sha256_file,
    verify_artifact,
)

from .conftest import point_label

WATER = ["open_water", "emergent_vegetation", "land"]


# ------------------------------------------------------------------ fixtures
def scene_bytes(height=64, width=64, bands=4, seed=5) -> bytes:
    rng = np.random.default_rng(seed)
    data = np.zeros((bands, height, width), dtype=np.float32)
    data[:, :, :32] = np.array([10, 20, 100, 120], dtype=np.float32)[:, None, None] + rng.normal(0, 2, (bands, height, 32))
    data[:, :, 32:] = np.array([80, 90, 30, 150], dtype=np.float32)[:, None, None] + rng.normal(0, 2, (bands, height, 32))
    buf = io.BytesIO()
    with rasterio.open(
        buf, "w", driver="GTiff", height=height, width=width, count=bands,
        dtype="float32", crs="EPSG:32631",
        transform=rasterio.transform.from_origin(500000, 4649776, 10, 10),
    ) as dst:
        dst.write(data)
    return buf.getvalue()


@pytest.fixture()
def project(client) -> dict:
    resp = client.post("/projects", json={"name": "Lineage", "classes": WATER})
    assert resp.status_code == 201, resp.text
    return resp.json()


def upload(client, pid: int, payload: bytes | None = None) -> dict:
    resp = client.post(
        f"/projects/{pid}/upload",
        files={"file": ("scene.tif", payload or scene_bytes(), "image/tiff")},
        data={"band_names": "blue,green,red,nir"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def label_all_three(client, pid: int, dsid: int) -> None:
    labels = [
        point_label(4, 4, "open_water", dataset_id=dsid),
        point_label(20, 4, "open_water", dataset_id=dsid),
        point_label(4, 40, "land", dataset_id=dsid),
        point_label(20, 40, "land", dataset_id=dsid),
        point_label(40, 4, "emergent_vegetation", dataset_id=dsid),
        point_label(40, 40, "emergent_vegetation", dataset_id=dsid),
    ]
    resp = client.post(f"/projects/{pid}/labels", json={"labels": labels})
    assert resp.status_code == 201, resp.text


def train(client, pid: int, **body) -> dict:
    resp = client.post(
        f"/projects/{pid}/train",
        json={"model_type": "rf", "resolution": "patch", "evaluation_strategy": "random", **body},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ------------------------------------------------------- unit: canonicalisation
def test_canonical_serialisation_is_stable_under_key_order():
    left = {"b": 2, "a": [1, {"z": 1, "y": 2}]}
    right = {"a": [1, {"y": 2, "z": 1}], "b": 2}
    assert canonical_bytes(left) == canonical_bytes(right)
    assert digest(left) == digest(right)
    assert digest(left) != digest({"a": 1, "b": 3})


def test_manifests_exclude_secrets_and_machine_paths():
    cleaned = scrub(
        {
            "api_key": "super-secret",
            "Authorization": "Bearer xyz",
            "path": "/home/user/WBALC/storage/uploads/1/file.tif",
            "nested": {"password": "p", "crs": "EPSG:32631"},
            "list": ["/tmp/thing.bin", 3],
        }
    )
    assert "api_key" not in cleaned and "Authorization" not in cleaned
    assert "password" not in cleaned["nested"]
    # A path leaks the machine, not the science: only the basename survives.
    assert cleaned["path"] == "file.tif"
    assert cleaned["list"][0] == "thing.bin"
    assert cleaned["nested"]["crs"] == "EPSG:32631"


def test_digest_covers_the_scrubbed_content_not_the_original():
    a = scrub({"path": "/one/dir/file.tif", "bands": 4})
    b = scrub({"path": "/another/place/file.tif", "bands": 4})
    assert digest(a) == digest(b)


# ------------------------------------------------ unit: label / dataset identity
def test_label_snapshot_hashes_versions_not_just_samples():
    class Fake:
        def __init__(self, id, sample_id, version, class_name="open_water"):
            self.id = id
            self.sample_id = sample_id
            self.version = version
            self.iteration = 0
            self.class_name = class_name
            self.dataset_id = 1
            self.query_batch_id = None
            self.query_item_id = None

    v1 = [Fake(1, "d1_r0_c0", 1), Fake(2, "d1_r0_c1", 1)]
    v2 = [Fake(1, "d1_r0_c0", 1), Fake(3, "d1_r0_c1", 2)]
    assert label_snapshot(v1)["hash"] != label_snapshot(v2)["hash"]
    # Same versions, different insertion order: identical snapshot.
    assert label_snapshot(v1)["hash"] == label_snapshot(list(reversed(v1)))["hash"]
    assert label_snapshot(v1)["count"] == 2


# ------------------------------------------------------------ API: inputs
def test_upload_records_content_identity(client, project):
    payload = scene_bytes()
    upload(client, project["id"], payload)
    dataset = client.get(f"/projects/{project['id']}/dataset").json()[0]
    assert len(dataset["content_sha256"]) == 64
    assert dataset["size_bytes"] == len(payload)
    # The recorded hash must describe exactly the bytes that were uploaded.
    import hashlib

    assert dataset["content_sha256"] == hashlib.sha256(payload).hexdigest()
    # ...and the stored file still has those bytes (uploads are immutable).
    uploaded = (Path(client.app.state.settings.storage_dir) / "uploads" / f"project_{project['id']}")
    stored = max(uploaded.iterdir(), key=lambda path: path.stat().st_mtime_ns)
    assert sha256_file(stored) == dataset["content_sha256"]


def test_reuploading_identical_bytes_yields_the_same_hash(client, project):
    payload = scene_bytes(seed=9)
    first = upload(client, project["id"], payload)
    second = upload(client, project["id"], payload)
    assert first["content_sha256"] == second["content_sha256"]
    assert first["id"] != second["id"]


def test_different_bytes_yield_different_hashes(client, project):
    first = upload(client, project["id"], scene_bytes(seed=1))
    second = upload(client, project["id"], scene_bytes(seed=2))
    assert first["content_sha256"] != second["content_sha256"]


def test_dataset_manifest_states_missing_content_identity():
    class Legacy:
        id = 1
        filename = "old.tif"
        width = 8
        height = 8
        bands = 4
        crs = "EPSG:32631"
        transform = None
        band_schema = None
        content_sha256 = None
        size_bytes = None

    manifest = dataset_manifest(Legacy())
    assert manifest["content_sha256"] is None
    assert manifest["band_schema"]["declared"] is False


# ------------------------------------------------------------ API: run manifest
def test_training_run_records_a_complete_manifest(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    run = train(client, project["id"])
    lineage = client.get(f"/projects/{project['id']}/runs/{run['id']}/lineage").json()
    assert lineage["lineage_status"] == "complete", lineage
    manifest = lineage["manifest"]
    assert manifest["manifest_version"] == "run-manifest-v1"
    assert manifest["inputs"][0]["content_sha256"] == dataset["content_sha256"]
    assert manifest["labels"]["count"] == 6
    assert manifest["config"]["resolution"] == "patch"
    assert manifest["config"]["random_state"] == 42
    assert manifest["config"]["evaluation_strategy"] == "random"
    assert manifest["environment"]["python"]
    assert "checkpoint_sha256" in manifest["config"]
    assert lineage["artifact"]["verified"] is True
    assert lineage["missing"] == []


def test_manifest_has_no_machine_local_paths_or_secrets(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    run = train(client, project["id"])
    lineage = client.get(f"/projects/{project['id']}/runs/{run['id']}/lineage").json()
    serialised = str(lineage["manifest"])
    assert "/home/user" not in serialised
    assert "storage/" not in serialised
    assert "password" not in serialised.lower()
    assert "token" not in serialised.lower()


def test_label_correction_changes_the_snapshot_and_leaves_the_old_run_alone(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    first = train(client, project["id"])
    before = client.get(f"/projects/{project['id']}/runs/{first['id']}/lineage").json()

    # Correct one sample: this creates version 2 of the same sample.
    resp = client.post(
        f"/projects/{project['id']}/labels",
        json={
            "geometry": {"type": "Point", "coordinates": [4, 4]},
            "class_name": "land",
            "dataset_id": dataset["id"],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["version"] == 2

    second = train(client, project["id"])
    after_first = client.get(f"/projects/{project['id']}/runs/{first['id']}/lineage").json()
    after_second = client.get(f"/projects/{project['id']}/runs/{second['id']}/lineage").json()

    assert before["manifest"] == after_first["manifest"]  # immutable record
    assert after_second["manifest_hash"] != after_first["manifest_hash"]
    assert (
        after_second["manifest"]["labels"]["hash"]
        != after_first["manifest"]["labels"]["hash"]
    )


def test_run_list_exposes_manifest_hash_and_experiment(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    run = train(client, project["id"])
    runs = client.get(f"/projects/{project['id']}/runs").json()
    entry = next(r for r in runs if r["id"] == run["id"])
    assert len(entry["manifest_hash"]) == 64
    assert entry["experiment_id"] is None


# ------------------------------------------------------- API: artifact integrity
def test_download_verifies_the_artifact_and_reports_its_checksum(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    train(client, project["id"])
    resp = client.get(f"/projects/{project['id']}/download/hard?dataset_id={dataset['id']}")
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-RSAL-Export-Integrity"] == "verified"
    assert len(resp.headers["X-RSAL-Export-Sha256"]) == 64


def test_modified_artifact_is_refused_rather_than_served(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    train(client, project["id"])
    first = client.get(f"/projects/{project['id']}/download/hard?dataset_id={dataset['id']}")
    assert first.status_code == 200

    # Corrupt the stored export behind the engine's back.
    exports = client.get(f"/projects/{project['id']}/exports").json()
    target = Path(next(e["path"] for e in exports if e["type"] == "hard"))
    original = target.read_bytes()
    target.write_bytes(original[:-10] + b"corrupted!")

    second = client.get(f"/projects/{project['id']}/download/hard?dataset_id={dataset['id']}")
    assert second.status_code == 409
    assert "checksum" in second.json()["detail"]
    # The record survives; nothing is replaced by the corrupted bytes.
    still = client.get(f"/projects/{project['id']}/exports").json()
    assert any(Path(e["path"]) == target for e in still)

    target.write_bytes(original)
    third = client.get(f"/projects/{project['id']}/download/hard?dataset_id={dataset['id']}")
    assert third.status_code == 200


def test_missing_artifact_is_reported_clearly(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    train(client, project["id"])
    # A first download materialises the export this test is about to remove.
    assert client.get(f"/projects/{project['id']}/download/hard?dataset_id={dataset['id']}").status_code == 200
    exports = client.get(f"/projects/{project['id']}/exports").json()
    target = Path(next(e["path"] for e in exports if e["type"] == "hard"))
    target.unlink()
    resp = client.get(f"/projects/{project['id']}/download/hard?dataset_id={dataset['id']}")
    # Either the engine regenerates (a run exists) or it refuses; it must not 200
    # with an empty body claiming success.
    assert resp.status_code in (200, 409)
    if resp.status_code == 200:
        assert len(resp.content) > 0


def test_verify_artifact_unit_handles_legacy_and_corruption(tmp_path):
    target = tmp_path / "artifact.tif"
    target.write_bytes(b"hello")
    observed = verify_artifact(target, sha256_file(target))
    assert observed["verified"] is True
    legacy = verify_artifact(target, None)
    assert legacy["verified"] is False and "no checksum" in legacy["reason"]
    with pytest.raises(IntegrityError, match="does not match"):
        verify_artifact(target, "0" * 64)
    target.unlink()
    with pytest.raises(IntegrityError, match="missing"):
        verify_artifact(target, "0" * 64)


# ------------------------------------------------------------ API: experiments
def test_experiment_lifecycle_keeps_runs_untouched(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    first = train(client, project["id"])
    second = train(client, project["id"])

    created = client.post(
        f"/projects/{project['id']}/experiments",
        json={"name": "Patch vs holdout", "hypothesis": "spatial holdout is harsher"},
    )
    assert created.status_code == 201, created.text
    experiment = created.json()
    assert experiment["run_ids"] == []

    before = client.get(f"/projects/{project['id']}/runs/{first['id']}/lineage").json()
    added = client.post(
        f"/projects/{project['id']}/experiments/{experiment['id']}/runs",
        json={"training_run_ids": [first["id"], second["id"]]},
    )
    assert added.status_code == 200, added.text
    assert added.json()["run_ids"] == [first["id"], second["id"]]
    after = client.get(f"/projects/{project['id']}/runs/{first['id']}/lineage").json()
    assert after["manifest"] == before["manifest"]
    assert after["experiment_id"] == experiment["id"]

    renamed = client.patch(
        f"/projects/{project['id']}/experiments/{experiment['id']}",
        json={"name": "Renamed"},
    )
    assert renamed.json()["name"] == "Renamed"

    removed = client.delete(
        f"/projects/{project['id']}/experiments/{experiment['id']}/runs/{second['id']}"
    )
    assert removed.json()["run_ids"] == [first["id"]]
    # Deleting the group must not delete history.
    assert client.delete(f"/projects/{project['id']}/experiments/{experiment['id']}").status_code == 204
    assert client.get(f"/projects/{project['id']}/runs/{first['id']}/lineage").json()["experiment_id"] is None


def test_run_cannot_be_silently_moved_between_experiments(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    run = train(client, project["id"])
    a = client.post(f"/projects/{project['id']}/experiments", json={"name": "A"}).json()
    b = client.post(f"/projects/{project['id']}/experiments", json={"name": "B"}).json()
    client.post(f"/projects/{project['id']}/experiments/{a['id']}/runs", json={"training_run_ids": [run["id"]]})
    resp = client.post(
        f"/projects/{project['id']}/experiments/{b['id']}/runs", json={"training_run_ids": [run["id"]]}
    )
    assert resp.status_code == 409
    assert "already belongs" in resp.json()["detail"]


def test_unknown_runs_are_refused_when_grouping(client, project):
    experiment = client.post(f"/projects/{project['id']}/experiments", json={"name": "E"}).json()
    resp = client.post(
        f"/projects/{project['id']}/experiments/{experiment['id']}/runs",
        json={"training_run_ids": [999]},
    )
    assert resp.status_code == 422


# ------------------------------------------------------------- API: comparison
def test_comparison_of_identical_inputs_is_marked_comparable(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    first = train(client, project["id"], params={"n_estimators": 10})
    second = train(client, project["id"], params={"n_estimators": 10})
    experiment = client.post(f"/projects/{project['id']}/experiments", json={"name": "Same"}).json()
    client.post(
        f"/projects/{project['id']}/experiments/{experiment['id']}/runs",
        json={"training_run_ids": [first["id"], second["id"]]},
    )
    comparison = client.get(
        f"/projects/{project['id']}/experiments/{experiment['id']}/compare"
    ).json()
    assert [row["run_id"] for row in comparison["runs"]] == [first["id"], second["id"]]
    assert comparison["comparable"] is True
    assert comparison["differences"] == {}
    assert comparison["runs"][0]["label_snapshot_hash"] == comparison["runs"][1]["label_snapshot_hash"]


def test_comparison_flags_different_label_snapshots(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    first = train(client, project["id"])
    client.post(
        f"/projects/{project['id']}/labels",
        json={
            "geometry": {"type": "Point", "coordinates": [4, 4]},
            "class_name": "land",
            "dataset_id": dataset["id"],
        },
    )
    second = train(client, project["id"])
    comparison = client.get(f"/projects/{project['id']}/compare?run_ids={first['id']},{second['id']}").json()
    assert comparison["comparable"] is False
    assert "label_snapshot_hash" in comparison["differences"]
    assert any("label versions" in caveat for caveat in comparison["caveats"])


def test_comparison_flags_different_evaluation_protocols(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    first = train(client, project["id"], evaluation_strategy="random")
    second = train(client, project["id"], evaluation_strategy="spatial")
    comparison = client.get(f"/projects/{project['id']}/compare?run_ids={first['id']},{second['id']}").json()
    assert comparison["comparable"] is False
    assert "evaluation" in comparison["differences"]
    assert comparison["differences"]["evaluation"][0][1] == "random"
    assert comparison["differences"]["evaluation"][1][1] == "spatial"
    assert any("not on the same scale" in caveat for caveat in comparison["caveats"])


def test_legacy_run_is_reported_incomplete_not_guessed(client, project):
    """A run row without a manifest must say so everywhere it appears."""
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    run = train(client, project["id"])

    import sqlite3

    db_path = Path(client.app.state.settings.database_url.split("///")[1])
    connection = sqlite3.connect(db_path)
    connection.execute("UPDATE training_runs SET manifest = NULL, checkpoint_sha256 = NULL WHERE id = ?", (run["id"],))
    connection.commit()
    connection.close()

    lineage = client.get(f"/projects/{project['id']}/runs/{run['id']}/lineage").json()
    assert lineage["lineage_status"] == "legacy"
    assert lineage["manifest"] is None
    assert "input content hashes" in lineage["missing"]
    assert any("predates reproducibility manifests" in note for note in lineage["notes"])

    comparison = client.get(f"/projects/{project['id']}/compare").json()
    assert comparison["runs"][0]["lineage_status"] == "legacy"
    assert comparison["comparable"] is False
    assert any("predates" in caveat for caveat in comparison["caveats"])


def test_single_run_is_not_reported_as_comparable(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    train(client, project["id"])
    comparison = client.get(f"/projects/{project['id']}/compare").json()
    assert comparison["comparable"] is False
    assert any("Only one run" in caveat for caveat in comparison["caveats"])


def test_comparison_needs_runs(client, project):
    assert client.get(f"/projects/{project['id']}/compare").status_code == 409
    experiment = client.post(f"/projects/{project['id']}/experiments", json={"name": "empty"}).json()
    assert (
        client.get(f"/projects/{project['id']}/experiments/{experiment['id']}/compare").status_code
        == 409
    )


# ------------------------------------------------- query batches linked to runs
def test_query_batches_are_attributable_to_the_run_that_answered_them(client, project):
    dataset = upload(client, project["id"])
    label_all_three(client, project["id"], dataset["id"])
    batch = client.post(
        f"/projects/{project['id']}/query",
        json={"strategy": "diversity", "batch_size": 3, "dataset_id": dataset["id"]},
    ).json()
    assert batch["batch_id"]
    run = train(client, project["id"])
    lineage = client.get(f"/projects/{project['id']}/runs/{run['id']}/lineage").json()
    # The run's label snapshot names which query items contributed labels.
    versions = lineage["manifest"]["labels"]["versions"]
    assert any(entry["query_item_id"] is None for entry in versions)
    assert lineage["manifest"]["hash"]
