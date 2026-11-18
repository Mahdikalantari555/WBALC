#!/usr/bin/env python3
"""Measure the workspace + engine hot paths, and print a markdown report body.

Read-only: it creates one temporary project, measures, and deletes it.

    .venv/bin/python scripts/audit_performance.py --base http://localhost:5174
"""
from __future__ import annotations

import argparse
import io
import statistics
import time

import httpx
import numpy as np
import rasterio
from rasterio.transform import from_origin


def timed(fn, repeat: int = 5) -> list[float]:
    out = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        out.append((time.perf_counter() - start) * 1000)
    return out


def summarise(samples: list[float]) -> str:
    s = sorted(samples)
    p50 = statistics.median(s)
    p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
    return f"{p50:7.1f} / {p95:7.1f} / {min(s):7.1f}"


def make_tiff(size: int, bands: int = 4) -> bytes:
    rng = np.random.default_rng(3)
    data = (rng.integers(300, 4000, (bands, size, size))).astype(np.uint16)
    buf = io.BytesIO()
    with rasterio.open(
        buf, "w", driver="GTiff", height=size, width=size, count=bands,
        dtype="uint16", crs="EPSG:32631", transform=from_origin(500000, 4649776, 10, 10),
        compress="deflate", tiled=True,
    ) as dst:
        dst.write(data)
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5174")
    ap.add_argument("--engine", default="http://localhost:8000")
    args = ap.parse_args()

    client = httpx.Client(base_url=args.base, timeout=180)
    direct = httpx.Client(base_url=args.engine, timeout=180)

    print("### Latency (ms) — p50 / p95 / min over 5 runs\n")
    print("| Path | via adapter | direct to engine | adapter overhead |")
    print("| --- | ---: | ---: | ---: |")

    rows = [
        ("GET /health", "/api/health", "/health"),
        ("GET projects", "/api/projects", "/projects"),
    ]
    for label, a, d in rows:
        ta = timed(lambda: client.get(a))
        td = timed(lambda: direct.get(d))
        print(f"| {label} | {summarise(ta)} | {summarise(td)} | {statistics.median(ta)-statistics.median(td):+7.1f} |")

    # A project with a real raster. Created on the engine directly: the adapter
    # is deliberately read-only apart from labels/query/train, so seeding state
    # is not part of what we are measuring.
    tiff = make_tiff(1024)
    pid = direct.post(
        "/projects",
        json={"name": f"perf-audit-{time.time():.0f}", "classes": ["open_water", "emergent_vegetation", "land"]},
    ).json()["id"]
    did = direct.post(
        f"/projects/{pid}/upload",
        files={"file": ("perf.tif", tiff, "image/tiff")},
    ).json()["id"]

    rows = [
        ("GET datasets", f"/api/projects/{pid}/datasets", f"/projects/{pid}/dataset"),
        ("GET labels", f"/api/projects/{pid}/labels", f"/projects/{pid}/labels"),
        ("GET runs", f"/api/projects/{pid}/runs", f"/projects/{pid}/metrics/history"),
    ]
    for label, a, d in rows:
        ta = timed(lambda: client.get(a))
        td = timed(lambda: direct.get(d))
        print(f"| {label} | {summarise(ta)} | {summarise(td)} | {statistics.median(ta)-statistics.median(td):+7.1f} |")

    # Raster proxy: full body and a range request.
    ta = timed(lambda: client.get(f"/api/projects/{pid}/datasets/{did}/file"), 3)
    size = len(client.get(f"/api/projects/{pid}/datasets/{did}/file").content)
    print(f"| GET dataset file ({size/1048576:.2f} MB) | {summarise(ta)} | — | — |")
    ta = timed(
        lambda: client.get(
            f"/api/projects/{pid}/datasets/{did}/file", headers={"range": "bytes=0-65535"}
        ),
        3,
    )
    print(f"| GET dataset file (64 KB range) | {summarise(ta)} | — | — |")

    # Submit a few labels so training has something to do.
    batch = client.post(
        f"/api/projects/{pid}/query",
        json={"strategy": "diversity", "batchSize": 12, "datasetId": str(did)},
    ).json()
    classes = ["open_water", "emergent_vegetation", "land"]
    for index, sample in enumerate(batch["samples"]):
        client.post(
            f"/api/projects/{pid}/labels",
            json={
                "sampleId": sample["sampleId"],
                "datasetId": str(did),
                "className": classes[index % 3],
                "col": sample["center"][0],
                "row": sample["center"][1],
            },
        )

    # Query batch on a large grid (1024² / 32px = 32×32 = 1024 candidates).
    ta = timed(
        lambda: client.post(
            f"/api/projects/{pid}/query",
            json={"strategy": "diversity", "batchSize": 20, "datasetId": str(did)},
        ),
        3,
    )
    print(f"| POST query diversity (1024 patches) | {summarise(ta)} | — | — |")

    # Train + map field on the same raster.
    statuses: list[int] = []

    def train_once() -> None:
        statuses.append(client.post(f"/api/projects/{pid}/train", json={"resolution": "patch"}).status_code)

    ta = timed(train_once, 1)
    if statuses[-1] != 201:
        print(f"| POST train | n/a (HTTP {statuses[-1]}) | — | — |")
    print(f"| POST train (patch, 1 run) | {summarise(ta)} | — | — |")
    try:
        ta = timed(lambda: client.get(f"/api/projects/{pid}/map-field?layer=hard&dataset={did}"), 3)
        print(f"| GET map-field hard (32x32 cells) | {summarise(ta)} | — | — |")
    except httpx.HTTPError as exc:
        print(f"| GET map-field hard | n/a ({exc}) | — | — |")

    # Export passthrough.
    ta = timed(lambda: client.get(f"/api/projects/{pid}/exports?type=hard&dataset={did}"), 2)
    print(f"| GET export hard GeoTIFF | {summarise(ta)} | — | — |")

    # SSR page render.
    ta = timed(lambda: client.get("/"), 5)
    print(f"| GET / (SSR shell) | {summarise(ta)} | — | — |")

    direct.delete(f"/projects/{pid}")


if __name__ == "__main__":
    main()
