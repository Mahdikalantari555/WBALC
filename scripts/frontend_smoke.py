#!/usr/bin/env python3
"""End-to-end smoke test for the TerraLab frontend adapter.

Runs against a live `next start` server (default http://localhost:3000) which
must proxy to a live RSAL backend. Exercises the full active-learning loop
through the *browser-facing* API only, then cleans up.

Usage: .venv/bin/python scripts/frontend_smoke.py [--base http://localhost:3000]
"""

from __future__ import annotations

import argparse
import io
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


def make_geotiff() -> bytes:
    """Synthetic 96x96 4-band EPSG:32631 scene with distinct spectral quadrants."""
    rng = np.random.default_rng(42)
    h = w = 96
    data = np.zeros((4, h, w), dtype=np.uint16)
    quadrants = [(0, 0), (0, 48), (48, 0), (48, 48)]
    for qi, (r0, c0) in enumerate(quadrants):
        base = 400 + qi * 900
        for b in range(4):
            data[b, r0 : r0 + 48, c0 : c0 + 48] = (
                base + b * 120 + rng.integers(0, 60, (48, 48))
            )
    buf = io.BytesIO()
    with rasterio.open(
        buf,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=4,
        dtype="uint16",
        crs="EPSG:32631",
        transform=from_origin(500000, 4649776, 10, 10),
    ) as dst:
        dst.write(data)
    return buf.getvalue()


