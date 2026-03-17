"""
Reruns count_visits for patients that failed (-1) and updates visit_counts.json.
"""

import os
import json
import asyncio
import random
import dotenv
import pandas as pd
from tqdm import tqdm
from together import AsyncTogether
from count_visits import build_patient_content, robust_json_load, SYSTEM_PROMPT

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
dotenv.load_dotenv(os.path.join(_HERE, '.env'))

model = 'openai/gpt-oss-120b'
csv_path = os.path.join(_ROOT, 'data', 'combined_dataset.csv')
output_file = os.path.join(_HERE, 'visit_counts.json')
max_concurrency = 8


def safe_get(entry, col, columns):
    if col in columns:
        val = entry[col]
        return str(val).strip() if pd.notna(val) else ""
    return ""


async def call_llm_with_retries(client, user_content, semaphore, max_retries=6):
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
            await asyncio.sleep(0.8 * (2 ** attempt) + random.random() * 0.3)
    return ""


async def main_async():
    together_key = os.getenv("TOGETHER_API_KEY")
    if not together_key:
        print("Error: TOGETHER_API_KEY not found")
        return

    with open(output_file) as f:
        results = json.load(f)

    failed_pids = [pid for pid, v in results.items() if v.get('visit_count') == -1]
    print(f"Rerunning {len(failed_pids)} failed patients...")

    df = pd.read_csv(csv_path, sep=';', engine='python', quotechar='"', doublequote=True, escapechar='\\')
    dedup_cols = ['Name: ', 'Date of visit(0 months)', 'Date of visit(6 months)', 'Date of visit(12 months)']
    df = df.drop_duplicates(subset=dedup_cols)
    columns = df.columns

    # Build patient_id → row lookup
    pid_to_row = {}
    for idx, entry in df.iterrows():
        record_id = safe_get(entry, 'Record ID', columns)
        name = safe_get(entry, 'Name: ', columns)
        pid = f"{record_id}_{name}" if record_id and name else name or record_id or f"patient_{idx}"
        pid_to_row[pid] = entry

    tasks = [(pid, build_patient_content(pid_to_row[pid], columns)) for pid in failed_pids if pid in pid_to_row]

    semaphore = asyncio.Semaphore(max_concurrency)
    client = AsyncTogether(api_key=together_key)
    pbar = tqdm(total=len(tasks), desc="Retrying", unit="patient")

    async def _run_one(task):
        pid, content = task
        response = await call_llm_with_retries(client, content, semaphore)
        parsed = robust_json_load(response) if response else {"visit_count": -1, "visit_dates": [], "notes": "no response"}
        return pid, parsed

    for coro in asyncio.as_completed([_run_one(t) for t in tasks]):
        pid, result = await coro
        results[pid] = result
        pbar.update(1)

    pbar.close()

    # Keep retrying until no -1s remain
    round_num = 1
    while True:
        still_failed = [pid for pid, v in results.items() if v.get('visit_count') == -1]
        if not still_failed:
            break
        print(f"\nRound {round_num}: {len(still_failed)} still failing, retrying...")
        round_num += 1
        await asyncio.sleep(1)

        retry_tasks = [(pid, build_patient_content(pid_to_row[pid], columns)) for pid in still_failed if pid in pid_to_row]
        pbar2 = tqdm(total=len(retry_tasks), desc=f"Retry round {round_num}", unit="patient")

        for coro in asyncio.as_completed([_run_one(t) for t in retry_tasks]):
            pid, result = await coro
            results[pid] = result
            pbar2.update(1)

        pbar2.close()

        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    from collections import Counter
    counts = Counter(v.get('visit_count', -1) for v in results.values())
    print(f"\nUpdated visit count distribution:")
    for n, c in sorted(counts.items()):
        print(f"  {n} visits: {c} patients")


if __name__ == "__main__":
    asyncio.run(main_async())
