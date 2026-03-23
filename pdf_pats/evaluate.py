"""Grade PDF-cohort predictions.

Usage:
    uv run python pdf_pats/evaluate.py
    uv run python pdf_pats/evaluate.py --visit 1 2 3
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from evaluation.grader import grade_patient, extract_prescribed_set

_GT_PATH = os.path.join(_HERE, "outputs", "drug_gt.json")
_PRED_DIR = os.path.join(_HERE, "outputs", "predictions")


def grade_all(predictions: dict, gt: dict, visit_num: int) -> dict:
    visit = f"Visit_{visit_num}"
    exact_matches = 0
    jaccards = []
    mono_exact, mono_total = 0, 0
    poly_exact, poly_total = 0, 0
    results = {}

    for pid, pred in predictions.items():
        patient_gt = gt.get(pid, {})
        regimen = pred.get("final_regimen", pred)
        result = grade_patient(regimen, patient_gt, visit)
        results[pid] = result

        if result.get("gt_empty"):
            continue

        if result["exact_match"]:
            exact_matches += 1
        jaccards.append(result["best_jaccard"])

        gt_drugs = extract_prescribed_set(patient_gt.get(visit, {}))
        if len(gt_drugs) == 1:
            mono_total += 1
            if result["exact_match"]:
                mono_exact += 1
        elif len(gt_drugs) > 1:
            poly_total += 1
            if result["exact_match"]:
                poly_exact += 1

    n = len(jaccards)
    return {
        "summary": {
            "exact_match_rate": exact_matches / n if n else 0.0,
            "n_patients": n,
            "mono_exact_rate": mono_exact / mono_total if mono_total else 0.0,
            "mono_total": mono_total,
            "poly_exact_rate": poly_exact / poly_total if poly_total else 0.0,
            "poly_total": poly_total,
            "mean_jaccard": sum(jaccards) / n if n else 0.0,
        },
        "per_patient": results,
    }


def find_prediction_files(visit_num: int) -> dict[str, str]:
    files = {}
    for fname in sorted(os.listdir(_PRED_DIR)):
        if f"_v{visit_num}" in fname and fname.endswith(".json") and "graded" not in fname:
            label = "baseline" if "baseline" in fname else "consilium"
            files[label] = os.path.join(_PRED_DIR, fname)
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--visit", type=int, nargs="+", default=list(range(1, 7)))
    args = parser.parse_args()

    with open(_GT_PATH, encoding="utf-8") as f:
        gt = json.load(f)

    print(f"\n{'='*60}")
    print(f"PDF COHORT EVALUATION (367 patients, 1509 visits)")
    print(f"{'='*60}")

    for v in args.visit:
        pred_files = find_prediction_files(v)
        if not pred_files:
            continue

        print(f"\nVisit {v}:")
        for label in ["baseline", "consilium"]:
            if label not in pred_files:
                continue
            with open(pred_files[label], encoding="utf-8") as f:
                preds = json.load(f)
            s = grade_all(preds, gt, v)["summary"]
            print(f"  {label.upper():<12}  exact={s['exact_match_rate']:.1%}  "
                  f"mono={s['mono_exact_rate']:.1%} ({s['mono_total']})  "
                  f"poly={s['poly_exact_rate']:.1%} ({s['poly_total']})  "
                  f"jaccard={s['mean_jaccard']:.3f}  n={s['n_patients']}")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
