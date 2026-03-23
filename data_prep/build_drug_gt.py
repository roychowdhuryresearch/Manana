"""
Build drug ground truth from split_results.json.

Step 1: For all patients, extract prescribed/stopped drugs from output side
        (output_text + output_columns) for each visit.

Step 2: For "not on medication" patients (drug-naive at baseline), run V1 backfill
        by passing V2's raw CSV columns to infer drugs active at V1 that were
        undocumented. Merge into V1 result (union only, never overwrite).

Output: raw_text/drug_gt.json
{
  "patient_id": {
    "Visit_1": {"prescribed": [...], "stopped": [...]},
    "Visit_2": {"prescribed": [...], "stopped": [...]},
    "Visit_3": {"prescribed": [...], "stopped": [...]}
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
extract_prompt_file = os.path.join(_HERE, 'gt_extract_prompt.txt')
backfill_prompt_file = os.path.join(_HERE, 'gt_backfill_prompt.txt')
output_file = os.path.join(_HERE, 'drug_gt.json')
max_concurrency = 12
limit_patients = None  # Set to int for debugging
# ========================================

DRUG_LIST = [
    "carbamazepine", "clobazam", "clonazepam", "ethosuximide",
    "lamotrigine", "levetiracetam", "phenobarbital", "phenytoin",
    "topiramate", "valproate",
]

NOT_ON_MED_VALUES = {
    "not on medication", "not on meds", "not on med", "not on medications",
    "not on anti seizure medication", "not on antiseizure medication",
}


# --- Helpers ---

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
    return {}


def parse_drug_result(parsed: dict) -> dict:
    """Validate and clean parsed drug result."""
    prescribed = [d for d in parsed.get("prescribed", []) if d in DRUG_LIST]
    stopped = [d for d in parsed.get("stopped", []) if d in DRUG_LIST]
    return {"prescribed": prescribed, "stopped": stopped}


def resolve_conflicts(ground_truth: dict) -> int:
    """If a drug is in both prescribed and stopped, keep prescribed only."""
    count = 0
    for pid, visits in ground_truth.items():
        for vname in ['Visit_1', 'Visit_2', 'Visit_3']:
            vd = visits.get(vname, {})
            overlap = set(vd.get('prescribed', [])) & set(vd.get('stopped', []))
            if overlap:
                vd['stopped'] = [d for d in vd['stopped'] if d not in overlap]
                count += 1
    return count


def apply_implicit_stops(ground_truth: dict) -> int:
    """Post-processing: if a drug was prescribed at V(N-1) but absent from V(N)
    prescribed and stopped lists, add it to V(N) stopped."""
    count = 0
    for pid, visits in ground_truth.items():
        for prev_num, curr_num in [(1, 2), (2, 3)]:
            prev = visits.get(f"Visit_{prev_num}", {})
            curr = visits.get(f"Visit_{curr_num}", {})
            prev_p = set(prev.get("prescribed", []))
            curr_p = set(curr.get("prescribed", []))
            curr_s = set(curr.get("stopped", []))
            implicit = prev_p - curr_p - curr_s
            if implicit:
                curr["stopped"] = sorted(curr_s | implicit)
                count += len(implicit)
    return count


def merge_drug_results(base: dict, backfill: dict) -> dict:
    """Merge backfill into base — union only, never remove existing entries."""
    prescribed = list(set(base["prescribed"]) | set(backfill["prescribed"]))
    stopped = list(set(base["stopped"]) | set(backfill["stopped"]))
    # If a drug is in both prescribed and stopped, prefer prescribed
    stopped = [d for d in stopped if d not in prescribed]
    return {"prescribed": prescribed, "stopped": stopped}


def safe_get(entry, col, columns):
    if col in columns:
        val = entry[col]
        return str(val).strip() if pd.notna(val) else ""
    return ""


def build_extract_text(visit_data: dict) -> str:
    """Combine output_text and output_columns into one text for extraction."""
    parts = []
    output_text = visit_data.get("output_text", "").strip()
    if output_text:
        parts.append(output_text)
    for col, val in visit_data.get("output_columns", {}).items():
        if val and str(val).strip():
            parts.append(f"{col}: {val}")
    return "\n".join(parts)


def build_backfill_text(entry, columns) -> str:
    """Build V2 raw text for V1 backfill, with date anchoring."""
    v1_date = safe_get(entry, 'Date of visit(0 months)', columns)
    v2_date = safe_get(entry, 'Date of visit(6 months)', columns)
    second_entry = safe_get(entry, 'Second Entry(6 months)', columns)
    med_dosage = safe_get(entry, 'Medication dosage and if there was a change in medication(6 months)', columns)

    parts = [
        f"Visit 1 date: {v1_date}",
        f"Visit 2 date: {v2_date}",
        "",
        "Visit 2 clinical notes:",
    ]
    if second_entry:
        parts.append(second_entry)
    if med_dosage:
        parts.append(f"Medication dosage (Visit 2): {med_dosage}")

    return "\n".join(parts)


# --- Async LLM ---

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
            max_tokens=512,
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
            await asyncio.sleep(0.8 * (2 ** attempt) + random.random() * 0.3)
    return ""


# --- Main ---

async def main_async():
    together_key = os.getenv("TOGETHER_API_KEY")
    if not together_key:
        print("Error: TOGETHER_API_KEY not found")
        return

    with open(extract_prompt_file, encoding='utf-8') as f:
        extract_prompt = f.read()
    with open(backfill_prompt_file, encoding='utf-8') as f:
        backfill_prompt = f.read()

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

    df['_pid'] = df.apply(get_pid, axis=1)
    pid_to_row = {row['_pid']: row for _, row in df.iterrows()}

    # Identify "not on medication" patients that are also in split_results
    not_on_med_pids = set()
    for _, row in df.iterrows():
        pid = row['_pid']
        if pid not in split_results:
            continue
        med_status = safe_get(row, 'Medication status', columns).lower().strip()
        if med_status in NOT_ON_MED_VALUES:
            not_on_med_pids.add(pid)

    patient_ids = list(split_results.keys())
    if limit_patients:
        patient_ids = patient_ids[:limit_patients]

    print(f"\n{'='*60}")
    print(f"BUILD DRUG GROUND TRUTH")
    print(f"{'='*60}")
    print(f"Model:            {model}")
    print(f"Total patients:   {len(patient_ids)}")
    print(f"Backfill targets: {len(not_on_med_pids & set(patient_ids))}")
    print(f"{'='*60}\n")

    client = AsyncTogether(api_key=together_key)
    semaphore = asyncio.Semaphore(max_concurrency)

    # --- Step 1: Extract tasks (all patients, all 3 visits) ---
    extract_tasks = []
    for pid in patient_ids:
        for visit_name in ["Visit_1", "Visit_2", "Visit_3"]:
            visit_data = split_results[pid].get(visit_name, {})
            text = build_extract_text(visit_data)
            extract_tasks.append((pid, visit_name, text))

    # --- Step 2: Backfill tasks (not-on-med patients, V1 only) ---
    backfill_pids = not_on_med_pids & set(patient_ids)
    backfill_tasks = []
    for pid in backfill_pids:
        if pid not in pid_to_row:
            continue
        entry = pid_to_row[pid]
        text = build_backfill_text(entry, columns)
        backfill_tasks.append((pid, text))

    total_calls = len(extract_tasks) + len(backfill_tasks)
    print(f"Step 1 calls: {len(extract_tasks)}")
    print(f"Step 2 calls: {len(backfill_tasks)}")
    print(f"Total calls:  {total_calls}\n")

    # --- Run Step 1 ---
    extract_results = {}  # pid -> visit_name -> {prescribed, stopped}
    pbar1 = tqdm(total=len(extract_tasks), desc="Step 1: Extracting", unit="call")

    async def _run_extract(task):
        pid, visit_name, text = task
        if not text.strip():
            return pid, visit_name, {"prescribed": [], "stopped": []}
        response = await call_llm_with_retries(client, extract_prompt, text, semaphore)
        parsed = parse_drug_result(robust_json_load(response)) if response else {"prescribed": [], "stopped": []}
        return pid, visit_name, parsed

    for coro in asyncio.as_completed([_run_extract(t) for t in extract_tasks]):
        pid, visit_name, result = await coro
        extract_results.setdefault(pid, {})[visit_name] = result
        pbar1.update(1)
    pbar1.close()

    # --- Run Step 2 ---
    backfill_results = {}  # pid -> {prescribed, stopped}
    pbar2 = tqdm(total=len(backfill_tasks), desc="Step 2: Backfilling V1", unit="call")

    async def _run_backfill(task):
        pid, text = task
        if not text.strip():
            return pid, {"prescribed": [], "stopped": []}
        response = await call_llm_with_retries(client, backfill_prompt, text, semaphore)
        parsed = parse_drug_result(robust_json_load(response)) if response else {"prescribed": [], "stopped": []}
        return pid, parsed

    for coro in asyncio.as_completed([_run_backfill(t) for t in backfill_tasks]):
        pid, result = await coro
        backfill_results[pid] = result
        pbar2.update(1)
    pbar2.close()

    # --- Merge and build final GT ---
    ground_truth = {}
    for pid in patient_ids:
        patient_gt = {}
        for visit_name in ["Visit_1", "Visit_2", "Visit_3"]:
            base = extract_results.get(pid, {}).get(visit_name, {"prescribed": [], "stopped": []})
            if visit_name == "Visit_1" and pid in backfill_results:
                base = merge_drug_results(base, backfill_results[pid])
            patient_gt[visit_name] = base
        ground_truth[pid] = patient_gt

    # Apply implicit stops then resolve any prescribed+stopped conflicts
    n_implicit = apply_implicit_stops(ground_truth)
    n_conflicts = resolve_conflicts(ground_truth)
    print(f"Conflicts resolved: {n_conflicts}")
    print(f"Implicit stops added: {n_implicit}")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ground_truth, f, indent=2, ensure_ascii=False)

    # Summary
    total_prescribed = sum(
        len(ground_truth[pid][v]["prescribed"])
        for pid in ground_truth for v in ["Visit_1", "Visit_2", "Visit_3"]
    )
    empty_visits = sum(
        1 for pid in ground_truth for v in ["Visit_1", "Visit_2", "Visit_3"]
        if not ground_truth[pid][v]["prescribed"]
    )
    print(f"\n{'='*60}")
    print(f"DONE! Saved to {output_file}")
    print(f"Total prescriptions across all visits: {total_prescribed}")
    print(f"Visits with no drugs found: {empty_visits}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main_async())
