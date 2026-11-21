"""Agent CLI input scanning: strict validation, no network required."""

from __future__ import annotations

import importlib.util
import sys
import json
from pathlib import Path

import pytest

_CLI = Path(__file__).resolve().parents[1] / "scripts" / "wbalc_cli.py"
_spec = importlib.util.spec_from_file_location("wbalc_cli", _CLI)
wbalc_cli = importlib.util.module_from_spec(_spec)
sys.modules["wbalc_cli"] = wbalc_cli
_spec.loader.exec_module(wbalc_cli)


def mt(date: str, platform: str = "sentinel-1a", **extra) -> dict:
    return {"datetime": date, "platform": platform, **extra}


def make_acquisition(root: Path, sensor_dir: str, name: str, meta: dict | None, with_merged: bool = True) -> Path:
    folder = root / sensor_dir / name
    folder.mkdir(parents=True)
    if meta is not None:
        (folder / "MTL.json").write_text(json.dumps(meta), encoding="utf-8")
    if with_merged:
        (folder / "merged.tif").write_bytes(b"fake tiff bytes")
    return folder


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "Data"


class TestScanDataRoot:
    def test_valid_acquisitions_are_planned(self, data_root: Path):
        make_acquisition(data_root, "s1_scenes", "s1_winter", mt("2025-01-04"))
        make_acquisition(data_root, "s2_scenes", "s2_winter", mt("2025-01-02T07:42:29Z", platform="Sentinel-2B"))
        plans, rejections = wbalc_cli.scan_data_root(data_root)
        assert not rejections
        assert [plan.folder for plan in plans] == ["s1_winter", "s2_winter"]
        assert plans[0].sensor == "Sentinel-1" and plans[0].band_form == "vh,vv"
        assert plans[1].band_form == "blue,green,red,nir08,swir16,swir22"
        # Date-only metadata is normalized to midnight UTC, never guessed further.
        assert plans[0].acquisition_datetime == "2025-01-04T00:00:00Z"
        assert plans[1].acquisition_datetime == "2025-01-02T07:42:29Z"

    def test_missing_metadata_is_rejected(self, data_root: Path):
        make_acquisition(data_root, "s1_scenes", "no_meta", None)
        plans, rejections = wbalc_cli.scan_data_root(data_root)
        assert not plans
        assert rejections[0].reason == "MTL.json is missing"

    def test_broken_metadata_is_rejected(self, data_root: Path):
        folder = data_root / "s2_scenes" / "broken"
        folder.mkdir(parents=True)
        (folder / "MTL.json").write_text("{not json", encoding="utf-8")
        (folder / "merged.tif").write_bytes(b"x")
        _, rejections = wbalc_cli.scan_data_root(data_root)
        assert "unreadable" in rejections[0].reason

    def test_metadata_without_datetime_is_rejected(self, data_root: Path):
        make_acquisition(data_root, "s2_scenes", "undated", {"platform": "Sentinel-2B"})
        _, rejections = wbalc_cli.scan_data_root(data_root)
        assert "datetime" in rejections[0].reason

    def test_folder_without_merged_is_rejected_not_guessed(self, data_root: Path):
        folder = make_acquisition(data_root, "s2_scenes", "bands_only", mt("2025-01-02"), with_merged=False)
        (folder / "green.tif").write_bytes(b"x")
        (folder / "nir08.tif").write_bytes(b"x")
        plans, rejections = wbalc_cli.scan_data_root(data_root)
        assert not plans
        assert "no merged.tif" in rejections[0].reason

    def test_unknown_root_is_a_usage_error(self, tmp_path: Path):
        with pytest.raises(wbalc_cli.CliError, match="does not exist"):
            wbalc_cli.scan_data_root(tmp_path / "nowhere")

    def test_empty_root_is_a_usage_error(self, tmp_path: Path):
        with pytest.raises(wbalc_cli.CliError, match="no s1_scenes"):
            wbalc_cli.scan_data_root(tmp_path)

    def test_s1_metadata_flows_into_the_registration_form(self, data_root: Path):
        make_acquisition(data_root, "s1_scenes", "s1_full", mt(
            "2025-01-04T14:52:52Z", instrument_mode="IW", orbit_state="ascending", relative_orbit=174,
        ))
        plans, _ = wbalc_cli.scan_data_root(data_root)
        assert plans[0].extras["acquisition_mode"] == "IW"
        assert plans[0].extras["orbit_direction"] == "ascending"
        assert plans[0].extras["relative_orbit"] == "174"
