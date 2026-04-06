"""Run EpiPick algorithm on extracted inputs.

Reads epipick/outputs/extracted.json (produced by extract.py),
runs the algorithm on each record, saves predictions.

Usage:
    conda run -n global_llm python epipick/run.py
    conda run -n global_llm python epipick/run.py --input epipick/outputs/extracted.json
    conda run -n global_llm python epipick/run.py --output epipick/outputs/predictions.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from tqdm import tqdm

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from epipick.algorithm import (
    SEIZURE_UNCERTAIN, SEIZURE_FOCAL, SEIZURE_ABSENCE,
    SEIZURE_MYOCLONIC, SEIZURE_MYOCLONIC_ABSENCE,
    SEIZURE_GTCS, SEIZURE_GTCS_MYOCLONIC,
    SEIZURE_GTCS_ABSENCE, SEIZURE_GTCS_MYOCLONIC_ABSENCE,
    Modifiers, run_epipick,
)

_DEFAULT_INPUT = os.path.join(_HERE, "outputs", "extracted.json")
_DEFAULT_OUTPUT = os.path.join(_HERE, "outputs", "predictions.json")

SEIZURE_TYPE_MAP = {
    "UNCERTAIN": SEIZURE_UNCERTAIN,
    "FOCAL": SEIZURE_FOCAL,
    "ABSENCE": SEIZURE_ABSENCE,
    "MYOCLONIC": SEIZURE_MYOCLONIC,
    "MYOCLONIC_ABSENCE": SEIZURE_MYOCLONIC_ABSENCE,
    "GTCS": SEIZURE_GTCS,
    "GTCS_MYOCLONIC": SEIZURE_GTCS_MYOCLONIC,
    "GTCS_ABSENCE": SEIZURE_GTCS_ABSENCE,
    "GTCS_MYOCLONIC_ABSENCE": SEIZURE_GTCS_MYOCLONIC_ABSENCE,
}


def build_modifiers(mod_dict: dict) -> Modifiers:
    return Modifiers(
        daily_medication=mod_dict.get("daily_medication", False),
        contraceptive=mod_dict.get("contraceptive", False),
        tumor=mod_dict.get("tumor", False),
        hepatic_failure=mod_dict.get("hepatic_failure", False),
        obesity=mod_dict.get("obesity", False),
        diabetes=mod_dict.get("diabetes", False),
        bleeding=mod_dict.get("bleeding", False),
        neutropenia=mod_dict.get("neutropenia", False),
        renal_stone=mod_dict.get("renal_stone", False),
        allergy=mod_dict.get("allergy", False),
        depression=mod_dict.get("depression", False),
        aggressive=mod_dict.get("aggressive", False),
        migraine=mod_dict.get("migraine", False),
        renal_failure=mod_dict.get("renal_failure", False),
    )


def process_record(record: dict) -> dict:
    ext = record["extracted"]
    seizure_str = ext.get("seizure_type", "UNCERTAIN").upper()
    seizure_type = SEIZURE_TYPE_MAP.get(seizure_str, SEIZURE_UNCERTAIN)
    age = float(ext.get("age") or 30)
    gender = (ext.get("gender") or "male").lower()
    menopausal = (ext.get("menopausal") or "post").lower()
    modifiers = build_modifiers(ext.get("modifiers", {}))

    groups = run_epipick(
        seizure_type=seizure_type,
        age=age,
        gender=gender,
        menopausal=menopausal,
        modifiers=modifiers,
    )

    return {
        "pid": record["pid"],
        "visit_num": record["visit_num"],
        "cohort": record["cohort"],
        "prescribed": record.get("prescribed", []),
        "extracted": ext,
        "group1": groups["group1"],
        "group2": groups["group2"],
        "group3": groups["group3"],
        "group4": groups["group4"],
    }


def main():
    parser = argparse.ArgumentParser(description="Run EpiPick algorithm on extracted inputs")
    parser.add_argument("--input", type=str, default=_DEFAULT_INPUT)
    parser.add_argument("--output", type=str, default=_DEFAULT_OUTPUT)
    args = parser.parse_args()

    with open(args.input) as f:
        records = json.load(f)
    print(f"Loaded {len(records)} extracted records")

    results = []
    errors = 0
    for record in tqdm(records, desc="Running EpiPick"):
        try:
            results.append(process_record(record))
        except Exception as e:
            print(f"  Error on {record.get('pid')} v{record.get('visit_num')}: {e}")
            errors += 1

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved {len(results)} predictions → {args.output}")
    if errors:
        print(f"Errors: {errors}")

    # Quick preview
    print("\nSample output:")
    r = results[0]
    print(f"  pid: {r['pid']} v{r['visit_num']}")
    print(f"  seizure_type: {r['extracted'].get('seizure_type')}")
    print(f"  prescribed (GT): {r['prescribed']}")
    print(f"  group1: {r['group1']}")
    print(f"  group2: {r['group2']}")
    print(f"  group3: {r['group3']}")


if __name__ == "__main__":
    main()
