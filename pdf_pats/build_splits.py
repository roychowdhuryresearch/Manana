"""Build split_results.json for all PDF patients using LLM to split each visit.

For each of 367 canonical patient folders, for each visit txt file:
- Call LLM to split into input_text (clinical notes) and output_text (prescription)
- Sort visits chronologically by date (extracted from raw text, no LLM needed)
- Assign Visit_1, Visit_2, ... in date order

Output: pdf_pats/outputs/split_results.json

Usage:
    uv run python pdf_pats/build_splits.py --limit 5
    uv run python pdf_pats/build_splits.py
"""

import os
import re
import sys
import json
import asyncio
import argparse
from datetime import datetime
from collections import defaultdict
from tqdm import tqdm

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from llm.client import LLMClient

_DATA_PATH = os.path.join(_ROOT, "data", "all_patient_pdfs")
_PROMPT_PATH = os.path.join(_HERE, "prompts", "split_prompt.txt")
_OUT_PATH = os.path.join(_HERE, "outputs", "split_results.json")


# ── Deduplication ─────────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    return re.sub(r"[\s_]+", " ", name.lower()).strip()


def canonical_folders(data_path: str) -> list[str]:
    folders = sorted([
        f for f in os.listdir(data_path)
        if os.path.isdir(os.path.join(data_path, f))
    ])
    seen, result = set(), []
    for f in folders:
        n = normalize_name(f)
        if n not in seen:
            seen.add(n)
            result.append(f)
    return result


# ── Date extraction (regex, no LLM) ──────────────────────────────────────────

def extract_date(content: str) -> datetime | None:
    m = re.search(r"Report opening date:\s*(\d{2}/\d{2}/\d{4})", content)
    if m:
        try:
            return datetime.strptime(m.group(1), "%d/%m/%Y")
        except ValueError:
            pass
    m = re.search(r"APP\.\s*Date\s*:(\d{2}-\w+-\d{4})", content)
    if m:
        try:
            return datetime.strptime(m.group(1).strip(), "%d-%b-%Y")
        except ValueError:
            pass
    return None


# ── LLM split ─────────────────────────────────────────────────────────────────

def parse_llm_response(content: str) -> tuple[str, str]:
    """Extract input_text and output_text from LLM JSON response."""
    # Strip markdown fences if present
    content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.MULTILINE)
    content = re.sub(r"\s*```$", "", content.strip(), flags=re.MULTILINE)
    try:
        obj = json.loads(content)
        return obj.get("input_text", "").strip(), obj.get("output_text", "").strip()
    except json.JSONDecodeError:
        # Fallback: try to extract with regex
        m_in  = re.search(r'"input_text"\s*:\s*"(.*?)"(?=\s*,\s*"output_text")', content, re.DOTALL)
        m_out = re.search(r'"output_text"\s*:\s*"(.*?)"(?=\s*\})', content, re.DOTALL)
        inp = m_in.group(1).replace("\\n", "\n").strip() if m_in else ""
        out = m_out.group(1).replace("\\n", "\n").strip() if m_out else ""
        return inp, out


async def split_visit_llm(
    client: LLMClient,
    system_prompt: str,
    raw_text: str,
) -> tuple[str, str]:
    """Call LLM to split one visit. Returns (input_text, output_text)."""
    _, content = await client.call(system_prompt, raw_text)
    return parse_llm_response(content)


# ── Per-patient processing ────────────────────────────────────────────────────

def get_visit_files(folder_path: str) -> list[tuple[datetime | None, str, str]]:
    """Return [(date, filename, raw_content)] sorted by date."""
    txt_files = [
        f for f in os.listdir(folder_path)
        if f.endswith(".txt") and "merged" not in f
    ]
    visits = []
    for fname in txt_files:
        fpath = os.path.join(folder_path, fname)
        try:
            content = open(fpath, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        date = extract_date(content)
        visits.append((date, fname, content))

    visits.sort(key=lambda v: v[0] or datetime(2099, 1, 1))
    return visits


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Process only N patients")
    parser.add_argument("--model", type=str, default="openai.gpt-oss-120b-1:0")
    args = parser.parse_args()

    with open(_PROMPT_PATH, encoding="utf-8") as f:
        system_prompt = f.read()

    folders = canonical_folders(_DATA_PATH)
    if args.limit:
        folders = folders[: args.limit]

    # Collect all (patient, visit_index, date, raw_text) tasks
    tasks = []
    for folder in folders:
        folder_path = os.path.join(_DATA_PATH, folder)
        visits = get_visit_files(folder_path)
        for i, (date, fname, raw) in enumerate(visits, 1):
            tasks.append((folder, i, date, fname, raw))

    print(f"Patients: {len(folders)}, total visit splits to run: {len(tasks)}")

    client = LLMClient(model=args.model)
    split_results: dict[str, dict] = defaultdict(dict)

    pbar = tqdm(total=len(tasks), desc="Splitting visits", unit="visit")

    async def _one(folder, visit_num, date, fname, raw):
        inp, out = await split_visit_llm(client, system_prompt, raw)
        pbar.update(1)
        return folder, visit_num, date, fname, inp, out

    results = await asyncio.gather(
        *[_one(*t) for t in tasks],
        return_exceptions=True,
    )
    pbar.close()
    await client.close()

    errors = 0
    for item in results:
        if isinstance(item, Exception):
            print(f"[ERROR] {item}")
            errors += 1
            continue
        folder, visit_num, date, fname, inp, out = item
        split_results[folder][f"Visit_{visit_num}"] = {
            "visit_date": date.strftime("%d/%m/%Y") if date else "",
            "file": fname,
            "input_text": inp,
            "output_text": out,
        }

    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    with open(_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(split_results, f, indent=2, ensure_ascii=False)

    total_visits = sum(len(v) for v in split_results.values())
    print(f"\nDone. Errors: {errors}")
    print(f"  Patients:     {len(split_results)}")
    print(f"  Total visits: {total_visits}")
    print(f"Saved → {_OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
