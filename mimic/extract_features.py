"""Extract classical baseline features for MIMIC patients from ICD codes + demographics.

Produces mimic/outputs/features_mimic.json in the same schema as
classical/outputs/features_v*.json so that classical/freq_baseline.py --mimic
can consume them directly.

Features derived (no LLM needed):
  Age_Years         — anchor_age
  Gender            — 1=M, 0=F
  SeizureType       — from primary epilepsy ICD code:
                        0=focal, 1=generalized_non_motor, 2=generalized_motor, -1=unknown
  SeizureFreq       — from intractability flag (rough proxy):
                        3=intractable (weekly proxy), 1=controlled (infrequent proxy), -1=unknown
  CognitivePriority — from comorbid intellectual-disability ICD codes:
                        0=none, 1=mild/moderate, 2=severe/profound
  OnsetAgeYears     — not available in MIMIC, always -1

ICD-10 G40 structure: G40.XYZ stored as "G40XYZ"
  X = seizure subtype  (3 = char index 3 in "G40XYZ")
  Y = intractability   (0=no, 1=yes) at char index 4
  Z = status epilepticus at char index 5

ICD-9 345 structure: "345XY" (5 chars)
  X = seizure subtype at char index 3
  Y = intractability (0=no, 1=yes) at char index 4

Usage:
    uv run python mimic/extract_features.py
"""

import json
import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from mimic.loader import _load_usable, DATA_DIR  # noqa: E402

_OUT_DIR = os.path.join(_HERE, "outputs")


# ── SeizureType ────────────────────────────────────────────────────────────

def _seizure_type_icd10(code: str) -> int:
    """G40.XYZ → 0=focal, 1=gen_nonmotor, 2=gen_motor, -1=unknown."""
    if len(code) < 4:
        return -1
    sub = code[3]
    if sub in ("0", "1", "2"):   # localization-related / focal
        return 0
    if sub == "3":               # generalized idiopathic (absence, JME precursor)
        return 1
    if sub in ("4", "5"):        # other generalized, epileptic spasms
        return 2
    if sub == "6":               # grand mal (unspecified)
        return 2
    if sub == "7":               # petit mal (unspecified)
        return 1
    if sub == "A":               # absence epilepsy syndromes
        return 1
    if sub == "B":               # juvenile myoclonic epilepsy
        return 2
    return -1                    # 8=other specified, 9=unspecified


def _seizure_type_icd9(code: str) -> int:
    """345.x → 0=focal, 1=gen_nonmotor, 2=gen_motor, -1=unknown."""
    if len(code) < 4:
        return -1
    sub = code[3]
    if sub == "0":               # grand mal
        return 2
    if sub in ("1", "2"):        # petit mal / petit mal status
        return 1
    if sub == "3":               # grand mal status
        return 2
    if sub in ("4", "5", "7"):   # partial / epilepsia partialis continua
        return 0
    if sub == "6":               # infantile spasms
        return 2
    return -1                    # 8, 9 = other/unspecified


# ── SeizureFreq (intractability proxy) ────────────────────────────────────

def _intractable_icd10(code: str) -> int:
    """Return 3 (intractable=weekly proxy), 1 (controlled=infrequent proxy), or -1."""
    if len(code) >= 5:
        y = code[4]  # intractability digit
        if y == "1":
            return 3
        if y == "0":
            return 1
    return -1


def _intractable_icd9(code: str) -> int:
    """345.xY — Y=intractability flag at position 4."""
    if len(code) >= 5:
        flag = code[4]
        if flag == "1":
            return 3
        if flag == "0":
            return 1
    return -1


# ── CognitivePriority ──────────────────────────────────────────────────────

