"""Inter-agent disagreement analysis for Consilium predictions.

Computes disagreement signals from multi-agent traces and tests whether
disagreement predicts prediction errors. Produces:
  1. Per-patient disagreement scores
  2. AUROC: does disagreement predict exact-match failure?
  3. Coverage-accuracy curves: accuracy when abstaining on high-disagreement cases
  4. Summary statistics by disagreement bucket

Usage:
    uv run python -m consilium.analysis.disagreement \
        --predictions outputs/v2/consilium_v2_openai.gptoss120b1:0_v1_d0.json \
        --visit 1 --cohort A
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from consilium.loader import load_ground_truth

DRUG_COLUMNS = [
    "carbamazepine", "clobazam", "clonazepam", "ethosuximide",
    "lamotrigine", "levetiracetam", "phenobarbital", "phenytoin",
    "topiramate", "valproate",
]


# ---------------------------------------------------------------------------
# Drug extraction helpers
# ---------------------------------------------------------------------------

def drugs_from_option(option: dict) -> set[str]:
    """Extract active drugs (continue/start) from a regimen option."""
    drugs = option.get("drugs", {})
    if isinstance(drugs, list):
        return set(d["drug"].lower() for d in drugs if d.get("action") in ("continue", "start"))
    return set(drug.lower() for drug, action in drugs.items() if action in ("continue", "start"))


def extract_drug_mentions(text: str) -> set[str]:
    """Extract mentions of tracked drugs from free-text agent output."""
    text_lower = text.lower()
    found = set()
    for drug in DRUG_COLUMNS:
        if drug in text_lower:
            found.add(drug)
    # Common abbreviations
    abbrevs = {
        "cbz": "carbamazepine", "vpa": "valproate", "lev": "levetiracetam",
        "lam": "lamotrigine", "ltg": "lamotrigine", "pb": "phenobarbital",
        "phb": "phenobarbital", "pht": "phenytoin", "tpm": "topiramate",
        "clb": "clobazam", "czp": "clonazepam", "esm": "ethosuximide",
    }
    for abbr, canonical in abbrevs.items():
        if re.search(rf'\b{abbr}\b', text_lower):
            found.add(canonical)
    return found


# ---------------------------------------------------------------------------
# Disagreement metrics
# ---------------------------------------------------------------------------

def compute_disagreement(record: dict) -> dict:
    """Compute multiple disagreement signals for a single patient record.

    Returns a dict with:
      - option_diversity: Jaccard distance between the 3 regimen options
      - pharma_concerns: 1 if pharmacologist raised concerns, 0 otherwise
      - debate_rounds: number of debate rounds (0 = no debate triggered)
      - regimen_changed: 1 if final regimen differs from initial epi regimen
      - phase1_drug_spread: number of distinct drugs mentioned across phase1 agents
      - composite_score: weighted combination of above signals
    """
    # --- Option diversity: how different are the 3 options? ---
    final = record.get("final_regimen", {})
    options = []
    for key in ["option_1", "option_2", "option_3"]:
        if key in final:
            options.append(drugs_from_option(final[key]))

    option_diversity = 0.0
    if len(options) >= 2:
        pairwise_jaccards = []
        for i in range(len(options)):
            for j in range(i + 1, len(options)):
                a, b = options[i], options[j]
                if a or b:
                    pairwise_jaccards.append(1.0 - len(a & b) / len(a | b))
                else:
                    pairwise_jaccards.append(0.0)
        option_diversity = np.mean(pairwise_jaccards) if pairwise_jaccards else 0.0

    # --- Pharmacologist concerns ---
    pharm = record.get("pharmacologist", "")
    pharma_concerns = 0
    if isinstance(pharm, str):
        pharma_concerns = 1 if "concerns_remain" in pharm.lower().replace(" ", "_") else 0

    # --- Debate rounds ---
    debate = record.get("debate", [])
    debate_rounds = len(debate) if isinstance(debate, list) else 0

    # --- Regimen changed after debate ---
    epi = record.get("epileptologist", {})
    initial_drugs = set()
    if isinstance(epi, dict) and "regimen" in epi:
        initial_drugs = drugs_from_option(epi["regimen"].get("option_1", {}))
    final_drugs = drugs_from_option(final.get("option_1", {}))
    regimen_changed = 1 if initial_drugs != final_drugs else 0

    # --- Phase 1 drug spread ---
    phase1 = record.get("phase1", {})
    all_phase1_drugs = set()
    per_agent_drugs = {}
    for agent_name, agent_output in phase1.items():
        if isinstance(agent_output, str):
            mentioned = extract_drug_mentions(agent_output)
            per_agent_drugs[agent_name] = mentioned
            all_phase1_drugs.update(mentioned)
    phase1_drug_spread = len(all_phase1_drugs)

    # --- Composite score ---
    # Weighted combination normalized to [0, 1]
    composite = (
        0.35 * option_diversity +
        0.25 * pharma_concerns +
        0.15 * min(debate_rounds / 2.0, 1.0) +
        0.15 * regimen_changed +
        0.10 * min(phase1_drug_spread / 6.0, 1.0)
    )

    return {
        "option_diversity": round(option_diversity, 4),
        "pharma_concerns": pharma_concerns,
        "debate_rounds": debate_rounds,
        "regimen_changed": regimen_changed,
        "phase1_drug_spread": phase1_drug_spread,
        "composite_score": round(composite, 4),
        "predicted_drugs_opt1": sorted(final_drugs),
        "initial_drugs_opt1": sorted(initial_drugs),
    }


# ---------------------------------------------------------------------------
# Evaluation: does disagreement predict errors?
# ---------------------------------------------------------------------------

def compute_auroc(scores: list[float], labels: list[int]) -> float:
    """Compute AUROC for disagreement predicting errors.

    Higher score = more disagreement = predicted to be wrong.
    label=1 means the prediction was wrong (error).
    """
    pairs = sorted(zip(scores, labels), key=lambda x: x[0])
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5

    # Wilcoxon-Mann-Whitney
    tp, fp = 0, 0
    auc = 0.0
    prev_score = None
    for score, label in sorted(zip(scores, labels), key=lambda x: -x[0]):
        if label == 1:
            tp += 1
        else:
            auc += tp
            fp += 1
    return auc / (n_pos * n_neg) if (n_pos * n_neg) > 0 else 0.5


def coverage_accuracy_curve(scores: list[float], correct: list[bool], n_points: int = 20) -> list[dict]:
    """Compute accuracy at various coverage levels.

    Abstain on the highest-disagreement cases first.
    """
    # Sort by disagreement ascending (lowest disagreement first = most confident)
    paired = sorted(zip(scores, correct), key=lambda x: x[0])
    n = len(paired)
    curve = []
    for i in range(1, n_points + 1):
        coverage = i / n_points
        k = int(coverage * n)
        if k == 0:
            continue
        subset = paired[:k]
        acc = sum(c for _, c in subset) / len(subset)
        curve.append({
            "coverage": round(coverage, 2),
            "n_cases": k,
            "accuracy": round(acc, 4),
        })
    return curve


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Inter-agent disagreement analysis")
    parser.add_argument("--predictions", type=str, required=True)
    parser.add_argument("--visit", type=int, required=True)
    parser.add_argument("--cohort", type=str, choices=["A", "B"], default="A")
    args = parser.parse_args()

    # Load predictions
    with open(args.predictions, encoding="utf-8") as f:
        data = json.load(f)

    # Load ground truth
    gt = load_ground_truth(visit_num=args.visit, cohort=args.cohort)

    # Process each patient
    results = []
    scores = []
    errors = []  # 1 = wrong, 0 = correct

    for pid, record in data.items():
        # Compute disagreement
        disagreement = compute_disagreement(record)

        # Check correctness against GT
        gt_key = f"{pid}__v{args.visit}"
        gt_entry = gt.get(gt_key)

        if gt_entry is None:
            # Try without prefix number
            alt_key = None
            for k in gt.keys():
                if k.endswith(f"__v{args.visit}") and pid.split("_", 1)[-1] in k:
                    alt_key = k
                    break
            gt_entry = gt.get(alt_key) if alt_key else None

        if gt_entry is None:
            continue

        gt_drugs = set(d.lower() for d in gt_entry.get("prescribed", []))
        if not gt_drugs:
            continue

        # Check EM@3
        final = record.get("final_regimen", {})
        pred_options = []
        for key in ["option_1", "option_2", "option_3"]:
            if key in final:
                pred_options.append(drugs_from_option(final[key]))

        em = any(opts == gt_drugs for opts in pred_options)

        results.append({
            "pid": pid,
            "gt_drugs": sorted(gt_drugs),
            "exact_match": em,
            **disagreement,
        })
        scores.append(disagreement["composite_score"])
        errors.append(0 if em else 1)

    if not results:
        print("No results matched. Check patient ID format and GT keys.")
        return

    # --- Compute AUROC ---
    auroc = compute_auroc(scores, errors)

    # --- Coverage-accuracy curve ---
    correct = [r["exact_match"] for r in results]
    cov_acc = coverage_accuracy_curve(scores, correct)

    # --- Bucket analysis ---
    n = len(results)
    sorted_results = sorted(results, key=lambda r: r["composite_score"])
    tercile_size = n // 3
    buckets = {
        "low_disagreement": sorted_results[:tercile_size],
        "medium_disagreement": sorted_results[tercile_size:2*tercile_size],
        "high_disagreement": sorted_results[2*tercile_size:],
    }
    bucket_summary = {}
    for bname, brecs in buckets.items():
        if brecs:
            em_rate = sum(r["exact_match"] for r in brecs) / len(brecs)
            avg_score = np.mean([r["composite_score"] for r in brecs])
            bucket_summary[bname] = {
                "n": len(brecs),
                "exact_match_rate": round(em_rate, 4),
                "avg_composite_score": round(avg_score, 4),
            }

    # --- Summary stats ---
    n_correct = sum(correct)
    n_concerns = sum(r["pharma_concerns"] for r in results)
    n_debate = sum(1 for r in results if r["debate_rounds"] > 0)
    n_changed = sum(r["regimen_changed"] for r in results)

    summary = {
        "visit": args.visit,
        "cohort": args.cohort,
        "n_patients": n,
        "overall_em": round(n_correct / n, 4),
        "auroc_disagreement_predicts_error": round(auroc, 4),
        "pharma_concerns_rate": round(n_concerns / n, 4),
        "debate_triggered_rate": round(n_debate / n, 4),
        "regimen_changed_rate": round(n_changed / n, 4),
        "bucket_analysis": bucket_summary,
        "coverage_accuracy_curve": cov_acc,
    }

    # --- Print ---
    print(f"\n{'='*60}")
    print(f"DISAGREEMENT ANALYSIS — Visit {args.visit}, Cohort {args.cohort.upper()}")
    print(f"{'='*60}")
    print(f"  Patients:              {n}")
    print(f"  Overall EM@3:          {n_correct/n:.1%}")
    print(f"  AUROC (disagree→err):  {auroc:.3f}")
    print(f"  Pharma concerns rate:  {n_concerns/n:.1%}")
    print(f"  Debate triggered:      {n_debate/n:.1%}")
    print(f"  Regimen changed:       {n_changed/n:.1%}")
    print(f"\n  Bucket analysis (terciles by composite disagreement):")
    for bname, bstats in bucket_summary.items():
        print(f"    {bname:25s}  n={bstats['n']:3d}  EM={bstats['exact_match_rate']:.1%}  avg_score={bstats['avg_composite_score']:.3f}")
    print(f"\n  Coverage-accuracy curve:")
    for pt in cov_acc:
        print(f"    coverage={pt['coverage']:.0%}  n={pt['n_cases']:3d}  accuracy={pt['accuracy']:.1%}")

    # --- Save ---
    out_dir = os.path.join(_ROOT, "outputs", "analysis")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"disagreement_v{args.visit}_{args.cohort}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "per_patient": results}, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved → {out_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
