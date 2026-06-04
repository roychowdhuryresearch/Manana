"""Run a saved Manana checkpoint on any config-backed Case JSONL split.

This script only produces predictions. Use `lib.grader` to score them:

    uv run python -m manana.evaluate --config configs/mimic.yaml \
      --run-dir manana/single/outputs/mimic/openai_gpt-oss-120b-1_0/20260512_120000 \
      --split test --round best

    uv run python -m lib.grader --predictions <predictions.json> --config configs/mimic.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from typing import Any

from lib.grader import case_key, regimen_options, visit_num_from_record
from lib.regimen_parser import parse_regimen
from lib.llm import DEFAULT_MODEL, LLMClient
from manana.datasets import ConfiguredSplit, load_configured_split
from manana.prompts import load_rendered_prompt
from manana.single import run_loop as single_loop
from manana.multi import run_loop as multi_loop


def detect_system(run_dir: str) -> str:
    parts = set(os.path.normpath(run_dir).lower().split(os.sep))
    if "single" in parts:
        return "single"
    if "multi" in parts:
        return "multi"
    raise ValueError(f"Cannot detect system from run dir. Pass --system single|multi: {run_dir}")


def _summary_field(run_dir: str, field: str) -> str | None:
    path = os.path.join(run_dir, "summary.md")
    if not os.path.exists(path):
        return None
    pattern = re.compile(rf"\*\*{re.escape(field)}:\*\*\s*([^ \n]+)")
    with open(path, encoding="utf-8") as f:
        match = pattern.search(f.read())
    return match.group(1).strip() if match else None


def detect_model(run_dir: str) -> str | None:
    return _summary_field(run_dir, "Model")


def detect_seed(run_dir: str) -> int | None:
    value = _summary_field(run_dir, "Seed")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _round_files(run_dir: str) -> list[int]:
    rounds = []
    for name in os.listdir(run_dir):
        match = re.fullmatch(r"round_(\d+)\.json", name)
        if match:
            rounds.append(int(match.group(1)))
    return sorted(rounds)


def find_best_round(run_dir: str) -> int:
    path = os.path.join(run_dir, "eval_progression.json")
    if not os.path.exists(path):
        rounds = _round_files(run_dir)
        if not rounds:
            raise ValueError(f"No round files found in {run_dir}")
        return rounds[-1]

    with open(path, encoding="utf-8") as f:
        progression = json.load(f)
    candidates = [row for row in progression if isinstance(row.get("round"), int)]
    if not candidates:
        raise ValueError(f"No numbered rounds found in {path}")
    best = max(candidates, key=lambda row: row.get("top3_rate", row.get("candidate_top3_rate", 0)))
    return int(best["round"])


def resolve_round(run_dir: str, requested: str) -> int | str:
    requested = str(requested).lower()
    if requested == "baseline":
        return "baseline"
    if requested == "best":
        return find_best_round(run_dir)
    if requested in {"last", "final"}:
        rounds = _round_files(run_dir)
        if not rounds:
            raise ValueError(f"No round files found in {run_dir}")
        return rounds[-1]
    return int(requested)


def load_round_json(run_dir: str, round_id: int) -> dict[str, Any]:
    path = os.path.join(run_dir, f"round_{round_id}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_single_prompt(template: str, run_dir: str, round_id: int | str) -> tuple[str, dict[str, Any]]:
    if round_id == "baseline":
        learnings = []
    else:
        round_data = load_round_json(run_dir, int(round_id))
        learnings = (
            round_data.get("shared_learnings_after")
            or round_data.get("candidate_shared_learnings")
            or []
        )
    prompt = single_loop.build_predictor_prompt(template, list(learnings))
    state = {"shared_learnings": list(learnings)}
    return prompt, state


def load_multi_agents(run_dir: str, round_id: int | str) -> dict[str, str]:
    if round_id == "baseline":
        return {}
    round_data = load_round_json(run_dir, int(round_id))
    agents = round_data.get("agents_after") or round_data.get("candidate_agents") or {}
    return {str(name): str(prompt) for name, prompt in agents.items()}


def split_cases(configured: ConfiguredSplit, split_name: str) -> list:
    if split_name == "train":
        return configured.train_cases
    if split_name in {"eval", "val", "validation"}:
        return configured.eval_cases
    if split_name == "test":
        return configured.test_cases
    if split_name == "all":
        return configured.train_cases + configured.eval_cases + configured.test_cases
    raise ValueError(f"Unknown split: {split_name}")


def case_record(case, split_name: str) -> dict[str, Any]:
    visit_num = visit_num_from_record({"visit_num": case.current_visit})
    return {
        "pid": str(case.patient_id),
        "visit_num": visit_num,
        "case_key": case_key(case.patient_id, visit_num),
        "cohort": str(getattr(case, "cohort", "") or ""),
        "split": split_name,
    }


async def run_single_case(
    client: LLMClient,
    prompt: str,
    case,
    split_name: str,
    temperature: float | None,
) -> dict[str, Any] | None:
    _, raw = await client.call(prompt, case.build_input_text(), temperature=temperature)
    if not raw:
        return None
    regimen = parse_regimen(raw)
    return {
        **case_record(case, split_name),
        "raw_prediction": raw,
        "regimen": regimen,
        "options": regimen_options(regimen),
    }


async def run_multi_case(
    client: LLMClient,
    predictor_template: str,
    agents: dict[str, str],
    case,
    split_name: str,
    temperature: float | None,
) -> dict[str, Any] | None:
    patient_notes = case.build_input_text()
    agent_outputs = {}
    if agents:
        tasks = {name: client.call(prompt, patient_notes, temperature=temperature) for name, prompt in agents.items()}
        results = await asyncio.gather(*tasks.values())
        agent_outputs = {name: (content or "") for name, (_, content) in zip(tasks.keys(), results)}

    prompt = multi_loop.build_predictor_prompt(predictor_template, agent_outputs)
    _, raw = await client.call(prompt, patient_notes, temperature=temperature)
    if not raw:
        return None
    regimen = parse_regimen(raw)
    return {
        **case_record(case, split_name),
        "raw_prediction": raw,
        "regimen": regimen,
        "options": regimen_options(regimen),
        "agent_outputs": agent_outputs,
    }


async def run_predictions(
    *,
    system: str,
    config_path: str,
    run_dir: str,
    split_name: str,
    round_id: int | str,
    seed: int,
    model: str,
    limit: int | None,
    concurrency: int,
    thinking_budget: int,
    temperature: float | None,
) -> dict[str, Any]:
    configured = load_configured_split(config_path, seed)
    cases = split_cases(configured, split_name)
    if limit is not None:
        cases = cases[:limit]
    if not cases:
        raise ValueError(
            f"Split '{split_name}' has no cases for {config_path}. "
            "For explicit JSONL splits, include rows with split='test' if you want test evaluation."
        )

    template = load_rendered_prompt(system, "predictor", configured.config)
    client = LLMClient(model=model, max_concurrency=concurrency, thinking_budget=thinking_budget)
    try:
        if system == "single":
            prompt, checkpoint_state = build_single_prompt(template, run_dir, round_id)
            tasks = [
                run_single_case(client, prompt, case, split_name, temperature)
                for case in cases
            ]
        else:
            agents = load_multi_agents(run_dir, round_id)
            checkpoint_state = {"agents": agents}
            tasks = [
                run_multi_case(client, template, agents, case, split_name, temperature)
                for case in cases
            ]

        predictions = []
        for idx, task in enumerate(asyncio.as_completed(tasks), 1):
            result = await task
            if result is not None:
                predictions.append(result)
            if idx % 25 == 0 or idx == len(tasks):
                print(f"Evaluated {idx}/{len(tasks)} cases")
    finally:
        await client.close()

    return {
        "metadata": {
            "config": os.path.abspath(config_path),
            "run_dir": os.path.abspath(run_dir),
            "system": system,
            "split": split_name,
            "round": round_id,
            "seed": seed,
            "model": model,
            "n_cases_requested": len(cases),
            "n_predictions": len(predictions),
        },
        "checkpoint": checkpoint_state,
        "predictions": predictions,
    }


def default_output_path(run_dir: str, split_name: str, round_id: int | str) -> str:
    round_label = "baseline" if round_id == "baseline" else f"r{round_id}"
    return os.path.join(run_dir, "evaluations", f"{split_name}_{round_label}_predictions.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a saved Manana checkpoint on a config split.")
    parser.add_argument("--config", required=True, help="Run YAML config")
    parser.add_argument("--run-dir", required=True, help="Completed Manana run directory")
    parser.add_argument("--system", choices=["single", "multi"], default=None, help="Auto-detected from run-dir if omitted")
    parser.add_argument("--split", choices=["train", "eval", "test", "all"], default="test")
    parser.add_argument("--round", default="best", help="Round number, baseline, best, or last")
    parser.add_argument("--seed", type=int, default=None, help="Defaults to seed in summary.md, then 42")
    parser.add_argument("--model", default=None, help="Defaults to model in summary.md, then project default")
    parser.add_argument("--limit", type=int, default=None, help="Optional case cap for sanity checks")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--thinking-budget", type=int, default=0)
    parser.add_argument("--temp", type=float, default=None)
    parser.add_argument("--out", default=None, help="Prediction JSON output path")
    args = parser.parse_args()

    system = args.system or detect_system(args.run_dir)
    round_id = resolve_round(args.run_dir, args.round)
    seed = args.seed if args.seed is not None else (detect_seed(args.run_dir) or 42)
    model = args.model or detect_model(args.run_dir) or DEFAULT_MODEL

    print(f"System: {system}")
    print(f"Round:  {round_id}")
    print(f"Split:  {args.split}")
    print(f"Model:  {model}")
    print(f"Seed:   {seed}")

    result = asyncio.run(
        run_predictions(
            system=system,
            config_path=args.config,
            run_dir=args.run_dir,
            split_name=args.split,
            round_id=round_id,
            seed=seed,
            model=model,
            limit=args.limit,
            concurrency=args.concurrency,
            thinking_budget=args.thinking_budget,
            temperature=args.temp,
        )
    )

    out_path = args.out or default_output_path(args.run_dir, args.split, round_id)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Saved predictions: {out_path}")
    print("Grade with:")
    print(f"  uv run python -m lib.grader --predictions {out_path} --config {args.config}")


if __name__ == "__main__":
    main()
