#!/usr/bin/env python3
"""End-to-end RSAL demo: runs the full active learning loop against a live server.

Generates a synthetic 4-band GeoTIFF, then: create project -> upload ->
diversity cold-start query -> label + auto-train -> uncertainty & hybrid
queries -> metrics -> region predict -> GeoTIFF downloads.

Usage: .venv/bin/python scripts/demo.py [--base-url http://localhost:8000]
"""

from __future__ import annotations

import argparse
import io
import sys

import httpx
import numpy as np
import rasterio
from rasterio.transform import from_origin


def make_geotiff() -> bytes:
    rng = np.random.default_rng(42)
    h = w = 128
    data = np.zeros((4, h, w), dtype=np.float32)
    data[:, :, :64] = np.array([10, 20, 100, 120])[:, None, None] + rng.normal(0, 2, (4, h, 64))
    data[:, :, 64:] = np.array([80, 90, 30, 150])[:, None, None] + rng.normal(0, 2, (4, h, 64))
    buf = io.BytesIO()
    with rasterio.open(
        buf, "w", driver="GTiff", height=h, width=w, count=4, dtype="float32",
        crs="EPSG:32631", transform=from_origin(500000, 4649776, 10, 10),
    ) as dst:
        dst.write(data)
    return buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    c = httpx.Client(base_url=args.base_url, timeout=120)

    def check(resp, code):
        if resp.status_code != code:
            print(f"FAILED {resp.request.method} {resp.request.url}: {resp.status_code} {resp.text[:500]}")
            sys.exit(1)
        return resp.json() if resp.content else None

    print("== health =="); print(check(c.get("/health"), 200))

    print("\n== 1. create project ==")
    project = check(c.post("/projects", json={
        "name": "Demo Active Learning", "classes": ["water", "vegetation"],
        "description": "synthetic demo", "status": "active",
    }), 201)
    pid = project["id"]; print(f"project id={pid} classes={project['classes']}")

    print("\n== 2. upload GeoTIFF ==")
    ds = check(c.post(f"/projects/{pid}/upload",
                      files={"file": ("demo_scene.tif", make_geotiff(), "image/tiff")}), 201)
    print(f"dataset id={ds['id']} {ds['width']}x{ds['height']} bands={ds['bands']} "
          f"crs={ds['crs']} dtype={ds['dtype']}")

    print("\n== 3. cold-start diversity query ==")
    q = check(c.post(f"/projects/{pid}/query", json={
        "strategy": "diversity", "batch_size": 8, "include_embedding": True,
    }), 200)
    for s in q["samples"][:3]:
        print(f"  {s['sample_id']} center=({s['coords']['center_x']},{s['coords']['center_y']})")
    print(f"  ... {q['batch_size']} samples returned")

    print("\n== 4. label batch + auto-train (RF) ==")
    labels = []
    for row in range(0, 128, 16):
        for col in range(0, 128, 16):
            x, y = col + 8, row + 8
            labels.append({
                "geometry": {"type": "Point", "coordinates": [x, y]},
                "class_name": "water" if col < 64 else "vegetation",
                "iteration": 0,
            })
    r = check(c.post(f"/projects/{pid}/labels",
                     json={"labels": labels, "auto_train": True, "model_type": "rf"}), 201)
    t = r["training"]
    print(f"  stored {len(r['labels'])} labels; trained iter={t['iteration']} "
          f"n={t['n_samples']} accuracy={t['metrics']['accuracy']:.3f}")

    print("\n== 5. correct one label (history preserved) ==")
    check(c.post(f"/projects/{pid}/labels", json={
        "geometry": {"type": "Point", "coordinates": [8, 8]},
        "class_name": "water", "iteration": 1,
    }), 201)
    hist = check(c.get(f"/projects/{pid}/history"), 200)
    print(f"  history now has {len(hist)} label versions")

    print("\n== 6. uncertainty, hybrid & SOM queries ==")
    for strategy in ("uncertainty", "hybrid", "som"):
        q = check(c.post(f"/projects/{pid}/query", json={
            "strategy": strategy, "batch_size": 5, "method": "entropy", "exclude_labeled": False,
        }), 200)
        top = q["samples"][0]
        print(f"  {strategy}: {q['batch_size']} samples; top uncertainty={top['uncertainty']:.3f} "
              f"pred={top['prediction']} conf={top['confidence']:.3f}")

    som_info = check(c.get(f"/projects/{pid}/som"), 200)
    print(f"  SOM grid={som_info['rows']}x{som_info['cols']} active={som_info['active_neurons']} "
          f"qe={som_info['quantization_error']:.3f} te={som_info['topographic_error']:.3f}")

    print("\n== 7. LightGBM training + metrics ==")
    t2 = check(c.post(f"/projects/{pid}/train", json={
        "model_type": "lightgbm", "params": {"n_estimators": 60, "min_child_samples": 5},
    }), 201)
    m = check(c.get(f"/projects/{pid}/metrics"), 200)
    print(f"  iter={t2['iteration']} accuracy={m['accuracy']:.3f} f1_macro={m['f1_macro']:.3f} "
          f"confusion={m['confusion_matrix']}")

    print("\n== 8. predict region + full maps ==")
    p = check(c.post(f"/projects/{pid}/predict", json={
        "region": {"x0": 64, "y0": 0, "x1": 128, "y1": 64},
    }), 200)
    hard = np.asarray(p["hard_map"])
    print(f"  region grid={p['grid_shape']} classes={p['classes']} "
          f"predicted vegetation fraction={(hard == 1).mean():.2f}")

    print("\n== 9. download GeoTIFF exports ==")
    for etype in ("hard", "probability"):
        resp = c.get(f"/projects/{pid}/download/{etype}")
        if resp.status_code != 200:
            print(f"FAILED download {etype}: {resp.status_code}"); sys.exit(1)
        with rasterio.open(io.BytesIO(resp.content)) as src:
            print(f"  {etype}: {src.width}x{src.height} bands={src.count} "
                  f"dtype={src.dtypes[0]} crs={src.crs}")

    print("\nAll demo steps passed ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
