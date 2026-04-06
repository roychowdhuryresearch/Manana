"""Evaluate EpiPick predictions against ground truth.

Metric: Hit@G1 — is the GT drug in EpiPick's Group 1 (first-line)?
Only tracked drugs are considered (no equivalence mapping).
Only mono GT patients evaluated (EpiPick is monotherapy-only).

For mono patients, the LLM baselines' EM@3 checks if GT is among 3 predictions;
EpiPick's Hit@G1 checks if GT is among its first-line recommendations.

Usage:
    conda run -n global_llm python epipick/evaluate.py
    conda run -n global_llm python epipick/evaluate.py --input epipick/outputs/predictions.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

_DEFAULT_INPUT = os.path.join(_HERE, "outputs", "predictions.json")
_DEFAULT_OUTPUT_DIR = os.path.join(_HERE, "outputs")

TRACKED = {
    "carbamazepine", "clobazam", "clonazepam", "ethosuximide",
    "lamotrigine", "levetiracetam", "phenobarbital", "phenytoin",
    "topiramate", "valproate",
}


def evaluate(records: list[dict]) -> dict:
    """Hit@G1 on mono, tracked-GT patients. No mapping."""
    eligible = 0
    hits = 0
    per_cv: dict[str, dict] = {}  # cohort_v{visit} → {hits, count}
    per_seizure: dict[str, dict] = {}

    for r in records:
        prescribed = r.get("prescribed", [])
        if len(prescribed) != 1:
            continue
        gt_drug = prescribed[0].lower()
        if gt_drug not in TRACKED:
            continue

        eligible += 1
        g1_tracked = {d for d in r.get("group1", []) if d in TRACKED}
        hit = gt_drug in g1_tracked

        if hit:
            hits += 1

        # Per cohort × visit
        cv = f"{r.get('cohort', '?')}_v{r['visit_num']}"
        if cv not in per_cv:
            per_cv[cv] = {"hits": 0, "count": 0, "g1_sizes": []}
        per_cv[cv]["count"] += 1
        per_cv[cv]["g1_sizes"].append(len(g1_tracked))
        if hit:
            per_cv[cv]["hits"] += 1

        # Per seizure type
        sz = r.get("extracted", {}).get("seizure_type", "UNKNOWN")
        if sz not in per_seizure:
            per_seizure[sz] = {"hits": 0, "count": 0}
        per_seizure[sz]["count"] += 1
        if hit:
            per_seizure[sz]["hits"] += 1

    return {
        "eligible": eligible,
        "hits": hits,
        "hit_rate": round(hits / eligible, 4) if eligible else 0.0,
        "per_cohort_visit": {
            cv: {
                "hit_rate": round(d["hits"] / d["count"], 4) if d["count"] else 0.0,
                "hits": d["hits"],
                "n": d["count"],
                "avg_g1_size": round(sum(d["g1_sizes"]) / len(d["g1_sizes"]), 1),
            }
            for cv, d in sorted(per_cv.items())
        },
        "per_seizure_type": {
            sz: {
                "hit_rate": round(d["hits"] / d["count"], 4) if d["count"] else 0.0,
                "hits": d["hits"],
                "n": d["count"],
            }
            for sz, d in sorted(per_seizure.items())
        },
    }


def print_results(res: dict):
    print(f"\n{'='*60}")
    print(f"  EPIPICK — Hit@G1 (tracked only, mono GT)")
    print(f"{'='*60}")
    print(f"  Eligible patients:  {res['eligible']}")
    print(f"  Hits:               {res['hits']}")
    print(f"  Hit@G1:             {res['hit_rate']*100:.1f}%")

    print(f"\n  Per cohort × visit:")
    for cv, d in res["per_cohort_visit"].items():
        print(f"    {cv:<12} {d['hit_rate']*100:5.1f}%  ({d['hits']}/{d['n']})  avg |G1|={d['avg_g1_size']}")

    print(f"\n  Per seizure type:")
    for sz, d in res["per_seizure_type"].items():
        bar = "█" * int(d["hit_rate"] * 20)
        print(f"    {sz:<30} {d['hit_rate']*100:5.1f}%  ({d['hits']}/{d['n']})  {bar}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate EpiPick predictions")
    parser.add_argument("--input", type=str, default=_DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=str, default=_DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    with open(args.input) as f:
        records = json.load(f)
    print(f"Loaded {len(records)} prediction records")

    res = evaluate(records)
    print_results(res)

    out_path = os.path.join(args.output_dir, "eval_g1.json")
    with open(out_path, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\n  Saved → {out_path}")


if __name__ == "__main__":
    main()
