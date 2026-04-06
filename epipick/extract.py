"""LLM-based extraction of EpiPick structured inputs from patient records.

Usage:
    conda run -n global_llm python epipick/extract.py
    conda run -n global_llm python epipick/extract.py --visit 1
    conda run -n global_llm python epipick/extract.py --cohort csv --limit 100
    conda run -n global_llm python epipick/extract.py --cohort csv --mono-only --limit 50
    conda run -n global_llm python epipick/extract.py --visit 1 --visit 2

Saves to epipick/outputs/extracted.json (appends to existing if --resume).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys

from tqdm import tqdm

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from datasets import load_dataset
from llm.client import LLMClient

_OUTPUT_DIR = os.path.join(_HERE, "outputs")
_PROMPT_PATH = os.path.join(_HERE, "prompts", "extract.txt")
_OUTPUT_FILE = os.path.join(_OUTPUT_DIR, "extracted.json")

DATASET_NAME = "kartiksharma4/consilium"
TRACKED_DRUGS = {
    "carbamazepine", "clobazam", "clonazepam", "ethosuximide",
    "lamotrigine", "levetiracetam", "phenobarbital", "phenytoin",
    "topiramate", "valproate",
}


def load_prompt() -> str:
    with open(_PROMPT_PATH) as f:
        return f.read()


def parse_json_response(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown fences."""
    text = text.strip()
    # Strip markdown code fences
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        # Try to find first { ... } block
        m = re.search(r"\{[\s\S]+\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None


def is_mono(prescribed: list[str]) -> bool:
    return len(prescribed) == 1


def load_dataset_rows(
    visits: list[int] | None,
    cohort: str | None,
    mono_only: bool,
    limit: int | None,
) -> list[dict]:
    ds = load_dataset(DATASET_NAME, split="train")

    if visits:
        ds = ds.filter(lambda x: x["visit_num"] in visits)
    if cohort:
        ds = ds.filter(lambda x: x["cohort"] == cohort)
    if mono_only:
        ds = ds.filter(lambda x: len(x.get("prescribed", [])) == 1)

    if limit:
        ds = ds.select(range(min(limit, len(ds))))

    return list(ds)


async def extract_all(rows: list[dict], concurrency: int) -> list[dict]:
    prompt_base = load_prompt()
    client = LLMClient(
        model="openai.gpt-oss-120b-1:0",
        max_tokens=800,
        thinking_budget=0,
        max_concurrency=concurrency,
    )

    results = []
    failed = 0
    pbar = tqdm(total=len(rows), desc="Extracting")

    async def process_one(row: dict) -> dict | None:
        pid = row["pid"]
        visit_num = row["visit_num"]
        user_content = prompt_base + "\n" + row["input"]

        _, text = await client.call(
            system_prompt="You are a precise clinical data extractor. Output only valid JSON.",
            user_content=user_content,
            temperature=0.0,
        )

        parsed = parse_json_response(text) if text else None
        if parsed is None:
            return None

        return {
            "pid": pid,
            "visit_num": visit_num,
            "cohort": row["cohort"],
            "prescribed": row.get("prescribed", []),
            "extracted": parsed,
            "raw_response": text,
        }

    tasks = [process_one(row) for row in rows]
    outputs = await asyncio.gather(*tasks)

    for result in outputs:
        pbar.update(1)
        if result is not None:
            results.append(result)
        else:
            failed += 1

    pbar.close()
    print(f"Extracted: {len(results)}, Failed: {failed}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Extract EpiPick inputs via LLM")
    parser.add_argument("--visit", type=int, action="append", dest="visits",
                        help="Visit number(s) to include (can repeat: --visit 1 --visit 2)")
    parser.add_argument("--cohort", type=str, default=None, choices=["csv", "pdf"],
                        help="Filter to cohort")
    parser.add_argument("--mono-only", action="store_true",
                        help="Only extract patients with single-drug GT prescription")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max patients to extract")
    parser.add_argument("--concurrency", type=int, default=8,
                        help="Concurrent LLM calls (default 8)")
    parser.add_argument("--resume", action="store_true",
                        help="Append to existing extracted.json instead of overwriting")
    parser.add_argument("--output", type=str, default=_OUTPUT_FILE,
                        help="Output JSON path")
    args = parser.parse_args()

    # Load rows
    rows = load_dataset_rows(
        visits=args.visits,
        cohort=args.cohort,
        mono_only=args.mono_only,
        limit=args.limit,
    )
    print(f"Loaded {len(rows)} rows")

    # Cost estimate: ~800 input tokens + 150 output tokens per patient
    # GPT-4o-mini class model — rough estimate
    est_input_tokens = len(rows) * 800
    est_output_tokens = len(rows) * 150
    print(f"Estimated tokens: ~{est_input_tokens:,} input, ~{est_output_tokens:,} output")

    # Run extraction
    results = asyncio.run(extract_all(rows, args.concurrency))

    # Handle resume
    if args.resume and os.path.exists(args.output):
        with open(args.output) as f:
            existing = json.load(f)
        existing_keys = {f"{r['pid']}__v{r['visit_num']}" for r in existing}
        new = [r for r in results if f"{r['pid']}__v{r['visit_num']}" not in existing_keys]
        results = existing + new
        print(f"Merged: {len(existing)} existing + {len(new)} new = {len(results)} total")

    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved {len(results)} records → {args.output}")

    # Quick stats
    from collections import Counter
    seizure_dist = Counter(
        r["extracted"].get("seizure_type", "?") for r in results
        if "extracted" in r
    )
    print("\nSeizure type distribution:")
    for k, v in seizure_dist.most_common():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
