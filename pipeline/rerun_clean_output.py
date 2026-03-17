"""
Reruns build_clean_output for any visits with empty results.
Skips 102_Mulungi Rodney Visit_3 which is genuinely missing data.
Updates clean_output.json in place.
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

model = 'openai/gpt-oss-120b'
max_concurrency = 8

GENUINELY_EMPTY = {('102_Mulungi Rodney', 'Visit_3')}

NOT_ON_MED_VALUES = {
    "not on medication", "not on meds", "not on med", "not on medications",
    "not on anti seizure medication", "not on antiseizure medication",
}

STANDARD_PROMPT = """You are cleaning a clinical prescription record from a Ugandan epilepsy clinic.

You are given the prescription output for one visit, which may come from two overlapping sources (free-text plan and a structured medication column). They may be duplicates, partial overlaps, or one may have extra detail.

Your task: produce a single clean unified prescription text that preserves ALL unique clinical information — drug names, doses, durations, formulations, and any non-drug plan items (e.g. EEG orders, physiotherapy, follow-up instructions). Deduplicate where the same item appears twice. Preserve original clinical wording as much as possible.

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


def safe_get(row, col, columns):
    if col in columns:
        val = row[col]
        return str(val).strip() if pd.notna(val) else ""
    return ""


def get_pid(row):
    rid  = str(row.get('Record ID', '')).strip() if pd.notna(row.get('Record ID')) else ''
    name = str(row.get('Name: ', '')).strip()     if pd.notna(row.get('Name: '))    else ''
    return f"{rid}_{name}" if rid and name else name or rid


def build_standard_user_content(visit_data: dict) -> str:
    parts = []
    ot = visit_data.get("output_text", "").strip()
    oc = " | ".join(v for v in visit_data.get("output_columns", {}).values() if v and str(v).strip())
    if ot:
        parts.append(f"Free-text plan:\n{ot}")
    if oc:
        parts.append(f"Structured medication column:\n{oc}")
    return "\n\n".join(parts)


def build_backfill_user_content(v1_data: dict, v2_data: dict) -> str:
    parts = []
    ot = v1_data.get("output_text", "").strip()
    oc = " | ".join(v for v in v1_data.get("output_columns", {}).values() if v and str(v).strip())
    if ot:
        parts.append(f"V1 free-text plan:\n{ot}")
    if oc:
        parts.append(f"V1 structured medication column:\n{oc}")
    if not ot and not oc:
        parts.append("V1 prescription output: [not documented]")

    v2_input_text  = v2_data.get("input_text", "").strip()
    v2_output_text = v2_data.get("output_text", "").strip()
    v2_oc_vals     = " | ".join(v for v in v2_data.get("output_columns", {}).values() if v and str(v).strip())

    if v2_input_text:
        parts.append(f"V2 clinical notes (observation side):\n{v2_input_text}")
    if v2_output_text or v2_oc_vals:
        v2_rx = "\n".join(x for x in [v2_output_text, v2_oc_vals] if x)
        parts.append(f"V2 prescription output:\n{v2_rx}")

    return "\n\n".join(parts)


async def call_llm_with_retries(client, system_prompt, user_content, semaphore, max_retries=6):
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

    with open(os.path.join(_HERE, 'clean_output.json'), encoding='utf-8') as f:
        clean_output = json.load(f)
    with open(os.path.join(_HERE, 'split_results.json'), encoding='utf-8') as f:
        split_results = json.load(f)

    df = pd.read_csv(
        os.path.join(_ROOT, 'data', 'combined_dataset.csv'),
        sep=';', engine='python', quotechar='"', doublequote=True, escapechar='\\',
    )
    df = df.drop_duplicates(subset=[
        'Name: ', 'Date of visit(0 months)',
        'Date of visit(6 months)', 'Date of visit(12 months)'
    ])
    columns = df.columns
    pid_to_row = {get_pid(row): row for _, row in df.iterrows()}

    not_on_med_pids = set()
    for _, row in df.iterrows():
        pid = get_pid(row)
        if safe_get(row, 'Medication status', columns).lower().strip() in NOT_ON_MED_VALUES:
            not_on_med_pids.add(pid)

    # Find empty visits to rerun
    to_rerun = [
        (pid, v)
        for pid in clean_output
        for v in ['Visit_1', 'Visit_2', 'Visit_3']
        if not clean_output[pid][v].strip() and (pid, v) not in GENUINELY_EMPTY
    ]

    print(f"\n{'='*50}")
    print(f"RERUN CLEAN OUTPUT")
    print(f"{'='*50}")
    print(f"Empty visits to rerun: {len(to_rerun)}")
    for pid, v in to_rerun:
        print(f"  {pid} | {v}")
    print(f"{'='*50}\n")

    if not to_rerun:
        print("Nothing to rerun.")
        return

    client = AsyncTogether(api_key=together_key)
    semaphore = asyncio.Semaphore(max_concurrency)
    pbar = tqdm(total=len(to_rerun), desc="Rerunning", unit="visit")

    async def _run_one(pid, visit_name):
        visit_data = split_results[pid].get(visit_name, {})
        if visit_name == "Visit_1" and pid in not_on_med_pids:
            v2_data = split_results[pid].get("Visit_2", {})
            user_content = build_backfill_user_content(visit_data, v2_data)
            system_prompt = BACKFILL_PROMPT
        else:
            user_content = build_standard_user_content(visit_data)
            system_prompt = STANDARD_PROMPT
        if not user_content.strip():
            return pid, visit_name, ""
        result = await call_llm_with_retries(client, system_prompt, user_content, semaphore)
        return pid, visit_name, result

    results = {}
    for coro in asyncio.as_completed([_run_one(pid, v) for pid, v in to_rerun]):
        pid, visit_name, result = await coro
        results[(pid, visit_name)] = result
        pbar.update(1)
    pbar.close()

    # Update clean_output
    for (pid, v), result in results.items():
        clean_output[pid][v] = result

    with open(os.path.join(_HERE, 'clean_output.json'), 'w', encoding='utf-8') as f:
        json.dump(clean_output, f, indent=2, ensure_ascii=False)

    # Final check
    still_empty = [
        (pid, v)
        for pid in clean_output
        for v in ['Visit_1', 'Visit_2', 'Visit_3']
        if not clean_output[pid][v].strip() and (pid, v) not in GENUINELY_EMPTY
    ]
    print(f"\nUpdated clean_output.json")
    print(f"Still empty (excl. genuinely missing): {len(still_empty)}")
    for pid, v in still_empty:
        print(f"  {pid} | {v}")
    print("Done.\n")


if __name__ == "__main__":
    asyncio.run(main_async())
