"""Load patient cases from the Consilium HuggingFace dataset.

Each row in the dataset is one (patient, visit) pair with a fully built
clinical context, doctor prescription, and ground-truth drug lists.
"""

from __future__ import annotations

from datasets import load_dataset

from schemas.patient import PatientCase

DATASET_NAME = "kartiksharma4/consilium"


def load_cases(
    visit_num: int | None = None,
    cohort: str | None = None,
    limit: int | None = None,
) -> list[PatientCase]:
    """Load patient cases from the dataset.

    Args:
        visit_num: Filter to a specific visit number (1-indexed). None = all visits.
        cohort: Filter to 'csv' or 'pdf'. None = all cohorts.
        limit: Max number of cases to return. None = all.

    Returns:
        List of PatientCase objects ready for pipeline processing.
    """
    ds = load_dataset(DATASET_NAME, split="train")

    if visit_num is not None:
        ds = ds.filter(lambda x: x["visit_num"] == visit_num)
    if cohort is not None:
        ds = ds.filter(lambda x: x["cohort"] == cohort)
    if limit is not None:
        ds = ds.select(range(min(limit, len(ds))))

    cases = []
    for row in ds:
        case = PatientCase(
            patient_id=row["pid"],
            current_visit=f"Visit_{row['visit_num']}",
            clinical_context=row["input"],
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
    ds = load_dataset(DATASET_NAME, split="train")

    if visit_num is not None:
        ds = ds.filter(lambda x: x["visit_num"] == visit_num)
    if cohort is not None:
        ds = ds.filter(lambda x: x["cohort"] == cohort)
    if limit is not None:
        ds = ds.select(range(min(limit, len(ds))))

    gt = {}
    for row in ds:
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
