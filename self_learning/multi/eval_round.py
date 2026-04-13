"""Run a self-learning round's agents on full cohort(s) and save predictions.

Output format matches run_pipeline.py exactly so scripts/evaluate.py works unchanged.

Usage:
    # R7, all visits, csv cohort
    uv run python self_learning/multi/eval_round.py --round 7 --visit 1 2 3 --cohort csv

    # All visits
    uv run python self_learning/multi/eval_round.py --round 7 --all --cohort csv

    # Different run directory
    uv run python self_learning/multi/eval_round.py --round 7 --all --cohort csv \\
        --run-dir self_learning/multi/outputs/openai_gpt-oss-120b-1_0/loop_20260412_1008

    # Small test
    uv run python self_learning/multi/eval_round.py --round 7 --visit 1 --cohort csv --limit 5

Then evaluate with:
    uv run python scripts/evaluate.py --predictions outputs/predictions/sl_r7_csv_v1_*.json
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

from tqdm import tqdm
from llm.client import LLMClient, DEFAULT_MODEL
from core.regimen_parser import parse_regimen
from scripts.loader import load_cases
from self_learning.multi.run_loop import (
    build_predictor_prompt,
    get_visit_num,
    sanitize_model_name,
)

_DEFAULT_RUN_DIR = os.path.join(
    _HERE, "outputs", "openai_gpt-oss-120b-1_0", "loop_20260412_2150"
)
_OUTPUT_DIR = os.path.join(_HERE, "outputs", "eval_full")


def load_agents_from_round(run_dir: str, round_num: int | str) -> dict[str, str]:
    """Load agents_after from round_{N}.json. Returns {} for 'baseline'."""
    if str(round_num).lower() == "baseline":
        return {}
    path = os.path.join(run_dir, f"round_{round_num}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Round file not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    agents = data.get("agents_after", {})
    if not agents:
        print(f"  [WARN] agents_after is empty in round_{round_num}.json — treating as baseline")
    return agents


def load_predictor_prompt() -> str:
    with open(os.path.join(_HERE, "prompts", "predictor.txt"), encoding="utf-8") as f:
        return f.read()


async def _run_agent(client: LLMClient, prompt: str, notes: str) -> str:
    _, out = await client.call(prompt, notes)
    return out or ""


async def run_case(
    client: LLMClient,
    agents: dict[str, str],
    predictor_template: str,
    case,
) -> dict | None:
    patient_notes = case.build_input_text()

    agent_outputs: dict[str, str] = {}
    if agents:
        results = await asyncio.gather(*[
            _run_agent(client, prompt, patient_notes)
            for prompt in agents.values()
        ])
        agent_outputs = dict(zip(agents.keys(), results))

    predictor_prompt = build_predictor_prompt(predictor_template, agent_outputs)
    _, pred_raw = await client.call(predictor_prompt, patient_notes)
    if not pred_raw:
        print(f"  [WARN] Predictor failure for {case.patient_id} v{get_visit_num(case)}")
        return None

    return {
        "pid": case.patient_id,
        "cohort": case.cohort,
        "visit_num": get_visit_num(case),
        "agent_outputs": agent_outputs,
        "trace": {
            "final_regimen": parse_regimen(pred_raw),
            "predictor_raw": pred_raw,
        },
    }


async def run_visit(
    visit_num: int,
    cohort: str,
    agents: dict[str, str],
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
        result = await run_case(client, agents, predictor_template, case)
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
        f"sl_r{round_num}_{short_model}_{cohort}_v{visit_num}_{ts}.json",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "round": round_num,
                "run_dir": run_dir,
                "model": model,
                "cohort": cohort,
                "visit": visit_num,
                "agents": agents,
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
    agents = load_agents_from_round(run_dir, round_num)
    predictor_template = load_predictor_prompt()

    print(f"\n{'='*60}")
    print(f"SELF-LEARNING EVAL — Round {round_num}")
    print(f"{'='*60}")
    print(f"Run dir:  {run_dir}")
    print(f"Model:    {model}")
    print(f"Agents ({len(agents)}): {list(agents.keys())}")
    print(f"Cohort:   {cohort}  |  Visits: {visit_nums}")
    if limit:
        print(f"Limit:    {limit} cases per visit")
    print(f"{'='*60}\n")

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    for v in visit_nums:
        await run_visit(v, cohort, agents, predictor_template, model, round_num, run_dir, limit, ts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run self-learning round agents on full cohort")
    parser.add_argument("--round", required=True,
                        help="Round number (e.g. 7) or 'baseline'")
    parser.add_argument("--visit", type=int, nargs="+", default=None,
                        help="Visit number(s) to run")
    parser.add_argument("--all", action="store_true",
                        help="Run all visits (1-10)")
    parser.add_argument("--cohort", type=str, choices=["csv", "pdf"], required=True,
                        help="Cohort to evaluate: csv or pdf")
    parser.add_argument("--run-dir", default=_DEFAULT_RUN_DIR,
                        help="Path to loop run directory (default: loop_20260412_2150)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap cases per visit (for testing)")
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
