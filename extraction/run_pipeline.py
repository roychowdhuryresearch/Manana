"""Run multi-agent Consilium pipeline on the extraction cohort (53 patients, 3-6 visits).

Usage:
    uv run python extraction/run_pipeline.py --visit 1
    uv run python extraction/run_pipeline.py --all
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
from extraction.loader import load_all_cases

_OUTPUT_DIR = os.path.join(_HERE, "outputs", "predictions")


async def run_visit(visit_num: int, model: str, max_rounds: int, limit: int | None, output_dir: str):
    cases = load_all_cases(visit_num=visit_num, limit=limit)
    if not cases:
        print(f"  No patients found for Visit {visit_num}, skipping.")
        return {}

    client = LLMClient(model=model)
    pipeline = ConsiliumPipeline(llm_client=client, max_debate_rounds=max_rounds)

    all_results = {}
    pbar = tqdm(total=len(cases), desc=f"Pipeline V{visit_num}", unit="patient")

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

    short_model = model.replace("/", "_").replace("-", "")[:20]
    out_path = os.path.join(output_dir, f"extraction_consilium_{short_model}_v{visit_num}_d{max_rounds}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"  Saved {len(all_results)} patients → {out_path}")
    return all_results


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--visit", type=int, nargs="+", default=None)
    parser.add_argument("--all", action="store_true", help="Run all visits (1-6)")
    parser.add_argument("--model", type=str, default="openai.gpt-oss-120b-1:0")
    parser.add_argument("--max-rounds", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    visit_nums = list(range(1, 7)) if args.all else (args.visit or [1])
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"EXTRACTION COHORT — MULTI-AGENT PIPELINE")
    print(f"Model: {args.model}  |  Visits: {visit_nums}  |  Debate rounds: {args.max_rounds}")
    print(f"{'='*60}\n")

    for v in visit_nums:
        await run_visit(v, args.model, args.max_rounds, args.limit, _OUTPUT_DIR)


if __name__ == "__main__":
    asyncio.run(main())
