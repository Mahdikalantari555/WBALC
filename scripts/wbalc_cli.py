#!/usr/bin/env python3
"""WBALC agent CLI — thin, strict, and boring on purpose.

The engine owns every invariant; this CLI only makes the common agent loop
(health, list, ingest a folder tree of acquisitions) scriptable without a
browser. Input validation here is deliberately strict: a folder that does not
provably match the expected acquisition layout is rejected, never guessed.

Usage (against a running engine):
    python scripts/wbalc_cli.py health
    python scripts/wbalc_cli.py projects
    python scripts/wbalc_cli.py scenes --project 4
    python scripts/wbalc_cli.py ingest D:/RS/Projects/Geomatic/Data --project "Zarivar AL Audit" --dry-run
    python scripts/wbalc_cli.py ingest D:/RS/Projects/Geomatic/Data --project "Zarivar AL Audit"

Exit codes: 0 ok, 1 some or all inputs rejected, 2 usage/connection error.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_API = "http://127.0.0.1:8010"

# Exactly one of these per acquisition folder is registered; anything else is
# reported as a rejection instead of being silently skipped.
MERGED_NAME = "merged.tif"
S2_REQUIRED_BANDS = ("blue", "green", "red", "nir08", "swir16", "swir22")
S2_BAND_FORM = "blue,green,red,nir08,swir16,swir22"
S1_BAND_FORM = "vh,vv"
S1_REQUIRED_BANDS = ("vv", "vh")


class CliError(Exception):
    """Fatal usage or connection problem."""


@dataclass
class ScenePlan:
    folder: str
    sensor: str
    file: Path
    band_form: str
    acquisition_datetime: str
    metadata: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, str] = field(default_factory=dict)


@dataclass
class Rejection:
    folder: str
    reason: str


# --------------------------------------------------------------------- helpers

def _utc_from_metadata(meta: dict[str, Any]) -> str | None:
    """Normalize the metadata instant to `...Z`; date-only becomes midnight UTC."""
    properties = meta.get("properties") if isinstance(meta.get("properties"), dict) else {}
    for value in (properties.get("datetime"), properties.get("start_datetime"), meta.get("datetime")):
        if isinstance(value, str) and value.strip():
            text = value.strip().replace("Z", "+00:00")
            if "T" not in text:
                text = f"{text}T00:00:00+00:00"
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return None


def discover_acquisitions(root: Path, sensor_dir: str, sensor: str) -> tuple[list[ScenePlan], list[Rejection]]:
    """Strictly scan one `s1_scenes/`-style directory into plans or rejections."""
    plans: list[ScenePlan] = []
    rejections: list[Rejection] = []
    directory = root / sensor_dir
    if not directory.is_dir():
        return plans, rejections

    for folder in sorted(path for path in directory.iterdir() if path.is_dir()):
        try:
            meta = json.loads((folder / "MTL.json").read_text(encoding="utf-8"))
            if not isinstance(meta, dict):
                raise ValueError("MTL.json must contain a JSON object")
        except FileNotFoundError as exc:
            rejections.append(Rejection(folder.name, "MTL.json is missing"))
            continue
        except (json.JSONDecodeError, ValueError) as exc:
            rejections.append(Rejection(folder.name, f"MTL.json unreadable: {exc}"))
            continue
        when = _utc_from_metadata(meta)
        if when is None:
            rejections.append(Rejection(folder.name, "MTL.json carries no parseable acquisition datetime"))
            continue

        merged = folder / MERGED_NAME
        if merged.is_file():
            band_form = S1_BAND_FORM if sensor == "Sentinel-1" else S2_BAND_FORM
            extras: dict[str, str] = {}
            if sensor == "Sentinel-1":
                extras = {
                    "product_type": "GRD",
                    "product_level": "L1",
                    "polarization": "VV,VH",
                    **({"acquisition_mode": mode} if (mode := meta.get("instrument_mode")) else {}),
                    **({"orbit_direction": orbit} if (orbit := meta.get("orbit_state")) else {}),
                    **({"relative_orbit": str(orbit)} if (orbit := meta.get("relative_orbit")) else {}),
                }
            else:
                props = meta.get("properties", {})
                extras = {
                    "product_type": "S2MSI2A",
                    "product_level": "L2A",
                    **({"orbit_direction": orbit} if (orbit := props.get("sat:orbit_state")) else {}),
                    **({"relative_orbit": str(orbit)} if (orbit := props.get("sat:relative_orbit")) else {}),
                }
            plans.append(ScenePlan(folder.name, sensor, merged, band_form, when, meta, extras))
            continue

        # No merged product: refuse with the exact expectation, never guess.
        expected = " or ".join(S1_REQUIRED_BANDS if sensor == "Sentinel-1" else S2_REQUIRED_BANDS)
        rejections.append(
            Rejection(
                folder.name,
                f"no {MERGED_NAME}; the CLI registers one stacked product per acquisition "
                f"(single-band sets are not stitched here — expected bands: {expected})",
            )
        )
    return plans, rejections


def scan_data_root(root: Path) -> tuple[list[ScenePlan], list[Rejection]]:
    if not root.is_dir():
        raise CliError(f"data root does not exist: {root}")
    plans: list[ScenePlan] = []
    rejections: list[Rejection] = []
    for sensor_dir, sensor in (("s1_scenes", "Sentinel-1"), ("s2_scenes", "Sentinel-2")):
        found, rejected = discover_acquisitions(root, sensor_dir, sensor)
        plans.extend(found)
        rejections.extend(rejected)
    if not plans and not rejections:
        raise CliError(f"no s1_scenes/ or s2_scenes/ folders under {root}")
    return plans, rejections


# ------------------------------------------------------------------------ HTTP

def api_request(api: str, method: str, path: str, **kwargs: Any):
    import requests

    try:
        response = requests.request(method, f"{api.rstrip('/')}{path}", timeout=600, **kwargs)
    except requests.ConnectionError as exc:
        raise CliError(f"engine is unreachable at {api}: {exc}") from exc
    return response


def register_plan(api: str, project_id: int, plan: ScenePlan):
    form = {
        "sensor": plan.sensor,
        "acquisition_datetime": plan.acquisition_datetime,
        "band_names": plan.band_form,
        "acquisition_metadata": json.dumps(plan.metadata),
        **plan.extras,
    }
    with plan.file.open("rb") as handle:
        return api_request(
            api,
            "POST",
            f"/projects/{project_id}/scenes",
            data=form,
            files={"file": (plan.file.name, handle, "image/tiff")},
        )


def resolve_project(api: str, name: str) -> tuple[int, str]:
    response = api_request(api, "GET", "/projects")
    response.raise_for_status()
    for project in response.json():
        if project["name"] == name:
            return int(project["id"]), f"reusing existing project {name}"
    created = api_request(
        api,
        "POST",
        "/projects",
        json={
            "name": name,
            "description": f"Created by wbalc_cli ingest from {name}",
            "classes": ["open_water", "emergent_vegetation", "land"],
            "generic_classes": True,
        },
    )
    if created.status_code >= 300:
        raise CliError(f"project creation failed: {created.status_code} {created.text[:300]}")
    return int(created.json()["id"]), f"created project {name}"


# -------------------------------------------------------------------- commands

def cmd_health(api: str) -> int:
    response = api_request(api, "GET", "/health")
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))
    return 0


def cmd_projects(api: str) -> int:
    response = api_request(api, "GET", "/projects")
    response.raise_for_status()
    for project in response.json():
        print(f"#{project['id']}\t{project['name']}\t{project['status']}\tclasses={','.join(project['classes'])}")
    return 0


def cmd_scenes(api: str, project_id: int) -> int:
    response = api_request(api, "GET", f"/projects/{project_id}/scenes")
    response.raise_for_status()
    for scene in response.json():
        when = scene.get("acquisition_datetime") or "—"
        print(f"#{scene['id']}\t{scene['sensor']}\t{when}\t{scene['source_filename']}\t{','.join(scene.get('band_names') or [])}")
    return 0


def cmd_ingest(api: str, root: Path, project_name: str, dry_run: bool) -> int:
    plans, rejections = scan_data_root(root)
    for rejection in rejections:
        print(f"REJECT {rejection.folder}: {rejection.reason}")
    for plan in plans:
        print(f"OK     {plan.folder}: {plan.sensor} {plan.acquisition_datetime} <- {plan.file.name} [{plan.band_form}]")
    if not plans:
        print("nothing registrable found", file=sys.stderr)
        return 1
    if dry_run:
        print(f"dry run: {len(plans)} scene(s) would be registered, {len(rejections)} rejected")
        return 1 if rejections else 0

    project_id, note = resolve_project(api, project_name)
    print(note)
    registered = 0
    failures = len(rejections)
    for plan in plans:
        response = register_plan(api, project_id, plan)
        if response.status_code >= 300:
            failures += 1
            detail = response.text[:300].replace("\n", " ")
            print(f"FAIL   {plan.folder}: {response.status_code} {detail}")
        else:
            registered += 1
            print(f"SENT   {plan.folder}: scene #{response.json()['id']}")
    print(f"done: {registered} registered, {failures} problem(s)")
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wbalc", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default=DEFAULT_API, help=f"engine base URL (default {DEFAULT_API})")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    sub.add_parser("projects")
    scenes = sub.add_parser("scenes")
    scenes.add_argument("--project", required=True, help="project id")
    ingest = sub.add_parser("ingest", help="register every valid acquisition under a data root")
    ingest.add_argument("root", type=Path, help="folder containing s1_scenes/ and/or s2_scenes/")
    ingest.add_argument("--project", required=True, help="project name (created with the default water taxonomy when missing)")
    ingest.add_argument("--dry-run", action="store_true", help="validate and list only; register nothing")
    args = parser.parse_args(argv)

    try:
        if args.command == "health":
            return cmd_health(args.api)
        if args.command == "projects":
            return cmd_projects(args.api)
        if args.command == "scenes":
            return cmd_scenes(args.api, int(args.project))
        if args.command == "ingest":
            return cmd_ingest(args.api, args.root, args.project, args.dry_run)
        return 2
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
