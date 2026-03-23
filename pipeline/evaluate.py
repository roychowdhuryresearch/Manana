"""Evaluate pipeline or baseline predictions against dataset ground truth.

Loads ground truth from the dataset and computes exact match and Jaccard
similarity for predicted vs prescribed drug sets.

Usage:
    uv run python pipeline/evaluate.py --predictions outputs/predictions/consilium_*.json --visit 1
    uv run python pipeline/evaluate.py --predictions outputs/baseline/baseline_*.json --visit 1 --cohort csv
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from pipeline.loader import load_ground_truth


# ---------------------------------------------------------------------------
# Drug extraction
# ---------------------------------------------------------------------------

def extract_predicted(prediction: dict) -> set[str]:
    """Extract active drugs from a prediction entry.

    Handles both consilium format (final_regimen) and baseline format (option_1).
    """
    regimen = prediction.get("final_regimen", prediction)
    drugs = regimen.get("drugs", {})
    if isinstance(drugs, list):
        return set(d["drug"].lower() for d in drugs if d.get("action") in ("continue", "start"))
    return set(drug.lower() for drug, action in drugs.items() if action in ("continue", "start"))


def extract_gt(gt_entry: dict) -> set[str]:
    return set(d.lower() for d in gt_entry.get("prescribed", []))


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

def grade(predictions: dict, gt: dict) -> dict:
    """Grade predictions against ground truth.

    Args:
        predictions: {pid: prediction_dict}
        gt: {pid__vN: gt_dict} from load_ground_truth()

    Returns:
        Summary + per-patient results.
    """
    results = {}
    exact_matches, jaccards = 0, []
    mono_exact, mono_total, poly_exact, poly_total = 0, 0, 0, 0

    for pid, pred in predictions.items():
        # Match pid to GT — try exact key, then match by pid prefix
        gt_entry = None
        for key, val in gt.items():
            if val["pid"] == pid:
                gt_entry = val
                break

        if gt_entry is None:
            continue

        gt_drugs = extract_gt(gt_entry)
        if not gt_drugs:
            results[pid] = {"exact_match": False, "jaccard": 0.0, "gt_empty": True}
            continue

        pred_drugs = extract_predicted(pred)
        em = pred_drugs == gt_drugs
        jac = jaccard(pred_drugs, gt_drugs)

        if em:
            exact_matches += 1
        jaccards.append(jac)

        if len(gt_drugs) == 1:
            mono_total += 1
            if em:
                mono_exact += 1
        elif len(gt_drugs) > 1:
            poly_total += 1
            if em:
                poly_exact += 1

        results[pid] = {
            "exact_match": em,
            "jaccard": jac,
            "predicted": sorted(pred_drugs),
            "gt": sorted(gt_drugs),
            "gt_empty": False,
        }

    n = len(jaccards)
    return {
        "summary": {
            "n_patients": n,
            "exact_match_rate": exact_matches / n if n else 0.0,
            "mean_jaccard": sum(jaccards) / n if n else 0.0,
            "mono_exact_rate": mono_exact / mono_total if mono_total else 0.0,
            "mono_total": mono_total,
            "poly_exact_rate": poly_exact / poly_total if poly_total else 0.0,
            "poly_total": poly_total,
        },
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Evaluate predictions against dataset ground truth")
    parser.add_argument("--predictions", type=str, required=True, help="Path to predictions JSON")
    parser.add_argument("--visit", type=int, required=True, help="Visit number")
    parser.add_argument("--cohort", type=str, choices=["csv", "pdf"], default=None)
    parser.add_argument("--output-dir", type=str, default="outputs/evaluation")
    args = parser.parse_args()

    with open(args.predictions, encoding="utf-8") as f:
        predictions = json.load(f)

    gt = load_ground_truth(visit_num=args.visit, cohort=args.cohort)

    results = grade(predictions, gt)

    os.makedirs(args.output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.predictions))[0]
    out_path = os.path.join(args.output_dir, f"eval_{base}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    s = results["summary"]
    print(f"\n{'='*60}")
    print(f"EVALUATION RESULTS")
    print(f"{'='*60}")
    print(f"  Patients:       {s['n_patients']}")
    print(f"  Exact match:    {s['exact_match_rate']:.1%}")
    print(f"  Mean Jaccard:   {s['mean_jaccard']:.3f}")
    print(f"  Mono exact:     {s['mono_exact_rate']:.1%}  ({s['mono_total']} patients)")
    print(f"  Poly exact:     {s['poly_exact_rate']:.1%}  ({s['poly_total']} patients)")
    print(f"\n  Saved → {out_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
