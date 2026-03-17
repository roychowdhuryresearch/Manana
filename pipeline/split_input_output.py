"""
Step 1: LLM-based text splitting for all visits.

For each visit, pre-classified columns are tagged as INPUT or OUTPUT directly.
Ambiguous free-text fields are sent to the LLM to split into observations vs. plan.

Output: raw_text/split_results.json
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
visit_counts_file = os.path.join(_HERE, 'visit_counts.json')
prompt_file = os.path.join(_HERE, 'split_prompt.txt')
max_concurrency = 12
num_patients = None  # Set to int for debugging, None for all 3-visit patients
output_file = os.path.join(_HERE, 'split_results.json')
# ========================================

# Clear OUTPUT columns — stored directly, not sent to LLM
ALWAYS_OUTPUT_V1 = ['Current dose']
ALWAYS_OUTPUT_V2 = ['Medication dosage and if there was a change in medication(6 months)']
ALWAYS_OUTPUT_V3 = ['Medication dosage and if there was a change in medication(12 months)']


# ---- Helpers ----

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
    return {"input_text": "", "output_text": ""}


def safe_get(entry, col, columns):
    if col in columns:
        val = entry[col]
        return str(val).strip() if pd.notna(val) else ""
    return ""


def collect_columns(entry, col_list, columns):
    result = {}
    for col in col_list:
        val = safe_get(entry, col, columns)
        if val:
            result[col] = val
    return result  # used for output_columns only


def build_split_text(entry, visit_num, columns):
    if visit_num == 1:
        return f"""Visit 1 (Initial Visit - 0 months):
Visit Date: {safe_get(entry, 'Date of visit(0 months)', columns)}
Date of Birth: {safe_get(entry, 'Date of Birth:', columns)}

History of Presenting Illness: {safe_get(entry, 'History of Presenting Illness', columns)}
Detailed description of seizure history: {safe_get(entry, 'Detailed description of seizure history', columns)}
Current drug regimen: {safe_get(entry, 'Current drug regimen', columns)}"""

    elif visit_num == 2:
        return f"""Visit 2 (6 months follow-up):
Visit Date: {safe_get(entry, 'Date of visit(6 months)', columns)}

Second Entry: {safe_get(entry, 'Second Entry(6 months)', columns)}"""

    elif visit_num == 3:
        return f"""Visit 3 (12 months follow-up):
Visit Date: {safe_get(entry, 'Date of visit(12 months)', columns)}

Third Entry: {safe_get(entry, 'Third Entry(12 months)', columns)}"""


# ---- Async LLM ----

async def call_llm_with_retries(
    client: AsyncTogether,
    system_prompt: str,
    user_content: str,
    model: str = "openai/gpt-oss-120b",
    temperature: float = 0.0,
    max_tokens: int = 4096,
    semaphore: asyncio.Semaphore | None = None,
    max_retries: int = 6,
):
    async def _one_call():
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    for attempt in range(max_retries):
        try:
            if semaphore is None:
                return await _one_call()
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


# ---- Async Inference ----

async def run_inference_async(df, client, system_prompt, max_concurrency):
    columns = df.columns
    semaphore = asyncio.Semaphore(max_concurrency)

    visit_output_cols = {
        1: ALWAYS_OUTPUT_V1,
        2: ALWAYS_OUTPUT_V2,
        3: ALWAYS_OUTPUT_V3,
    }

    patient_order = []
    tasks = []

    for idx, entry in df.iterrows():
        record_id = safe_get(entry, 'Record ID', columns)
        name = safe_get(entry, 'Name: ', columns)
        if record_id and name:
            patient_id = f"{record_id}_{name}"
        elif record_id:
            patient_id = record_id
        elif name:
            patient_id = name
        else:
            patient_id = f"patient_{idx}"

        patient_order.append(patient_id)

        for visit_num in [1, 2, 3]:
            output_columns = collect_columns(entry, visit_output_cols[visit_num], columns)
            split_text = build_split_text(entry, visit_num, columns)
            tasks.append((patient_id, visit_num, output_columns, split_text))

    results = {}
    pbar = tqdm(total=len(tasks), desc="Splitting visits", unit="call")

    async def _run_one(task):
        patient_id, visit_num, output_columns, split_text = task

        if split_text.strip():
            response = await call_llm_with_retries(
                client, system_prompt, split_text,
                model=model, semaphore=semaphore,
            )
            parsed = robust_json_load(response) if response else {}
        else:
            parsed = {}

        return (patient_id, visit_num, {
            "output_columns": output_columns,
            "input_text": parsed.get("input_text", ""),
            "output_text": parsed.get("output_text", ""),
        })

    for coro in asyncio.as_completed([_run_one(t) for t in tasks]):
        patient_id, visit_num, visit_result = await coro
        results.setdefault(patient_id, {})[f"Visit_{visit_num}"] = visit_result
        pbar.update(1)

    pbar.close()

    # Preserve patient order and visit order
    ordered = {}
    for pid in patient_order:
        per = results.get(pid, {})
        ordered[pid] = {
            "Visit_1": per.get("Visit_1", {}),
            "Visit_2": per.get("Visit_2", {}),
            "Visit_3": per.get("Visit_3", {}),
        }

    return ordered


# ---- Main ----

async def main_async():
    together_key = os.getenv("TOGETHER_API_KEY")
    if not together_key:
        print("Error: TOGETHER_API_KEY not found")
        return

    with open(prompt_file, 'r', encoding='utf-8') as f:
        system_prompt = f.read()

    print(f"\n{'='*60}")
    print(f"STEP 1: SPLIT INPUT/OUTPUT")
    print(f"{'='*60}")
    print(f"Model:       {model}")
    print(f"CSV:         {csv_path}")
    print(f"Prompt:      {prompt_file}")
    print(f"Output:      {output_file}")
    print(f"Concurrency: {max_concurrency}")
    print(f"{'='*60}\n")

    with open(visit_counts_file) as f:
        visit_counts = json.load(f)
    three_visit_pids = {pid for pid, v in visit_counts.items() if v.get('visit_count') == 3}
    print(f"3-visit patients: {len(three_visit_pids)}")

    df = pd.read_csv(
        csv_path, sep=';', engine='python',
        quotechar='"', doublequote=True, escapechar='\\',
    )
    dedup_cols = ['Name: ', 'Date of visit(0 months)',
                  'Date of visit(6 months)', 'Date of visit(12 months)']
    df = df.drop_duplicates(subset=dedup_cols)

    # Filter to 3-visit patients only
    columns = df.columns
    def get_pid(entry):
        record_id = str(entry['Record ID']).strip() if pd.notna(entry.get('Record ID')) else ''
        name = str(entry['Name: ']).strip() if pd.notna(entry.get('Name: ')) else ''
        return f"{record_id}_{name}" if record_id and name else name or record_id
    df = df[df.apply(get_pid, axis=1).isin(three_visit_pids)].reset_index(drop=True)

    if num_patients:
        df = df.head(num_patients)
        print(f"Debugging: limited to {num_patients} patients")

    print(f"Total patients to process: {len(df)}\n")

    client = AsyncTogether(api_key=together_key)
    results = await run_inference_async(df, client, system_prompt, max_concurrency)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"DONE! Saved {len(results)} patients to {output_file}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main_async())
