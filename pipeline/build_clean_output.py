"""
Build a single clean semantic prescription text per patient per visit.

Type A — all visits except not-on-med V1:
  Pass output_text + output_columns → one clean prescription string.

Type B — not-on-med patients, V1 only (123 patients):
  Pass V1 output_text + V1 output_columns + V2 input_text → one unified V1 prescription string.
  V2 input_text is used to recover what was started at V1 (cues: "Continue X", "on X since last visit").
  V2 output is NOT passed — no leakage of V2 new prescriptions.

Output: raw_text/clean_output.json
{
  "patient_id": {
    "Visit_1": "clean prescription text",
    "Visit_2": "...",
    "Visit_3": "..."
  }
}
"""

import os
import json
import asyncio
import random
import dotenv
import pandas as pd
from tqdm import tqdm
from together import AsyncTogether

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
dotenv.load_dotenv(os.path.join(_HERE, '.env'))

# ============ CONFIGURATION ============
model = 'openai/gpt-oss-120b'
split_results_path = os.path.join(_HERE, 'split_results.json')
csv_path = os.path.join(_ROOT, 'data', 'combined_dataset.csv')
output_file = os.path.join(_HERE, 'clean_output.json')
max_concurrency = 12
limit_patients = None
# ========================================

NOT_ON_MED_VALUES = {
    "not on medication", "not on meds", "not on med", "not on medications",
    "not on anti seizure medication", "not on antiseizure medication",
}

STANDARD_PROMPT = """You are processing a clinical visit record from a Ugandan epilepsy clinic.

You are given the prescription output for one visit from two sources (free-text plan and structured medication column). They may duplicate, partially overlap, or one may have extra detail.

Produce a single clean prescription text containing ONLY the treatment decisions made at this visit: drugs prescribed, doses, durations, formulations, and any plan items (EEG orders, physiotherapy, referrals, follow-up instructions). Do NOT include observations about what the patient was previously on or clinical findings — those belong in the input record, not here.

Deduplicate where the same item appears in both sources. Preserve original clinical wording.

Return only the unified prescription text. No preamble, no reasoning, no explanation."""

BACKFILL_PROMPT = """You are processing a Visit 1 record from a Ugandan epilepsy clinic. This patient was not on any medication at presentation — Visit 1 is when they were first prescribed treatment.

You are given:
1. V1 prescription output (may be partial, truncated, or empty)
2. V2 clinical notes (6-month follow-up observation side), which describe what the patient has been on since Visit 1
3. V2 prescription output, which records medication decisions made at V2

There are NO visits between V1 and V2. Any drug that V2 describes as already active (i.e. the patient is already taking it when they arrive at V2) must have been started at V1.

Produce a single clean prescription text for Visit 1 containing ONLY the treatment decisions made at Visit 1: drugs prescribed, doses, durations, formulations, and any plan items. Do NOT include observations about prior history or clinical findings.

RULES FOR USING V2 DATA TO RECOVER V1 DRUGS:

A drug from V2 should be INCLUDED in V1 output if V2 describes it as already active — the patient was already taking it when they came in for V2. This covers any phrasing: "continue", "maintain", "same as before", "on X since last visit", "has been on X", "still on X", dose adjustments to an existing drug (the drug itself was from V1, even if the dose is changing at V2), or any other language indicating the drug was running before V2 started.

A drug from V2 should be EXCLUDED from V1 output if V2 describes it as a new decision being made at V2. This covers any phrasing: "start", "add", "initiate", "new", "switch to", "trial of", or any language indicating the drug is being introduced for the first time at V2.

When including a V1 drug recovered from V2: use the drug name only, or the drug name with V1's dose if V1 mentions it. Do NOT copy V2's dose — it may reflect a V2 dose change, not what was prescribed at V1.

If a drug appears in V2 with no clear signal either way — you cannot tell whether it was already active or newly started — DO NOT include it. Omission is safer than incorrect inclusion.

Deduplicate where the same item appears in both V1 output and V2 data. Preserve original V1 clinical wording where available.

Return only the unified Visit 1 prescription text. No preamble, no reasoning, no explanation."""


def strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        first_newline = t.find("\n")
        if first_newline != -1:
            t = t[first_newline + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
        t = t.strip()
    return t


def safe_get(entry, col, columns):
    if col in columns:
        val = entry[col]
        return str(val).strip() if pd.notna(val) else ""
    return ""


def build_standard_user_content(visit_data: dict) -> str:
    parts = []
    output_text = visit_data.get("output_text", "").strip()
    oc_vals = " | ".join(v for v in visit_data.get("output_columns", {}).values() if v and str(v).strip())
    if output_text:
        parts.append(f"Free-text plan:\n{output_text}")
    if oc_vals:
        parts.append(f"Structured medication column:\n{oc_vals}")
    return "\n\n".join(parts)


def build_backfill_user_content(v1_data: dict, v2_data: dict) -> str:
    parts = []
    v1_output_text = v1_data.get("output_text", "").strip()
    v1_oc_vals = " | ".join(v for v in v1_data.get("output_columns", {}).values() if v and str(v).strip())

    if v1_output_text:
        parts.append(f"V1 free-text plan:\n{v1_output_text}")
    if v1_oc_vals:
        parts.append(f"V1 structured medication column:\n{v1_oc_vals}")
    if not v1_output_text and not v1_oc_vals:
        parts.append("V1 prescription output: [not documented]")

    v2_input_text = v2_data.get("input_text", "").strip()
    v2_output_text = v2_data.get("output_text", "").strip()
    v2_oc_vals = " | ".join(v for v in v2_data.get("output_columns", {}).values() if v and str(v).strip())

    if v2_input_text:
        parts.append(f"V2 clinical notes (observation side):\n{v2_input_text}")
    if v2_output_text or v2_oc_vals:
        v2_rx = "\n".join(x for x in [v2_output_text, v2_oc_vals] if x)
        parts.append(f"V2 prescription output:\n{v2_rx}")

    return "\n\n".join(parts)


async def call_llm_with_retries(
    client: AsyncTogether,
    system_prompt: str,
    user_content: str,
    semaphore: asyncio.Semaphore,
    max_retries: int = 6,
) -> str:
    async def _one_call():
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            max_tokens=1024,
        )
        return strip_code_fences((resp.choices[0].message.content or "").strip())

    for attempt in range(max_retries):
        try:
            async with semaphore:
                return await _one_call()
        except Exception as e:
            msg = str(e).lower()
            retryable = any(s in msg for s in [
                "rate", "429", "timeout", "temporar", "overload", "503", "500", "connection"
            ])
            if not retryable or attempt == max_retries - 1:
                return ""
            await asyncio.sleep(0.8 * (2 ** attempt) + random.random() * 0.3)
    return ""


async def main_async():
    together_key = os.getenv("TOGETHER_API_KEY")
    if not together_key:
        print("Error: TOGETHER_API_KEY not found")
        return

    with open(split_results_path, encoding='utf-8') as f:
        split_results = json.load(f)

    df = pd.read_csv(
        csv_path, sep=';', engine='python',
        quotechar='"', doublequote=True, escapechar='\\',
    )
    df = df.drop_duplicates(subset=[
        'Name: ', 'Date of visit(0 months)',
        'Date of visit(6 months)', 'Date of visit(12 months)'
    ])
    columns = df.columns

    def get_pid(row):
        rid = str(row.get('Record ID', '')).strip() if pd.notna(row.get('Record ID')) else ''
        name = str(row.get('Name: ', '')).strip() if pd.notna(row.get('Name: ')) else ''
        return f"{rid}_{name}" if rid and name else name or rid

    not_on_med_pids = set()
    for _, row in df.iterrows():
        pid = get_pid(row)
        if pid not in split_results:
            continue
        if safe_get(row, 'Medication status', columns).lower().strip() in NOT_ON_MED_VALUES:
            not_on_med_pids.add(pid)

    patient_ids = list(split_results.keys())
    if limit_patients:
        patient_ids = patient_ids[:limit_patients]

    print(f"\n{'='*60}")
    print(f"BUILD CLEAN OUTPUT")
    print(f"{'='*60}")
    print(f"Model:            {model}")
    print(f"Total patients:   {len(patient_ids)}")
    print(f"Not-on-med (backfill V1): {len(not_on_med_pids & set(patient_ids))}")
    print(f"Total LLM calls:  {len(patient_ids) * 3}")
    print(f"{'='*60}\n")

    client = AsyncTogether(api_key=together_key)
    semaphore = asyncio.Semaphore(max_concurrency)

    tasks = []
    for pid in patient_ids:
        for visit_name in ["Visit_1", "Visit_2", "Visit_3"]:
            visit_data = split_results[pid].get(visit_name, {})
            if visit_name == "Visit_1" and pid in not_on_med_pids:
                v2_data = split_results[pid].get("Visit_2", {})
                user_content = build_backfill_user_content(visit_data, v2_data)
                system_prompt = BACKFILL_PROMPT
            else:
                user_content = build_standard_user_content(visit_data)
                system_prompt = STANDARD_PROMPT
            tasks.append((pid, visit_name, system_prompt, user_content))

    results = {}
    pbar = tqdm(total=len(tasks), desc="Building clean outputs", unit="visit")

    async def _run_one(task):
        pid, visit_name, system_prompt, user_content = task
        if not user_content.strip():
            return pid, visit_name, ""
        response = await call_llm_with_retries(client, system_prompt, user_content, semaphore)
        return pid, visit_name, response

    for coro in asyncio.as_completed([_run_one(t) for t in tasks]):
        pid, visit_name, result = await coro
        results.setdefault(pid, {})[visit_name] = result
        pbar.update(1)

    pbar.close()

    ordered = {}
    for pid in patient_ids:
        ordered[pid] = {
            "Visit_1": results.get(pid, {}).get("Visit_1", ""),
            "Visit_2": results.get(pid, {}).get("Visit_2", ""),
            "Visit_3": results.get(pid, {}).get("Visit_3", ""),
        }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ordered, f, indent=2, ensure_ascii=False)

    empty = sum(1 for pid in ordered for v in ["Visit_1", "Visit_2", "Visit_3"] if not ordered[pid][v])
    print(f"\n{'='*60}")
    print(f"DONE! Saved to {output_file}")
    print(f"Empty visits: {empty} / {len(patient_ids) * 3}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main_async())
