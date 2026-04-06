"""Shared data-loading utilities for classical baselines."""

import json
import os
import numpy as np
import pandas as pd
from datasets import load_dataset

_HERE = os.path.dirname(os.path.abspath(__file__))
_OUTPUT_DIR = os.path.join(_HERE, "outputs")
_DATASET_NAME = "kartiksharma4/consilium"

DRUGS = [
    "carbamazepine", "clobazam", "clonazepam", "ethosuximide",
    "levetiracetam", "lamotrigine", "phenobarbital", "phenytoin",
    "topiramate", "valproate",
]

NAN_FIELDS = {"OnsetAgeYears", "SeizureFreq", "SeizureType"}


def load_features(visits: list[int], feature_cols: list[str]) -> pd.DataFrame:
    """Load extracted features for given visits and columns."""
    rows = []
    for v in visits:
        path = os.path.join(_OUTPUT_DIR, f"features_v{v}.json")
        if not os.path.exists(path):
            print(f"  WARNING: {path} not found, skipping v{v}")
            continue
        for rec in json.load(open(path)):
            f = rec.get("features", {})
            if not f:
                continue
            row = {"pid": rec["pid"], "cohort": rec["cohort"], "visit_num": rec["visit_num"]}
            for col in feature_cols:
                val = f.get(col, {}).get("value")
                if col in NAN_FIELDS and val == -1:
                    val = np.nan
                row[col] = val
            rows.append(row)
    return pd.DataFrame(rows)


def load_labels() -> dict[str, list[str]]:
    """Returns {pid__vN: [drug, ...]} from HuggingFace."""
    ds = load_dataset(_DATASET_NAME, split="train")
    labels = {}
    for row in ds:
        key = f"{row['pid']}__v{row['visit_num']}"
        labels[key] = [d.lower() for d in row["prescribed"]]
    return labels


def build_label_matrix(df: pd.DataFrame, labels: dict) -> np.ndarray:
    Y = np.zeros((len(df), len(DRUGS)), dtype=np.float32)
    for i, (_, row) in enumerate(df.iterrows()):
        key = f"{row['pid']}__v{int(row['visit_num'])}"
        prescribed = labels.get(key, [])
        for j, drug in enumerate(DRUGS):
            Y[i, j] = 1.0 if drug in prescribed else 0.0
    return Y


def patient_strata(df: pd.DataFrame, labels: dict) -> dict[str, int]:
    """Assign each patient a stratum: (cohort) x (ever poly)."""
    pat_cohort = df.groupby("pid")["cohort"].first()
    pat_poly = {}
    for pid in df["pid"].unique():
        visits = df[df["pid"] == pid]["visit_num"].tolist()
        ever_poly = any(
            len(labels.get(f"{pid}__v{int(v)}", [])) > 1 for v in visits
        )
        pat_poly[pid] = ever_poly

    strata = {}
    for pid in df["pid"].unique():
        cohort_id = 0 if pat_cohort[pid] == "csv" else 1
        poly_id = 1 if pat_poly[pid] else 0
        strata[pid] = cohort_id * 2 + poly_id
    return strata
