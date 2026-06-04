"""Load patient cases from the Consilium dataset.

Each row in the dataset is one (patient, visit) pair with a fully built
clinical context, doctor prescription, and ground-truth drug lists.
"""

from __future__ import annotations

import json
import os

from datasets import load_dataset

from lib.patient import PatientCase

DATASET_NAME = "kartiksharma4/consilium"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CASES_PATH = os.path.join(_ROOT, "data", "uganda_cases.jsonl")


def _load_rows() -> list[dict]:
    """Load local release JSONL when present, otherwise fall back to HF."""
    cases_path = os.getenv("CONSILIUM_CASES_PATH", DEFAULT_CASES_PATH)
    if cases_path and os.path.exists(cases_path):
        with open(cases_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    return list(load_dataset(DATASET_NAME, split="train"))


def _filter_rows(
    rows: list[dict],
    visit_num: int | None,
    cohort: str | None,
    limit: int | None,
) -> list[dict]:
    if visit_num is not None:
        rows = [row for row in rows if row["visit_num"] == visit_num]
    if cohort is not None:
        rows = [row for row in rows if row["cohort"] == cohort]
    if limit is not None:
        rows = rows[:limit]
    return rows


def load_cases(
    visit_num: int | None = None,
    cohort: str | None = None,
    limit: int | None = None,
) -> list[PatientCase]:
    """Load patient cases from the dataset.

    Args:
        visit_num: Filter to a specific visit number (1-indexed). None = all visits.
        cohort: Filter to 'A' or 'B'. None = all cohorts.
        limit: Max number of cases to return. None = all.

    Returns:
        List of PatientCase objects ready for pipeline processing.
    """
    rows = _filter_rows(_load_rows(), visit_num, cohort, limit)

    cases = []
    for row in rows:
        case = PatientCase(
            patient_id=row["pid"],
            current_visit=f"Visit_{row['visit_num']}",
            clinical_context=row["input"],
            cohort=row["cohort"],
        )
        cases.append(case)

    return cases


def load_ground_truth(
    visit_num: int | None = None,
    cohort: str | None = None,
    limit: int | None = None,
) -> dict[str, dict]:
    """Load ground truth labels keyed by (pid, visit_num).

    Returns:
        {pid: {"visit_num": int, "prescribed": [...], "stopped": [...], "output": str}}
    """
    rows = _filter_rows(_load_rows(), visit_num, cohort, limit)

    gt = {}
    for row in rows:
        key = f"{row['pid']}__v{row['visit_num']}"
        gt[key] = {
            "pid": row["pid"],
            "visit_num": row["visit_num"],
            "cohort": row["cohort"],
            "prescribed": row["prescribed"],
            "stopped": row["stopped"],
            "output": row["output"],
        }

    return gt
