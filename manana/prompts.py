"""Prompt template rendering for dataset-configured Manana runs."""

from __future__ import annotations

import os
from typing import Any

from manana.datasets import resolve_config_path


_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_PROMPT_ROOT = os.path.join(_ROOT, "prompts")


def drug_list_from_config(config: dict[str, Any]) -> list[str]:
    if "drug_list" in config:
        return [str(x) for x in config.get("drug_list") or []]
    path = config.get("drug_list_path")
    if path:
        full_path = resolve_config_path(config, str(path))
        with open(full_path, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.lstrip().startswith("#")]
    return []


def render_prompt_template(template: str, config: dict[str, Any]) -> str:
    prompt_cfg = config.get("prompt") or {}
    drugs = drug_list_from_config(config)
    replacements = {
        "{dataset_name}": str(config.get("name", "the dataset")),
        "{setting}": str(config.get("setting", "the target clinical setting")),
        "{input_description}": str(
            config.get("input_description", "the clinical information available before the decision")
        ),
        "{target_description}": str(
            config.get("target_description", "the clinician-prescribed medication regimen")
        ),
        "{drug_list}": ", ".join(drugs),
        "{drug_count}": str(len(drugs)),
        "{n_drugs}": str(len(drugs)),
        "{candidate_label}": str(prompt_cfg.get("candidate_label", "CANDIDATE_LEARNING")),
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


def load_rendered_prompt(system: str, name: str, config: dict[str, Any]) -> str:
    prompt_root = resolve_config_path(config, config.get("prompt_root")) or DEFAULT_PROMPT_ROOT
    path = os.path.join(prompt_root, system, f"{name}.txt")
    with open(path, encoding="utf-8") as f:
        return render_prompt_template(f.read(), config)


def load_prompt_set(system: str, config: dict[str, Any]) -> dict[str, str]:
    """Load predictor, inspector, and architect prompts for a configured system."""
    return {
        "predictor": load_rendered_prompt(system, "predictor", config),
        "inspector": load_rendered_prompt(system, "inspector", config),
        "architect": load_rendered_prompt(system, "architect", config),
    }
