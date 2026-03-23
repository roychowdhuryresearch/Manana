"""Run the single-agent baseline.

Loads patient cases from the dataset and runs the single-agent baseline
for comparison with the multi-agent system.

Usage:
    uv run python pipeline/run_baseline.py --visit 1
    uv run python pipeline/run_baseline.py --visit 1 --limit 5
    uv run python pipeline/run_baseline.py --all
"""

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

from llm.client import LLMClient
from pipeline.loader import load_cases
from schemas.output import DRUG_COLUMNS, ALLOWED_ACTIONS

_OUTPUT_DIR = os.path.join(_ROOT, "outputs", "baseline")
_PROMPT_PATH = os.path.join(_ROOT, "baseline", "prompts", "single_agent.txt")


def _find_drug(text: str) -> str | None:
    for drug in DRUG_COLUMNS:
        if drug in text:
            return drug
    return None


def parse_options(content: str) -> dict:
    """Parse 3 ranked drug options from baseline output."""
    sec2 = re.search(r'---\s*SECTION\s*2.*?---\s*(.*?)$', content, re.DOTALL | re.IGNORECASE)
    section_text = sec2.group(1).strip() if sec2 else content

    options = {}
    block_pattern = re.compile(
        r'Option\s+(\d)\s*:\s*(.+?)(?=Option\s+\d\s*:|$)',
        re.DOTALL | re.IGNORECASE,
    )
    for m in block_pattern.finditer(section_text):
        num = int(m.group(1))
        if num not in (1, 2, 3):
            continue
        block_lines = m.group(2).strip().split('\n')
        label = block_lines[0].strip() if block_lines else ""
        drugs, rationale_parts, in_rationale = {}, [], False

        for line in block_lines[1:]:
            s = line.strip()
            if not s:
                continue
            rat = re.match(r'[*_`]*Rationale[*_`]*\s*:?\s*(.*)', s, re.IGNORECASE)
            if rat:
                in_rationale = True
                rationale_parts.append(rat.group(1).strip())
                continue
            if in_rationale:
                rationale_parts.append(s)
                continue
            clean = re.sub(r'[*_`]', '', s)
            for seg in re.split(r'[.;]\s*', clean):
                seg_lower = seg.lower().strip()
                found_drug = _find_drug(seg_lower)
                found_action = next((a for a in ALLOWED_ACTIONS if a in seg_lower), None)
                if found_drug and found_action and found_drug not in drugs:
                    drugs[found_drug] = found_action

        options[f"option_{num}"] = {
            "label": label,
            "drugs": drugs,
            "rationale": " ".join(rationale_parts),
        }
    return options


async def run_visit(visit_num: int, model: str, limit: int | None, cohort: str | None, system_prompt: str, client: LLMClient):
    cases = load_cases(visit_num=visit_num, cohort=cohort, limit=limit)
    if not cases:
        print(f"  No cases found for visit {visit_num}, skipping.")
        return

    results = {}
    pbar = tqdm(total=len(cases), desc=f"Visit {visit_num}", unit="patient")

    async def _one(case):
        thinking, content = await client.call(system_prompt, case.build_input_text())
        pbar.update(1)
        return case.patient_id, thinking, content

    for coro in asyncio.as_completed([_one(c) for c in cases]):
        pid, thinking, content = await coro
        results[pid] = {"think": thinking, "raw_content": content, **parse_options(content)}

    pbar.close()

    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    short_model = model.replace("/", "_").replace("-", "")[:20]
    suffix = f"_{cohort}" if cohort else ""
    out_path = os.path.join(_OUTPUT_DIR, f"baseline_{short_model}_v{visit_num}{suffix}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  Saved {len(results)} patients → {out_path}")


async def main():
    parser = argparse.ArgumentParser(description="Single-Agent Baseline")
    parser.add_argument("--visit", type=int, nargs="+", default=None)
    parser.add_argument("--all", action="store_true", help="Run all visits")
    parser.add_argument("--cohort", type=str, choices=["csv", "pdf"], default=None)
    parser.add_argument("--model", type=str, default="openai.gpt-oss-120b-1:0")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    visit_nums = list(range(1, 11)) if args.all else (args.visit or [1])

    with open(_PROMPT_PATH, encoding="utf-8") as f:
        system_prompt = f.read()

    client = LLMClient(model=args.model)

    print(f"\n{'='*60}")
    print(f"BASELINE — SINGLE-AGENT PREDICTION")
    print(f"Model: {args.model}  |  Visits: {visit_nums}")
    if args.cohort:
        print(f"Cohort: {args.cohort}")
    print(f"{'='*60}\n")

    for v in visit_nums:
        await run_visit(v, args.model, args.limit, args.cohort, system_prompt, client)

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
