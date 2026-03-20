"""Drug match grading — exact match and partial match (Jaccard).

Compares predictions against drug_gt.json.
"""

from __future__ import annotations
import json
import os

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "processed")


def load_ground_truth() -> dict:
    """Load drug_gt.json."""
    with open(os.path.join(_DATA_DIR, "drug_gt.json"), encoding="utf-8") as f:
        return json.load(f)


def extract_prescribed_set(gt_entry: dict) -> set[str]:
    """Extract the set of prescribed drugs from a GT entry."""
    return set(d.lower() for d in gt_entry.get("prescribed", []))


def extract_prediction_set(option: dict) -> set[str]:
    """Extract the set of active drugs from a prediction option.

    V2 format: {"drugs": {"valproate": "continue", ...}}
    """
    drugs = option.get("drugs", {})
    return set(
        drug.lower()
        for drug, action in drugs.items()
        if action in ("continue", "start")
    )


def exact_match(predicted: set[str], ground_truth: set[str]) -> bool:
    """Check if predicted drug set exactly matches ground truth."""
    return predicted == ground_truth


def jaccard_similarity(predicted: set[str], ground_truth: set[str]) -> float:
    """Compute Jaccard similarity between predicted and GT drug sets."""
    if not predicted and not ground_truth:
        return 1.0
    if not predicted or not ground_truth:
        return 0.0
    return len(predicted & ground_truth) / len(predicted | ground_truth)


def grade_patient(
    patient_predictions: dict,
    patient_gt: dict,
    visit: str,
    top_k: int = 3,
) -> dict:
    """Grade a single patient's predictions against ground truth.

    Returns:
        {
            "exact_match": bool (any of top-k options match),
            "best_jaccard": float,
            "per_option": [{option_num, exact, jaccard, predicted, gt}]
        }
    """
    gt_entry = patient_gt.get(visit, {})
    gt_drugs = extract_prescribed_set(gt_entry)

    if not gt_drugs:
        return {"exact_match": False, "best_jaccard": 0.0, "per_option": [], "gt_empty": True}

    per_option = []
    best_jaccard = 0.0
    any_exact = False

    for n in range(1, top_k + 1):
        option = patient_predictions.get(f"option_{n}", {})
        pred_drugs = extract_prediction_set(option)

        em = exact_match(pred_drugs, gt_drugs)
        jac = jaccard_similarity(pred_drugs, gt_drugs)

        if em:
            any_exact = True
        best_jaccard = max(best_jaccard, jac)

        per_option.append({
            "option_num": n,
            "exact": em,
            "jaccard": jac,
            "predicted": sorted(pred_drugs),
            "gt": sorted(gt_drugs),
        })

    return {
        "exact_match": any_exact,
        "best_jaccard": best_jaccard,
        "per_option": per_option,
        "gt_empty": False,
    }


def grade_all(
    predictions: dict,
    visit_num: int = 1,
) -> dict:
    """Grade all predictions against ground truth.

    Args:
        predictions: {patient_id: {option_1: {...}, option_2: {...}, option_3: {...}}}
        visit_num: 1, 2, or 3.

    Returns:
        {
            "summary": {exact_match_rate, mean_jaccard, n_patients, mono_exact, poly_exact},
            "per_patient": {patient_id: grade_result}
        }
    """
    gt = load_ground_truth()
    visit = f"Visit_{visit_num}"

    results = {}
    exact_matches = 0
    jaccards = []
    mono_exact = 0
    mono_total = 0
    poly_exact = 0
    poly_total = 0

    for pid, pred in predictions.items():
        patient_gt = gt.get(pid, {})
        # V2 format: read from final_regimen
        regimen = pred.get("final_regimen", pred)
        result = grade_patient(regimen, patient_gt, visit)
        results[pid] = result

        if result.get("gt_empty"):
            continue

        if result["exact_match"]:
            exact_matches += 1
        jaccards.append(result["best_jaccard"])

        # Mono vs poly
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
            "mean_jaccard": sum(jaccards) / n if n else 0.0,
            "n_patients": n,
            "mono_exact_rate": mono_exact / mono_total if mono_total else 0.0,
            "mono_total": mono_total,
            "poly_exact_rate": poly_exact / poly_total if poly_total else 0.0,
            "poly_total": poly_total,
        },
        "per_patient": results,
    }
