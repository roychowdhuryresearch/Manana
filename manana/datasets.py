"""Shared config and dataset-loading helpers for Manana runs."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from manana.config import import_object, load_config, resolve_config_path


@dataclass
class ConfiguredSplit:
    """Configured split plus release-facing metadata used by run loops."""

    config: dict[str, Any]
    name: str
    tag: str
    train_cases: list
    eval_cases: list
    test_cases: list
    gt_data: dict
    stats: dict
    train_label: str
    eval_label: str
    test_label: str


def safe_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9-]+", "_", value)
    name = re.sub(r"_+", "_", name).strip("_")
    return name.lower() or "dataset"


def load_object(spec: str):
    obj = import_object(spec)
    if not callable(obj):
        raise TypeError(f"Adapter is not callable: {spec}")
    return obj


def _label(stats: dict, prefix: str) -> str:
    patients = stats.get(f"{prefix}_patients")
    cases = stats.get(f"{prefix}_cases")
    poly = stats.get(f"{prefix}_poly")
    if patients is not None and cases is not None and poly is not None:
        return f"{patients} patients, {cases} cases ({poly} poly)"
    if patients is not None and poly is not None:
        return f"{patients} patients ({poly} poly)"
    if patients is not None and cases is not None:
        return f"{patients} patients, {cases} cases"
    if cases is not None:
        return f"{cases} cases"
    return "unknown"


def load_configured_split(config_path: str, seed: int) -> ConfiguredSplit:
    config = load_config(config_path)
    adapter_spec = config.get("adapter")
    if not adapter_spec:
        raise ValueError(f"Missing required 'adapter' in config: {config_path}")

    adapter = load_object(str(adapter_spec))
    split = adapter(config, seed=seed)
    required = {"train_cases", "eval_cases", "gt_data"}
    missing = sorted(required - set(split))
    if missing:
        raise ValueError(f"Adapter {adapter_spec} did not return required keys: {missing}")

    stats = dict(split.get("stats", {}))
    stats.setdefault("seed", seed)

    name = str(config.get("name") or os.path.splitext(os.path.basename(config_path))[0])
    tag = safe_name(str(config.get("tag") or name))

    return ConfiguredSplit(
        config=config,
        name=name,
        tag=tag,
        train_cases=split["train_cases"],
        eval_cases=split["eval_cases"],
        test_cases=list(split.get("test_cases") or []),
        gt_data=split["gt_data"],
        stats=stats,
        train_label=str(split.get("train_label") or _label(stats, "train")),
        eval_label=str(split.get("eval_label") or _label(stats, "eval")),
        test_label=str(split.get("test_label") or _label(stats, "test")),
    )
