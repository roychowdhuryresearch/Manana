"""Grade extraction-cohort predictions — same logic as evaluation/grader.py.

Reads GT from extraction/outputs/drug_gt.json instead of data/processed/.

Usage:
    uv run python extraction/evaluate.py --visit 1
    uv run python extraction/evaluate.py --visit 1 2 3 4 --all-predictions
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


def load_gt() -> dict:
    with open(_GT_PATH, encoding="utf-8") as f:
        return json.load(f)


def grade_all(predictions: dict, gt: dict, visit_num: int) -> dict:
    visit = f"Visit_{visit_num}"
    exact_matches = 0
    jaccards = []
    mono_exact, mono_total = 0, 0
    poly_exact, poly_total = 0, 0
    results = {}

    for pid, pred in predictions.items():
        patient_gt = gt.get(pid, {})
        regimen = pred.get("final_regimen", pred)  # consilium vs baseline
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
    """Return {label: filepath} for all prediction files matching visit_num."""
    files = {}
    for fname in sorted(os.listdir(_PRED_DIR)):
        if f"_v{visit_num}" in fname and fname.endswith(".json"):
            label = "baseline" if "baseline" in fname else "consilium"
            files[label] = os.path.join(_PRED_DIR, fname)
    return files


def print_summary(label: str, visit_num: int, summary: dict):
    print(f"\n  {label.upper()} — Visit {visit_num}")
    print(f"    Overall:  {summary['exact_match_rate']:.1%}  (n={summary['n_patients']})")
    print(f"    Mono:     {summary['mono_exact_rate']:.1%}  (n={summary['mono_total']})")
    print(f"    Poly:     {summary['poly_exact_rate']:.1%}  (n={summary['poly_total']})")
    print(f"    Jaccard:  {summary['mean_jaccard']:.3f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--visit", type=int, nargs="+", default=[1, 2, 3, 4])
    parser.add_argument("--save", action="store_true", help="Save per-patient results to outputs/")
    args = parser.parse_args()

    gt = load_gt()
    print(f"\n{'='*55}")
    print(f"EXTRACTION COHORT EVALUATION")
    print(f"{'='*55}")

    for v in args.visit:
        pred_files = find_prediction_files(v)
        if not pred_files:
            print(f"\n  Visit {v}: no prediction files found in {_PRED_DIR}")
            continue

        print(f"\nVisit {v}:")
        for label, fpath in pred_files.items():
            with open(fpath, encoding="utf-8") as f:
                preds = json.load(f)
            result = grade_all(preds, gt, v)
            print_summary(label, v, result["summary"])

            if args.save:
                out = os.path.join(_PRED_DIR, fpath.replace(".json", "_graded.json"))
                with open(out, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*55}\n")


if __name__ == "__main__":
    main()
