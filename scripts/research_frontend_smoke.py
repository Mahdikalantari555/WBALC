#!/usr/bin/env python3
"""End-to-end smoke test for the SvelteKit research-workspace adapter.

Runs against a live dev/preview server of `examples/wbalc-geospatial-research-interface`
(default http://localhost:5173) which must proxy to a live RSAL backend, and
drives only the *browser-facing* adapter routes:

    create project -> upload GeoTIFF -> durable query batches -> label -> train
    -> metrics/runs -> map field -> exports -> scene registration -> label
    import -> label deletion -> i18n document attributes

The project it creates is deleted at the end. Usage:

    .venv/bin/python scripts/research_frontend_smoke.py [--base http://localhost:5173]
"""

from __future__ import annotations

import argparse
import io
import re
import sys

import httpx
import numpy as np
import rasterio
from rasterio.transform import from_origin

PASS = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global PASS
    if not ok:
        print(f"  FAIL  {name} {extra}")
        sys.exit(1)
    PASS += 1
    print(f"  ok    {name} {extra}")


def make_geotiff(height: int = 96, width: int = 96, crs: str | None = "EPSG:32631") -> bytes:
    """Synthetic multi-quadrant scene: separable classes, real GeoTIFF bytes."""
    rng = np.random.default_rng(11)
    data = np.zeros((4, height, width), dtype=np.uint16)
    for qi, (r0, c0) in enumerate([(0, 0), (0, width // 2), (height // 2, 0), (height // 2, width // 2)]):
        base = 500 + qi * 1200
        for band in range(4):
            data[band, r0 : r0 + height // 2, c0 : c0 + width // 2] = (
                base + band * 140 + rng.integers(0, 50, (height // 2, width // 2))
            ).astype(np.uint16)
    buffer = io.BytesIO()
    kwargs = {}
    if crs:
        kwargs = {"crs": crs, "transform": from_origin(500000, 4649776, 10, 10)}
    with rasterio.open(
        buffer, "w", driver="GTiff", height=height, width=width, count=4,
        dtype="uint16", **kwargs,
    ) as dst:
        dst.write(data)
    return buffer.getvalue()


def _utm_to_lonlat(easting: float, northing: float, zone: int = 31) -> tuple[float, float]:
    """Minimal UTM-31N inverse for building a WGS84 import fixture."""
    import math

    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    x, y = easting - 500000, northing
    m = y / 0.9996
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    sin_p, cos_p, tan_p = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    c1, t1 = ep2 * cos_p**2, tan_p**2
    n1 = a / math.sqrt(1 - e2 * sin_p**2)
    r1 = a * (1 - e2) / (1 - e2 * sin_p**2) ** 1.5
    d = x / (n1 * 0.9996)
    lat = phi1 - (n1 * tan_p / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
    )
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    lon = lon0 + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
    ) / cos_p
    return math.degrees(lon), math.degrees(lat)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:5173")
    parser.add_argument("--backend", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    backend = args.backend.rstrip("/")

    client = httpx.Client(base_url=base, timeout=180)
    direct = httpx.Client(base_url=backend, timeout=180)

    print(f"Research-workspace adapter smoke against {base}")

    # ------------------------------------------------------------------ health
    r = client.get("/api/health")
    check("health via adapter", r.status_code == 200 and r.json()["engine"] is True, str(r.json()))

    # ----------------------------------------------------------- SSR document
    r = client.get("/")
    check("SSR page renders", r.status_code == 200 and "<html" in r.text)
    check("SSR <html lang=en dir=ltr>", 'lang="en"' in r.text and 'dir="ltr"' in r.text)
    r_fa = client.get("/", cookies={"wbalc.locale": "fa"})
    check(
        "SSR Persian locale sets dir=rtl",
        'dir="rtl"' in r_fa.text and 'lang="fa"' in r_fa.text,
        "",
    )
    check("Persian chrome string present in SSR", "فضای کار" in r_fa.text)

    # --------------------------------------------------------------- project
    r = direct.post(
        "/projects",
        json={
            "name": "Adapter smoke project",
            "description": "research frontend e2e",
            "study_area_crs": "EPSG:4326",
        },
    )
    check("create project (engine)", r.status_code == 201, str(r.status_code))
    pid = r.json()["id"]

    try:
        r = client.get("/api/projects")
        check(
            "adapter lists projects",
            r.status_code == 200 and any(item["id"] == str(pid) for item in r.json()),
        )
        r = client.get(f"/api/projects/{pid}")
        project = r.json()
        check(
            "project view model carries taxonomy",
            project["classificationConfig"]["internalClasses"] == ["open_water", "emergent_vegetation", "land"],
            str(project["classes"]),
        )
        check(
            "water taxonomy snapshot recorded",
            project["taxonomy"] is not None
            and project["taxonomy"]["version"] == "wbalc-water-taxonomy-v1"
            and project["taxonomy"]["classes"] == ["open_water", "emergent_vegetation", "land"],
            str(project["taxonomy"] and project["taxonomy"].get("version")),
        )

        # -------------------------------------------------------------- upload
        # 256x256 -> an 8x8 patch grid, so a 20-sample diversity batch is real.
        tif = make_geotiff(256, 256)
        # Declared band names: the engine refuses to train or predict on rasters
        # whose ordered bands it cannot identify without an explicit override.
        r = direct.post(
            f"/projects/{pid}/upload",
            files={"file": ("smoke.tif", tif, "image/tiff")},
            data={"band_names": "blue,green,red,nir", "sensor": "sentinel-2"},
        )
        check("upload GeoTIFF (engine)", r.status_code == 201, str(r.status_code))
        did = r.json()["id"]

        r = client.get(f"/api/projects/{pid}/datasets")
        datasets = r.json()
        check("adapter lists datasets", r.status_code == 200 and len(datasets) == 1)
        dataset = datasets[0]
        check("dataset georeferenced + bounds", dataset["georeferenced"] is True and dataset["bounds"] is not None)
        check("dataset url is adapter-relative", dataset["url"] == f"/api/projects/{pid}/datasets/{did}/file")
        check(
            "dataset reports its declared band schema",
            dataset["bandSchemaDeclared"] is True
            and dataset["bandNames"] == ["blue", "green", "red", "nir"]
            and dataset["sensor"] == "sentinel-2",
            str(dataset.get("bandNames")),
        )

        r = client.get(dataset["url"])
        check(
            "raster bytes proxied byte-identical",
            r.status_code == 200 and r.content == tif and r.headers["content-type"].startswith("image/tiff"),
            f"{len(r.content)} bytes",
        )
        r = client.get(dataset["url"], headers={"range": "bytes=0-1023"})
        check(
            "range request forwarded",
            r.status_code in (200, 206) and len(r.content) <= 1024,
            f"status={r.status_code} len={len(r.content)}",
        )

        # ------------------------------------------------------- map field gate
        r = client.get(f"/api/projects/{pid}/map-field?layer=hard&dataset={did}")
        check("map field without model -> 409", r.status_code == 409, str(r.status_code))

        # ------------------------------------------------------------- query
        r = client.post(
            f"/api/projects/{pid}/query",
            json={"strategy": "uncertainty", "batchSize": 5, "datasetId": str(did)},
        )
        check("uncertainty cold start -> actionable 409", r.status_code == 409 and "diversity" in r.json()["message"], r.json().get("message", "")[:70])

        r = client.post(
            f"/api/projects/{pid}/query",
            json={"strategy": "diversity", "batchSize": 20, "datasetId": str(did)},
        )
        check("diversity batch", r.status_code == 200, str(r.status_code))
        batch = r.json()
        check(
            "batch honours requested size",
            len(batch["samples"]) == 20,
            f"{len(batch['samples'])} samples",
        )
        sample = batch["samples"][0]
        check("sample view model has pixel window", sample["window"]["x1"] > sample["window"]["x0"])
        check("sample has geo centre (CRS)", sample["geo"] is not None and len(sample["geo"]) == 2)

        # ------------------------------------------ durable batches (Phase 2)
        check(
            "batch carries durable identity + pool",
            isinstance(batch.get("batchId"), str)
            and batch["pool"]["size"] > 0
            and batch["pool"]["eligibility"].startswith("valid-source-pixels"),
            str(batch.get("batchId")),
        )
        check(
            "deterministic strategy records no seed",
            batch["seed"] is None,
            str(batch["seed"]),
        )

        seeded = client.post(
            f"/api/projects/{pid}/query",
            json={
                "strategy": "random",
                "batchSize": 12,
                "datasetId": str(did),
                "seed": 4242,
            },
        ).json()
        check("seeded random baseline", seeded["seed"] == 4242 and len(seeded["samples"]) == 12)
        check(
            "random and diversity share one candidate pool",
            seeded["pool"]["hash"] == batch["pool"]["hash"],
        )
        again = client.post(
            f"/api/projects/{pid}/query",
            json={
                "strategy": "random",
                "batchSize": 12,
                "datasetId": str(did),
                "seed": 4242,
            },
        ).json()
        check(
            "seeded random is repeatable across requests",
            [s["sampleId"] for s in again["samples"]]
            == [s["sampleId"] for s in seeded["samples"]]
            and again["batchId"] != seeded["batchId"],
        )

        history = client.get(f"/api/projects/{pid}/queries").json()
        check(
            "history lists batches newest first",
            [entry["batchId"] for entry in history][:2]
            == [again["batchId"], seeded["batchId"]],
            str([entry["batchId"] for entry in history[:3]]),
        )
        reopened = client.get(f"/api/projects/{pid}/queries/{batch['batchId']}").json()
        check(
            "batch reopens with the same items and order",
            [item["sampleId"] for item in reopened["items"]]
            == [s["sampleId"] for s in batch["samples"]],
        )

        target = reopened["items"][0]
        r = client.patch(
            f"/api/projects/{pid}/queries/{batch['batchId']}/items/{target['id']}",
            json={"status": "rejected", "note": "smoke: not water"},
        )
        check(
            "rejection is a durable decision",
            r.status_code == 200 and r.json()["status"] == "rejected",
            str(r.status_code),
        )
        r = client.patch(
            f"/api/projects/{pid}/queries/{batch['batchId']}/items/{target['id']}",
            json={"status": "deferred"},
        )
        check("decision transitions persist", r.json()["status"] == "deferred")
        listing = client.get(f"/api/projects/{pid}/queries").json()
        entry = next(e for e in listing if e["batchId"] == str(batch["batchId"]))
        check(
            "history reports decision counts",
            entry["decisions"]["deferred"] == 1
            and entry["decisions"]["pending"] == entry["returned"] - 1,
            str(entry["decisions"]),
        )

        # ------------------------------------------------------------ labels
        classes = project["classes"]
        submitted = batch["samples"][:12]
        linked_item = reopened["items"][1]
        for index, item in enumerate(submitted):
            r = client.post(
                f"/api/projects/{pid}/labels",
                json={
                    "sampleId": item["sampleId"],
                    "datasetId": str(did),
                    "className": classes[index % len(classes)],
                    "col": item["center"][0],
                    "row": item["center"][1],
                    "iteration": 0,
                    # The first sample is answered from its durable query item,
                    # so the engine records query provenance for it.
                    **(
                        {"queryBatchId": batch["batchId"], "queryItemId": linked_item["id"]}
                        if index == 1
                        else {}
                    ),
                },
            )
            check(f"submit label {index + 1}/{len(submitted)}", r.status_code == 200, str(r.status_code))
        label = r.json()
        check("label returned with version", label["version"] >= 1 and label["sampleId"] == submitted[-1]["sampleId"])

        # correction of the same sample must create a new version, not a new label
        first = batch["samples"][0]
        before = client.get(f"/api/projects/{pid}/labels").json()
        r = client.post(
            f"/api/projects/{pid}/labels",
            json={
                "sampleId": first["sampleId"],
                "datasetId": str(did),
                "className": classes[1],
                "col": first["center"][0],
                "row": first["center"][1],
                "revise": True,
            },
        )
        after = client.get(f"/api/projects/{pid}/labels").json()
        check(
            "label correction versions the same sample",
            r.status_code == 200 and len(after) == len(before) and r.json()["version"] == 2,
            f"labels {len(before)}->{len(after)} v{r.json().get('version')}",
        )

        r = client.get(f"/api/projects/{pid}/labels")
        labels = r.json()
        check("adapter label list", len(labels) == len(submitted) and labels[0]["center"] is not None)
        linked = next(
            (entry for entry in labels if entry["sampleId"] == submitted[1]["sampleId"]), None
        )
        check(
            "label answered from a query item records query provenance",
            linked is not None and linked["provenance"] == "query",
            str(linked and linked["provenance"]),
        )
        check(
            "typed labels report manual provenance",
            all(
                entry["provenance"] == "manual"
                for entry in labels
                if entry["sampleId"] != submitted[1]["sampleId"]
            ),
        )
        item_after = client.get(f"/api/projects/{pid}/queries/{batch['batchId']}").json()["items"][1]
        check(
            "the query item became labeled and points at the label version",
            item_after["status"] == "labeled" and item_after["labelId"] == linked["id"],
            str(item_after["status"]),
        )

        # ------------------------------------------------------------- train
        # Through the adapter: the resolution and validation protocol must be
        # explicit, echoed back, and never silently defaulted by the UI layer.
        r = client.post(
            f"/api/projects/{pid}/train",
            json={"model_type": "rf", "resolution": "patch", "evaluationStrategy": "random"},
        )
        check("train via adapter", r.status_code == 201, r.text[:160])
        trained = r.json()
        check(
            "adapter echoes the requested resolution + protocol",
            trained["resolution"] == "patch" and trained["metrics"]["evaluationStrategy"] == "random",
            f"{trained.get('resolution')}/{trained.get('metrics', {}).get('evaluationStrategy')}",
        )

        r = client.post(f"/api/projects/{pid}/train", json={"resolution": "nonsense"})
        check("rejects an unknown resolution before training", r.status_code == 400, r.text[:120])
        r = client.post(f"/api/projects/{pid}/train", json={"evaluationStrategy": "leaky"})
        check("rejects an unknown evaluation protocol", r.status_code == 400, r.text[:120])

        r = client.get(f"/api/projects/{pid}/runs")
        check("adapter lists runs", r.status_code == 200 and len(r.json()) == 1)
        run = r.json()[0]
        check("run carries metrics + protocol", run["metrics"]["accuracy"] > 0 and run["metrics"]["evaluationStrategy"] == "random")
        check("run carries per-class metrics", len(run["metrics"]["perClass"]) >= 2)
        # `insufficient` must mirror the engine's own evaluation string, never be
        # invented: a 12-sample/3-class holdout is genuinely thin.
        engine_metrics = direct.get(f"/projects/{pid}/metrics").json()
        check(
            "insufficient flag mirrors the engine evaluation string",
            run["metrics"]["insufficient"]
            == engine_metrics["evaluation"].startswith("insufficient_train"),
            f"engine evaluation={engine_metrics['evaluation']}",
        )

        # ------------------------------- content identity + manifests (Phase 3)
        dataset_view = next(d for d in client.get(f"/api/projects/{pid}/datasets").json())
        check(
            "upload records a content hash the adapter exposes",
            isinstance(dataset_view["contentSha256"], str) and len(dataset_view["contentSha256"]) == 64,
            str(dataset_view["contentSha256"])[:12],
        )
        check(
            "run list reports lineage completeness",
            run["lineageStatus"] == "complete" and len(run["manifestHash"]) == 64,
            f"{run['lineageStatus']}/{str(run['manifestHash'])[:8]}",
        )
        lineage = client.get(f"/api/projects/{pid}/runs/{run['id']}/lineage").json()
        check(
            "run lineage names its inputs and label snapshot",
            lineage["inputs"][0]["sha256"] == dataset_view["contentSha256"]
            and lineage["labelSnapshotHash"] is not None
            and lineage["status"] == "complete",
            f"{lineage['status']}/{str(lineage['labelSnapshotHash'])[:8]}",
        )
        check(
            "checkpoint artifact verifies against its recorded checksum",
            lineage["artifact"]["verified"] is True,
            str(lineage["artifact"]),
        )
        check(
            "manifest carries environment + config",
            lineage["environment"]["python"] and lineage["config"]["resolution"] == "patch",
            str(lineage["environment"]),
        )
        check(
            "manifest exposes no machine-local paths",
            "/home/" not in str(lineage) and "storage/" not in str(lineage),
        )

        # The adapter's exports route streams a file, so artifact metadata is read
        # from the engine (which is also where the checksum is recorded).
        materialised = client.get(f"/api/projects/{pid}/exports?type=hard&dataset={did}")
        exports = direct.get(f"/projects/{pid}/exports").json()
        check(
            "export download streams the artifact",
            materialised.status_code == 200
            and materialised.headers["content-type"].startswith("image/tiff"),
            str(materialised.status_code),
        )
        check(
            "export records its checksum and integrity verdict",
            len(exports) > 0 and len(exports[0]["sha256"]) == 64 and exports[0]["integrity"] == "verified",
            str(exports[0]["integrity"] if exports else None),
        )

        experiment = client.post(
            f"/api/projects/{pid}/experiments",
            json={"name": "Smoke experiment", "runIds": [run["id"]]},
        )
        check(
            "experiment groups a run without touching it",
            experiment.status_code == 201 and experiment.json()["runIds"] == [run["id"]],
            experiment.text[:120],
        )
        exp_id = experiment.json()["id"]
        comparison = client.get(f"/api/projects/{pid}/compare?runs={run['id']}").json()
        check(
            "single-run comparison refuses to claim comparability",
            comparison["comparable"] is False and comparison["caveats"],
            str(comparison["caveats"])[:80],
        )
        detail = client.get(f"/api/projects/{pid}/experiments/{exp_id}").json()
        check(
            "experiment detail carries its membership",
            detail["experiment"]["runIds"] == [run["id"]],
        )
        check(
            "evaluation protocol is exposed",
            run["metrics"]["evaluationStrategy"] == "random" and run["metrics"]["nTest"] is not None,
        )

        # --------------------------------------------------------- map fields
        r = client.get(f"/api/projects/{pid}/map-field?layer=hard&dataset={did}")
        check("hard map field", r.status_code == 200, r.text[:120])
        field = r.json()
        check(
            "hard field grid + values",
            field["resolution"] == "patch"
            and len(field["values"]) == field["grid"]["rows"]
            and len(field["values"][0]) == field["grid"]["cols"],
        )
        check(
            "hard field reports provenance",
            field["bandSchemaVerified"] is True
            and field["studyAreaApplied"] is False
            and field["trainingRunId"] == str(trained["id"]),
            f"verified={field.get('bandSchemaVerified')}",
        )
        r = client.get(f"/api/projects/{pid}/map-field?layer=uncertainty&method=entropy&dataset={did}")
        check("uncertainty map field", r.status_code == 200 and r.json()["layer"] == "uncertainty")

        # ------------------------------------- band-schema refusal + override
        # A raster that names no bands cannot be proven to carry the model's
        # ordered bands. The engine must refuse, the adapter must relay the
        # refusal, and only an explicit override may produce a product.
        r = direct.post(
            f"/projects/{pid}/upload",
            files={"file": ("unnamed.tif", make_geotiff(256, 256), "image/tiff")},
        )
        check("upload without declared bands", r.status_code == 201, r.text[:120])
        unnamed = r.json()["id"]
        r = client.get(f"/api/projects/{pid}/datasets")
        undeclared = next(item for item in r.json() if item["id"] == str(unnamed))
        check(
            "undeclared raster is reported as undeclared, not guessed",
            undeclared["bandSchemaDeclared"] is False
            and undeclared["bandNames"] is None
            and undeclared["sensor"] is None,
            str(undeclared.get("bandNames")),
        )
        r = client.get(f"/api/projects/{pid}/map-field?layer=hard&dataset={unnamed}")
        check(
            "undeclared bands -> refusal relayed by the adapter",
            r.status_code == 409 and "accept_unverified_schema" in r.json()["message"],
            f"{r.status_code} {r.json().get('message', '')[:70]}",
        )
        # The override records the operator's decision; it cannot invent a
        # schema. The product is still produced, and still flagged unverified.
        r = client.get(
            f"/api/projects/{pid}/map-field?layer=hard&dataset={unnamed}&accept_unverified_schema=true"
        )
        check(
            "explicit override produces a product flagged unverified",
            r.status_code == 200 and r.json()["bandSchemaVerified"] is False,
            f"{r.status_code} body={r.text[:120]}",
        )

        # -------------------------------------- water taxonomy + binary product
        r = direct.get(f"/projects/{pid}/taxonomy")
        described = r.json()
        check(
            "taxonomy endpoint describes the binary plan",
            r.status_code == 200
            and described["binary"]["interpretation"] == "water_vs_non_water"
            and described["binary"]["mapping"]["emergent_vegetation"] == "water",
            str(described.get("binary", {}).get("mapping")),
        )

        r = client.get(f"/api/projects/{pid}/map-field?layer=binary&dataset={did}")
        check(
            "derived binary map layer",
            r.status_code == 200 and r.json()["classes"] == ["non_water", "water"],
            f"{r.status_code} {r.text[:80]}",
        )
        binary_field = r.json()
        check(
            "binary layer reports its mapping and availability",
            binary_field["binary"]["available"] is True
            and set(binary_field["binary"]["mapping"].values()) <= {"water", "non_water"},
        )
        r = client.get(f"/api/projects/{pid}/exports?type=binary&dataset={did}")
        check(
            "derived binary GeoTIFF proxied",
            r.status_code == 200 and r.headers["content-type"].startswith("image/tiff"),
            str(r.status_code),
        )
        with rasterio.open(io.BytesIO(r.content)) as exported:
            check(
                "binary export is a categorical source-grid product",
                exported.width == 256
                and exported.height == 256
                and exported.tags().get("derived") == "true"
                and exported.tags().get("interpretation") == "water_vs_non_water",
            )

        # ------------------------------------------------------------ exports
        r = client.get(f"/api/projects/{pid}/exports?type=hard&dataset={did}")
        check(
            "GeoTIFF export proxied",
            r.status_code == 200 and r.headers["content-type"].startswith("image/tiff") and len(r.content) > 1000,
            f"{len(r.content)} bytes",
        )
        with rasterio.open(io.BytesIO(r.content)) as exported:
            check(
                "export on the source grid",
                exported.width == 256 and exported.height == 256 and exported.crs is not None,
            )

        # ----------------------------------------------- post-model query/labels
        r = client.post(
            f"/api/projects/{pid}/query",
            json={"strategy": "uncertainty", "method": "entropy", "batchSize": 4, "datasetId": str(did)},
        )
        check("uncertainty batch after training", r.status_code == 200 and len(r.json()["samples"]) == 4)
        check("uncertainty scores present", r.json()["samples"][0]["uncertainty"] is not None)

        # -------------------------------------------------------------- scenes
        for day, sensor in (("2025-01-10T08:00:00Z", "Sentinel-2"), ("2025-02-11T03:00:00Z", "Sentinel-1")):
            r = direct.post(
                f"/projects/{pid}/scenes",
                files={"file": (f"scene-{day[:10]}.tif", make_geotiff(64, 80), "image/tiff")},
                data={"sensor": sensor, "acquisition_datetime": day},
            )
            check(f"register {sensor} scene", r.status_code == 201, r.text[:120])
        r = client.get(f"/api/projects/{pid}/scenes")
        scenes = r.json()
        check("adapter lists scenes", r.status_code == 200 and len(scenes) == 2)
        check(
            "scene view model fields",
            scenes[0]["sensor"] in {"Sentinel-1", "Sentinel-2"}
            and scenes[0]["acquisitionDateTime"] is not None
            and scenes[0]["width"] in {256, 80},
        )

        # ------------------------------------------------------- label import
        # A WGS84 feature derived from the dataset's own UTM origin.
        lon, lat = _utm_to_lonlat(500400.0, 4649500.0)
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {"class": "open_water"},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {"class": "reed"},
                },
            ],
        }
        r = client.post(f"/api/projects/{pid}/labels/import", json={"geojson": geojson})
        check("GeoJSON import (WGS84)", r.status_code == 200, r.text[:160])
        result = r.json()
        check(
            "wgs84 feature imported + unknown class skipped",
            result["imported"] >= 1 and result["skipped"] == 1,
            f"imported={result['imported']} skipped={result['skipped']}",
        )
        check(
            "unknown class is not silently recoded",
            any("reed" in error for error in result["errors"]),
            str(result["errors"])[:120],
        )

        # The same features declared in the dataset CRS must also land, which
        # proves the import honours the explicit coordinate-system choice.
        projected = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [500500.0, 4649400.0]},
                    "properties": {"class": "land"},
                }
            ],
        }
        r = client.post(
            f"/api/projects/{pid}/labels/import",
            json={"geojson": projected, "coordinateCrs": "dataset"},
        )
        check(
            "projected-CRS import honoured",
            r.status_code == 200 and r.json()["imported"] == 1,
            r.text[:160],
        )

        # ------------------------------------------------------ label deletion
        target = batch["samples"][1]["sampleId"]
        r = client.delete(f"/api/projects/{pid}/labels/{target}")
        check("delete label via adapter", r.status_code == 204, str(r.status_code))
        remaining = [item["sampleId"] for item in client.get(f"/api/projects/{pid}/labels").json()]
        check("deleted sample gone (all versions)", target not in remaining)

        # ------------------------------------------------------------ i18n
        r = client.get("/")
        check("English chrome string present", "Geospatial Workspace" in r.text or "Overview" in r.text)
        # Both locales must render the same nav labels from the same markup.
        en_nav = re.findall(r'class="nav-label[^"]*">([^<]+)<', r.text)
        fa_nav = re.findall(r'class="nav-label[^"]*">([^<]+)<', r_fa.text)
        check(
            "nav labels switch with the locale",
            len(en_nav) >= 6 and len(en_nav) == len(fa_nav) and set(en_nav) != set(fa_nav),
            f"{en_nav[:2]} vs {fa_nav[:2]}",
        )

        print(f"\n{PASS} checks passed")
    finally:
        direct.delete(f"/projects/{pid}")


if __name__ == "__main__":
    main()
