"""Integrated acceptance: one offline synthetic workflow across Phases 0-5.

The point of this test is not to re-check each phase (their own suites do that) but
to prove the chain holds together: a scene ingested once keeps one identity as it
travels through labelling, active learning, training, inference, temporal analysis
and a held-out report — and that every step which *cannot* be established says so
instead of producing a plausible number.

Synthetic data only. Nothing here is evidence about real water mapping.
"""

from __future__ import annotations

import json

import pytest

from app.services.report_service import bundle_markdown

from .test_temporal_phase4 import classify, labelled_dataset, register_scene, scene_bytes, train

WATER = ["open_water", "emergent_vegetation", "land"]


@pytest.fixture()
def project(client) -> dict:
    resp = client.post(
        "/projects",
        json={"name": "End to end", "classes": WATER, "description": "integrated acceptance"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_offline_scene_to_report_workflow(client, project):
    pid = project["id"]

    # ---------------------------------------------------------------- ingest
    dataset_id = labelled_dataset(client, pid)
    dataset = client.get(f"/projects/{pid}/dataset").json()
    assert len(dataset) == 1
    assert dataset[0]["crs"] == "EPSG:32631"
    assert dataset[0]["band_schema"]["declared"] is True

    # The dataset keeps a content identity the rest of the pipeline points at.
    assert len(dataset[0]["content_sha256"]) == 64

    scene_a = register_scene(client, pid, seed=11, acquired="2025-03-01T00:00:00Z")
    scene_b = register_scene(client, pid, seed=12, acquired="2025-04-01T00:00:00Z")
    scenes = client.get(f"/projects/{pid}/scenes").json()
    by_id = {entry["id"]: entry for entry in scenes}
    assert by_id[scene_a]["crs"] == by_id[scene_b]["crs"] == "EPSG:32631"
    assert by_id[scene_a]["acquisition_datetime"] != by_id[scene_b]["acquisition_datetime"]

    # ------------------------------------------------- Phase 2: active learning
    batch = client.post(
        f"/projects/{pid}/query", json={"strategy": "diversity", "budget": 3, "seed": 4242}
    )
    assert batch.status_code == 200, batch.text
    # A deterministic strategy must not claim a seed it never used; the random
    # baseline must record the one it did.
    assert batch.json()["seed"] is None
    random_batch = client.post(
        f"/projects/{pid}/query", json={"strategy": "random", "budget": 3, "seed": 4242}
    )
    assert random_batch.status_code == 200
    assert random_batch.json()["seed"] == 4242

    # ------------------------------------------------ Phase 0/1: train + infer
    run = train(client, pid)
    # The training response is a summary; the manifest lives on the lineage record,
    # which is exactly the separation Phase 3 introduced.
    assert run["metrics"]["accuracy"] >= 0
    assert run["n_samples"] > 0

    hard = client.get(f"/projects/{pid}/predict/map", params={"layer": "hard", "dataset_id": dataset_id})
    assert hard.status_code == 200
    assert set(hard.json()["classes"]) == set(WATER)

    uncertainty = client.get(
        f"/projects/{pid}/predict/map", params={"layer": "uncertainty", "dataset_id": dataset_id}
    )
    assert uncertainty.status_code == 200

    # -------------------------------------------------- Phase 3: run lineage
    lineage = client.get(f"/projects/{pid}/runs/{run['id']}/lineage")
    assert lineage.status_code == 200, lineage.text
    lineage_body = lineage.json()
    assert lineage_body["lineage_status"] in {"complete", "incomplete"}
    assert lineage_body["manifest_hash"]

    # ----------------------------------------------- Phase 4: scenes + change
    first = classify(client, pid, scene_a)
    assert first.status_code == 201, first.text
    second = classify(client, pid, scene_b)
    assert second.status_code == 201, second.text
    analysis_a = first.json()["analysis"]
    analysis_b = second.json()["analysis"]
    assert analysis_a["grid"]["crs"] == analysis_b["grid"]["crs"]
    assert analysis_a["areas"]["available"] is True
    assert {entry["class_name"] for entry in analysis_a["areas"]["per_class"]} == set(WATER)
    assert analysis_a["areas"]["method"]["kind"] == "projected"

    comparison = client.post(
        f"/projects/{pid}/temporal/compare",
        json={"before_scene_id": scene_a, "after_scene_id": scene_b},
    )
    assert comparison.status_code == 200, comparison.text
    change = comparison.json()
    # Nothing was resampled behind our back: the comparison records its alignment
    # explicitly and the transition matrix covers the jointly valid footprint.
    assert change["alignment"]["method"] in {"none", "nearest"}
    assert change["transitions"]["classes"] == change["classes"]

    fusion = client.post(
        f"/projects/{pid}/fusion",
        json={
            "rule": "weighted_probability",
            "target_scene_id": scene_a,
            "analysis_ids": [analysis_a["id"], analysis_b["id"]],
            "weights": {"Sentinel-2": 0.5},
        },
    )
    assert fusion.status_code == 201, fusion.text

    # --------------------------------- Phase 5: held-out protocol + evaluation
    protocol = client.post(
        f"/projects/{pid}/research/protocols",
        json={"protocol": "random", "seed": 5, "test_size": 0.34},
    )
    assert protocol.status_code == 201, protocol.text
    protocol_body = protocol.json()
    assert protocol_body["status"] == "ok"
    assert protocol_body["split_hash"]

    evaluation = client.post(
        f"/projects/{pid}/research/evaluations",
        json={
            "protocol_id": protocol_body["id"],
            "model_type": "rf",
            "resolution": "patch",
        },
    )
    assert evaluation.status_code == 201, evaluation.text
    scored = evaluation.json()
    assert scored["split_hash"] == protocol_body["split_hash"]
    assert scored["metrics"]["n_test"] > 0
    # The evaluation model is a separate fit; it cannot be the production run.
    assert scored["config"].get("run_id") is None or scored["config"]["run_id"] != run["id"]

    # Temporal holdout has to be refused or honest: never silently a random split.
    temporal = client.post(
        f"/projects/{pid}/research/protocols", json={"protocol": "temporal", "seed": 5}
    )
    assert temporal.status_code == 201, temporal.text
    temporal_body = temporal.json()
    assert temporal_body["protocol"] == "temporal"
    if temporal_body["status"] != "ok":
        assert temporal_body["reason"], "an insufficient split must say why"

    # -------------------------------------------------- area error stays absent
    area_error = client.get(f"/projects/{pid}/research/area-error")
    assert area_error.status_code == 409
    assert "reference" in area_error.json()["detail"].lower()

    client.post(
        f"/projects/{pid}/research/reference-areas",
        json={
            "scene_id": scene_a,
            "water_area_m2": float(
                next(
                    entry["area_m2"]
                    for entry in analysis_a["areas"]["per_class"]
                    if entry["class_name"] == "open_water"
                )
                or 1024.0
            ),
            "source": "synthetic fixture (not independent)",
            "method": "derived from the fixture, for wiring only",
        },
    )
    area_error = client.get(f"/projects/{pid}/research/area-error")
    # With a reference *and* a classified scene the metric exists — and it is
    # still labelled as an estimate chain, never as validated accuracy.
    assert area_error.status_code == 200, area_error.text
    row = area_error.json()[0]
    # The error always travels with its provenance and its caveat.
    assert row["reference_source"] and row["reference_method"]
    assert row["caveat"]
    assert row["signed_error_m2"] == pytest.approx(
        row["mapped_area_m2"] - row["reference_area_m2"]
    )

    # ------------------------------------------------------ report + honesty
    report = client.post(f"/projects/{pid}/research/reports", json={"title": "End to end"})
    assert report.status_code == 201, report.text
    report_body = report.json()
    assert set(report_body["artifacts"]) == {"json", "csv", "markdown"}
    assert report_body["scientific_status"]["scientific_validity"] == "not established"

    payload = client.get(f"/projects/{pid}/research/reports/{report_body['id']}/files/json")
    assert payload.status_code == 200
    bundle = json.loads(payload.content)
    # Every phase is represented in the bundle, and the excluded/included split is explicit.
    assert bundle["runs"]["included"] or bundle["runs"]["excluded"]
    assert bundle["protocols"][0]["split_hash"] == protocol_body["split_hash"]
    assert bundle["results"][0]["id"] == scored["id"]
    assert bundle["scenes"] and bundle["fusions"]
    assert bundle["reference_areas"][0]["source"]

    markdown = bundle_markdown(bundle)
    assert "not established" in markdown.lower()

    # Regeneration from the same records is byte-identical in digest, which is the
    # whole claim: the report is a view, not a new measurement.
    again = client.post(f"/projects/{pid}/research/reports", json={"title": "End to end"})
    assert again.json()["digest"] == report_body["digest"]
    # ...but a different title is a different document.
    retitled = client.post(f"/projects/{pid}/research/reports", json={"title": "Other"})
    assert retitled.json()["digest"] != report_body["digest"]

    # -------------------------------------------------- status keeps the split
    status = client.get(f"/projects/{pid}/research/status").json()
    assert status["software_validation"]
    assert status["scientific_validity"] == "not established"
    assert status["protocols"] >= 2 and status["results"] >= 1


def test_the_smoke_fixture_scene_bytes_are_stable():
    """Guard the fixture identity the whole file leans on."""
    assert scene_bytes(seed=11) == scene_bytes(seed=11)
    assert scene_bytes(seed=11) != scene_bytes(seed=12)
