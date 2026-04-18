"""Evaluate TextGrad optimized learnings on full cohort(s).

Learnings are stored as a single string (the system prompt) in round_{N}.json
under the key 'learnings_after'. The predictor template is textgrad_opt/prompts/predictor.txt
and is used as the user message; learnings are injected as the system prompt directly.

Usage:
    uv run python textgrad_opt/eval.py --round 11 --visit 1 2 3 --cohort csv
    uv run python textgrad_opt/eval.py --round 11 --visit 1 2 3 --cohort pdf \\
        --run-dir textgrad_opt/outputs/tg_20260417_2032_037e14
    uv run python textgrad_opt/eval.py --round baseline --visit 1 2 3 --cohort csv
    uv run python textgrad_opt/eval.py --round 11 --all --cohort csv
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from tqdm import tqdm
from llm.client import LLMClient, DEFAULT_MODEL
from core.regimen_parser import parse_regimen
from scripts.loader import load_cases

_DEFAULT_RUN_DIR = os.path.join(_HERE, "outputs", "tg_20260417_2032_037e14")
_OUTPUT_DIR = os.path.join(_HERE, "outputs", "eval_full")


def sanitize_model_name(model: str) -> str:
    name = re.sub(r'[^a-zA-Z0-9-]', '_', model)
    name = re.sub(r'_+', '_', name).strip('_')
    return name.lower()


def get_visit_num(case) -> int:
    return int(case.current_visit.split("_")[1])


def load_learnings_from_round(run_dir: str, round_num: int | str) -> str:
    """Load learnings_after from round_{N}.json as a single string. Returns '' for baseline."""
    if str(round_num).lower() == "baseline":
        return ""
    path = os.path.join(run_dir, f"round_{round_num}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Round file not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    learnings = data.get("learnings_after", "")
    if not learnings:
        print(f"  [WARN] learnings_after is empty in round_{round_num}.json — treating as baseline")
    return learnings


def load_predictor_template() -> str:
    with open(os.path.join(_HERE, "prompts", "predictor.txt"), encoding="utf-8") as f:
        return f.read()


async def run_case(
    client: LLMClient,
    system_prompt: str,
    predictor_template: str,
    case,
) -> dict | None:
    patient_notes = case.build_input_text()
    user_msg = predictor_template + "\n" + patient_notes
    _, pred_raw = await client.call(system_prompt, user_msg)
    if not pred_raw:
        print(f"  [WARN] Predictor failure for {case.patient_id} v{get_visit_num(case)}")
        return None

    return {
        "pid": case.patient_id,
        "cohort": case.cohort,
        "visit_num": get_visit_num(case),
        "trace": {
            "final_regimen": parse_regimen(pred_raw),
            "predictor_raw": pred_raw,
        },
    }


async def run_visit(
    visit_num: int,
    cohort: str,
    system_prompt: str,
    predictor_template: str,
    model: str,
    round_num: int | str,
    run_dir: str,
    limit: int | None,
    ts: str,
):
    cases = load_cases(visit_num=visit_num, cohort=cohort, limit=limit)
    if not cases:
        print(f"  No cases for visit {visit_num}, skipping.")
        return

    client = LLMClient(model=model)
    pbar = tqdm(total=len(cases), desc=f"Visit {visit_num}", unit="patient")

    async def _one(case):
        result = await run_case(client, system_prompt, predictor_template, case)
        pbar.update(1)
        return result

    results = await asyncio.gather(*[_one(c) for c in cases], return_exceptions=True)
    pbar.close()
    await client.close()

    records = []
    for r in results:
        if isinstance(r, Exception):
            print(f"  [ERROR] {r}")
        elif r is not None:
            records.append(r)

    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    short_model = sanitize_model_name(model)[:20].strip('-_')
    out_path = os.path.join(
        _OUTPUT_DIR,
        f"tg_r{round_num}_{short_model}_{cohort}_v{visit_num}_{ts}.json",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "round": round_num,
                "run_dir": run_dir,
                "model": model,
                "cohort": cohort,
                "visit": visit_num,
                "records": records,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"  Saved {len(records)} records → {out_path}")


async def main(
    visit_nums: list[int],
    cohort: str,
    round_num: int | str,
    run_dir: str,
    model: str,
    limit: int | None,
):
    system_prompt = load_learnings_from_round(run_dir, round_num)
    predictor_template = load_predictor_template()

    print(f"\n{'='*60}")
    print(f"TEXTGRAD EVAL — Round {round_num}")
    print(f"{'='*60}")
    print(f"Run dir:   {run_dir}")
    print(f"Model:     {model}")
    print(f"Learnings: {'(baseline — empty)' if not system_prompt else system_prompt[:120] + '...'}")
    print(f"Cohort:    {cohort}  |  Visits: {visit_nums}")
    if limit:
        print(f"Limit:     {limit} cases per visit")
    print(f"{'='*60}\n")

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    for v in visit_nums:
        await run_visit(v, cohort, system_prompt, predictor_template, model, round_num, run_dir, limit, ts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate TextGrad optimized learnings on full cohort")
    parser.add_argument("--round", required=True, help="Round number or 'baseline'")
    parser.add_argument("--visit", type=int, nargs="+", default=None)
    parser.add_argument("--all", action="store_true", help="Run all visits (1-10)")
    parser.add_argument("--cohort", type=str, choices=["csv", "pdf"], required=True)
    parser.add_argument("--run-dir", default=_DEFAULT_RUN_DIR)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if not args.visit and not args.all:
        parser.error("Specify --visit 1 2 3 or --all")

    visit_nums = list(range(1, 11)) if args.all else args.visit
    round_num = args.round if args.round.lower() == "baseline" else int(args.round)

    asyncio.run(main(
        visit_nums=visit_nums,
        cohort=args.cohort,
        round_num=round_num,
        run_dir=args.run_dir,
        model=args.model,
        limit=args.limit,
    ))
