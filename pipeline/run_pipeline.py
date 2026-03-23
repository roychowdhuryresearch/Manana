"""Run the Consilium multi-agent pipeline.

Loads patient cases from the dataset and runs the full multi-agent pipeline.
Traces and predictions are saved locally.

Usage:
    uv run python pipeline/run_pipeline.py --visit 1
    uv run python pipeline/run_pipeline.py --visit 1 --limit 5
    uv run python pipeline/run_pipeline.py --all
"""

import argparse
import asyncio
import json
import os
import sys

from tqdm import tqdm

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from llm.client import LLMClient
from orchestrator.pipeline import ConsiliumPipeline
from pipeline.loader import load_cases

_OUTPUT_DIR = os.path.join(_ROOT, "outputs", "predictions")


async def run_visit(visit_num: int, model: str, max_rounds: int, limit: int | None, cohort: str | None):
    cases = load_cases(visit_num=visit_num, cohort=cohort, limit=limit)
    if not cases:
        print(f"  No cases found for visit {visit_num}, skipping.")
        return

    client = LLMClient(model=model)
    pipeline = ConsiliumPipeline(llm_client=client, max_debate_rounds=max_rounds)

    all_results = {}
    pbar = tqdm(total=len(cases), desc=f"Visit {visit_num}", unit="patient")

    async def _one(case):
        result = await pipeline.run(case)
        pbar.update(1)
        return case.patient_id, result

    results = await asyncio.gather(*[_one(c) for c in cases], return_exceptions=True)
    pbar.close()
    await client.close()

    for item in results:
        if isinstance(item, Exception):
            print(f"[ERROR] {item}")
        else:
            pid, result = item
            all_results[pid] = result

    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    short_model = model.replace("/", "_").replace("-", "")[:20]
    suffix = f"_{cohort}" if cohort else ""
    out_path = os.path.join(_OUTPUT_DIR, f"consilium_{short_model}_v{visit_num}_d{max_rounds}{suffix}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"  Saved {len(all_results)} patients → {out_path}")


async def main():
    parser = argparse.ArgumentParser(description="Consilium Multi-Agent Pipeline")
    parser.add_argument("--visit", type=int, nargs="+", default=None, help="Visit number(s) to run")
    parser.add_argument("--all", action="store_true", help="Run all visits")
    parser.add_argument("--cohort", type=str, choices=["csv", "pdf"], default=None, help="Filter by cohort")
    parser.add_argument("--model", type=str, default="openai.gpt-oss-120b-1:0")
    parser.add_argument("--max-rounds", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    visit_nums = list(range(1, 11)) if args.all else (args.visit or [1])

    print(f"\n{'='*60}")
    print(f"CONSILIUM — MULTI-AGENT PIPELINE")
    print(f"Model: {args.model}  |  Visits: {visit_nums}  |  Debate rounds: {args.max_rounds}")
    if args.cohort:
        print(f"Cohort: {args.cohort}")
    print(f"{'='*60}\n")

    for v in visit_nums:
        await run_visit(v, args.model, args.max_rounds, args.limit, args.cohort)


if __name__ == "__main__":
    asyncio.run(main())
