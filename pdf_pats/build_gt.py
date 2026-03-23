"""Build drug_gt.json for all PDF patients.

For each visit in split_results.json, call LLM with the clean output_text
to extract prescribed/stopped drugs. Same prompt as pipeline/gt_extract_prompt.txt.

Output: pdf_pats/outputs/drug_gt.json

Usage:
    uv run python pdf_pats/build_gt.py --limit 5
    uv run python pdf_pats/build_gt.py
"""

import os
import re
import sys
import json
import asyncio
import argparse
from tqdm import tqdm

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from llm.client import LLMClient

_SPLITS_PATH = os.path.join(_HERE, "outputs", "split_results.json")
_PROMPT_PATH = os.path.join(_ROOT, "pipeline", "prompts", "gt_extract_prompt.txt")
_OUT_PATH = os.path.join(_HERE, "outputs", "drug_gt.json")

VALID_DRUGS = {
    "carbamazepine", "clobazam", "clonazepam", "ethosuximide",
    "lamotrigine", "levetiracetam", "phenobarbital", "phenytoin",
    "topiramate", "valproate",
}


def parse_gt_response(content: str) -> tuple[list[str], list[str]]:
    content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.MULTILINE)
    content = re.sub(r"\s*```$", "", content.strip(), flags=re.MULTILINE)
    try:
        obj = json.loads(content)
        prescribed = [d for d in obj.get("prescribed", []) if d in VALID_DRUGS]
        stopped = [d for d in obj.get("stopped", []) if d in VALID_DRUGS]
    except json.JSONDecodeError:
        return [], []
    # If a drug appears in both (taper-to-stop), keep only in prescribed
    overlap = set(prescribed) & set(stopped)
    stopped = [d for d in stopped if d not in overlap]
    return prescribed, stopped


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Process only N patients")
    parser.add_argument("--model", type=str, default="openai.gpt-oss-120b-1:0")
    args = parser.parse_args()

    with open(_SPLITS_PATH, encoding="utf-8") as f:
        splits = json.load(f)

    with open(_PROMPT_PATH, encoding="utf-8") as f:
        system_prompt = f.read()

    patients = list(splits.keys())
    if args.limit:
        patients = patients[: args.limit]

    # Collect all (patient, visit_key, output_text) tasks
    tasks = []
    for patient in patients:
        for visit_key, visit_data in splits[patient].items():
            output_text = visit_data.get("output_text", "").strip()
            tasks.append((patient, visit_key, output_text))

    print(f"Patients: {len(patients)}, total visits: {len(tasks)}")

    client = LLMClient(model=args.model)
    gt: dict[str, dict] = {p: {} for p in patients}

    pbar = tqdm(total=len(tasks), desc="Extracting GT", unit="visit")

    async def _one(patient, visit_key, output_text):
        if not output_text:
            pbar.update(1)
            return patient, visit_key, [], []
        _, content = await client.call(system_prompt, output_text)
        prescribed, stopped = parse_gt_response(content)
        pbar.update(1)
        return patient, visit_key, prescribed, stopped

    results = await asyncio.gather(
        *[_one(*t) for t in tasks],
        return_exceptions=True,
    )
    pbar.close()
    await client.close()

    errors = 0
    for item in results:
        if isinstance(item, Exception):
            print(f"[ERROR] {item}")
            errors += 1
            continue
        patient, visit_key, prescribed, stopped = item
        gt[patient][visit_key] = {"prescribed": prescribed, "stopped": stopped}

    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    with open(_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(gt, f, indent=2, ensure_ascii=False)

    total_visits = sum(len(v) for v in gt.values())
    print(f"\nDone. Errors: {errors}")
    print(f"  Patients:     {len(gt)}")
    print(f"  Total visits: {total_visits}")
    print(f"Saved → {_OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
