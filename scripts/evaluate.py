"""Evaluate pipeline or baseline predictions against dataset ground truth.

Loads ground truth from the HuggingFace dataset and computes exact match and
Jaccard similarity for predicted vs prescribed drug sets.

Usage:
    conda run -n global_llm python pipeline/evaluate.py --predictions outputs/predictions/consilium_*.json
    conda run -n global_llm python pipeline/evaluate.py --predictions outputs/baseline/baseline_*.json
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from scripts.loader import load_ground_truth

_OUTPUT_DIR = os.path.join(_ROOT, "outputs", "evaluation")


# ---------------------------------------------------------------------------
# Drug extraction
# ---------------------------------------------------------------------------

def _drugs_from_option(option: dict) -> set[str]:
    drugs = option.get("drugs", {})
    if isinstance(drugs, list):
        return set(d["drug"].lower() for d in drugs if d.get("action") in ("continue", "start"))
    return set(drug.lower() for drug, action in drugs.items() if action in ("continue", "start"))


def extract_all_options(record: dict) -> list[set[str]]:
    """Extract drugs from all 3 options (top-1, top-2, top-3).

    Returns a list of 3 sets, one per option (option_1 first).
    """
    trace = record.get("trace", {})
    source = trace.get("final_regimen", {}) if trace else record
    return [
        _drugs_from_option(source.get("option_1", {})),
        _drugs_from_option(source.get("option_2", {})),
        _drugs_from_option(source.get("option_3", {})),
    ]


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

def grade(records: list[dict], gt: dict) -> dict:
    """Grade predictions against ground truth using top-3 accuracy.

    A patient is an exact match if ANY of the 3 options matches GT exactly.
    Jaccard is the best score across all 3 options.
    """
    results = {}
    exact_matches, jaccards = 0, []
    mono_exact, mono_total, poly_exact, poly_total = 0, 0, 0, 0

    for record in records:
        pid = record["pid"]
        visit_num = record["visit_num"]
        key = f"{pid}__v{visit_num}"

        gt_entry = gt.get(key)
        if gt_entry is None:
            continue

        gt_drugs = extract_gt(gt_entry)
        if not gt_drugs:
            results[key] = {"gt_empty": True}
            continue

        options = extract_all_options(record)
        ems = [opts == gt_drugs for opts in options]
        jacs = [jaccard(opts, gt_drugs) for opts in options]

        em = any(ems)
        jac = max(jacs)

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

        results[key] = {
            "pid": pid,
            "cohort": record.get("cohort", ""),
            "visit_num": visit_num,
            "exact_match": em,
            "jaccard": jac,
            "options": [{"predicted": sorted(o), "exact_match": e, "jaccard": j}
                        for o, e, j in zip(options, ems, jacs)],
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
    parser.add_argument("--predictions", type=str, required=True, help="Path to predictions JSON file")
    parser.add_argument("--cohort", type=str, choices=["csv", "pdf"], default=None, help="Filter GT by cohort")
    args = parser.parse_args()

    with open(args.predictions, encoding="utf-8") as f:
        records = json.load(f)

    # Infer visit numbers from records to load only relevant GT
    visit_nums = set(r["visit_num"] for r in records)
    gt = {}
    for v in visit_nums:
        gt.update(load_ground_truth(visit_num=v, cohort=args.cohort))

    results = grade(records, gt)

    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.predictions))[0]
    out_path = os.path.join(_OUTPUT_DIR, f"eval_{base}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    s = results["summary"]
    print(f"\n{'='*60}")
    print(f"EVALUATION RESULTS  (top-3 accuracy)")
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
