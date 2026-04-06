"""Extract structured clinical features from each HuggingFace dataset entry.

For each (patient, visit) row, runs one LLM call with the extraction prompt
and saves the structured features alongside HF metadata to a JSON file.

Usage:
    conda run -n global_llm python classical/extract.py --visit 1
    conda run -n global_llm python classical/extract.py --visit 1 --limit 10
    conda run -n global_llm python classical/extract.py --all
    conda run -n global_llm python classical/extract.py --visit 1 --cohort csv
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

from datasets import load_dataset
from llm.client import LLMClient

_DATASET_NAME = "kartiksharma4/consilium"
_PROMPT_PATH = os.path.join(_HERE, "extract_features.txt")
_OUTPUT_DIR = os.path.join(_HERE, "outputs")


def _parse_features(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t[t.find("\n") + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3].strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        s, e = t.find("{"), t.rfind("}")
        if s != -1 and e > s:
            try:
                return json.loads(t[s:e + 1])
            except Exception:
                pass
    return {}


async def extract_one(row: dict, system_prompt: str, client: LLMClient) -> dict:
    _, content = await client.call(system_prompt, row["input"], temperature=0.0)
    features = _parse_features(content) if content else {}
    return {
        "pid": row["pid"],
        "cohort": row["cohort"],
        "visit_num": row["visit_num"],
        "features": features,
    }


async def run_visit(
    visit_num: int,
    system_prompt: str,
    client: LLMClient,
    cohort: str | None,
    limit: int | None,
):
    ds = load_dataset(_DATASET_NAME, split="train")
    ds = ds.filter(lambda x: x["visit_num"] == visit_num)
    if cohort:
        ds = ds.filter(lambda x: x["cohort"] == cohort)
    if limit:
        ds = ds.select(range(min(limit, len(ds))))

    rows = list(ds)
    print(f"  Visit {visit_num}: {len(rows)} entries")

    pbar = tqdm(total=len(rows), desc=f"Visit {visit_num}", unit="patient")
    records = []

    async def _one(row):
        result = await extract_one(row, system_prompt, client)
        pbar.update(1)
        return result

    for coro in asyncio.as_completed([_one(r) for r in rows]):
        records.append(await coro)

    pbar.close()

    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    cohort_suffix = f"_{cohort}" if cohort else ""
    out_path = os.path.join(_OUTPUT_DIR, f"features_v{visit_num}{cohort_suffix}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    print(f"  Saved {len(records)} records → {out_path}")


async def main():
    parser = argparse.ArgumentParser(description="Classical feature extraction")
    parser.add_argument("--visit", type=int, nargs="+", default=None,
                        help="Visit number(s) to process (e.g. --visit 1 2 3)")
    parser.add_argument("--all", action="store_true", help="Run all visits")
    parser.add_argument("--cohort", type=str, choices=["csv", "pdf"], default=None)
    parser.add_argument("--model", type=str, default="openai.gpt-oss-120b-1:0")
    parser.add_argument("--prompt", type=str, default=_PROMPT_PATH,
                        help="Path to extraction prompt file. Defaults to extract_features.txt.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max entries per visit (for testing)")
    args = parser.parse_args()

    visit_nums = list(range(1, 5)) if args.all else (args.visit or [1])

    with open(args.prompt, encoding="utf-8") as f:
        system_prompt = f.read()

    client = LLMClient(model=args.model)

    print(f"\n{'='*60}")
    print(f"FEATURE EXTRACTION")
    print(f"Model: {args.model}  |  Visits: {visit_nums}  |  Prompt: {os.path.basename(args.prompt)}")
    if args.cohort:
        print(f"Cohort: {args.cohort}")
    print(f"{'='*60}\n")

    for v in visit_nums:
        await run_visit(v, system_prompt, client, args.cohort, args.limit)

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
