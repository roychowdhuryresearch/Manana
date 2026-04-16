"""
MIMIC-IV Ground Truth AED Extraction
======================================
Extracts oral AEDs active at discharge for all filtered admissions.

Rules:
  - Drug name matches one of 10 tracked AEDs (via alias mapping)
  - Route is oral (PO, PO/NG, ORAL, NG, GT, PEG, etc.)
  - stoptime >= dischtime (still active when patient left)
  - Started during this admission (starttime > admittime) — fresh clinical decision
  - Fosphenytoin excluded (IV-only prodrug, never a discharge med)

Output (mimic/filtered/):
  gt_drugs.parquet — (hadm_id, gt_drugs) where gt_drugs is a list of canonical drug names

Usage:
    uv run python mimic/gt.py
"""

import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_DIR = os.path.join(os.path.dirname(__file__), "filtered")


def path(f):
    return os.path.join(DATA_DIR, f)


# Canonical name → list of substrings to match (all lowercase)
AED_ALIASES = {
    "levetiracetam": ["levetiracet", "keppra"],
    "lamotrigine":   ["lamotrigin", "lamictal"],
    "carbamazepine": ["carbamazep", "tegretol"],
    "valproate":     ["valproat", "divalproex", "depakot", "depaken", "valproic acid"],
    "phenytoin":     ["phenytoin", "dilantin"],
    "phenobarbital": ["phenobarb", "luminal"],
    "topiramate":    ["topiramat", "topamax"],
    "clonazepam":    ["clonazep"],
    "clobazam":      ["clobazam", "onfi"],
    "ethosuximide":  ["ethosuximid", "zarontin"],
    # MIMIC-only AEDs (not in Uganda formulary, preserved for now)
    "zonisamide":    ["zonisamid"],
    "lacosamide":    ["lacosamid"],
    "oxcarbazepine": ["oxcarbazep"],
}

ORAL_ROUTES = {"po", "po/ng", "oral", "ng", "gt", "peg", "sl", "po/ng/peg/gt"}

EXCLUDE = ["fosphenytoin"]


def canonical(drug_name: str) -> str | None:
    d = drug_name.lower()
    if any(ex in d for ex in EXCLUDE):
        return None
    for canon, aliases in AED_ALIASES.items():
        if any(alias in d for alias in aliases):
            return canon
    return None


def main():
    notes = pd.read_parquet(os.path.join(OUT_DIR, "discharge_notes.parquet"))
    valid_hadms = set(notes["hadm_id"])

    adm = pd.read_csv(
        path("admissions.csv.gz"),
        usecols=["hadm_id", "admittime", "dischtime"],
        parse_dates=["admittime", "dischtime"],
    )
    adm = adm[adm["hadm_id"].isin(valid_hadms)]

    pattern = "|".join(
        alias for aliases in AED_ALIASES.values() for alias in aliases
    ) + "|fosphenytoin"

    print("Scanning prescriptions...")
    chunks = []
    for chunk in pd.read_csv(
        path("prescriptions.csv.gz"),
        chunksize=100_000,
        usecols=["hadm_id", "drug", "route", "starttime", "stoptime"],
        parse_dates=["starttime", "stoptime"],
    ):
        chunk = chunk[chunk["hadm_id"].isin(valid_hadms)]
        chunk = chunk[chunk["drug"].str.lower().str.contains(pattern, na=False)]
        if not chunk.empty:
            chunks.append(chunk)

    rx = pd.concat(chunks, ignore_index=True)
    rx = rx.merge(adm, on="hadm_id")

    # Apply filters
    rx = rx[rx["stoptime"] >= rx["dischtime"]]                    # active at discharge
    rx = rx[rx["starttime"] > rx["admittime"]]                    # new during admission
    rx = rx[rx["route"].str.lower().str.strip().isin(ORAL_ROUTES)]  # oral only
    rx["canonical"] = rx["drug"].apply(canonical)
    rx = rx[rx["canonical"].notna()]                              # exclude fosphenytoin etc

    print(f"Qualifying prescription rows: {len(rx)}")

    # One row per (hadm_id, canonical drug)
    gt = (
        rx.groupby("hadm_id")["canonical"]
        .apply(lambda x: sorted(set(x)))
        .reset_index()
        .rename(columns={"canonical": "gt_drugs"})
    )

    out_path = os.path.join(OUT_DIR, "gt_drugs.parquet")
    gt.to_parquet(out_path, index=False)
    print(f"Saved gt_drugs.parquet — {len(gt)} admissions with GT drugs\n")

    # ── Stats ──────────────────────────────────────────────────────────────
    total = len(gt)
    mono = gt[gt["gt_drugs"].apply(len) == 1]
    poly = gt[gt["gt_drugs"].apply(len) > 1]

    print(f"{'='*50}")
    print(f"GT STATS")
    print(f"{'='*50}")
    print(f"Admissions with ≥1 AED at discharge: {total}")
    print(f"  Monotherapy: {len(mono)} ({len(mono)/total:.0%})")
    print(f"  Polytherapy: {len(poly)} ({len(poly)/total:.0%})")
    print()

    # Drug distribution
    from collections import Counter
    all_drugs = [d for drugs in gt["gt_drugs"] for d in drugs]
    dist = Counter(all_drugs)
    print("Drug distribution (appearances across all admissions):")
    for drug, count in dist.most_common():
        print(f"  {drug:<20} {count:>5}  ({count/total:.0%})")

    print()
    # Polytherapy combos
    poly_combos = poly["gt_drugs"].apply(tuple).value_counts()
    print(f"Top polytherapy combinations:")
    for combo, count in poly_combos.head(10).items():
        print(f"  {' + '.join(combo):<45} {count}")

    print()
    # Admissions with no AED at discharge
    all_hadms = len(valid_hadms)
    print(f"Admissions with no qualifying AED at discharge: {all_hadms - total} (dropped)")
    print(f"Working set: {total} admissions")


if __name__ == "__main__":
    main()
