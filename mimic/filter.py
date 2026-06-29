"""
MIMIC-IV Epilepsy Patient Filter
=================================
Filters MIMIC-IV to hospital admissions where:
  1. Primary diagnosis (seq_num=1) is epilepsy — ICD-9 345.x or ICD-10 G40.x
  2. Managing clinical team is Neurology (service code: NMED)

These are patients admitted specifically for epilepsy management under
active neurologist care — the closest structural equivalent to the Uganda
epilepsy clinic cohort.

Output (mimic/filtered/):
  filtered_ids.csv          — (subject_id, hadm_id) for all qualifying admissions
  discharge_notes.parquet   — (subject_id, hadm_id, text) discharge summaries

Usage:
    uv run python mimic/filter.py
"""

import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_DIR = os.path.join(os.path.dirname(__file__), "filtered")
os.makedirs(OUT_DIR, exist_ok=True)


def path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)


def is_epilepsy(icd_code: pd.Series, icd_version: pd.Series) -> pd.Series:
    icd9 = (icd_version == 9) & icd_code.str.startswith("345")
    icd10 = (icd_version == 10) & icd_code.str.startswith("G40")
    return icd9 | icd10


def main():
    print("Loading diagnoses_icd...")
    dx = pd.read_csv(path("diagnoses_icd.csv.gz"), dtype={"icd_code": str})

    print("Loading services...")
    svc = pd.read_csv(path("services.csv.gz"))
    # Keep only the first service per admission (the primary managing team)
    svc = svc.sort_values("transfertime").groupby("hadm_id").first().reset_index()
    neuro_hadms = set(svc.loc[svc["curr_service"] == "NMED", "hadm_id"])

    # Primary epilepsy dx + neurology service
    epilepsy_primary = dx[is_epilepsy(dx["icd_code"], dx["icd_version"]) & (dx["seq_num"] == 1)]
    filtered = epilepsy_primary[epilepsy_primary["hadm_id"].isin(neuro_hadms)][
        ["subject_id", "hadm_id"]
    ].drop_duplicates()

    print(f"Qualifying admissions: {len(filtered):,}")

    filtered.to_csv(os.path.join(OUT_DIR, "filtered_ids.csv"), index=False)
    print("Saved filtered_ids.csv.")

    # Discharge notes for all qualifying admissions
    target_hadms = set(filtered["hadm_id"])
    print(f"\nExtracting discharge notes for {len(target_hadms):,} admissions...")
    print("(Streaming discharge.csv.gz in chunks — this may take a few minutes)")

    chunks = []
    for i, chunk in enumerate(
        pd.read_csv(path("discharge.csv.gz"), chunksize=50_000, dtype=str)
    ):
        keep = chunk[
            (chunk["hadm_id"].astype(float).astype(int).isin(target_hadms))
            & (chunk["note_type"] == "DS")
        ][["subject_id", "hadm_id", "text"]]
        if not keep.empty:
            chunks.append(keep)
        if i % 20 == 0:
            print(f"  chunk {i}...", flush=True)

    notes = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(
        columns=["subject_id", "hadm_id", "text"]
    )
    notes["hadm_id"] = notes["hadm_id"].astype(int)
    notes["subject_id"] = notes["subject_id"].astype(int)
    # One note per admission — take the longest if duplicates exist
    notes = notes.sort_values("text", key=lambda s: s.str.len(), ascending=False)
    notes = notes.drop_duplicates(subset="hadm_id", keep="first")

    notes.to_parquet(os.path.join(OUT_DIR, "discharge_notes.parquet"), index=False)

    print(f"\n{'='*50}")
    print(f"DONE")
    print(f"{'='*50}")
    print(f"Admissions:      {len(filtered):,}")
    print(f"Discharge notes: {len(notes):,}")
    print(f"Output:          {OUT_DIR}/")


if __name__ == "__main__":
    main()
