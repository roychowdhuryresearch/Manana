"""Run single-agent baseline on the extraction cohort (53 patients, 3-6 visits).

Usage:
    uv run python extraction/run_baseline.py --visit 1
    uv run python extraction/run_baseline.py --visit 1 2 3 4   # run multiple visits
    uv run python extraction/run_baseline.py --all              # all visits for all patients
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
from baseline.predict import parse_options
from extraction.loader import load_all_cases

_OUTPUT_DIR = os.path.join(_HERE, "outputs", "predictions")


async def run_visit(visit_num: int, model: str, limit: int | None, output_dir: str):
    prompt_path = os.path.join(_ROOT, "baseline", "prompts", "predict_prompt.txt")
    with open(prompt_path, encoding="utf-8") as f:
        system_prompt = f.read()

    cases = load_all_cases(visit_num=visit_num, limit=limit)
    if not cases:
        print(f"  No patients found for Visit {visit_num}, skipping.")
        return {}

    client = LLMClient(model=model)
    results = {}
    pbar = tqdm(total=len(cases), desc=f"Baseline V{visit_num}", unit="patient")

    async def _one(case):
        input_text = case.build_input_text()
        thinking, content = await client.call(system_prompt, input_text)
        return case.patient_id, thinking, content

    for coro in asyncio.as_completed([_one(c) for c in cases]):
        pid, thinking, content = await coro
        results[pid] = {"think": thinking, "raw_content": content, **parse_options(content)}
        pbar.update(1)

    pbar.close()
    await client.close()

    short_model = model.replace("/", "_").replace("-", "")[:20]
    out_path = os.path.join(output_dir, f"extraction_baseline_{short_model}_v{visit_num}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  Saved {len(results)} patients → {out_path}")
    return results


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--visit", type=int, nargs="+", default=None,
                        help="Visit number(s) to run (e.g. --visit 1 2 3)")
    parser.add_argument("--all", action="store_true", help="Run all visits (1-6)")
    parser.add_argument("--model", type=str, default="openai.gpt-oss-120b-1:0")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    visit_nums = list(range(1, 7)) if args.all else (args.visit or [1])
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"EXTRACTION COHORT — BASELINE")
    print(f"Model: {args.model}  |  Visits: {visit_nums}")
    print(f"{'='*60}\n")

    for v in visit_nums:
        await run_visit(v, args.model, args.limit, _OUTPUT_DIR)


if __name__ == "__main__":
    asyncio.run(main())
