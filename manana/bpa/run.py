"""Run Bayesian Prompt Averaging (BPA) over a multi-agent Manana run trajectory.

For each case in a split, the top-``num`` rounds (by validation top-3 rate) each
produce a ranked regimen via the existing `manana.evaluate` inference; their
options are combined by `manana.bpa.aggregate` into a weighted vote over complete
regimens. The output is a `lib.grader`-compatible predictions JSON (so scoring is
unchanged) plus a per-case BPA confidence used for selective prediction.

Example:
    uv run python -m manana.bpa.run \
      --config configs/jsonl_example.yaml \
      --run-dir manana/multi/outputs/<dataset>/<model>/<run_id> \
      --num 5 --split test
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

from lib.grader import (
    case_key,
    grade_files,
    print_scores,
    resolve_gt_jsonl_from_config,
)
from lib.llm import DEFAULT_MODEL, LLMClient
from manana.bpa.aggregate import DEFAULT_TAU, aggregate, coverage_precision, select_rounds
from manana.datasets import load_configured_split
from manana.evaluate import (
    case_record,
    detect_model,
    detect_seed,
    load_multi_agents,
    run_multi_case,
    split_cases,
)
from manana.prompts import load_rendered_prompt

COVERAGE_TARGETS = (0.25, 0.5, 0.75, 1.0)


def load_progression(run_dir: str) -> list[dict[str, Any]]:
    path = os.path.join(run_dir, "eval_progression.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"BPA needs the validation trajectory: missing {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def _bpa_one_case(
    client: LLMClient,
    predictor_template: str,
    selected,
    agents_by_round: dict[int, dict[str, str]],
    case,
    split_name: str,
    temperature: float | None,
    sem: asyncio.Semaphore,
) -> dict[str, Any] | None:
    """Run the selected rounds for one case and aggregate into a BPA prediction."""
    async with sem:
        tasks = [
            run_multi_case(client, predictor_template, agents_by_round[s.round_id], case, split_name, temperature)
            for s in selected
        ]
        round_results = await asyncio.gather(*tasks)

    per_round_options: list[tuple[float, list[dict[str, Any]]]] = []
    round_detail = []
    for s, result in zip(selected, round_results):
        options = (result or {}).get("options") or []
        per_round_options.append((s.weight, options))
        round_detail.append(
            {
                "round": s.round_id,
                "weight": round(s.weight, 4),
                "top3_rate": round(s.top3_rate, 4),
                "options": [o.get("drugs") for o in options],
            }
        )

    bpa = aggregate(per_round_options)
    if not bpa["options"]:
        return None

    return {
        **case_record(case, split_name),
        "options": [{"rank": o["rank"], "drugs": o["drugs"]} for o in bpa["options"]],
        "bpa": {
            "confidence": bpa["confidence"],
            "n_unique_regimens": bpa["n_unique_regimens"],
            "options": bpa["options"],
            "vote_distribution": bpa["vote_distribution"],
            "rounds": round_detail,
        },
    }


async def run_bpa(
    *,
    config_path: str,
    run_dir: str,
    split_name: str,
    num: int,
    weighting: str,
    tau: float,
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
        raise ValueError(f"Split {split_name!r} has no cases for {config_path}")

    progression = load_progression(run_dir)
    selected = select_rounds(progression, num=num, weighting=weighting, tau=tau)
    agents_by_round = {s.round_id: load_multi_agents(run_dir, s.round_id) for s in selected}
    predictor_template = load_rendered_prompt("multi", "predictor", configured.config)

    print(f"Selected {len(selected)} rounds (weighting={weighting}, tau={tau}):")
    for s in selected:
        n_agents = len(agents_by_round[s.round_id])
        print(f"  round {s.round_id:>2}: val top3={s.top3_rate:.3f}  weight={s.weight:.3f}  agents={n_agents}")
    print(f"Running BPA on {len(cases)} {split_name} cases "
          f"(~{num * (1 + max((len(a) for a in agents_by_round.values()), default=0))} Bedrock calls/case)...\n")

    client = LLMClient(model=model, max_concurrency=concurrency, thinking_budget=thinking_budget)
    sem = asyncio.Semaphore(max(1, concurrency))
    try:
        tasks = [
            _bpa_one_case(client, predictor_template, selected, agents_by_round, case, split_name, temperature, sem)
            for case in cases
        ]
        predictions = []
        for idx, task in enumerate(asyncio.as_completed(tasks), 1):
            result = await task
            if result is not None:
                predictions.append(result)
            if idx % 10 == 0 or idx == len(tasks):
                print(f"  aggregated {idx}/{len(tasks)} cases")
    finally:
        await client.close()

    return {
        "metadata": {
            "config": os.path.abspath(config_path),
            "run_dir": os.path.abspath(run_dir),
            "system": "multi",
            "method": "bpa",
            "split": split_name,
            "num": num,
            "weighting": weighting,
            "tau": tau,
            "seed": seed,
            "model": model,
            "n_cases_requested": len(cases),
            "n_predictions": len(predictions),
        },
        "bpa_rounds": [
            {"round": s.round_id, "top3_rate": s.top3_rate, "weight": s.weight} for s in selected
        ],
        "predictions": predictions,
    }


def default_output_path(run_dir: str, split_name: str, num: int, weighting: str) -> str:
    name = f"{split_name}_bpa_n{num}_{weighting}_predictions.json"
    return os.path.join(run_dir, "evaluations", name)


def report(predictions_path: str, config_path: str) -> None:
    """Grade BPA predictions and print the selective-prediction (coverage→precision) table."""
    gt_jsonl = resolve_gt_jsonl_from_config(config_path)
    result = grade_files(predictions_path, gt_jsonl)

    print("\n" + "=" * 56)
    print("BPA — exact-match scores (graded by lib.grader)")
    print("=" * 56)
    print_scores(result["scores"])

    # Join per-case top-1 correctness with BPA confidence for the deferral curve.
    with open(predictions_path, encoding="utf-8") as f:
        preds = json.load(f)["predictions"]
    conf_by_key = {
        case_key(p["pid"], p["visit_num"]): (p.get("bpa") or {}).get("confidence", 0.0)
        for p in preds
    }
    rows = [
        {"top1_match": pc["top1_match"], "confidence": conf_by_key.get(case_key(pc["pid"], pc["visit_num"]), 0.0)}
        for pc in result["per_case"]
    ]
    curve = coverage_precision(rows)

    print("\nSelective prediction (rank by BPA confidence):")
    print("  coverage   top-1 precision   conf threshold")
    total = len(curve)
    for target in COVERAGE_TARGETS:
        idx = min(int(target * total) - 1, total - 1)
        if idx >= 0:
            row = curve[idx]
            print(f"   {row['coverage']*100:5.1f}%        {row['precision']*100:5.1f}%          >= {row['confidence']:.3f}")
    print("=" * 56)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bayesian Prompt Averaging over a Manana multi-agent trajectory.")
    parser.add_argument("--config", required=True, help="Run YAML config")
    parser.add_argument("--run-dir", required=True, help="Completed multi-agent run directory")
    parser.add_argument("--split", choices=["train", "eval", "test", "all"], default="test")
    parser.add_argument("--num", type=int, default=5, help="Number of top rounds to ensemble (paper default: 5)")
    parser.add_argument("--weighting", choices=["uniform", "linear", "softmax"], default="softmax")
    parser.add_argument("--tau", type=float, default=DEFAULT_TAU, help="Softmax temperature (paper default: 5)")
    parser.add_argument("--seed", type=int, default=None, help="Defaults to seed in summary.md, then 42")
    parser.add_argument("--model", default=None, help="Defaults to model in summary.md, then project default")
    parser.add_argument("--limit", type=int, default=None, help="Optional case cap for sanity checks")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--thinking-budget", type=int, default=0)
    parser.add_argument("--temp", type=float, default=None)
    parser.add_argument("--out", default=None, help="Prediction JSON output path")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else (detect_seed(args.run_dir) or 42)
    model = args.model or detect_model(args.run_dir) or DEFAULT_MODEL

    print(f"Method: BPA (multi-agent)\nRun:    {args.run_dir}\nModel:  {model}\nSeed:   {seed}\n")

    result = asyncio.run(
        run_bpa(
            config_path=args.config,
            run_dir=args.run_dir,
            split_name=args.split,
            num=args.num,
            weighting=args.weighting,
            tau=args.tau,
            seed=seed,
            model=model,
            limit=args.limit,
            concurrency=args.concurrency,
            thinking_budget=args.thinking_budget,
            temperature=args.temp,
        )
    )

    out_path = args.out or default_output_path(args.run_dir, args.split, args.num, args.weighting)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nSaved BPA predictions: {out_path}")

    if result["predictions"]:
        report(out_path, args.config)


if __name__ == "__main__":
    main()
