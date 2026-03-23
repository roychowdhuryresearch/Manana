"""
Reruns split for visits where input_text is empty but raw CSV has content.
Patches split_results.json in place.
"""

import os
import json
import asyncio
import random
import dotenv
import pandas as pd
from tqdm import tqdm
from together import AsyncTogether
from split_input_output import (
    build_split_text, collect_columns, robust_json_load,
    call_llm_with_retries, safe_get,
    ALWAYS_OUTPUT_V1, ALWAYS_OUTPUT_V2, ALWAYS_OUTPUT_V3,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
dotenv.load_dotenv(os.path.join(_HERE, '.env'))

model = 'openai/gpt-oss-120b'
csv_path = os.path.join(_ROOT, 'data', 'combined_dataset.csv')
split_results_file = os.path.join(_HERE, 'split_results.json')
prompt_file = os.path.join(_HERE, 'split_prompt.txt')
max_concurrency = 12


def has_raw_content(entry, visit_num, columns):
    """Check if the raw CSV has any actual content for this visit's free-text fields."""
    if visit_num == 1:
        fields = [
            'History of Presenting Illness',
            'Detailed description of seizure history',
            'Current drug regimen',
        ]
    elif visit_num == 2:
        fields = ['Second Entry(6 months)']
    elif visit_num == 3:
        fields = ['Third Entry(12 months)']
    else:
        return False

    for f in fields:
        val = safe_get(entry, f, columns)
        if val and val.lower() != 'nan':
            return True
    return False


async def main_async():
    together_key = os.getenv("TOGETHER_API_KEY")
    if not together_key:
        print("Error: TOGETHER_API_KEY not found")
        return

    with open(split_results_file, encoding='utf-8') as f:
        split_results = json.load(f)

    with open(prompt_file, encoding='utf-8') as f:
        system_prompt = f.read()

    df = pd.read_csv(
        csv_path, sep=';', engine='python',
        quotechar='"', doublequote=True, escapechar='\\',
    )
    dedup_cols = ['Name: ', 'Date of visit(0 months)',
                  'Date of visit(6 months)', 'Date of visit(12 months)']
    df = df.drop_duplicates(subset=dedup_cols)
    columns = df.columns

    # Build pid -> row lookup
    pid_to_row = {}
    for idx, entry in df.iterrows():
        record_id = safe_get(entry, 'Record ID', columns)
        name = safe_get(entry, 'Name: ', columns)
        pid = f"{record_id}_{name}" if record_id and name else name or record_id or f"patient_{idx}"
        pid_to_row[pid] = entry

    visit_output_cols = {
        1: ALWAYS_OUTPUT_V1,
        2: ALWAYS_OUTPUT_V2,
        3: ALWAYS_OUTPUT_V3,
    }

    # Find failed visits: empty input_text but raw CSV has content
    failed = []
    for pid, visits in split_results.items():
        if pid not in pid_to_row:
            continue
        entry = pid_to_row[pid]
        for visit_num in [1, 2, 3]:
            visit_name = f"Visit_{visit_num}"
            vd = visits.get(visit_name, {})
            if not vd.get('input_text', '').strip():
                if has_raw_content(entry, visit_num, columns):
                    output_columns = collect_columns(entry, visit_output_cols[visit_num], columns)
                    split_text = build_split_text(entry, visit_num, columns)
                    failed.append((pid, visit_num, visit_name, output_columns, split_text))

    print(f"Found {len(failed)} visits to rerun")

    semaphore = asyncio.Semaphore(max_concurrency)
    client = AsyncTogether(api_key=together_key)

    async def _run_one(task):
        pid, visit_num, visit_name, output_columns, split_text = task
        response = await call_llm_with_retries(
            client, system_prompt, split_text,
            model=model, semaphore=semaphore,
        )
        parsed = robust_json_load(response) if response else {}
        return pid, visit_name, {
            "output_columns": output_columns,
            "input_text": parsed.get("input_text", ""),
            "output_text": parsed.get("output_text", ""),
        }

    pbar = tqdm(total=len(failed), desc="Rerunning", unit="visit")
    for coro in asyncio.as_completed([_run_one(t) for t in failed]):
        pid, visit_name, result = await coro
        split_results[pid][visit_name] = result
        pbar.update(1)
    pbar.close()

    # Check if any still empty
    still_empty = []
    for pid, visit_num, visit_name, _, _ in failed:
        inp = split_results[pid][visit_name].get('input_text', '').strip()
        if not inp:
            still_empty.append(f"{pid} {visit_name}")

    with open(split_results_file, 'w', encoding='utf-8') as f:
        json.dump(split_results, f, indent=2, ensure_ascii=False)

    print(f"\nPatched {split_results_file}")
    if still_empty:
        print(f"Still empty after rerun ({len(still_empty)}):")
        for s in still_empty:
            print(f"  {s}")
    else:
        print("All fixed!")


if __name__ == "__main__":
    asyncio.run(main_async())
