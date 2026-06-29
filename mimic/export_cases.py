"""Export prepared MIMIC data to Case JSONL.

Usage:
    uv run python mimic/export_cases.py
"""

from __future__ import annotations

import argparse
import json
import os

from mimic.loader import FILT_DIR, _clean_note, _load_usable


def build_input(row) -> str:
    race = str(row.get("race", "")).strip()
    header = f"Age: {int(row['anchor_age'])} | Sex: {row['gender']}"
    if race and race.lower() not in ("nan", "unknown", "unable to obtain", "other"):
        header += f" | Race: {race}"
    return header + "\n\n" + _clean_note(row["cleaned_text"])


def export_cases(output_path: str) -> int:
    df = _load_usable()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            record = {
                "pid": str(row["subject_id"]),
                "visit_num": int(row["visit_num"]),
                "cohort": "mimic",
                "input": build_input(row),
                "output": "",
                "prescribed": list(row["gt_drugs"]),
                "stopped": [],
                "hadm_id": str(row["hadm_id"]),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export prepared MIMIC data to Case JSONL")
    parser.add_argument(
        "--out",
        default=os.path.join(FILT_DIR, "cases.jsonl"),
        help="Output JSONL path",
    )
    args = parser.parse_args()

    n = export_cases(args.out)
    print(f"Saved {n} cases -> {args.out}")


if __name__ == "__main__":
    main()