def _cognitive_priority(all_codes: list[str]) -> int:
    """Scan all diagnoses for intellectual disability ICD codes."""
    for code in all_codes:
        if not isinstance(code, str):
            continue
        # ICD-10: F70–F73
        if code.startswith("F7") and len(code) >= 3:
            d = code[2]
            if d in ("2", "3"):   # F72=severe, F73=profound
                return 2
            if d in ("0", "1"):   # F70=mild, F71=moderate
                return 1
        # ICD-9: 317–319
        try:
            c = int(code[:3])
        except ValueError:
            continue
        if c == 318:
            return 2   # moderate / severe / profound
        if c in (317, 319):
            return 1   # mild / unspecified
    return 0


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("Loading MIMIC usable cohort...")
    df = _load_usable()
    print(f"  {len(df)} admissions")
    hadm_ids = set(df["hadm_id"].astype(int))

    print("Loading diagnoses_icd...")
    dx = pd.read_csv(
        os.path.join(DATA_DIR, "diagnoses_icd.csv.gz"),
        dtype={"icd_code": str},
    )
    dx = dx[dx["hadm_id"].isin(hadm_ids)].copy()

    # All ICD codes per admission (for CognitivePriority scan)
    all_codes_by_hadm = dx.groupby("hadm_id")["icd_code"].apply(list).to_dict()

    # Primary epilepsy code per admission (lowest seq_num with G40/345)
    epi_mask = dx["icd_code"].str.startswith("G40") | (
        (dx["icd_version"] == 9) & dx["icd_code"].str.startswith("345")
    )
    epi_dx = dx[epi_mask].sort_values("seq_num")
    primary_epi = epi_dx.groupby("hadm_id").first()

    records = []
    for _, row in df.iterrows():
        hadm_id = int(row["hadm_id"])
        age = int(row["anchor_age"])
        gender = 1 if str(row["gender"]).upper() == "M" else 0

        # Seizure type + freq from primary epilepsy ICD
        st = -1
        sf = -1
        if hadm_id in primary_epi.index:
            code = str(primary_epi.loc[hadm_id, "icd_code"])
            ver = int(primary_epi.loc[hadm_id, "icd_version"])
            if ver == 10:
                st = _seizure_type_icd10(code)
                sf = _intractable_icd10(code)
            else:
                st = _seizure_type_icd9(code)
                sf = _intractable_icd9(code)

        # Cognitive priority from all comorbidities
        cp = _cognitive_priority(all_codes_by_hadm.get(hadm_id, []))

        records.append({
            "pid":       str(hadm_id),
            "cohort":    "mimic",
            "visit_num": 1,
            "features":  {
                "Age_Years":         {"value": age},
                "Gender":            {"value": gender},
                "SeizureType":       {"value": st},
                "SeizureFreq":       {"value": sf},
                "CognitivePriority": {"value": cp},
                "OnsetAgeYears":     {"value": -1},   # not available in MIMIC
            },
        })

    os.makedirs(_OUT_DIR, exist_ok=True)
    out_path = os.path.join(_OUT_DIR, "features_mimic.json")
    with open(out_path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"Saved {len(records)} records → {out_path}")

    # Quick stats
    from collections import Counter
    st_counts = Counter(r["features"]["SeizureType"]["value"] for r in records)
    sf_counts = Counter(r["features"]["SeizureFreq"]["value"] for r in records)
    cp_counts = Counter(r["features"]["CognitivePriority"]["value"] for r in records)

    st_labels = {0: "focal", 1: "gen_nonmotor", 2: "gen_motor", -1: "unknown"}
    sf_labels = {3: "intractable", 1: "controlled", -1: "unknown"}
    cp_labels = {0: "none", 1: "mild/mod", 2: "severe"}

    print(f"\nSeizureType:")
    for k, label in sorted(st_labels.items()):
        print(f"  {label:>20}: {st_counts.get(k, 0):4d}")
    print(f"\nSeizureFreq (intractability proxy):")
    for k, label in sorted(sf_labels.items()):
        print(f"  {label:>20}: {sf_counts.get(k, 0):4d}")
    print(f"\nCognitivePriority:")
    for k, label in sorted(cp_labels.items()):
        print(f"  {label:>20}: {cp_counts.get(k, 0):4d}")


if __name__ == "__main__":
    main()
