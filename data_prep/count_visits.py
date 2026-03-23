"""
Counts the actual number of clinic visits per patient by passing all note columns
to an LLM. Handles typos, ambiguous date formats, and extra visits buried in free text.

Output: raw_text/visit_counts.json
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
csv_path = os.path.join(_ROOT, 'data', 'combined_dataset.csv')
max_concurrency = 12
limit_patients = None
output_file = os.path.join(_HERE, 'visit_counts.json')
# ========================================

SYSTEM_PROMPT = """You are reviewing a full epilepsy patient record from a Ugandan neurology clinic. Each record has 3 official documented visits (0, 6, and 12 months) — always include these 3 regardless. However, sometimes additional visits occurred between these and have been merged into the notes. Only flag an extra visit if it involved a drug plan change (new drug started, drug stopped, dose changed). Do not flag visits that were just a checkup, EEG, investigation, or routine review with no medication change.

Dates may be written in dd/mm/yyyy, dd/mm/yy. Some dates may have typos (e.g. wrong year digit) — use context to correct them if possible.

Do NOT count as extra visits:
- EEG, CT, MRI or other investigation dates
- Dates of birth
- Historical admission dates
- Routine follow-up mentions with no prescription change

Return a JSON object with exactly these keys:
{
  "visit_count": <integer — total number of distinct clinic visits>,
  "visit_dates": [<list of visit dates as strings, in chronological order, corrected if typo>],
  "notes": "<any ambiguity, typos corrected, or assumptions made>"
}

Do not output anything except the JSON object."""


def safe_get(entry, col, columns):
    if col in columns:
        val = entry[col]
        return str(val).strip() if pd.notna(val) else ""
    return ""


def build_patient_content(entry, columns):
    return f"""
--- VISIT 1 (0 months) ---
Official Visit 1 Date: {safe_get(entry, 'Date of visit(0 months)', columns)}
History of Presenting Illness: {safe_get(entry, 'History of Presenting Illness', columns)}
Detailed description of seizure history: {safe_get(entry, 'Detailed description of seizure history', columns)}
Current drug regimen: {safe_get(entry, 'Current drug regimen', columns)}
Date of commencement of medication: {safe_get(entry, 'Date of commencement of medication', columns)}
Current dose: {safe_get(entry, 'Current dose', columns)}

--- VISIT 2 (6 months) ---
Official Visit 2 Date: {safe_get(entry, 'Date of visit(6 months)', columns)}
Second Entry: {safe_get(entry, 'Second Entry(6 months)', columns)}
Medication dosage and changes: {safe_get(entry, 'Medication dosage and if there was a change in medication(6 months)', columns)}

--- VISIT 3 (12 months) ---
Official Visit 3 Date: {safe_get(entry, 'Date of visit(12 months)', columns)}
Third Entry: {safe_get(entry, 'Third Entry(12 months)', columns)}
Medication dosage and changes: {safe_get(entry, 'Medication dosage and if there was a change in medication(12 months)', columns)}"""


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


def robust_json_load(text: str) -> dict:
    raw = strip_code_fences(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {"visit_count": -1, "visit_dates": [], "notes": "parse error"}


async def call_llm_with_retries(
    client: AsyncTogether,
    user_content: str,
    semaphore: asyncio.Semaphore,
    max_retries: int = 6,
):
    async def _one_call():
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            max_tokens=1024,
        )
        return (resp.choices[0].message.content or "").strip()

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
            base = 0.8 * (2 ** attempt)
            await asyncio.sleep(base + random.random() * 0.3)
    return ""


async def run_inference_async(df, client, max_concurrency):
    columns = df.columns
    semaphore = asyncio.Semaphore(max_concurrency)

    patient_order = []
    tasks = []

    for idx, entry in df.iterrows():
        record_id = safe_get(entry, 'Record ID', columns)
        name = safe_get(entry, 'Name: ', columns)
        patient_id = f"{record_id}_{name}" if record_id and name else name or record_id or f"patient_{idx}"
        patient_order.append(patient_id)
        tasks.append((patient_id, build_patient_content(entry, columns)))

    results = {}
    pbar = tqdm(total=len(tasks), desc="Counting visits", unit="patient")

    async def _run_one(task):
        patient_id, content = task
        response = await call_llm_with_retries(client, content, semaphore)
        parsed = robust_json_load(response) if response else {"visit_count": -1, "visit_dates": [], "notes": "no response"}
        return patient_id, parsed

    for coro in asyncio.as_completed([_run_one(t) for t in tasks]):
        patient_id, result = await coro
        results[patient_id] = result
        pbar.update(1)

    pbar.close()

    return {pid: results.get(pid, {}) for pid in patient_order}


async def main_async():
    together_key = os.getenv("TOGETHER_API_KEY")
    if not together_key:
        print("Error: TOGETHER_API_KEY not found")
        return

    print(f"\n{'='*60}")
    print(f"VISIT COUNT CHECK")
    print(f"{'='*60}")
    print(f"Model:       {model}")
    print(f"CSV:         {csv_path}")
    print(f"Output:      {output_file}")
    print(f"Concurrency: {max_concurrency}")
    print(f"{'='*60}\n")

    df = pd.read_csv(
        csv_path, sep=';', engine='python',
        quotechar='"', doublequote=True, escapechar='\\',
    )
    dedup_cols = ['Name: ', 'Date of visit(0 months)',
                  'Date of visit(6 months)', 'Date of visit(12 months)']
    df = df.drop_duplicates(subset=dedup_cols)

    if limit_patients:
        df = df.head(limit_patients)
        print(f"Limited to {limit_patients} patients")

    print(f"Total patients: {len(df)}\n")

    client = AsyncTogether(api_key=together_key)
    results = await run_inference_async(df, client, max_concurrency)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Summary
    from collections import Counter
    counts = Counter(v.get("visit_count", -1) for v in results.values())
    print(f"\n{'='*60}")
    print(f"DONE! Saved {len(results)} patients to {output_file}")
    print(f"\nVisit count distribution:")
    for n, c in sorted(counts.items()):
        print(f"  {n} visits: {c} patients")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main_async())
