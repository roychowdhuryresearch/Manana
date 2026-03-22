"""Single-agent baseline prediction — adapted from predict_drugs_clean.py.

Uses the original 7-stage reasoning prompt as a single-agent baseline
for comparison with the multi-agent system.
"""

import os
import re
import json
import asyncio
from tqdm import tqdm

from llm.client import LLMClient
from data.loader import load_all_cases
from schemas.output import DRUG_COLUMNS, ALLOWED_ACTIONS

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _find_drug_in_line(text: str) -> str | None:
    """Find a drug name in a line of text."""
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
            # Strip markdown bold/italic markers before matching
            clean = re.sub(r'[*_`]', '', s)
            segments = re.split(r'[.;]\s*', clean)
            for seg in segments:
                seg_lower = seg.lower().strip()
                if not seg_lower:
                    continue
                found_drug = _find_drug_in_line(seg_lower)
                found_action = None
                for act in ALLOWED_ACTIONS:
                    if act in seg_lower:
                        found_action = act
                        break
                if found_drug and found_action:
                    if found_drug not in drugs:
                        drugs[found_drug] = found_action

        options[f"option_{num}"] = {
            "label": label,
            "drugs": drugs,
            "rationale": " ".join(rationale_parts),
        }
    return options


def format_drugs_str(drugs: dict) -> str:
    return "; ".join(f"{drug}:{action}" for drug, action in drugs.items())


async def run_baseline(
    visit_num: int = 1,
    model: str = "openai.gpt-oss-120b-1:0",
    limit: int | None = None,
    output_dir: str | None = None,
):
    """Run single-agent baseline on all patients for a given visit."""
    if output_dir is None:
        output_dir = os.path.join(_ROOT, "outputs", "baseline")
    os.makedirs(output_dir, exist_ok=True)

    # Load prompt
    prompt_path = os.path.join(_HERE, "prompts", "predict_prompt.txt")
    with open(prompt_path, encoding="utf-8") as f:
        system_prompt = f.read()

    # Load patients
    cases = load_all_cases(visit_num=visit_num, limit=limit)

    client = LLMClient(model=model)

    print(f"\n{'='*60}")
    print(f"BASELINE PREDICTION — SINGLE AGENT")
    print(f"{'='*60}")
    print(f"Model:    {model}")
    print(f"Visit:    {visit_num}")
    print(f"Patients: {len(cases)}")
    print(f"Output:   {output_dir}")
    print(f"{'='*60}\n")

    results = {}
    pbar = tqdm(total=len(cases), desc="Predicting", unit="patient")

    async def _run_one(case):
        input_text = case.build_input_text()
        thinking, content = await client.call(system_prompt, input_text)
        return case.patient_id, thinking, content

    for coro in asyncio.as_completed([_run_one(c) for c in cases]):
        pid, thinking, content = await coro
        results[pid] = {"think": thinking, "raw_content": content, **parse_options(content)}
        pbar.update(1)

    pbar.close()
    await client.close()

    # Save
    short_model = model.replace("/", "_").replace("-", "")[:20]
    output_path = os.path.join(output_dir, f"{short_model}_v{visit_num}_baseline.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(results)} patients saved to {output_path}")
    return results
