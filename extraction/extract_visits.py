"""
Extract structured visits for the 53 patients with 4+ visits.

For each patient, runs N LLM calls (one per visit date) with the same full
CSV context each time. Only the target date changes per call.

Output:
  extraction/outputs/split_results.json  — same format as data/processed/split_results.json
  extraction/outputs/clean_output.json   — same format as data/processed/clean_output.json
"""

import os
import sys
import json
import asyncio
import argparse
import pandas as pd
from tqdm import tqdm

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from llm.client import LLMClient

_CSV_PATH = os.path.join(_ROOT, "data", "combined_dataset.csv")
_VISIT_COUNTS_PATH = os.path.join(_ROOT, "data", "processed", "visit_counts.json")
_PROMPT_PATH = os.path.join(_HERE, "prompts", "visit_extraction.txt")
_OUTPUT_DIR = os.path.join(_HERE, "outputs")


def _safe(row: dict, col: str) -> str:
    val = row.get(col, "")
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none") else ""


def build_context(row: dict) -> str:
    """Build full patient context from all relevant CSV columns (same cols as
    split_input_output.py used, plus the output/medication columns)."""
    lines = []

    lines.append(f"History of Presenting Illness: {_safe(row, 'History of Presenting Illness')}")
    lines.append(f"Detailed description of seizure history: {_safe(row, 'Detailed description of seizure history')}")
    lines.append(f"Date of Birth: {_safe(row, 'Date of Birth:')}")
    lines.append(f"First visit date: {_safe(row, 'Date of visit(0 months)')}")
    lines.append(f"Current drug regimen (at first visit): {_safe(row, 'Current drug regimen')}")
    lines.append(f"Current dose (at first visit): {_safe(row, 'Current dose')}")

    lines.append(f"\nSecond column date: {_safe(row, 'Date of visit(6 months)')}")
    lines.append(f"Second Entry: {_safe(row, 'Second Entry(6 months)')}")
    lines.append(f"Medication dosage and changes (second column): {_safe(row, 'Medication dosage and if there was a change in medication(6 months)')}")

    lines.append(f"\nThird column date: {_safe(row, 'Date of visit(12 months)')}")
    lines.append(f"Third Entry: {_safe(row, 'Third Entry(12 months)')}")
    lines.append(f"Medication dosage and changes (third column): {_safe(row, 'Medication dosage and if there was a change in medication(12 months)')}")

    return "\n".join(lines)


def build_user_message(
    context: str,
    dates: list[str],
    target_date: str,
    visit_num: int,
    total: int,
    notes: str = "",
) -> str:
    header = (
        f"Known visits (chronological): {', '.join(dates)}\n"
        f"Target visit: {target_date} (Visit {visit_num} of {total})\n"
    )
    if notes:
        header += f"Note on this patient's record: {notes}\n"
    return header + f"\n{context}"


def parse_response(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t[t.find("\n") + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3].strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        s, e = t.find("{"), t.rfind("}")
        if s != -1 and e > s:
            try:
                return json.loads(t[s : e + 1])
            except Exception:
                pass
    return {"input_text": "", "output_text": ""}


async def extract_patient(
    pid: str,
    row: dict,
    multi_visit_info: dict,
    system_prompt: str,
    client: LLMClient,
) -> dict:
    dates = multi_visit_info["visit_dates"]
    context = build_context(row)

    notes = multi_visit_info.get("notes", "")

    async def _one_visit(visit_key: str, target_date: str, visit_num: int):
        msg = build_user_message(context, dates, target_date, visit_num, len(dates), notes)
        _, content = await client.call(system_prompt, msg)
        parsed = parse_response(content) if content else {}
        return visit_key, {
            "input_text": parsed.get("input_text", ""),
            "output_text": parsed.get("output_text", ""),
            "output_columns": {},
        }

    tasks = [
        _one_visit(f"Visit_{i + 1}", date, i + 1)
        for i, date in enumerate(dates)
    ]
    results = await asyncio.gather(*tasks)
    return {vk: data for vk, data in results}


async def main(limit: int | None = None):
    with open(_VISIT_COUNTS_PATH) as f:
        visit_counts = json.load(f)

    multi_visit = {
        pid: v for pid, v in visit_counts.items() if v["visit_count"] > 3
    }
    print(f"Patients with 4+ visits: {len(multi_visit)}")

    df = pd.read_csv(
        _CSV_PATH,
        sep=";",
        engine="python",
        quotechar='"',
        doublequote=True,
        escapechar="\\",
        dtype=str,
    )
    df = df.drop_duplicates(
        subset=[
            "Name: ",
            "Date of visit(0 months)",
            "Date of visit(6 months)",
            "Date of visit(12 months)",
        ]
    )

    def _pid(r) -> str:
        rid = str(r.get("Record ID", "")).strip()
        name = str(r.get("Name: ", "")).strip()
        return f"{rid}_{name}" if rid and name else name or rid

    pid_to_row = {_pid(row): row.to_dict() for _, row in df.iterrows()}

    with open(_PROMPT_PATH) as f:
        system_prompt = f.read()

    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    client = LLMClient()

    pids = list(multi_visit.keys())
    if limit:
        pids = pids[:limit]

    split_results = {}
    clean_output = {}

    pbar = tqdm(total=len(pids), desc="Extracting patients", unit="patient")

    async def _run_patient(pid: str):
        row = pid_to_row.get(pid)
        if row is None:
            print(f"\nWARNING: {pid} not found in CSV, skipping")
            return
        visits = await extract_patient(pid, row, multi_visit[pid], system_prompt, client)
        split_results[pid] = visits
        clean_output[pid] = {vk: v["output_text"] for vk, v in visits.items()}
        pbar.update(1)

    await asyncio.gather(*[_run_patient(pid) for pid in pids])
    pbar.close()
    await client.close()

    with open(os.path.join(_OUTPUT_DIR, "split_results.json"), "w", encoding="utf-8") as f:
        json.dump(split_results, f, indent=2, ensure_ascii=False)

    with open(os.path.join(_OUTPUT_DIR, "clean_output.json"), "w", encoding="utf-8") as f:
        json.dump(clean_output, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(split_results)} patients → {_OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Max patients (for testing)")
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit))
