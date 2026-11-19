"""Evaluation protocols: explicit splits, leakage controls, deterministic hashes (Phase 5).

A protocol answers three questions before any score is quoted: *which samples
were held out, grouped how, and with what seed*. This module builds those splits
from the labelled samples of a project, refuses to pretend when the data cannot
support the requested independence, and returns everything a report needs to
reconstruct the split from stored records.

Three protocols:

- `random` — stratified random holdout over labelled samples. Neighbouring
  patches are almost certainly correlated, so this is *optimistic* and says so.
- `spatial` — grouped by square blocks with an optional buffer; blocks in the
  test set have their buffered neighbours removed from training.
- `temporal` — holds out whole scenes (acquisition groups); any sample from a
  held-out scene is absent from training.

Nothing here fits a model. It produces the split, its membership and its hash.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .lineage_service import digest

PROTOCOLS = ("random", "spatial", "temporal")

PROTOCOL_CAVEATS = {
    "random": (
        "Random holdout over labelled samples: neighbouring patches are correlated, so the "
        "score is optimistic and must not be quoted as spatial generalisation."
    ),
    "spatial": (
        "Spatially blocked holdout: reported performance describes held-out blocks, not "
        "unseen regions outside the block layout."
    ),
    "temporal": (
        "Acquisition-holdout: reported performance describes held-out acquisition dates, "
        "not years or sensors the model never saw."
    ),
}


class ProtocolError(ValueError):
    """The requested protocol cannot be built from the available data."""


def _block_key(x: float, y: float, block: float) -> tuple[int, int]:
    return (int(math.floor(x / block)), int(math.floor(y / block)))


def _block_group(dataset_id, key: tuple[int, int]) -> str:
    """Block identity includes the raster: two datasets are separate footprints.

    Without the dataset in the key, samples from different acquisitions that happen
    to share pixel coordinates would be placed in the same spatial block, and a
    "spatial" holdout would silently become an acquisition holdout (or worse, put
    the same location in both partitions).
    """
    return f"block:{dataset_id}:{key[0]}:{key[1]}"


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(int(seed))


def build_split(
    samples: list[dict],
    *,
    protocol: str,
    seed: int,
    test_size: float = 0.3,
    block_size: float = 256.0,
    buffer: float = 0.0,
    spatial_unit: str = "pixels",
    scene_key: str = "scene_id",
) -> dict:
    """Build a split.

    Each sample is a dict with at least:
      `sample_id`, `class_index`, `x`, `y` (pixel coordinates) and `scene_id`.

    Returns `{status, protocol, ...}` where `status` is `"ok"` or `"insufficient"`.
    An insufficient split never comes back with invented membership: it carries a
    reason and zero-member lists.
    """
    if protocol not in PROTOCOLS:
        raise ProtocolError(f"Unknown protocol '{protocol}'; choose from {list(PROTOCOLS)}")
    if not 0.0 < test_size < 1.0:
        raise ProtocolError("test_size must be between 0 and 1")
    if not samples:
        return _insufficient(protocol, "the project has no usable labelled samples", seed=seed)
    if block_size <= 0:
        raise ProtocolError("block_size must be positive")
    if buffer < 0:
        raise ProtocolError("buffer must not be negative")

    if protocol == "random":
        return _random_split(samples, seed=seed, test_size=test_size)
    if protocol == "spatial":
        return _spatial_split(
            samples,
            seed=seed,
            test_size=test_size,
            block_size=block_size,
            buffer=buffer,
            spatial_unit=spatial_unit,
        )
    return _temporal_split(samples, seed=seed, test_size=test_size, scene_key=scene_key)


def _insufficient(protocol: str, reason: str, **extra) -> dict:
    return {
        "status": "insufficient",
        "protocol": protocol,
        "reason": reason,
        "train": [],
        "test": [],
        "train_count": 0,
        "test_count": 0,
        "groups": [],
        "held_out_groups": [],
        "overlap": [],
        "split_hash": None,
        "caveats": [PROTOCOL_CAVEATS.get(protocol, ""), f"insufficient: {reason}"],
        **extra,
    }


def _finalize(
    protocol: str,
    *,
    train: list[dict],
    test: list[dict],
    groups: dict[str, list[str]],
    configuration: dict,
    caveats: list[str],
    excluded: list[str] | None = None,
    **extra,
) -> dict:
    train_ids = sorted(entry["sample_id"] for entry in train)
    test_ids = sorted(entry["sample_id"] for entry in test)
    overlap = sorted(set(train_ids) & set(test_ids))
    held_out = sorted({entry["group"] for entry in test})
    train_groups = sorted({entry["group"] for entry in train})
    # A leakage check that is enforced, not assumed.
    leaked_groups = sorted(set(held_out) & set(train_groups)) if protocol != "random" else []
    body = {
        "protocol": protocol,
        "configuration": configuration,
        "train_count": len(train_ids),
        "test_count": len(test_ids),
        "train": train_ids,
        "test": test_ids,
        "groups": [
            {
                "group": group,
                "members": sorted(groups.get(group, [])),
                "role": "test" if group in held_out else "train",
            }
            for group in sorted(groups)
        ],
        "held_out_groups": held_out,
        "group_overlap": leaked_groups,
        "overlap": overlap,
        "excluded": excluded or [],
        "train_class_support": _support(train),
        "test_class_support": _support(test),
    }
    split_hash = digest(body)
    status = "ok" if not overlap and not leaked_groups and len(test_ids) > 0 else "insufficient"
    reason = None
    if overlap:
        reason = f"{len(overlap)} sample ids appear in both partitions"
    elif leaked_groups:
        reason = f"{len(leaked_groups)} groups appear in both partitions"
    elif not test_ids:
        reason = "the held-out partition is empty"
    return {
        "status": status,
        "reason": reason,
        "split_hash": split_hash,
        "caveats": caveats,
        **body,
        **extra,
    }


def _support(entries: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        name = entry.get("class_name", str(entry.get("class_index")))
        counts[name] = counts.get(name, 0) + 1
    return counts


def _random_split(samples: list[dict], *, seed: int, test_size: float) -> dict:
    by_class: dict[int, list[dict]] = {}
    for sample in samples:
        by_class.setdefault(int(sample["class_index"]), []).append(sample)
    rng = _rng(seed)
    train: list[dict] = []
    test: list[dict] = []
    short: list[str] = []
    for class_index in sorted(by_class):
        entries = sorted(by_class[class_index], key=lambda entry: entry["sample_id"])
        if len(entries) < 2:
            short.append(entries[0].get("class_name", str(class_index)))
            train.extend({**entry, "group": "all"} for entry in entries)
            continue
        order = rng.permutation(len(entries))
        n_test = max(1, min(len(entries) - 1, int(round(len(entries) * test_size))))
        test_indexes = set(order[:n_test].tolist())
        for position, entry in enumerate(entries):
            record = {**entry, "group": "all"}
            (test if position in test_indexes else train).append(record)
    if len({entry["class_index"] for entry in train}) < 2 or len(
        {entry["class_index"] for entry in test}
    ) < 2:
        return _insufficient(
            "random",
            "a stratified holdout could not cover two classes in both partitions "
            f"({len(train)} train / {len(test)} test samples)",
            seed=seed,
            test_size=test_size,
        )
    caveats = [PROTOCOL_CAVEATS["random"]]
    if short:
        caveats.append(
            "Classes with a single sample were kept in training only and cannot be evaluated: "
            + ", ".join(short)
        )
    return _finalize(
        "random",
        train=train,
        test=test,
        groups={"all": [entry["sample_id"] for entry in train + test]},
        configuration={"seed": int(seed), "test_size": test_size, "stratified": True},
        caveats=caveats,
        excluded=short,
    )


def _spatial_split(
    samples: list[dict],
    *,
    seed: int,
    test_size: float,
    block_size: float,
    buffer: float,
    spatial_unit: str,
) -> dict:
    blocks: dict[str, list[dict]] = {}
    coordinates: dict[str, tuple[int, int]] = {}
    for sample in samples:
        key = _block_key(float(sample["x"]), float(sample["y"]), block_size)
        group = _block_group(sample.get("dataset_id"), key)
        coordinates[group] = key
        blocks.setdefault(group, []).append(sample)
    if len(blocks) < 3:
        return _insufficient(
            "spatial",
            f"only {len(blocks)} spatial block(s) at block_size={block_size} {spatial_unit}; "
            "a blocked holdout needs at least 3",
            seed=seed,
            test_size=test_size,
            block_size=block_size,
            buffer=buffer,
            spatial_unit=spatial_unit,
        )

    rng = _rng(seed)
    keys = sorted(blocks)
    order = rng.permutation(len(keys))
    n_test_blocks = max(1, min(len(keys) - 2, int(round(len(keys) * test_size))))
    test_keys = {keys[index] for index in order[:n_test_blocks].tolist()}
    # Buffer: drop blocks within `reach` block units of a held-out block, measured
    # inside the same raster (a neighbour in another acquisition is not adjacent).
    buffered: set[str] = set()
    if buffer > 0:
        reach = int(math.ceil(buffer / block_size))
        held_out_by_dataset: dict[object, set[tuple[int, int]]] = {}
        for group in test_keys:
            dataset_id = blocks[group][0].get("dataset_id")
            held_out_by_dataset.setdefault(dataset_id, set()).add(coordinates[group])
        for group in keys:
            dataset_id = blocks[group][0].get("dataset_id")
            key = coordinates[group]
            for held in held_out_by_dataset.get(dataset_id, set()):
                if max(abs(key[0] - held[0]), abs(key[1] - held[1])) <= reach:
                    buffered.add(group)
                    break
    train_keys = [key for key in keys if key not in test_keys and key not in buffered]

    train = [{**entry, "group": key} for key in train_keys for entry in blocks[key]]
    test = [{**entry, "group": key} for key in sorted(test_keys) for entry in blocks[key]]
    dropped = [key for key in keys if key in buffered]
    groups = {key: [entry["sample_id"] for entry in blocks[key]] for key in keys}

    if len({entry["class_index"] for entry in train}) < 2 or len(
        {entry["class_index"] for entry in test}
    ) < 2:
        return _insufficient(
            "spatial",
            "the blocked holdout does not contain two classes in both partitions",
            seed=seed,
            test_size=test_size,
            block_size=block_size,
            buffer=buffer,
            spatial_unit=spatial_unit,
            test_blocks=sorted(test_keys),
        )
    if not train:
        return _insufficient(
            "spatial",
            "every remaining block was excluded by the buffer; reduce block_size or buffer",
            seed=seed,
            test_size=test_size,
            block_size=block_size,
            buffer=buffer,
            spatial_unit=spatial_unit,
        )

    caveats = [PROTOCOL_CAVEATS["spatial"]]
    if dropped:
        caveats.append(
            f"{len(dropped)} block(s) within {buffer} {spatial_unit} of a held-out block were "
            "excluded from training to reduce boundary leakage"
        )
    return _finalize(
        "spatial",
        train=train,
        test=test,
        groups=groups,
        configuration={
            "seed": int(seed),
            "test_size": test_size,
            "block_size": block_size,
            "buffer": buffer,
            "spatial_unit": spatial_unit,
            "blocks_total": len(keys),
            "blocks_held_out": len(test_keys),
            "blocks_buffered_out": len(dropped),
            "block_key": "dataset + block row/col",
        },
        caveats=caveats,
        excluded=dropped,
    )


def _temporal_split(
    samples: list[dict], *, seed: int, test_size: float, scene_key: str
) -> dict:
    scenes: dict[str, list[dict]] = {}
    for sample in samples:
        scene = sample.get(scene_key)
        if scene is None:
            return _insufficient(
                "temporal",
                "a sample has no scene/acquisition group, so an acquisition holdout cannot "
                "be built without guessing which acquisition it belongs to",
                seed=seed,
                test_size=test_size,
            )
        scenes.setdefault(str(scene), []).append(sample)
    if len(scenes) < 2:
        return _insufficient(
            "temporal",
            f"only {len(scenes)} acquisition group(s); an acquisition holdout needs at least 2",
            seed=seed,
            test_size=test_size,
        )

    names = sorted(scenes)
    rng = _rng(seed)
    order = rng.permutation(len(names))
    n_test = max(1, min(len(names) - 1, int(round(len(names) * test_size))))
    test_names = {names[index] for index in order[:n_test].tolist()}
    train = [{**entry, "group": name} for name in names if name not in test_names for entry in scenes[name]]
    test = [{**entry, "group": name} for name in names if name in test_names for entry in scenes[name]]
    groups = {name: [entry["sample_id"] for entry in scenes[name]] for name in names}

    if len({entry["class_index"] for entry in test}) < 2:
        return _insufficient(
            "temporal",
            "the held-out acquisition(s) contain only one class, so per-class recall cannot "
            "be measured there",
            seed=seed,
            test_size=test_size,
            held_out_scenes=sorted(test_names),
        )
    if len({entry["class_index"] for entry in train}) < 2:
        return _insufficient(
            "temporal",
            "the remaining acquisitions contain only one class; a temporal split would train "
            "a single-class model",
            seed=seed,
            test_size=test_size,
            held_out_scenes=sorted(test_names),
        )
    return _finalize(
        "temporal",
        train=train,
        test=test,
        groups=groups,
        configuration={
            "seed": int(seed),
            "test_size": test_size,
            "grouping": "acquisition (scene_id)",
            "scenes_total": len(names),
            "scenes_held_out": len(test_names),
        },
        caveats=[PROTOCOL_CAVEATS["temporal"]],
    )


def sample_records(
    labels: list,
    datasets: dict[int, Any],
    class_names: list[str],
    *,
    group_map: dict[int, str] | None = None,
) -> list[dict]:
    """Turn stored labels into split units, keeping their acquisition group.

    This engine has no dataset → scene link, so the acquisition group of a label is
    its dataset (one raster = one acquisition) unless the caller supplies an
    explicit `group_map` (dataset id → group name, e.g. one group per acquisition
    date spanning several tiles). The grouping is recorded on the split, so a
    temporal holdout never claims an independence it was not given.
    """
    class_index = {name: index for index, name in enumerate(class_names)}
    units: list[dict] = []

    def group_for(dataset_id: int | None) -> str | None:
        if dataset_id is None:
            return None
        if group_map and int(dataset_id) in group_map:
            return str(group_map[int(dataset_id)])
        return f"dataset:{dataset_id}"

    for label in labels:
        name = label.class_name
        if name not in class_index:
            continue
        geometry = label.geometry or {}
        if geometry.get("type") != "Point":
            # Polygon labels target many pixels; a split unit needs one location.
            continue
        coordinates = geometry.get("coordinates") or []
        if len(coordinates) < 2:
            continue
        x, y = float(coordinates[0]), float(coordinates[1])
        if label.coordinate_space != "pixel":
            dataset = datasets.get(label.dataset_id)
            transform = getattr(dataset, "transform", None) if dataset else None
            if not transform:
                continue
            a, b, c, d, e, f = [float(value) for value in transform[:6]]
            # Invert the affine for a map-space point.
            det = a * e - b * d
            if det == 0:
                continue
            dx, dy = x - c, y - f
            x = (e * dx - b * dy) / det
            y = (-d * dx + a * dy) / det
        units.append(
            {
                "sample_id": label.sample_id,
                "label_id": label.id,
                "version": label.version,
                "class_index": class_index[name],
                "class_name": name,
                "dataset_id": label.dataset_id,
                "scene_id": group_for(label.dataset_id),
                "x": x,
                "y": y,
            }
        )
    return units
