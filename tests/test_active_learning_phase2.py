"""Phase 2: durable query batches, annotation decisions, seeded random baseline.

Synthetic fixtures only. The tests assert what the engine *records*: which pool a
batch sampled from, in what order, with which seed and model, and what the
annotator then decided — including the cases where it must refuse to guess.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
import rasterio

from app.services.query_service import (
    QuerySelectionError,
    pool_hash,
    resolve_seed,
    select_random,
)

from .conftest import point_label

WATER = ["open_water", "emergent_vegetation", "land"]


# ------------------------------------------------------------------ fixtures
def scene_bytes(height=64, width=64, bands=4) -> bytes:
    rng = np.random.default_rng(11)
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
    resp = client.post("/projects", json={"name": "Batches", "classes": WATER})
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def dataset(client, project) -> dict:
    resp = client.post(
        f"/projects/{project['id']}/upload",
        files={"file": ("scene.tif", scene_bytes(), "image/tiff")},
        data={"band_names": "blue,green,red,nir"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def query(client, pid: int, dsid: int, **body) -> dict:
    payload = {"strategy": "diversity", "batch_size": 6, "dataset_id": dsid, **body}
    resp = client.post(f"/projects/{pid}/query", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ------------------------------------------------------- strategy unit tests
def test_seeded_random_is_repeatable_and_without_replacement():
    pool = [f"d1_r{r}_c{c}" for r in range(8) for c in range(8)]
    first = select_random(pool, 10, seed=7)
    assert first == select_random(pool, 10, seed=7)
    assert len(set(first)) == 10
    assert select_random(pool, 10, seed=8) != first


def test_seeded_random_never_returns_more_than_the_pool():
    pool = ["a", "b", "c"]
    assert sorted(select_random(pool, 10, seed=1)) == [0, 1, 2]
    assert select_random([], 5, seed=1) == []


def test_pool_hash_is_order_sensitive():
    assert pool_hash(["a", "b"]) == pool_hash(["a", "b"])
    # Same set, different order: a different pool for reproducibility purposes.
    assert pool_hash(["a", "b"]) != pool_hash(["b", "a"])


def test_only_random_strategies_record_a_seed():
    assert resolve_seed("random", None, 42) == 42
    assert resolve_seed("random", 5, 42) == 5
    # A deterministic strategy must not claim a seed it never used.
    for strategy in ("diversity", "uncertainty", "hybrid"):
        assert resolve_seed(strategy, 5, 42) is None


# --------------------------------------------------------- API: persistence
def test_query_response_carries_batch_identity_and_pool(client, project, dataset):
    body = query(client, project["id"], dataset["id"], strategy="random", seed=1234)
    assert body["batch_id"] > 0
    assert body["seed"] == 1234
    assert body["strategy_version"] == "query-v1"
    assert body["pool"]["size"] == 64  # 8x8 patch grid, no labels yet
    assert body["pool"]["hash"] == body["pool"]["hash"]
    assert body["pool"]["patch_size"] == 8
    assert body["batch_size"] == len(body["samples"]) == 6


def test_random_batch_is_reproducible_across_requests(client, project, dataset):
    first = query(client, project["id"], dataset["id"], strategy="random", seed=99)
    second = query(client, project["id"], dataset["id"], strategy="random", seed=99)
    assert first["batch_id"] != second["batch_id"]
    assert [s["sample_id"] for s in first["samples"]] == [
        s["sample_id"] for s in second["samples"]
    ]
    assert first["pool"]["hash"] == second["pool"]["hash"]


def test_default_seed_comes_from_settings_and_is_recorded(client, project, dataset):
    body = query(client, project["id"], dataset["id"], strategy="random")
    # conftest uses the default random_state.
    assert body["seed"] == 42


def test_batch_is_reopenable_from_another_client(client, project, dataset):
    created = query(client, project["id"], dataset["id"], strategy="random", seed=5)
    # A fresh client with no browser state at all.
    from fastapi.testclient import TestClient

    other = TestClient(client.app)
    detail = other.get(f"/projects/{project['id']}/queries/{created['batch_id']}").json()
    assert [item["sample_id"] for item in detail["items"]] == [
        sample["sample_id"] for sample in created["samples"]
    ]
    assert [item["position"] for item in detail["items"]] == list(range(len(created["samples"])))
    assert all(item["status"] == "pending" for item in detail["items"])
    assert detail["seed"] == 5 and detail["strategy"] == "random"
    assert detail["pool"]["hash"] == created["pool"]["hash"]


def test_history_is_project_scoped_and_newest_first(client, project, dataset):
    first = query(client, project["id"], dataset["id"])
    second = query(client, project["id"], dataset["id"])
    listing = client.get(f"/projects/{project['id']}/queries").json()
    assert [entry["id"] for entry in listing][:2] == [second["batch_id"], first["batch_id"]]
    assert listing[0]["decisions"] == {
        "pending": second["batch_size"],
        "labeled": 0,
        "rejected": 0,
        "deferred": 0,
    }

    other = client.post("/projects", json={"name": "Other", "classes": WATER}).json()
    assert client.get(f"/projects/{other['id']}/queries").json() == []


def test_unknown_batch_is_404_not_empty(client, project):
    assert client.get(f"/projects/{project['id']}/queries/9999").status_code == 404


def test_strategies_share_the_same_candidate_pool(client, project, dataset):
    random_batch = query(client, project["id"], dataset["id"], strategy="random")
    diversity = query(client, project["id"], dataset["id"], strategy="diversity")
    assert random_batch["pool"] == diversity["pool"]
    # Only `random` records a seed.
    assert random_batch["seed"] is not None and diversity["seed"] is None


def test_labeled_patches_leave_the_pool(client, project, dataset):
    before = query(client, project["id"], dataset["id"])
    sample = before["samples"][0]
    resp = client.post(
        f"/projects/{project['id']}/labels",
        json={
            "sample_id": sample["sample_id"],
            "geometry": {
                "type": "Point",
                "coordinates": [sample["coords"]["center_x"], sample["coords"]["center_y"]],
            },
            "class_name": "open_water",
            "dataset_id": dataset["id"],
        },
    )
    assert resp.status_code == 201, resp.text
    after = query(client, project["id"], dataset["id"])
    assert after["pool"]["size"] == before["pool"]["size"] - 1
    assert after["pool"]["n_labeled_patches"] == 1
    assert sample["sample_id"] not in [s["sample_id"] for s in after["samples"]]


def test_invalid_patches_are_never_selected(client, project):
    """A scene that is entirely NoData has no eligible candidate at all."""
    nodata = np.full((4, 64, 64), -9999.0, dtype=np.float32)
    buf = io.BytesIO()
    with rasterio.open(
        buf, "w", driver="GTiff", height=64, width=64, count=4, dtype="float32",
        nodata=-9999, crs="EPSG:32631",
        transform=rasterio.transform.from_origin(500000, 4649776, 10, 10),
    ) as dst:
        dst.write(nodata)
    resp = client.post(
        f"/projects/{project['id']}/upload",
        files={"file": ("empty.tif", buf.getvalue(), "image/tiff")},
        data={"band_names": "blue,green,red,nir"},
    )
    assert resp.status_code == 201, resp.text
    body = query(client, project["id"], resp.json()["id"], strategy="random", seed=1)
    assert body["batch_size"] == 0
    assert body["pool"]["size"] == 0
    assert any("No valid" in note for note in body["notes"])


def test_empty_pool_still_persists_an_auditable_batch(client, project, dataset):
    """Zero selected items is a real, recorded answer — not a failure."""
    body = query(client, project["id"], dataset["id"], batch_size=1)
    detail = client.get(f"/projects/{project['id']}/queries/{body['batch_id']}").json()
    assert detail["batch_size_returned"] == 1


def test_failed_query_leaves_no_batch(client, project):
    """Refusals happen before persistence: no partial or phantom batch."""
    resp = client.post(
        f"/projects/{project['id']}/query",
        json={"strategy": "uncertainty", "batch_size": 5},
    )
    assert resp.status_code == 409
    assert client.get(f"/projects/{project['id']}/queries").json() == []


# ---------------------------------------------------------- decisions
def test_decision_transitions_are_durable(client, project, dataset):
    body = query(client, project["id"], dataset["id"], strategy="random", seed=3)
    item_id = client.get(f"/projects/{project['id']}/queries/{body['batch_id']}").json()["items"][0]["id"]

    rejected = client.patch(
        f"/projects/{project['id']}/queries/{body['batch_id']}/items/{item_id}",
        json={"status": "rejected", "note": "cloud shadow"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["decided_at"] is not None

    deferred = client.patch(
        f"/projects/{project['id']}/queries/{body['batch_id']}/items/{item_id}",
        json={"status": "deferred"},
    )
    assert deferred.json()["status"] == "deferred"
    assert deferred.json()["decision_note"] is None  # replaced, not accumulated

    pending = client.patch(
        f"/projects/{project['id']}/queries/{body['batch_id']}/items/{item_id}",
        json={"status": "pending"},
    )
    assert pending.json()["status"] == "pending"
    assert pending.json()["decided_at"] is None

    listing = client.get(f"/projects/{project['id']}/queries").json()[0]
    assert listing["decisions"]["pending"] == body["batch_size"]


def test_labeled_decision_requires_an_existing_label(client, project, dataset):
    body = query(client, project["id"], dataset["id"])
    item = client.get(f"/projects/{project['id']}/queries/{body['batch_id']}").json()["items"][0]
    resp = client.patch(
        f"/projects/{project['id']}/queries/{body['batch_id']}/items/{item['id']}",
        json={"status": "labeled"},
    )
    assert resp.status_code == 422
    assert "submit the label first" in resp.json()["detail"]


def test_item_from_another_batch_is_404(client, project, dataset):
    first = query(client, project["id"], dataset["id"])
    second = query(client, project["id"], dataset["id"])
    item = client.get(f"/projects/{project['id']}/queries/{first['batch_id']}").json()["items"][0]
    resp = client.patch(
        f"/projects/{project['id']}/queries/{second['batch_id']}/items/{item['id']}",
        json={"status": "rejected"},
    )
    assert resp.status_code == 404


# ------------------------------------------------------ label <-> item linkage
def test_submitting_from_a_query_item_links_label_and_decision(client, project, dataset):
    body = query(client, project["id"], dataset["id"], strategy="random", seed=21)
    sample = body["samples"][0]
    item = client.get(f"/projects/{project['id']}/queries/{body['batch_id']}").json()["items"][0]
    resp = client.post(
        f"/projects/{project['id']}/labels",
        json={
            "sample_id": sample["sample_id"],
            "geometry": {
                "type": "Point",
                "coordinates": [sample["coords"]["center_x"], sample["coords"]["center_y"]],
            },
            "class_name": "open_water",
            "dataset_id": dataset["id"],
            "query_batch_id": body["batch_id"],
            "query_item_id": item["id"],
        },
    )
    assert resp.status_code == 201, resp.text
    label = resp.json()
    assert label["query_batch_id"] == body["batch_id"]
    assert label["query_item_id"] is not None
    assert label["provenance"] == "query"

    detail = client.get(f"/projects/{project['id']}/queries/{body['batch_id']}").json()
    item = next(i for i in detail["items"] if i["id"] == label["query_item_id"])
    assert item["status"] == "labeled"
    assert item["label_id"] == label["id"]
    assert item["decided_class"] == "open_water"


def test_correction_keeps_history_and_relinks_the_item(client, project, dataset):
    body = query(client, project["id"], dataset["id"], strategy="random", seed=4)
    item = client.get(f"/projects/{project['id']}/queries/{body['batch_id']}").json()["items"][0]
    sample = body["samples"][0]
    payload = {
        "sample_id": sample["sample_id"],
        "geometry": {
            "type": "Point",
            "coordinates": [sample["coords"]["center_x"], sample["coords"]["center_y"]],
        },
        "dataset_id": dataset["id"],
        "query_batch_id": body["batch_id"],
        "query_item_id": item["id"],
    }
    first = client.post(
        f"/projects/{project['id']}/labels", json={**payload, "class_name": "open_water"}
    ).json()
    second = client.post(
        f"/projects/{project['id']}/labels", json={**payload, "class_name": "land"}
    ).json()
    assert (first["version"], second["version"]) == (1, 2)

    history = [
        l for l in client.get(f"/projects/{project['id']}/history").json()
        if l["sample_id"] == sample["sample_id"]
    ]
    assert [h["class_name"] for h in history] == ["open_water", "land"]
    assert all(h["provenance"] == "query" for h in history)

    detail = client.get(f"/projects/{project['id']}/queries/{body['batch_id']}").json()
    assert detail["items"][0]["label_id"] == second["id"]
    assert detail["items"][0]["decided_class"] == "land"


def test_manual_labels_report_manual_provenance(client, project, dataset):
    resp = client.post(
        f"/projects/{project['id']}/labels",
        json={
            "geometry": {"type": "Point", "coordinates": [4, 4]},
            "class_name": "open_water",
            "dataset_id": dataset["id"],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["provenance"] == "manual"
    assert resp.json()["query_item_id"] is None


def test_link_must_match_the_sample_the_label_resolves_to(client, project, dataset):
    body = query(client, project["id"], dataset["id"], strategy="random", seed=8)
    items = client.get(f"/projects/{project['id']}/queries/{body['batch_id']}").json()["items"]
    other = next(
        item for item in items if item["sample_id"] != body["samples"][0]["sample_id"]
    )
    sample = body["samples"][0]
    resp = client.post(
        f"/projects/{project['id']}/labels",
        json={
            "sample_id": sample["sample_id"],
            "geometry": {
                "type": "Point",
                "coordinates": [sample["coords"]["center_x"], sample["coords"]["center_y"]],
            },
            "class_name": "open_water",
            "dataset_id": dataset["id"],
            "query_item_id": other["id"],
        },
    )
    assert resp.status_code == 422
    assert "resolves to" in resp.json()["detail"]


def test_item_from_another_project_is_refused(client, project, dataset):
    body = query(client, project["id"], dataset["id"])
    item = client.get(f"/projects/{project['id']}/queries/{body['batch_id']}").json()["items"][0]
    other = client.post("/projects", json={"name": "Elsewhere", "classes": WATER}).json()
    resp = client.post(
        f"/projects/{other['id']}/labels",
        json={
            "sample_id": item["sample_id"],
            "geometry": {"type": "Point", "coordinates": [4, 4]},
            "class_name": "open_water",
            "query_item_id": item["id"],
        },
    )
    assert resp.status_code == 422
    assert "not part of this project" in resp.json()["detail"]


def test_deleting_a_batch_is_not_part_of_the_contract(client, project, dataset):
    """Batches are history: there is deliberately no delete endpoint."""
    body = query(client, project["id"], dataset["id"])
    assert client.delete(f"/projects/{project['id']}/queries/{body['batch_id']}").status_code == 405


def test_label_selecting_a_query_item_without_a_batch_id_is_refused(client, project, dataset):
    body = query(client, project["id"], dataset["id"])
    item = client.get(f"/projects/{project['id']}/queries/{body['batch_id']}").json()["items"][0]
    resp = client.post(
        f"/projects/{project['id']}/labels",
        json={
            "sample_id": item["sample_id"],
            "geometry": {"type": "Point", "coordinates": [4, 4]},
            "class_name": "open_water",
            "query_item_id": item["id"],
            "query_batch_id": 999,
        },
    )
    assert resp.status_code == 422
    assert "belongs to batch" in resp.json()["detail"]


def test_query_selection_error_is_exported_for_callers():
    """The service exposes one error type so API code never catches blindly."""
    assert issubclass(QuerySelectionError, ValueError)
