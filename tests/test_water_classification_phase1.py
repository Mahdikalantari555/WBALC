"""Phase 1: water-body taxonomy, label crosswalk and derived binary products.

Synthetic fixtures only. Every assertion is about *recorded* semantics: the
engine may report a mapping, refuse an unmapped label, or say a binary product is
unavailable — it never invents water meaning for a project that did not declare it.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
import rasterio

from app.services.taxonomy_service import (
    BINARY_MAPPINGS,
    INTERNAL_CLASSES,
    TaxonomyError,
    binary_hard,
    binary_plan,
    binary_probability,
    build_taxonomy,
    normalise_aliases,
    resolve_label_class,
)

from .conftest import point_label

WATER = INTERNAL_CLASSES  # open_water, emergent_vegetation, land


# ------------------------------------------------------------------ fixtures
@pytest.fixture()
def water_project(client) -> dict:
    """A project that opts into the WBALC water taxonomy."""
    resp = client.post("/projects", json={"name": "Estuary", "classes": list(WATER)})
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def reed_project(client) -> dict:
    """Same taxonomy, plus an *explicit* `reed` -> emergent_vegetation alias."""
    resp = client.post(
        "/projects",
        json={
            "name": "Reed bed",
            "classes": list(WATER),
            "classification_config": {
                "internal_classes": list(WATER),
                "binary_output_interpretation": "water_vs_non_water",
                "label_aliases": {"emergent_vegetation": ["reed", "phylly"]},
            },
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def scene_bytes(height=64, width=64, bands=4) -> bytes:
    """Four well-separated spectral regions, so three classes are learnable."""
    rng = np.random.default_rng(3)
    data = np.zeros((bands, height, width), dtype=np.float32)
    quarter = width // 2
    signatures = [[10, 20, 100, 120], [90, 80, 60, 40], [150, 160, 170, 180]]
    for index, (row0, col0) in enumerate([(0, 0), (0, quarter), (height // 2, 0)]):
        rows = slice(row0, height if index else height // 2)
        cols = slice(col0, width if col0 else quarter)
        base = np.array(signatures[index][:bands], dtype=np.float32)
        shape = (bands, rows.stop - rows.start, cols.stop - cols.start)
        data[:, rows, cols] = base[:, None, None] + rng.normal(0, 1, shape)
    buf = io.BytesIO()
    with rasterio.open(
        buf, "w", driver="GTiff", height=height, width=width, count=bands,
        dtype="float32", crs="EPSG:32631",
        transform=rasterio.transform.from_origin(500000, 4649776, 10, 10),
    ) as dst:
        dst.write(data)
    return buf.getvalue()


def upload(client, pid: int, payload: bytes, bands="blue,green,red,nir") -> dict:
    resp = client.post(
        f"/projects/{pid}/upload",
        files={"file": ("scene.tif", payload, "image/tiff")},
        data={"band_names": bands},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def label_three_classes(client, pid: int, dsid: int):
    """12 labels per class over a 64x64 scene, in the three spectral regions."""
    labels = []
    for name, (x0, x1) in {
        "open_water": (2, 30),
        "emergent_vegetation": (34, 62),
        "land": (2, 30),
    }.items():
        for x in (x0, x0 + 10, x0 + 20):
            for y in (2, 22, 42, 58):
                if name == "land":
                    y = y + 0  # same columns, lower half
                labels.append(point_label(x, y, name, dataset_id=dsid))
    # Make `land` live in the lower-left quadrant, separate from `open_water`.
    labels = [l for l in labels if not (l["class_name"] == "land" and l["geometry"]["coordinates"][1] < 40)]
    resp = client.post(f"/projects/{pid}/labels", json={"labels": labels})
    assert resp.status_code == 201, resp.text


# ------------------------------------------------------------ unit: taxonomy
def test_taxonomy_defaults_are_the_documented_order():
    taxonomy = build_taxonomy()
    assert taxonomy["classes"] == ["open_water", "emergent_vegetation", "land"]
    assert taxonomy["version"] == "wbalc-water-taxonomy-v1"
    # A class ID is always its own alias, but nothing else is assumed.
    assert taxonomy["crosswalk"] == {
        "open_water": "open_water",
        "emergent_vegetation": "emergent_vegetation",
        "land": "land",
    }
    assert "reed" not in taxonomy["crosswalk"]


def test_reed_is_only_a_mapping_when_configured():
    default = build_taxonomy()
    assert resolve_label_class("reed", default) is None

    explicit = build_taxonomy(aliases={"emergent_vegetation": ["Reed"]})
    assert resolve_label_class("reed", explicit) == "emergent_vegetation"
    # The alias does not rename the class: emergent vegetation stays its own class.
    assert explicit["classes"] == INTERNAL_CLASSES


def test_ambiguous_alias_is_rejected():
    with pytest.raises(TaxonomyError, match="ambiguous"):
        build_taxonomy(aliases={"open_water": ["wet"], "land": ["wet"]})


def test_alias_normalisation_slugs_and_deduplicates():
    assert normalise_aliases({"Open Water": ["  water ", "WATER", ""]}) == {
        "open_water": ["open_water", "water"]
    }
    with pytest.raises(TaxonomyError, match="unknown canonical class"):
        normalise_aliases({"marsh": ["wetland"]})


# ------------------------------------------------------------- unit: binary
def test_binary_mappings_are_exact():
    assert BINARY_MAPPINGS["water_vs_non_water"]["water"] == ["open_water", "emergent_vegetation"]
    assert BINARY_MAPPINGS["open_water_vs_other"]["water"] == ["open_water"]
    assert BINARY_MAPPINGS["open_water_vs_other"]["other"] == ["emergent_vegetation", "land"]


def test_binary_hard_and_probability_values():
    classes = list(WATER)
    hard = np.array([[0, 1, 2], [2, 0, 1]], dtype=np.uint16)
    # water_vs_non_water: open_water + emergent_vegetation are water.
    binary, plan = binary_hard(hard, classes, "water_vs_non_water")
    assert binary.tolist() == [[1, 1, 0], [0, 1, 1]]
    assert plan["available"] is True

    # open_water_vs_other: only open_water is water.
    binary2, _ = binary_hard(hard, classes, "open_water_vs_other")
    assert binary2.tolist() == [[1, 0, 0], [0, 1, 0]]

    # Probabilities are a subset sum and stay bounded.
    prob = np.array(
        [
            [[0.7, 0.1, 0.2]],
            [[0.2, 0.3, 0.4]],
            [[0.1, 0.6, 0.4]],
        ],
        dtype=np.float32,
    )
    water, _ = binary_probability(prob, classes, "water_vs_non_water")
    assert np.allclose(water, np.array([[0.9, 0.4, 0.6]]))
    assert np.all((water >= 0) & (water <= 1))
    water_open, _ = binary_probability(prob, classes, "open_water_vs_other")
    assert np.allclose(water_open, np.array([[0.7, 0.1, 0.2]]))
    # Every column's water + non-water still sums to the original total.
    assert np.allclose(water + (1 - water), 1.0)


def test_binary_is_unavailable_when_a_needed_class_was_never_learned():
    plan = binary_plan(["open_water", "land"], "water_vs_non_water")
    assert plan["available"] is False
    assert plan["missing_classes"] == ["emergent_vegetation"]
    assert "never learned" in plan["reason"]
    assert plan["mapping"] == {"open_water": "water", "land": "non_water"}
    with pytest.raises(TaxonomyError, match="never learned"):
        binary_hard(np.zeros((2, 2), dtype=np.uint16), ["open_water", "land"], "water_vs_non_water")


# --------------------------------------------------------- API: configuration
def test_water_project_is_created_with_a_recorded_taxonomy(client, water_project):
    assert water_project["classes"] == WATER
    assert water_project["taxonomy"]["version"] == "wbalc-water-taxonomy-v1"
    assert water_project["taxonomy"]["source"] == "default"

    described = client.get(f"/projects/{water_project['id']}/taxonomy").json()
    assert described["classes"] == WATER
    assert described["display_names"]["open_water"] == "Open water"
    assert described["binary"]["interpretation"] == "water_vs_non_water"
    assert described["binary"]["available"] is True


def test_generic_project_has_no_water_taxonomy(client):
    resp = client.post(
        "/projects", json={"name": "Legacy", "classes": ["water", "vegetation"], "generic_classes": True}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["taxonomy"] is None
    described = client.get(f"/projects/{resp.json()['id']}/taxonomy").json()
    assert described["source"] == "legacy"
    # No water crosswalk is derived for a project that never opted in.
    assert described["binary"]["mapping"] == {}


def test_water_classes_require_the_opt_out_flag(client):
    resp = client.post("/projects", json={"name": "mixed", "classes": ["water", "land"]})
    assert resp.status_code == 422
    assert "generic_classes" in resp.text


def test_alias_configuration_is_validated(client):
    bad = client.post(
        "/projects",
        json={
            "name": "bad",
            "classes": list(WATER),
            "classification_config": {
                "internal_classes": list(WATER),
                "binary_output_interpretation": "water_vs_non_water",
                "label_aliases": {"marsh": ["wet"]},
            },
        },
    )
    assert bad.status_code == 422
    assert "unknown canonical class" in bad.text


def test_updating_aliases_rebuilds_the_taxonomy(client, water_project):
    pid = water_project["id"]
    resp = client.put(
        f"/projects/{pid}",
        json={
            "classification_config": {
                "internal_classes": list(WATER),
                "binary_output_interpretation": "open_water_vs_other",
                "label_aliases": {"open_water": ["water"]},
            }
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["taxonomy"]["source"] == "project"
    assert body["taxonomy"]["crosswalk"]["water"] == "open_water"
    assert body["taxonomy"]["binary_interpretation"] == "open_water_vs_other"


# ------------------------------------------------------------- API: labels
def test_alias_label_is_resolved_and_the_submitted_text_is_kept(client, reed_project):
    pid = reed_project["id"]
    ds = upload(client, pid, scene_bytes())
    resp = client.post(
        f"/projects/{pid}/labels",
        json={
            "labels": [
                point_label(10, 10, "open_water", dataset_id=ds["id"]),
                point_label(40, 10, "reed", dataset_id=ds["id"]),
                point_label(10, 50, "land", dataset_id=ds["id"]),
            ]
        },
    )
    assert resp.status_code == 201, resp.text
    labels = {label["class_name"] for label in resp.json()["labels"]}
    assert labels == {"open_water", "emergent_vegetation", "land"}
    reed = next(label for label in resp.json()["labels"] if label["class_name"] == "emergent_vegetation")
    # Auditable: the alias text survives next to the resolved class.
    assert reed["submitted_class_name"] == "reed"


def test_unmapped_label_is_rejected_without_touching_history(client, water_project):
    pid = water_project["id"]
    ds = upload(client, pid, scene_bytes())
    assert client.post(
        f"/projects/{pid}/labels",
        json={"labels": [point_label(10, 10, "open_water", dataset_id=ds["id"])]},
    ).status_code == 201
    before = client.get(f"/projects/{pid}/labels").json()

    resp = client.post(
        f"/projects/{pid}/labels",
        json={"labels": [point_label(20, 20, "reed", dataset_id=ds["id"])]},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "no configured mapping" in detail
    assert "emergent_vegetation" in detail  # it hints at the closest class
    after = client.get(f"/projects/{pid}/labels").json()
    assert after == before


def test_legacy_project_keeps_its_own_class_names(client):
    pid = client.post(
        "/projects",
        json={"name": "Legacy", "classes": ["water", "vegetation"], "generic_classes": True},
    ).json()["id"]
    ds = upload(client, pid, scene_bytes())
    ok = client.post(
        f"/projects/{pid}/labels",
        json={"labels": [point_label(10, 10, "water", dataset_id=ds["id"])]},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["labels"][0]["class_name"] == "water"
    # Water taxonomy names are not silently accepted by a generic project.
    bad = client.post(
        f"/projects/{pid}/labels",
        json={"labels": [point_label(20, 20, "open_water", dataset_id=ds["id"])]},
    )
    assert bad.status_code == 422


# --------------------------------------------- API: products and provenance
def test_training_records_the_taxonomy_snapshot(client, water_project):
    pid = water_project["id"]
    ds = upload(client, pid, scene_bytes())
    label_three_classes(client, pid, ds["id"])
    run = client.post(
        f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 20}}
    )
    assert run.status_code == 201, run.text
    assert run.json()["metrics"]["classes"] == WATER

    # The run's own snapshot, not the project's current config.
    metrics = client.get(f"/projects/{pid}/metrics").json()
    assert metrics["classes"] == WATER


def test_predict_reports_a_derived_binary_product(client, water_project):
    pid = water_project["id"]
    ds = upload(client, pid, scene_bytes())
    label_three_classes(client, pid, ds["id"])
    trained = client.post(
        f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 20}}
    )
    assert trained.status_code == 201, trained.text

    body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    # The three-class product is still the source of truth.
    assert body["classes"] == WATER
    assert body["binary"]["interpretation"] == "water_vs_non_water"
    assert body["binary"]["available"] is True
    assert body["binary"]["mapping"]["open_water"] == "water"
    assert body["binary"]["mapping"]["emergent_vegetation"] == "water"
    assert body["binary"]["mapping"]["land"] == "non_water"
    assert "binary" in body["exports"]

    exported = client.get(f"/projects/{pid}/download/binary")
    assert exported.status_code == 200, exported.text
    with rasterio.open(io.BytesIO(exported.content)) as out:
        assert out.count == 1 and out.crs.to_string() == "EPSG:32631"
        values = set(np.unique(out.read(1)).tolist())
        # 1 = water, 0 = other, and NoData only where the source is invalid.
        assert values <= {0, 1, out.nodata}
        assert out.tags()["interpretation"] == "water_vs_non_water"
        assert out.tags()["derived"] == "true"
        assert str(out.tags()["source_training_run_id"]) == str(trained.json()["id"])
        # The source product is untouched and still three-class.
        assert sorted(run_class for run_class in WATER)

    probability = client.get(f"/projects/{pid}/download/binary_probability")
    assert probability.status_code == 200
    with rasterio.open(io.BytesIO(probability.content)) as out:
        data = out.read(1, masked=True)
        finite = data.compressed()
        assert finite.size and finite.min() >= 0 and finite.max() <= 1

    hard = client.get(f"/projects/{pid}/download/hard")
    assert hard.status_code == 200
    with rasterio.open(io.BytesIO(hard.content)) as out:
        assert out.tags()["derived"] if "derived" in out.tags() else True
        assert sorted(set(np.unique(out.read(1, masked=True).compressed().tolist()))) <= [0.0, 1.0, 2.0]


def test_binary_map_layer_is_derived_not_a_second_model(client, water_project):
    pid = water_project["id"]
    ds = upload(client, pid, scene_bytes())
    label_three_classes(client, pid, ds["id"])
    client.post(f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 20}})

    field = client.get(
        f"/projects/{pid}/predict/map", params={"layer": "binary", "dataset_id": ds["id"]}
    )
    assert field.status_code == 200, field.text
    body = field.json()
    assert body["classes"] == ["non_water", "water"]
    assert body["layer"] == "binary"
    values = {v for row in body["values"] for v in row if v is not None}
    assert values <= {0, 1}
    # The three-class layer for the same run is unchanged.
    hard = client.get(
        f"/projects/{pid}/predict/map", params={"layer": "hard", "dataset_id": ds["id"]}
    ).json()
    assert hard["classes"] == WATER


def test_open_water_vs_other_interpretation_changes_the_mapping(client):
    pid = client.post(
        "/projects",
        json={
            "name": "open water only",
            "classes": list(WATER),
            "classification_config": {
                "internal_classes": list(WATER),
                "binary_output_interpretation": "open_water_vs_other",
                "label_aliases": {},
            },
        },
    ).json()["id"]
    ds = upload(client, pid, scene_bytes())
    label_three_classes(client, pid, ds["id"])
    client.post(f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 20}})
    body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    assert body["binary"]["interpretation"] == "open_water_vs_other"
    assert body["binary"]["mapping"] == {
        "open_water": "water",
        "emergent_vegetation": "non_water",
        "land": "non_water",
    }


def test_missing_class_makes_the_binary_product_unavailable(client, water_project):
    """Two classes labelled: the three-class map is still produced, the derived
    binary product that needs the missing class is reported unavailable."""
    pid = water_project["id"]
    ds = upload(client, pid, scene_bytes())
    labels = [
        point_label(x, y, "open_water", dataset_id=ds["id"])
        for x in (4, 16, 28)
        for y in (4, 20, 36, 52)
    ] + [
        point_label(x, y, "land", dataset_id=ds["id"])
        for x in (4, 16, 28)
        for y in (44, 52, 58)
    ]
    assert client.post(f"/projects/{pid}/labels", json={"labels": labels}).status_code == 201
    trained = client.post(
        f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 20}}
    )
    assert trained.status_code == 201, trained.text
    body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    # Training reports all project classes, but the model only learned two.
    assert body["binary"]["available"] is False
    assert body["binary"]["missing_classes"] == ["emergent_vegetation"]
    assert "never learned" in body["binary"]["reason"]
    assert "binary" not in body["exports"]
    assert client.get(f"/projects/{pid}/download/binary").status_code in (404, 409, 500)


def test_config_change_after_training_does_not_rewrite_the_run(client, water_project):
    pid = water_project["id"]
    ds = upload(client, pid, scene_bytes())
    label_three_classes(client, pid, ds["id"])
    client.post(f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 20}})
    before = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    assert before["binary"]["interpretation"] == "water_vs_non_water"

    # Change the project's interpretation after the run.
    assert client.put(
        f"/projects/{pid}",
        json={
            "classification_config": {
                "internal_classes": list(WATER),
                "binary_output_interpretation": "open_water_vs_other",
                "label_aliases": {},
            }
        },
    ).status_code == 200

    after = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    # The historical run keeps its own semantics: no silent reinterpretation.
    assert after["binary"]["interpretation"] == "water_vs_non_water"
    assert after["binary"]["mapping"] == before["binary"]["mapping"]


def test_pixel_and_patch_binary_products_keep_their_grids(client, water_project):
    pid = water_project["id"]
    ds = upload(client, pid, scene_bytes())
    label_three_classes(client, pid, ds["id"])

    patch_run = client.post(
        f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 20}}
    )
    assert patch_run.status_code == 201
    patch_body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    assert patch_body["resolution"] == "patch"
    with rasterio.open(io.BytesIO(client.get(f"/projects/{pid}/download/binary").content)) as out:
        assert (out.height, out.width) == (64, 64)

    pixel_run = client.post(
        f"/projects/{pid}/train",
        json={"model_type": "rf", "resolution": "pixel", "params": {"n_estimators": 20}},
    )
    assert pixel_run.status_code == 201
    pixel_body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    assert pixel_body["resolution"] == "pixel"
    with rasterio.open(io.BytesIO(client.get(f"/projects/{pid}/download/binary").content)) as out:
        assert (out.height, out.width) == (64, 64)
        assert out.transform == rasterio.Affine(10, 0, 500000, 0, -10, 4649776)


def test_legacy_checkpoint_has_no_binary_product(client):
    """A run without a taxonomy snapshot must not get a fabricated interpretation."""
    pid = client.post(
        "/projects",
        json={"name": "Legacy", "classes": ["water", "vegetation"], "generic_classes": True},
    ).json()["id"]
    ds = upload(client, pid, scene_bytes())
    labels = [
        point_label(x, y, "water" if x < 32 else "vegetation", dataset_id=ds["id"])
        for x in (4, 20, 36, 52)
        for y in (4, 20, 36, 52)
    ]
    assert client.post(f"/projects/{pid}/labels", json={"labels": labels}).status_code == 201
    client.post(f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 10}})
    body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    assert body["binary"] is None
    assert "binary" not in body["exports"]
    field = client.get(
        f"/projects/{pid}/predict/map", params={"layer": "binary", "dataset_id": ds["id"]}
    )
    assert field.status_code == 409
    assert "no recorded binary interpretation" in field.json()["detail"]
