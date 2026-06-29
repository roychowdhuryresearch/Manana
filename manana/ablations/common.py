"""Shared helpers for Manana ablation runners."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from lib.regimen_parser import parse_regimen
from manana.datasets import load_configured_split, resolve_config_path
from manana.single import run_loop as single_loop


ABLATIONS_DIR = os.path.dirname(os.path.abspath(__file__))


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_ablation_prompt(name: str) -> str:
    return load_text(os.path.join(ABLATIONS_DIR, "prompts", name))


def load_rewrite_prompt(name: str) -> str:
    return load_text(os.path.join(ABLATIONS_DIR, "rewrite", "prompts", name))


def make_output_dir(
    config: dict,
    system: str,
    study: str,
    model: str,
    seed: int,
    tag: str,
) -> str:
    model_folder = single_loop.sanitize_model_name(model)
    run_id = f"{study}_{tag}_{system}_s{seed}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_root = resolve_config_path(config, config.get("output_root"))
    if output_root:
        output_dir = os.path.join(output_root, "manana", "ablations", study, system, model_folder, run_id)
    else:
        output_dir = os.path.join(ABLATIONS_DIR, "runs", study, system, model_folder, run_id)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def load_split(config_path: str, seed: int):
    return load_configured_split(config_path, seed)


def get_visit_num(case) -> int:
    return int(case.current_visit.split("_")[1])


def get_gt_key(case) -> str:
    return f"{case.patient_id}__v{get_visit_num(case)}"


def drugs_from_regimen(regimen: dict, option_key: str = "option_1") -> set[str]:
    opt = regimen.get(option_key, {})
    drugs = opt.get("drugs", {})
    return {d for d, action in drugs.items() if action in ("continue", "start")}


def parsed_options(pred_raw: str) -> dict[str, list[str]]:
    regimen = parse_regimen(pred_raw)
    return {
        f"option_{i}": sorted(drugs_from_regimen(regimen, f"option_{i}"))
        for i in [1, 2, 3]
    }


def best_matching_option(options: dict[str, list[str]], gt_drugs: set[str]) -> str | None:
    for opt_key, drugs in options.items():
        if set(drugs) == gt_drugs:
            return opt_key
    return None


def summarize_eval(eval_entry: dict) -> str:
    mono = f"{eval_entry['mono_top3']}/{eval_entry['mono_total']}"
    poly = f"{eval_entry['poly_top3']}/{eval_entry['poly_total']}"
    return (
        f"top3={eval_entry['top3_correct']}/{eval_entry['total']} "
        f"({eval_entry['top3_rate']:.0%})  mono={mono}  poly={poly}"
    )


def strip_code_fences(text: str) -> str:
    text = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", text)
    return text.replace("```", "").strip()


def parse_json_object(raw: str) -> dict | None:
    text = strip_code_fences(raw)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group())
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def print_header(title: str, rows: list[tuple[str, str]]) -> None:
    print(f"\n{'=' * 60}")
    print(title)
    print(f"{'=' * 60}")
    for key, value in rows:
        print(f"{key:<12} {value}")
    print(f"{'=' * 60}")
