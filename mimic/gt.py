"""
MIMIC-IV Ground Truth AED Extraction
======================================
Extracts oral ASMs active at discharge for all filtered admissions.

Rules:
  - Drug matches one of the canonical ASMs via alias mapping
  - Oral route only (PO, PO/NG, ORAL, NG, GT, PEG, SL, etc.)
  - stoptime >= dischtime  (still active when patient left)
  - starttime > admittime  (new decision made during this admission)
  - Fosphenytoin excluded  (IV-only prodrug, never a discharge med)

Output (mimic/filtered/):
  gt_drugs.parquet — (hadm_id, gt_drugs) list of canonical drug names

Usage:
    uv run python mimic/gt.py
"""

import os
import pandas as pd
from collections import Counter

_HERE    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_HERE, "data")
FILT_DIR = os.path.join(_HERE, "filtered")
OUT_DIR  = os.path.join(_HERE, "filtered")
os.makedirs(OUT_DIR, exist_ok=True)


# Each canonical drug maps to substrings matched against lowercase drug name.
# No alias string appears under more than one canonical entry.
AED_ALIASES = {
    "levetiracetam":    ["levetiracet", "keppra"],
    "lamotrigine":      ["lamotrigin", "lamictal"],
    "carbamazepine":    ["carbamazep", "tegretol"],
    "valproate":        ["valproat", "divalproex", "depakot", "depaken", "valproic"],
    "phenytoin":        ["phenytoin", "dilantin"],       # fosphenytoin caught by EXCLUDE first
    "phenobarbital":    ["phenobarb", "luminal"],
    "topiramate":       ["topiramat", "topamax"],
    "clonazepam":       ["clonazep", "klonopin"],
    "clobazam":         ["clobazam", "onfi"],
    "ethosuximide":     ["ethosuximid", "zarontin"],
    "zonisamide":       ["zonisamid", "zonegran"],
    "lacosamide":       ["lacosamid", "vimpat"],
    "oxcarbazepine":    ["oxcarbazep", "trileptal"],
    "brivaracetam":     ["brivaracet", "briviact"],
    "perampanel":       ["perampanel", "fycompa"],
    "rufinamide":       ["rufinamide", "banzel"],
    "felbamate":        ["felbamate", "felbatol"],
    "vigabatrin":       ["vigabatrin", "sabril"],
    "primidone":        ["primidone", "mysoline"],
    "acetazolamide":    ["acetazolamide", "diamox"],
    "methsuximide":     ["methsuximide", "celontin"],
    "gabapentin":       ["gabapentin", "neurontin"],
    "pregabalin":       ["pregabalin", "lyrica"],
    "cannabidiol":      ["cannabidiol", "epidiolex"],
    "eslicarbazepine":  ["eslicarbazep", "aptiom"],
    "ezogabine":        ["ezogabine", "retigabine", "potiga"],
    "lorazepam":        ["lorazepam"],
    "diazepam":         ["diazepam"],
    "midazolam":        ["midazolam"],
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
    ids   = pd.read_csv(os.path.join(FILT_DIR, "filtered_ids.csv"))
    notes = pd.read_parquet(os.path.join(FILT_DIR, "discharge_notes.parquet"))
    valid_hadms = set(ids["hadm_id"]) & set(notes["hadm_id"])

    adm = pd.read_csv(
        os.path.join(DATA_DIR, "admissions.csv.gz"),
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
        os.path.join(DATA_DIR, "prescriptions.csv.gz"),
        chunksize=100_000,
        usecols=["hadm_id", "drug", "route", "starttime", "stoptime", "doses_per_24_hrs"],
        parse_dates=["starttime", "stoptime"],
    ):
        chunk = chunk[chunk["hadm_id"].isin(valid_hadms)]
        chunk = chunk[chunk["drug"].str.lower().str.contains(pattern, na=False)]
        if not chunk.empty:
            chunks.append(chunk)

    rx = pd.concat(chunks, ignore_index=True)
    rx = rx.merge(adm, on="hadm_id")

    rx = rx[rx["stoptime"] >= rx["dischtime"]]                      # active at discharge
    rx = rx[rx["starttime"] > rx["admittime"]]                      # new during admission
    rx = rx[rx["route"].str.lower().str.strip().isin(ORAL_ROUTES)]  # oral only
    rx = rx[rx["doses_per_24_hrs"].notna() & (rx["doses_per_24_hrs"] > 0)]  # scheduled only (drop PRN)
    rx["canonical"] = rx["drug"].apply(canonical)
    rx = rx[rx["canonical"].notna()]                                 # drop excluded

    print(f"Qualifying prescription rows: {len(rx)}")

    gt = (
        rx.groupby("hadm_id")["canonical"]
        .apply(lambda x: sorted(set(x)))
        .reset_index()
        .rename(columns={"canonical": "gt_drugs"})
    )

    out_path = os.path.join(OUT_DIR, "gt_drugs.parquet")
    gt.to_parquet(out_path, index=False)
    print(f"Saved gt_drugs.parquet — {len(gt)} admissions\n")

    # Stats
    total = len(gt)
    mono  = gt["gt_drugs"].apply(len) == 1
    poly  = gt["gt_drugs"].apply(len) > 1
    print(f"Monotherapy: {mono.sum()} ({mono.sum()/total:.0%})")
    print(f"Polytherapy: {poly.sum()} ({poly.sum()/total:.0%})")
    print()

    all_drugs = [d for drugs in gt["gt_drugs"] for d in drugs]
    print(f"{'Drug':<22} {'admissions':>10}  {'%':>6}")
    print("-" * 42)
    for drug, cnt in Counter(all_drugs).most_common():
        print(f"{drug:<22} {cnt:>10}  {cnt/total*100:>5.1f}%")


if __name__ == "__main__":
    main()
