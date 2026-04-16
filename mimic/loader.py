"""
MIMIC-IV Patient Loader
========================
Loads the clean, filtered MIMIC epilepsy cohort for use in the self-learning loop.

All filters are applied on load. The current loader returns exactly one admission
per patient: the chronologically earliest admission that satisfies the note and GT
filters.

Returns PatientCase objects (with clinical_context set to truncated note)
and a gt_data dict in the same format as scripts/loader.py — drop-in compatible
with the self-learning loop.

Usage:
    from mimic.loader import load_mimic_cases, load_mimic_ground_truth
"""

from __future__ import annotations

import os
import pandas as pd
from schemas.patient import PatientCase

# The 10 drugs shared with Uganda — filter GT to these only
UGANDA_DRUGS = {
    "carbamazepine", "clobazam", "clonazepam", "ethosuximide",
    "lamotrigine", "levetiracetam", "phenobarbital", "phenytoin",
    "topiramate", "valproate",
}

_HERE = os.path.dirname(os.path.abspath(__file__))
FILTERED_DIR = os.path.join(_HERE, "filtered")
DATA_DIR = os.path.join(_HERE, "data")

def _load_usable() -> pd.DataFrame:
    """Load and apply all filters. Returns one row per patient (first admission only).

    Filters applied:
      1. Has truncatable discharge note ("Discharge Medications:" section)
      2. Has at least one qualifying AED in ground truth
      3. First admission per patient only (V1, chronologically earliest)
    """
    ids = pd.read_csv(os.path.join(FILTERED_DIR, "filtered_ids.csv"))
    notes = pd.read_parquet(os.path.join(FILTERED_DIR, "discharge_notes.parquet"))
    gt = pd.read_parquet(os.path.join(FILTERED_DIR, "gt_drugs.parquet"))

    # Filter 1: has truncatable section
    notes = notes[notes["text"].str.contains("Discharge Medications:", na=False)]

    # Filter 2: has GT drugs
    valid_hadms = set(notes["hadm_id"]) & set(gt["hadm_id"])
    ids = ids[ids["hadm_id"].isin(valid_hadms)]

    # Filter 3: first admission per patient only
    adm = pd.read_csv(
        os.path.join(DATA_DIR, "admissions.csv.gz"),
        usecols=["hadm_id", "admittime", "race"],
        parse_dates=["admittime"],
    )
    df = ids.merge(adm, on="hadm_id")
    df = df.sort_values("admittime").groupby("subject_id").first().reset_index()
    df["visit_num"] = 1

    # Join patient demographics
    pts = pd.read_csv(
        os.path.join(DATA_DIR, "patients.csv.gz"),
        usecols=["subject_id", "gender", "anchor_age"],
    )
    df = df.merge(pts, on="subject_id")

    # Join notes and gt
    df = df.merge(notes[["hadm_id", "text"]], on="hadm_id")
    df = df.merge(gt, on="hadm_id")

    # Filter GT to 10 Uganda drugs only (preserve parquet, filter at runtime)
    df["gt_drugs"] = df["gt_drugs"].apply(
        lambda drugs: [d for d in drugs if d in UGANDA_DRUGS]
    )
    # Drop cases where no Uganda drug remains
    df = df[df["gt_drugs"].apply(len) > 0].reset_index(drop=True)

    return df


def _truncate_note(text: str) -> str:
    """Return only the clinical input sections — strips everything that leaks the answer.

    Removed:
      - 'Brief Hospital Course' onwards (mentions drugs started/stopped during stay)
      - 'Discharge Medications' onwards (the answer list)

    Kept:
      - Chief Complaint, HPI, PMH, Social/Family History
      - Physical Exam, Pertinent Results (labs, imaging, EEG)
      - Medications on Admission (prior drug history — valid context)
    """
    # Strip from Brief Hospital Course onwards (contains drug initiation cues)
    for marker in ["Brief Hospital Course:", "Brief Hospital course:"]:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
            break

    # Also strip Discharge Medications as a safety net
    idx = text.find("Discharge Medications:")
    if idx != -1:
        text = text[:idx]

    return text.strip()


def load_mimic_cases(limit: int | None = None) -> list[PatientCase]:
    """Load MIMIC cases as PatientCase objects, compatible with the self-learning loop."""
    df = _load_usable()
    if limit is not None:
        df = df.head(limit)

    cases = []
    for _, row in df.iterrows():
        race = str(row.get("race", "")).strip()
        header = f"Age: {int(row['anchor_age'])} | Sex: {row['gender']}"
        if race and race.lower() not in ("nan", "unknown", "unable to obtain", "other"):
            header += f" | Race: {race}"
        clinical_context = header + "\n\n" + _truncate_note(row["text"])
        case = PatientCase(
            patient_id=str(row["hadm_id"]),
            current_visit=f"Visit_{row['visit_num']}",
            clinical_context=clinical_context,
            cohort="mimic",
        )
        cases.append(case)
    return cases


def load_mimic_ground_truth(limit: int | None = None) -> dict[str, dict]:
    """Load MIMIC GT in the same format as scripts/loader.py load_ground_truth().

    Returns:
        {"{hadm_id}__v{visit_num}": {"prescribed": [...], "stopped": []}}
    """
    df = _load_usable()
    if limit is not None:
        df = df.head(limit)

    gt = {}
    for _, row in df.iterrows():
        key = f"{row['hadm_id']}__v{row['visit_num']}"
        gt[key] = {
            "pid": str(row["hadm_id"]),
            "visit_num": row["visit_num"],
            "cohort": "mimic",
            "prescribed": list(row["gt_drugs"]),
            "stopped": [],
        }
    return gt


def mimic_stats() -> None:
    """Print a summary of the loaded cohort."""
    df = _load_usable()
    n_adm = len(df)
    n_pats = df["subject_id"].nunique()
    dist = df.groupby("subject_id")["hadm_id"].count().value_counts().sort_index()
    mono = df["gt_drugs"].apply(lambda d: len(d) == 1).sum()
    poly = df["gt_drugs"].apply(lambda d: len(d) > 1).sum()

    print(f"MIMIC cohort: {n_adm} admissions, {n_pats} patients")
    print(f"  Mono: {mono} ({mono/n_adm:.0%})  Poly: {poly} ({poly/n_adm:.0%})")
    print(f"  Visits per patient: " + "  ".join(f"{k}v={v}" for k, v in dist.items()))


if __name__ == "__main__":
    mimic_stats()
