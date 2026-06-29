"""Config loading helpers for release-style Manana runs."""

from __future__ import annotations

import importlib
import os
from typing import Any, Callable

import yaml


def load_config(path: str) -> dict[str, Any]:
    """Load a YAML config and attach its directory for relative paths."""
    abs_path = os.path.abspath(path)
    with open(abs_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if not isinstance(config, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")
    config["_config_path"] = abs_path
    config["_config_dir"] = os.path.dirname(abs_path)
    return config


def resolve_config_path(config: dict[str, Any], path: str | None) -> str | None:
    """Resolve relative paths from the config file directory."""
    if path is None or os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(config["_config_dir"], path))


def import_object(spec: str) -> Callable:
    """Import `package.module:object`."""
    if ":" not in spec:
        raise ValueError(f"Expected import spec 'module:object', got: {spec}")
    module_name, object_name = spec.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, object_name)


def load_split_from_config(config: dict[str, Any], seed: int) -> dict:
    """Call the configured data adapter and return the standard split dict."""
    adapter_spec = config.get("adapter")
    if not adapter_spec:
        raise ValueError("Config missing required field: adapter")
    adapter = import_object(adapter_spec)
    split = adapter(config=config, seed=seed)
    required = {"train_cases", "eval_cases", "gt_data", "stats"}
    missing = required - set(split)
    if missing:
        raise ValueError(f"Adapter {adapter_spec} returned split missing keys: {sorted(missing)}")
    return split
