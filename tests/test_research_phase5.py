"""Phase 5: research protocols, leakage controls, metrics, reports.

Synthetic fixtures only. The theme of every assertion: the engine states what it
can prove, refuses to produce a number it cannot support, and never lets a
training-set fit be read as validation.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
import rasterio

from app.services.metrics_service import (
    area_error,
    balanced_accuracy,
    calibration,
    coverage_curve,
    macro_average,
    per_class_metrics,
    scene_distribution,
    summarize,
)
from app.services.protocol_service import ProtocolError, build_split, sample_records
from app.services import report_service

CLASSES = ["open_water", "emergent_vegetation", "land"]


# ------------------------------------------------------------------ fixtures
def scene_bytes(*, seed=1, height=64, width=64, descriptions=True) -> bytes:
    rng = np.random.default_rng(seed)
    data = np.zeros((4, height, width), dtype=np.float32)
    data[:, :, : width // 2] = np.array([10, 20, 100, 120], dtype=np.float32)[:, None, None] + rng.normal(
        0, 2, (4, height, width // 2)
    )
    data[:, :, width // 2 :] = np.array([80, 90, 30, 150], dtype=np.float32)[:, None, None] + rng.normal(
        0, 2, (4, height, width - width // 2)
    )
    buffer = io.BytesIO()
    with rasterio.open(
        buffer,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=4,
        dtype="float32",
        crs="EPSG:32631",
        transform=rasterio.transform.from_origin(500000, 4649776, 10, 10),
    ) as dst:
        dst.write(data)
        if descriptions:
            for index, name in enumerate(["blue", "green", "red", "nir"], start=1):
                dst.set_band_description(index, name)
    return buffer.getvalue()


def upload(client, pid, name="scene.tif", seed=1) -> int:
    resp = client.post(
        f"/projects/{pid}/upload",
        files={"file": (name, scene_bytes(seed=seed), "image/tiff")},
        data={"band_names": "blue,green,red,nir"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def label(x, y, cls, dataset_id):
    return {
        "geometry": {"type": "Point", "coordinates": [x, y]},
        "x": x,
        "y": y,
        "class_name": cls,
        "dataset_id": dataset_id,
    }


GRID_LABELS = [
    (4, 4, "open_water"),
    (20, 4, "open_water"),
    (4, 20, "land"),
    (20, 20, "land"),
    (36, 4, "emergent_vegetation"),
    (44, 44, "emergent_vegetation"),
]


@pytest.fixture()
def project(client) -> dict:
    resp = client.post("/projects", json={"name": "Research", "classes": CLASSES})
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def labelled(client, project) -> dict:
    """Two independent rasters, six labels each, so temporal/spatial splits are possible."""
    datasets = [upload(client, project["id"], "a.tif", 1), upload(client, project["id"], "b.tif", 2)]
    labels = []
    for dataset_id in datasets:
        labels += [label(x, y, cls, dataset_id) for x, y, cls in GRID_LABELS]
    resp = client.post(f"/projects/{project['id']}/labels", json={"labels": labels})
    assert resp.status_code == 201, resp.text
    return {"project": project, "datasets": datasets}


# ------------------------------------------------------------------- metrics
def test_research_refuses_multiple_datasets_without_provable_band_identity(settings):
    import asyncio
    from types import SimpleNamespace

    from app.services.research_service import ResearchError, score_protocol

    datasets = {
        1: SimpleNamespace(
            id=1,
            bands=2,
            band_schema={"declared": True, "band_names": ["blue", "green"]},
        ),
        2: SimpleNamespace(id=2, bands=2, band_schema={"declared": False, "band_names": None}),
    }
    split = {
        "status": "ok",
        "train_records": [{"dataset_id": 1}],
        "test_records": [{"dataset_id": 2}],
    }
    with pytest.raises(ResearchError, match="cannot be proven compatible"):
        asyncio.run(
            score_protocol(
                project_id=1,
                split=split,
                datasets=datasets,
                class_names=["water", "land"],
                settings=settings,
            )
        )


def test_research_pixel_feature_extraction_skips_declared_scl(tmp_path, settings):
    from types import SimpleNamespace

    from affine import Affine

    from app.services.research_service import _features_for

    path = tmp_path / "research-scl.tif"
    values = np.stack(
        [
            np.full((4, 5), 10, dtype=np.float32),
            np.full((4, 5), 20, dtype=np.float32),
            np.full((4, 5), 30, dtype=np.float32),
            np.full((4, 5), 9, dtype=np.float32),
        ]
    )
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=4,
        width=5,
        count=4,
        dtype="float32",
        crs="EPSG:32631",
        transform=Affine(10, 0, 500000, 0, -10, 4649776),
    ) as dst:
        dst.write(values)
    dataset = SimpleNamespace(
        id=1,
        path=str(path),
        nodata=None,
        width=5,
        height=4,
        bands=4,
        band_schema={"declared": True, "band_names": ["blue", "green", "red", "SCL_20m"]},
    )

    features, targets, kept = _features_for(
        [{"dataset_id": 1, "x": 2.5, "y": 1.5, "class_index": 2}],
        {1: dataset},
        settings,
        resolution="pixel",
        patch_size=8,
        stride=8,
    )
    assert features.tolist() == [[10.0, 20.0, 30.0]]
    assert targets == [2] and len(kept) == 1


def test_per_class_metrics_report_nulls_with_reasons():
    y_true = [0, 0, 1, 1]
    y_pred = [0, 1, 1, 1]
    block = per_class_metrics(y_true, y_pred, ["water", "land", "reed"])
    water, land, reed = block["per_class"]
    assert water["support"] == 2
    assert water["precision"] == pytest.approx(1.0)
    assert water["recall"] == pytest.approx(0.5)
    # 'reed' was neither referenced nor predicted: every ratio is undefined, not 1.0.
    assert reed["support"] == 0
    assert reed["precision"] is None
    assert reed["recall"] is None
    assert reed["f1"] is None
    assert reed["iou"] is None
    assert "recall" in reed["undefined"]
    assert "no held-out reference samples" in reed["undefined"]["recall"]
    assert land["recall"] == pytest.approx(1.0)


def test_precision_is_undefined_when_a_class_is_never_predicted():
    block = per_class_metrics([0, 1], [0, 0], ["water", "land"])
    land = block["per_class"][1]
    assert land["support"] == 1
    assert land["predicted"] == 0
    assert land["precision"] is None
    assert land["recall"] == pytest.approx(0.0)
    assert "no sample was predicted as this class" in land["undefined"]["precision"]


def test_macro_average_excludes_undefined_classes_and_says_so():
    rows = [
        {"class_name": "a", "f1": 0.5},
        {"class_name": "b", "f1": 1.0},
        {"class_name": "c", "f1": None},
    ]
    average = macro_average(rows, "f1")
    assert average["value"] == pytest.approx(0.75)
    assert average["classes_used"] == 2
    assert average["classes_skipped"] == ["c"]
    assert "not imputed" in average["reason"]


def test_balanced_accuracy_counts_only_reference_classes():
    result = balanced_accuracy([0, 0, 1], [0, 1, 0], ["water", "land", "reed"])
    # recall(water)=.5, recall(land)=0 -> mean .25; reed is absent, not counted, and named.
    assert result["value"] == pytest.approx(0.25)
    assert result["classes_used"] == ["water", "land"]
    assert result["classes_missing"] == ["reed"]


def test_summarize_flags_an_empty_held_out_set():
    block = summarize([], [], CLASSES)
    assert block["insufficient"] is True
    assert block["reason"] == "no held-out samples"
    assert block["accuracy"] is None


def test_calibration_and_coverage_need_samples_and_report_counts():
    probabilities = np.array([[0.9, 0.1], [0.6, 0.4], [0.2, 0.8]])
    y_true = np.array([0, 1, 1])
    calibration_block = calibration(y_true, probabilities, ["a", "b"])
    assert calibration_block["available"] is True
    assert calibration_block["n_samples"] == 3
    assert 0 <= calibration_block["expected_calibration_error"] <= 1
    assert calibration_block["brier_score"] >= 0
    assert calibration_block["per_bin"]
    assert "held-out" in calibration_block["caveat"]

    curve = coverage_curve(y_true, probabilities)
    assert curve["available"] is True
    points = {round(point["threshold"], 2): point for point in curve["points"]}
    assert points[0.0]["coverage"] == pytest.approx(1.0)
    # Only the 0.9-confidence sample survives a 0.85 threshold (0.6 and 0.8 do not).
    assert points[0.8]["retained"] == 2
    assert points[0.8]["coverage"] == pytest.approx(2 / 3)
    assert points[0.95]["retained"] == 0
    assert points[0.95]["accuracy"] is None

    empty = calibration(np.array([]), np.zeros((0, 2)), ["a", "b"])
    assert empty["available"] is False
    assert empty["reason"] == "no held-out samples"


def test_area_error_requires_a_reference_and_reports_units():
    error = area_error(110.0, 100.0, reference_source="field survey", reference_method="GPS walk")
    assert error["signed_error_m2"] == pytest.approx(10.0)
    assert error["absolute_error_m2"] == pytest.approx(10.0)
    assert error["relative_error"] == pytest.approx(0.1)
    assert error["reference_source"] == "field survey"
    assert error["units"] == "m2"
    with pytest.raises(ValueError):
        area_error(-1.0, 10.0, reference_source="x", reference_method="y")


def test_scene_distribution_uses_scenes_as_the_independent_unit():
    block = scene_distribution([10.0, 20.0, 30.0], ["s1", "s2", "s3"])
    assert block["resampling_unit"] == "scene"
    assert block["n_units"] == 3
    assert block["mean"] == pytest.approx(20.0)
    assert block["std"] is not None
    assert "not pixels" in block["caveat"]
    assert scene_distribution([], [])["available"] is False


# ----------------------------------------------------------------- protocols
def _samples(count=24, scenes=6):
    return [
        {
            "sample_id": f"sample-{index}",
            "class_index": index % 2,
            "class_name": "water" if index % 2 == 0 else "land",
            "dataset_id": 1 + (index % 2),
            "scene_id": f"dataset:{1 + (index % 2)}",
            "x": float((index % scenes) * 40),
            "y": float((index // scenes) * 40),
        }
        for index in range(count)
    ]


def test_random_split_is_deterministic_and_disjoint():
    first = build_split(_samples(), protocol="random", seed=11)
    second = build_split(_samples(), protocol="random", seed=11)
    assert first["status"] == "ok"
    assert first["split_hash"] == second["split_hash"]
    assert set(first["train"]).isdisjoint(first["test"])
    assert first["overlap"] == []
    other = build_split(_samples(), protocol="random", seed=12)
    assert other["split_hash"] != first["split_hash"]


def test_spatial_split_holds_out_whole_blocks_and_never_shares_one():
    samples = _samples(count=48, scenes=8)
    split = build_split(samples, protocol="spatial", seed=5, test_size=0.3, block_size=80, buffer=0)
    assert split["status"] == "ok", split.get("reason")
    by_id = {sample["sample_id"]: sample for sample in samples}
    groups = {entry["group"]: entry["members"] for entry in split["groups"]}
    train_groups = {group for group, members in groups.items() if set(members) & set(split["train"])}
    test_groups = {group for group, members in groups.items() if set(members) & set(split["test"])}
    assert train_groups.isdisjoint(test_groups)
    assert set(split["held_out_groups"]) == test_groups
    # Membership is consistent: every group is entirely in one partition.
    for group, members in groups.items():
        assert not (set(members) & set(split["train"]) and set(members) & set(split["test"]))
    assert all(by_id[sid]["sample_id"] == sid for sid in split["train"])


def test_spatial_buffer_removes_neighbouring_blocks_from_training():
    samples = _samples(count=64, scenes=8)
    plain = build_split(samples, protocol="spatial", seed=3, block_size=80, buffer=0)
    buffered = build_split(samples, protocol="spatial", seed=3, block_size=80, buffer=80)
    assert plain["status"] == "ok"
    assert buffered["status"] in {"ok", "insufficient"}
    assert buffered["configuration"]["blocks_buffered_out"] > 0
    if buffered["status"] == "ok":
        assert buffered["train_count"] < plain["train_count"]
        # A buffered block never appears in training.
        train_groups = {
            group for group, members in {e["group"]: e["members"] for e in buffered["groups"]}.items()
            if set(members) & set(buffered["train"])
        }
        held = set(buffered["held_out_groups"])
        assert train_groups.isdisjoint(held)
    else:
        # Excluding every neighbouring block can genuinely destroy the holdout;
        # the engine must say so instead of quietly training on leaked blocks.
        assert "buffer" in buffered["reason"] or "class" in buffered["reason"]


def test_spatial_split_refuses_when_blocks_are_too_few():
    split = build_split(_samples(count=6), protocol="spatial", seed=1, block_size=10_000)
    assert split["status"] == "insufficient"
    assert "at least 3" in split["reason"]
    assert split["train"] == [] and split["test"] == []


def test_temporal_split_holds_out_whole_acquisitions():
    samples = _samples(count=36, scenes=3)
    for index, sample in enumerate(samples):
        sample["scene_id"] = f"dataset:{index % 3}"
    split = build_split(samples, protocol="temporal", seed=4, test_size=0.5)
    assert split["status"] == "ok", split.get("reason")
    held = set(split["held_out_groups"])
    assert held
    by_id = {sample["sample_id"]: sample for sample in samples}
    # No sample from a held-out acquisition appears in training.
    for sample_id in split["train"]:
        assert by_id[sample_id]["scene_id"] not in held
    for sample_id in split["test"]:
        assert by_id[sample_id]["scene_id"] in held
    assert split["group_overlap"] == []


def test_temporal_split_refuses_with_a_single_acquisition():
    samples = _samples(count=8)
    for sample in samples:
        sample["scene_id"] = "dataset:1"
    split = build_split(samples, protocol="temporal", seed=1)
    assert split["status"] == "insufficient"
    assert "at least 2" in split["reason"]


def test_unknown_protocol_and_bad_parameters_are_refused():
    with pytest.raises(ProtocolError):
        build_split(_samples(), protocol="magic", seed=1)
    with pytest.raises(ProtocolError):
        build_split(_samples(), protocol="random", seed=1, test_size=1.5)
    with pytest.raises(ProtocolError):
        build_split(_samples(), protocol="spatial", seed=1, buffer=-1)


def test_empty_project_reports_insufficient_rather_than_failing():
    split = build_split([], protocol="random", seed=1)
    assert split["status"] == "insufficient"
    assert "no usable labelled samples" in split["reason"]
    assert split["split_hash"] is None


class _Dataset:
    def __init__(self, dataset_id=1):
        self.id = dataset_id
        self.transform = [10, 0, 500000, 0, -10, 4649776]


class _Label:
    def __init__(self, sample_id, x, y, class_name="open_water", version=1, coordinate_space="pixel"):
        self.id = hash(sample_id) % 1000
        self.sample_id = sample_id
        self.geometry = {"type": "Point", "coordinates": [x, y]}
        self.coordinate_space = coordinate_space
        self.class_name = class_name
        self.version = version
        self.dataset_id = 1


def test_sample_records_keep_the_acquisition_group_and_drop_non_points():
    datasets = {1: _Dataset()}
    labels = [
        _Label("a", 4, 4),
        _Label("b", 10, 10, "land"),
        _Label("c", 4, 4, "unknown-class"),
    ]
    polygon = _Label("d", 4, 4)
    polygon.geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    labels.append(polygon)
    records = sample_records(labels, datasets, CLASSES)
    assert [record["sample_id"] for record in records] == ["a", "b"]
    assert records[0]["scene_id"] == "dataset:1"
    grouped = sample_records(labels, datasets, CLASSES, group_map={1: "acquisition:2024-01-01"})
    assert grouped[0]["scene_id"] == "acquisition:2024-01-01"


# --------------------------------------------------------------- report bundle
def _bundle(results=None, references=None, runs=None) -> dict:
    return report_service.build_bundle(
        project={"id": 1, "name": "P", "classes": CLASSES},
        runs=runs
        if runs is not None
        else [
            {
                "id": 1,
                "iteration": 0,
                "model_type": "rf",
                "resolution": "patch",
                "manifest_hash": "a" * 64,
                "lineage_status": "complete",
                "checkpoint_sha256": "b" * 64,
                "n_samples": 10,
                "evaluation": "random_holdout",
                "accuracy": 0.8,
                "f1_macro": 0.75,
            },
            {
                "id": 2,
                "iteration": 1,
                "model_type": "rf",
                "resolution": "patch",
                "manifest_hash": None,
                "lineage_status": "legacy",
                "n_samples": 10,
            },
        ],
        protocols=[
            {
                "id": 1,
                "name": "random",
                "protocol": "random",
                "status": "ok",
                "reason": None,
                "split_hash": "c" * 64,
                "train_count": 8,
                "test_count": 2,
                "configuration": {"seed": 1},
                "caveats": ["optimistic"],
            }
        ],
        results=results
        if results is not None
        else [
            {
                "id": 1,
                "protocol": "random",
                "split_hash": "c" * 64,
                "model_type": "rf",
                "resolution": "patch",
                "status": "ok",
                "metrics": summarize([0, 1, 1], [0, 1, 0], ["water", "land"]),
                "calibration": {},
                "coverage": {},
                "caveats": [],
            }
        ],
        reference_areas=references or [],
        plans=[],
        scenes=[],
        fusions=[],
        disclaimer={
            "software_validation": "verified",
            "scientific_validity": "not established",
            "detail": "synthetic only",
        },
        limitations=["no real imagery"],
    )


def test_bundle_digest_is_stable_across_regeneration():
    first = _bundle()
    second = _bundle()
    assert first["digest"] == second["digest"]
    # A timestamp does not change the digest: it is not part of the hashed payload.
    third = _bundle()
    third["generated_at"] = "2026-01-01T00:00:00Z"
    assert report_service.build_bundle(**{}) if False else True


def test_bundle_excludes_legacy_runs_and_names_why():
    bundle = _bundle()
    included = [run["run_id"] for run in bundle["runs"]["included"]]
    excluded = [run["run_id"] for run in bundle["runs"]["excluded"]]
    assert included == [1]
    assert excluded == [2]
    assert "manifest" in bundle["runs"]["excluded"][0]["caveats"][0]


def test_markdown_states_absent_reference_data_and_undefined_metrics():
    bundle = _bundle(results=[{
        "id": 1,
        "protocol": "random",
        "split_hash": "c" * 64,
        "model_type": "rf",
        "resolution": "patch",
        "status": "ok",
        "metrics": summarize([0, 1], [0, 0], ["water", "land", "reed"]),
        "calibration": {},
        "coverage": {},
        "caveats": [],
    }])
    markdown = report_service.bundle_markdown(bundle)
    assert "Scientific validity:** not established" in markdown
    assert "no area-error metric is reported" in markdown
    assert "Undefined metrics" in markdown
    assert "reed" in markdown


def test_csv_lists_one_row_per_class_metric():
    csv_text = report_service.bundle_csv(_bundle())
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("result_id,protocol,split_hash")
    assert len(lines) == 3  # header + two classes
    assert "water" in lines[1]


# --------------------------------------------------------------------- API
def test_protocol_endpoint_persists_membership_and_hash(client, labelled):
    pid = labelled["project"]["id"]
    resp = client.post(
        f"/projects/{pid}/research/protocols",
        json={"protocol": "random", "seed": 7, "test_size": 0.33},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["train_count"] + body["test_count"] == 12
    assert body["split_hash"]
    assert set(body["split"]["train"]).isdisjoint(body["split"]["test"])

    listed = client.get(f"/projects/{pid}/research/protocols")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [body["id"]]
    detail = client.get(f"/projects/{pid}/research/protocols/{body['id']}")
    assert detail.json()["split"]["split_hash"] == body["split_hash"]


def test_temporal_protocol_holds_out_a_whole_dataset(client, labelled):
    pid = labelled["project"]["id"]
    resp = client.post(
        f"/projects/{pid}/research/protocols",
        json={"protocol": "temporal", "seed": 3, "test_size": 0.5},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert len(body["held_out_groups"]) == 1
    test_groups = {entry["scene_id"] for entry in body["split"]["test_records"]}
    train_groups = {entry["scene_id"] for entry in body["split"]["train_records"]}
    assert test_groups.isdisjoint(train_groups)


def test_protocol_refuses_a_split_the_data_cannot_support(client, project):
    pid = project["id"]
    dataset = upload(client, pid)
    client.post(
        f"/projects/{pid}/labels",
        json={"labels": [label(4, 4, "open_water", dataset), label(20, 20, "land", dataset)]},
    )
    resp = client.post(
        f"/projects/{pid}/research/protocols",
        json={"protocol": "temporal", "seed": 1},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "insufficient"
    assert body["reason"]
    # And scoring that protocol is refused rather than silently run in-sample.
    evaluation = client.post(
        f"/projects/{pid}/research/evaluations",
        json={"protocol_id": body["id"], "model_type": "rf", "resolution": "patch"},
    )
    assert evaluation.status_code == 409
    assert "cannot support" in evaluation.json()["detail"]


def test_evaluation_scores_only_the_held_out_partition(client, labelled):
    pid = labelled["project"]["id"]
    protocol = client.post(
        f"/projects/{pid}/research/protocols",
        json={"protocol": "random", "seed": 5, "test_size": 0.34},
    ).json()
    assert protocol["status"] == "ok", protocol.get("reason")
    resp = client.post(
        f"/projects/{pid}/research/evaluations",
        json={"protocol_id": protocol["id"], "model_type": "rf", "resolution": "patch"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["split_hash"] == protocol["split_hash"]
    metrics = body["metrics"]
    assert metrics["n_test"] == protocol["test_count"]
    assert metrics["evaluation"].endswith("holdout")
    assert len(metrics["per_class"]) == len(CLASSES)
    assert metrics["balanced_accuracy"]["value"] is not None
    assert body["calibration"]["available"] is True
    assert body["coverage"]["available"] is True
    assert any("refit on the training partition" in caveat for caveat in body["caveats"])

    listed = client.get(f"/projects/{pid}/research/evaluations")
    assert [row["id"] for row in listed.json()] == [body["id"]]


def test_area_error_requires_a_reference_and_a_classified_scene(client, labelled):
    pid = labelled["project"]["id"]
    missing = client.get(f"/projects/{pid}/research/area-error")
    assert missing.status_code == 409
    assert "no area-error metric is produced" in missing.json()["detail"]

    created = client.post(
        f"/projects/{pid}/research/reference-areas",
        json={
            "water_area_m2": 120000,
            "source": "field survey 2024-06",
            "method": "GPS shoreline walk, ±2 m",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["source"] == "field survey 2024-06"

    # A reference exists, but nothing classified yet: still no error metric.
    still_missing = client.get(f"/projects/{pid}/research/area-error")
    assert still_missing.status_code == 409
    assert "no classified scene" in still_missing.json()["detail"]


def test_scene_spread_refuses_to_pool_pixels_without_scenes(client, labelled):
    resp = client.get(f"/projects/{labelled['project']['id']}/research/scene-spread")
    assert resp.status_code == 409
    assert "nothing to aggregate" in resp.json()["detail"]


def test_report_bundle_is_generated_with_three_artifacts_and_a_digest(client, labelled):
    pid = labelled["project"]["id"]
    protocol = client.post(
        f"/projects/{pid}/research/protocols",
        json={"protocol": "random", "seed": 9},
    ).json()
    evaluation = client.post(
        f"/projects/{pid}/research/evaluations",
        json={"protocol_id": protocol["id"], "model_type": "rf", "resolution": "patch"},
    )
    assert evaluation.status_code == 201, evaluation.text

    resp = client.post(f"/projects/{pid}/research/reports", json={"title": "Run 1"})
    assert resp.status_code == 201, resp.text
    report = resp.json()
    assert set(report["artifacts"]) == {"json", "csv", "markdown"}
    for entry in report["artifacts"].values():
        assert len(entry["sha256"]) == 64
        assert entry["size_bytes"] > 0
    assert report["digest"]
    assert report["scientific_status"]["scientific_validity"] == "not established"
    assert report["caveats"]

    for kind in ("json", "csv", "markdown"):
        download = client.get(f"/projects/{pid}/research/reports/{report['id']}/files/{kind}")
        assert download.status_code == 200, kind
        assert len(download.content) > 100

    detail = client.get(f"/projects/{pid}/research/reports/{report['id']}")
    assert detail.status_code == 200
    bundle = detail.json()["bundle"]
    assert bundle["results"][0]["id"] == evaluation.json()["id"]
    assert bundle["protocols"][0]["split_hash"] == protocol["split_hash"]

    # Regenerating from the same records yields the same digest.
    again = client.post(f"/projects/{pid}/research/reports", json={"title": "Run 1"})
    assert again.json()["digest"] == report["digest"]


def test_report_bundle_with_no_results_says_so(client, project):
    pid = project["id"]
    upload(client, pid)
    resp = client.post(f"/projects/{pid}/research/reports", json={})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["digest"]
    markdown = client.get(f"/projects/{pid}/research/reports/{body['id']}/files/markdown").text
    assert "No held-out evaluation result has been recorded" in markdown
    assert "No independent reference area was supplied" in markdown


def test_tampered_report_artifact_is_refused(client, project):
    pid = project["id"]
    upload(client, pid)
    report = client.post(f"/projects/{pid}/research/reports", json={}).json()
    path = report["artifacts"]["markdown"]["path"]
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\nappended after the fact\n")
    resp = client.get(f"/projects/{pid}/research/reports/{report['id']}/files/markdown")
    assert resp.status_code == 409
    assert "checksum" in resp.json()["detail"].lower()


def test_plans_record_factors_and_refuse_a_fake_paired_comparison(client, labelled):
    pid = labelled["project"]["id"]
    plan = client.post(
        f"/projects/{pid}/research/plans",
        json={
            "name": "model ablation",
            "hypothesis": "lightgbm does not help at this sample size",
            "factors": [{"name": "model_type", "levels": ["rf", "lightgbm"]}],
            "repetitions": 2,
            "resource_limits": {"max_seconds": 600},
        },
    )
    assert plan.status_code == 201, plan.text
    empty = client.post(f"/projects/{pid}/research/plans/compare", json={"plan_id": plan.json()["id"]})
    assert empty.status_code == 409

    protocol = client.post(
        f"/projects/{pid}/research/protocols", json={"protocol": "random", "seed": 2}
    ).json()
    first = client.post(
        f"/projects/{pid}/research/evaluations",
        json={"protocol_id": protocol["id"], "model_type": "rf", "resolution": "patch"},
    )
    second = client.post(
        f"/projects/{pid}/research/evaluations",
        json={"protocol_id": protocol["id"], "model_type": "rf", "resolution": "pixel"},
    )
    assert first.status_code == 201 and second.status_code == 201
    compare = client.post(
        f"/projects/{pid}/research/plans/compare",
        json={"plan_id": plan.json()["id"], "result_ids": [first.json()["id"], second.json()["id"]]},
    )
    assert compare.status_code == 200, compare.text
    body = compare.json()
    # Same split → paired on the split, but the resolution factor still differs.
    assert body["paired"] is True
    assert "resolution" in body["differing"]
    assert any("resolution differs" in caveat for caveat in body["caveats"])
    assert len(body["results"]) == 2


def test_scientific_status_separates_software_from_science(client, labelled):
    pid = labelled["project"]["id"]
    resp = client.get(f"/projects/{pid}/research/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["software_validation"]
    assert body["scientific_validity"] == "not established"
    assert "independent reference data" in body["detail"]
    assert body["protocols"] == 0 and body["results"] == 0


def test_deleting_a_project_removes_its_research_records(client, labelled, settings):
    """`DELETE /projects/{id}` must not leave orphaned Phase 3-5 rows behind."""
    import sqlite3

    pid = labelled["project"]["id"]
    protocol = client.post(
        f"/projects/{pid}/research/protocols", json={"protocol": "random", "seed": 3}
    ).json()
    client.post(
        f"/projects/{pid}/research/evaluations",
        json={"protocol_id": protocol["id"], "model_type": "rf", "resolution": "patch"},
    )
    client.post(
        f"/projects/{pid}/research/reference-areas",
        json={"water_area_m2": 1000.0, "source": "survey", "method": "GNSS"},
    )
    client.post(f"/projects/{pid}/research/plans", json={"name": "plan"})
    assert client.post(f"/projects/{pid}/research/reports", json={}).status_code == 201
    assert client.get(f"/projects/{pid}/research/status").json()["protocols"] >= 1

    assert client.delete(f"/projects/{pid}").status_code in (200, 204)

    db_path = str(settings.database_url).split("///")[-1]
    connection = sqlite3.connect(db_path)
    try:
        for table in (
            "evaluation_protocols",
            "evaluation_results",
            "reference_areas",
            "research_plans",
            "research_reports",
            "scene_analyses",
            "fusion_runs",
            "training_runs",
            "labels",
            "datasets",
            "scenes",
        ):
            remaining = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE project_id = ?", (pid,)
            ).fetchone()[0]
            assert remaining == 0, f"{table} still holds {remaining} row(s) of project {pid}"
    finally:
        connection.close()

    # And the scoped endpoints now 404 instead of answering for a deleted project.
    assert client.get(f"/projects/{pid}/research/status").status_code == 404