def make_plain_tiff() -> bytes:
    """96x96 4-band TIFF with no CRS (pixel-space fallback)."""
    rng = np.random.default_rng(7)
    buf = io.BytesIO()
    with rasterio.open(
        buf, "w", driver="GTiff", height=96, width=96, count=4, dtype="uint16"
    ) as dst:
        dst.write(rng.integers(100, 3000, (4, 96, 96)).astype(np.uint16))
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:3000")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    client = httpx.Client(base_url=base, timeout=120)

    print(f"TerraLab adapter smoke against {base}")

    r = client.get("/api/health")
    check("health via adapter", r.status_code == 200 and r.json().get("ok"), str(r.json()))

    r = client.post(
        "/api/projects",
        json={
            "name": "Smoke test project",
            "description": "frontend adapter e2e",
            "classes": [
                {"id": "Water", "name": "Water", "color": "#5cbb96"},
                {"id": "Vegetation", "name": "Vegetation", "color": "#e0a458"},
                {"id": "Bare soil", "name": "Bare soil", "color": "#7d9bd4"},
            ],
        },
    )
    check("create project", r.status_code == 201, str(r.status_code))
    project = r.json()
    pid = project["id"]
    check("class id == name + palette", project["classes"][0]["id"] == "Water")
    check("empty project stats", project["labeledCount"] == 0 and project["iteration"] == 0)

    try:
        # ---------------------------------------------------------- upload
        tif = make_geotiff()
        r = client.post(
            f"/api/projects/{pid}/upload",
            files={"file": ("smoke-scene.tif", tif, "image/tiff")},
        )
        check("upload GeoTIFF", r.status_code == 201, str(r.status_code))
        ds = r.json()
        did = ds["id"]
        check("dataset metadata", ds["bands"] == 4 and ds["width"] == 96 and ds["crs"] == "EPSG:32631")
        check("dataset size", ds["size"] == len(tif), f'{ds["size"]} bytes')
        check("WGS84 bounds reprojected", ds["bounds"] is not None and not ds["pixelSpace"] and 40 < ds["bounds"][1] < 45, str(ds["bounds"]))
        check("file url points at adapter", ds["url"] == f"/api/projects/{pid}/dataset/{did}/file")

        r = client.get(f"/api/projects/{pid}/dataset")
        check("dataset list", r.status_code == 200 and len(r.json()) == 1)

        r = client.get(ds["url"])
        check(
            "raster bytes proxied intact",
            r.status_code == 200 and r.content == tif and r.headers["content-type"].startswith("image/tiff"),
            f"{len(r.content)} bytes",
        )

        # ---------------------------------- unsupervised SOM (zero labels)
        r = client.post(
            f"/api/projects/{pid}/som-classify",
            json={"rows": 4, "cols": 4, "nClusters": 4, "epochs": 30, "resolution": "pixel"},
        )
        check("unsupervised SOM classify (zero labels)", r.status_code == 200, str(r.status_code))
        unsup = r.json()
        check(
            "unsupervised SOM clusters + full pixel shape",
            unsup["nClusters"] == 4
            and unsup["shape"] == [96, 96]
            and sum(c["pixelCount"] for c in unsup["clusters"]) == 96 * 96,
        )
        r_tif = client.get(unsup["downloadUrl"])
        check(
            "unsupervised SOM GeoTIFF download",
            r_tif.status_code == 200 and r_tif.headers["content-type"].startswith("image/tiff"),
            f"{len(r_tif.content)} bytes",
        )
        with rasterio.open(io.BytesIO(r_tif.content)) as som_ds:
            check(
                "unsupervised SOM GeoTIFF valid + 4 quadrants separated",
                som_ds.width == 96 and som_ds.height == 96 and len(np.unique(som_ds.read(1))) == 4,
            )

        # ------------------------------------------------ cold-start query
        r = client.post(f"/api/projects/{pid}/query", json={"batchSize": 8, "strategy": "entropy"})
        check("uncertainty before model -> actionable 409", r.status_code == 409 and "diversity" in r.json()["error"], r.json().get("error", "")[:80])

        r = client.get(f"/api/projects/{pid}/som?rows=3&cols=3")
        check("cold-start SOM explorer", r.status_code == 200, str(r.status_code))
        som_data = r.json()
        check(
            "SOM grid + cells",
            som_data["rows"] == 3
            and som_data["cols"] == 3
            and len(som_data["cells"]) == 9
            and sum(c["hitCount"] for c in som_data["cells"]) == som_data["totalPatches"],
        )

        r = client.post(f"/api/projects/{pid}/query", json={"batchSize": 4, "strategy": "som"})
        check("SOM cold-start query", r.status_code == 200 and len(r.json()["samples"]) == 4)

        r = client.post(f"/api/projects/{pid}/query", json={"batchSize": 8, "strategy": "diversity"})
        check("diversity cold-start query", r.status_code == 200, str(r.status_code))
        samples = r.json()["samples"]
        check("batch size honored", len(samples) == 8)
        s0 = samples[0]
        check("sample ids are patch ids", s0["id"].startswith(f"d{did}_r"))
        check("sample display coords in WGS84", 40 < s0["lat"] < 45 and 2 < s0["lng"] < 4, f'({s0["lat"]:.4f}, {s0["lng"]:.4f})')
        check("sample bbox + pixel present", s0["bbox"] is not None and s0["pixel"] is not None)
        check("cold-start prediction empty", s0["prediction"] == "")

        # ------------------------------------------------ label + train
        labels = [
            {
                "sampleId": s["id"],
                "label": ["Water", "Vegetation", "Bare soil"][i % 3],
                "status": "labeled",
                "note": "",
                "datasetId": did,
                "pixel": s["pixel"],
            }
            for i, s in enumerate(samples[:6])
        ] + [
            {"sampleId": samples[6]["id"], "label": None, "status": "skipped", "note": "hard", "datasetId": did, "pixel": samples[6]["pixel"]}
        ]
        r = client.post(f"/api/projects/{pid}/labels", json={"labels": labels})
        check("submit labels (skips filtered)", r.status_code == 201 and r.json()["saved"] == 6, str(r.json()))

        r = client.get(f"/api/projects/{pid}/labels")
        saved = r.json()
        check("saved labels as samples", r.status_code == 200 and len(saved) == 6 and saved[0]["saved"] is True)
        check("saved label display coords", 40 < saved[0]["lat"] < 45)

        r = client.get(f"/api/projects/{pid}/metrics")
        m = r.json()
        check("metrics before train -> zeros", r.status_code == 200 and m["iteration"] == 0 and m["curve"] == [] and m["labeledCount"] == 6)

        r = client.post(f"/api/projects/{pid}/train", json={})
        check("train model", r.status_code == 201, str(r.status_code))
        it = r.json()["iteration"]
        check("iteration payload", it["number"] >= 0 and 0 <= it["accuracy"] <= 1, f'iter={it["number"]} acc={it["accuracy"]:.3f}')

        r = client.get(f"/api/projects/{pid}/metrics")
        m = r.json()
        check("metrics curve + per-class", len(m["curve"]) == 1 and len(m["perClass"]) == 3 and len(m["confusionMatrix"]) >= 2)
        check("distribution counts", sum(d["value"] for d in m["distribution"]) == 6)
        check("totalSamples from patch grid", m["totalSamples"] > 0, str(m["totalSamples"]))

        r = client.get("/api/projects")
        p1 = next(p for p in r.json() if p["id"] == pid)
        check("project stats fan-out", p1["iteration"] == it["number"] and p1["labeledCount"] == 6 and p1["status"] == "in_progress" and p1["modelVersion"])

        # ------------------------------------- model-based query strategies
        for strategy in ("entropy", "margin", "least-confidence", "hybrid", "som"):
            r = client.post(f"/api/projects/{pid}/query", json={"batchSize": 4, "strategy": strategy})
            check(f"{strategy} query with model", r.status_code == 200 and len(r.json()["samples"]) > 0)
            if strategy == "entropy":
                check("model prediction surfaced", r.json()["samples"][0]["prediction"] in ("Water", "Vegetation", "Bare soil"))

        r = client.get(f"/api/projects/{pid}/som?rows=3&cols=3")
        som_after = r.json()
        check(
            "SOM after training includes uncertainty",
            r.status_code == 200
            and som_after["modelIteration"] is not None
            and any(c["meanUncertainty"] is not None for c in som_after["cells"]),
        )
        unlabeled_cell = next(c for c in som_after["cells"] if c["unlabeledCount"] > 0)
        r = client.post(
            f"/api/projects/{pid}/query",
            json={
                "batchSize": 3,
                "strategy": "som",
                "somRows": 3,
                "somCols": 3,
                "somCell": [unlabeled_cell["row"], unlabeled_cell["col"]],
            },
        )
        check(
            "SOM neuron-targeted query",
            r.status_code == 200
            and 1 <= len(r.json()["samples"]) <= 3
            and {s["id"] for s in r.json()["samples"]} <= set(unlabeled_cell["sampleIds"]),
        )

        # ------------------------------------------------ label correction
        corr = dict(labels[0])
        corr["label"] = "Water" if corr["label"] != "Water" else "Vegetation"
        r = client.post(f"/api/projects/{pid}/labels", json={"labels": [corr]})
        check("label correction accepted", r.status_code == 201)
        r = client.get(f"/api/projects/{pid}/labels")
        fixed = next(s for s in r.json() if s["id"] == corr["sampleId"])
        check("correction is latest version", fixed["label"] == corr["label"])
        check("no duplicate after correction", len(r.json()) == 6)

        # ------------------------------------------------ import (map space)
        lat, lng = s0["lat"], s0["lng"]
        r = client.post(
            f"/api/projects/{pid}/labels",
            json={
                "labels": [
                    {
                        "sampleId": "import-smoke-1",
                        "label": "Water",
                        "status": "labeled",
                        "note": "imported",
                        "lat": lat + 0.001,
                        "lng": lng + 0.001,
                        "geometry": {"type": "Point", "coordinates": [lng + 0.001, lat + 0.001]},
                        "datasetId": did,
                    }
                ]
            },
        )
        check("WGS84 import reprojected to map space", r.status_code == 201, str(r.json()))
        r = client.get(f"/api/projects/{pid}/history")
        check("label history includes versions", r.status_code == 200 and len(r.json()) == 8, f"{len(r.json())} rows")

        # --------------------------------------- polygon label + correction
        ring = [[lng, lat], [lng + 0.002, lat], [lng + 0.002, lat + 0.002],
                [lng, lat + 0.002], [lng, lat]]
        poly = {
            "sampleId": "manual-smoke-poly", "label": "Water", "status": "labeled",
            "note": "", "datasetId": did, "lat": lat + 0.001, "lng": lng + 0.001,
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        }
        r = client.post(f"/api/projects/{pid}/labels", json={"labels": [poly]})
        check("polygon label accepted", r.status_code == 201)
        r = client.get(f"/api/projects/{pid}/labels")
        poly_saved = next(s for s in r.json() if s["id"].startswith("poly_"))
        check("polygon id derived + displayed", poly_saved["geometry"]["type"] == "Polygon" and 40 < poly_saved["lat"] < 45)
        poly_fix = {**poly, "sampleId": poly_saved["id"], "label": "Vegetation"}
        r = client.post(f"/api/projects/{pid}/labels", json={"labels": [poly_fix]})
        check("polygon correction accepted", r.status_code == 201)
        r = client.get(f"/api/projects/{pid}/labels")
        fixed_poly = next(s for s in r.json() if s["id"] == poly_saved["id"])
        check("polygon correction is a version, not a duplicate",
              fixed_poly["label"] == "Vegetation" and sum(1 for s in r.json() if s["id"].startswith("poly_")) == 1)
        r = client.delete(f"/api/projects/{pid}/labels/{poly_saved['id']}")
        check("polygon label deleted", r.status_code == 200)

        # ------------------------------------------------ deletes
        r = client.delete(f"/api/projects/{pid}/labels/import-smoke-1")
        check("delete label", r.status_code == 200 and r.json()["deleted"])
        r = client.delete(f"/api/projects/{pid}/labels/import-smoke-1")
        check("delete missing label -> 404", r.status_code == 404)

        r = client.delete(f"/api/projects/{pid}/dataset/{did}")
        check("delete dataset cascade", r.status_code == 200)
        r = client.get(ds["url"])
        check("file gone after delete", r.status_code == 404)
        r = client.get(f"/api/projects/{pid}/labels")
        check("labels gone after cascade", r.json() == [])

        # ------------------------- pixel-space scene + dataset-targeted query
        r = client.post(
            f"/api/projects/{pid}/upload",
            files={"file": ("plain-scene.tif", make_plain_tiff(), "image/tiff")},
        )
        check("no-CRS upload accepted", r.status_code == 201)
        plain = r.json()
        check("pixel-space flag + bounds", plain["pixelSpace"] is True and plain["bounds"] == [0, 0, 96, 96])
        r = client.post(
            f"/api/projects/{pid}/query",
            json={"batchSize": 4, "strategy": "diversity", "datasetId": plain["id"]},
        )
        check("dataset-targeted query", r.status_code == 200 and all(s["datasetId"] == plain["id"] for s in r.json()["samples"]))
        ps = r.json()["samples"][0]
        check("pixel-space display coords", 0 <= ps["lat"] <= 96 and 0 <= ps["lng"] <= 96, f'({ps["lat"]}, {ps["lng"]})')
        r = client.post(
            f"/api/projects/{pid}/labels",
            json={"labels": [{
                "sampleId": ps["id"], "label": "Water", "status": "labeled", "note": "",
                "datasetId": plain["id"], "pixel": ps["pixel"],
            }]},
        )
        check("pixel-space label saved", r.status_code == 201)
        r = client.get(f"/api/projects/{pid}/labels")
        px_saved = next(s for s in r.json() if s["id"] == ps["id"])
        check("pixel label round-trips display", abs(px_saved["lat"] - ps["lat"]) < 1e-6 and abs(px_saved["lng"] - ps["lng"]) < 1e-6)
        r = client.delete(f"/api/projects/{pid}/dataset/{plain['id']}")
        check("pixel-space dataset deleted", r.status_code == 200)

        # ------------------------------------------------ bad input paths
        r = client.post(f"/api/projects/{pid}/upload", files={"file": ("evil.txt", b"nope", "text/plain")})
        check("non-TIFF upload rejected", r.status_code == 400)
        r = client.post(f"/api/projects/{pid}/query", json={"batchSize": 4, "strategy": "bogus"})
        check("unknown strategy rejected", r.status_code == 400)

    finally:
        r = client.delete(f"/api/projects/{pid}")
        check("project delete cleanup", r.status_code == 200)
        r = client.get("/api/projects")
        check("project gone", all(p["id"] != pid for p in r.json()))

    print(f"\nAll {PASS} checks passed.")


if __name__ == "__main__":
    main()
