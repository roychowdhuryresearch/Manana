"""
MIMIC-IV Note Cleaning
=======================
Cleans raw discharge notes into leakage-free model inputs.

For each note in discharge_notes.parquet (that has a matching GT):
  - Calls LLM with the cleaning prompt
  - Returns minimally edited note with treatment decisions removed
  - Strips BHC, discharge sections, and in-admission treatment sentences from HPI

Output (mimic/filtered/):
  cleaned_notes.parquet — (hadm_id, cleaned_text)

Usage:
    uv run python mimic/clean.py
    uv run python mimic/clean.py --workers 8  # parallel workers
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.llm import LLMClient, DEFAULT_MODEL

_HERE       = Path(__file__).parent
FILT_DIR    = _HERE / "filtered"
OUT_DIR     = _HERE / "filtered"
PROMPT_PATH = _HERE / "prompts" / "clean_note.txt"

OUT_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = "You are a clinical note editor. Follow the instructions exactly."
PROMPT_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")


def build_prompt(note_text: str) -> str:
    return PROMPT_TEMPLATE.replace("...note text here...", note_text)


def resolve_output_path(limit: int | None, out_path: str | None) -> Path:
    if out_path:
        return Path(out_path)
    if limit is not None:
        return OUT_DIR / f"cleaned_notes_limit_{limit}.parquet"
    return OUT_DIR / "cleaned_notes.parquet"


async def run(limit: int | None, workers: int, model: str, out_path: str | None):
    notes = pd.read_parquet(FILT_DIR / "discharge_notes.parquet")
    gt    = pd.read_parquet(OUT_DIR / "gt_drugs.parquet")

    valid_hadms = set(gt["hadm_id"])
    notes = notes[notes["hadm_id"].isin(valid_hadms)].reset_index(drop=True)

    if limit:
        notes = notes.head(limit)

    print(f"Cleaning {len(notes)} notes with {workers} workers (model: {model})")

    client = LLMClient(model=model, max_concurrency=workers)

    items = [
        (str(row["hadm_id"]), build_prompt(row["text"]))
        for _, row in notes.iterrows()
    ]

    done = 0
    def on_complete(item_id, thinking, content):
        nonlocal done
        done += 1
        if done % 50 == 0:
            print(f"  {done}/{len(items)} done", flush=True)

    raw_results = await client.call_batch(SYSTEM_PROMPT, items, on_complete=on_complete)

    results = []
    for hadm_id in notes["hadm_id"]:
        hadm_id_str = str(int(hadm_id))
        _, cleaned_text = raw_results.get(hadm_id_str, ("", ""))
        if cleaned_text.strip():
            results.append({"hadm_id": int(hadm_id_str), "cleaned_text": cleaned_text.strip()})

    df = pd.DataFrame(results)
    output_path = resolve_output_path(limit, out_path)
    df.to_parquet(output_path, index=False)

    print(f"\nSaved {len(df)} cleaned notes → {output_path}")
    print(f"Failed/empty: {len(items) - len(df)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",   type=int, default=None, help="limit to N notes (for testing)")
    parser.add_argument("--workers", type=int, default=8,    help="concurrent LLM calls")
    parser.add_argument("--model",   type=str, default=DEFAULT_MODEL, help="Bedrock model to use")
    parser.add_argument("--out",     type=str, default=None, help="optional parquet output path")
    args = parser.parse_args()

    asyncio.run(run(args.limit, args.workers, args.model, args.out))


if __name__ == "__main__":
    main()
