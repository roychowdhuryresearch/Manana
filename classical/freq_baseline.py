"""Frequency-table (Naive Bayes) baseline for drug prediction.

Builds a lookup table: P(drug | SeizureType, SeizureFreq, CognitivePriority)
from training folds, predicts on test folds via log-prob top-3 ranking.

Variants:
  --mode unigram   — P(drug)
  --mode bigram    — P(drug | SeizureType)
  --mode trigram   — P(drug | SeizureType, SeizureFreq)        [default]
  --mode fourgram  — P(drug | SeizureType, SeizureFreq, CognitivePriority)

Also prints the raw frequency table for inspection.

Usage:
    conda run -n global_llm python classical/freq_baseline.py
    conda run -n global_llm python classical/freq_baseline.py --mode bigram
    conda run -n global_llm python classical/freq_baseline.py --print-table
"""

import argparse
import json
import os
import sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from classical.data import (
    DRUGS, load_features as _load_features, load_labels,
    build_label_matrix, patient_strata, _OUTPUT_DIR,
)

# Conditioner feature sets per mode
CONDITIONERS = {
    "unigram":  [],
    "bigram":   ["SeizureType"],
    "trigram":  ["SeizureType", "SeizureFreq"],
    "fourgram": ["SeizureType", "SeizureFreq", "CognitivePriority"],
}

# Discrete values each conditioner can take (including -1 = unknown)
FEATURE_VALUES = {
    "SeizureType":      [-1, 0, 1, 2],
    "SeizureFreq":      [-1, 0, 1, 2, 3, 4],
    "CognitivePriority": [0, 1, 2],
}

FEATURE_COLS = [
    "Age_Years", "Gender", "OnsetAgeYears", "SeizureFreq",
    "CognitivePriority", "SeizureType",
]


def load_features(visits: list[int]) -> pd.DataFrame:
    return _load_features(visits, FEATURE_COLS)


# ---------------------------------------------------------------------------
# Frequency table
# ---------------------------------------------------------------------------

def get_key(row: pd.Series, conditioners: list) -> tuple:
    """Get the lookup key for a patient row."""
    if not conditioners:
        return ()
    key = []
    for c in conditioners:
        v = row[c]
        if pd.isna(v):
            key.append(-1)
        else:
            key.append(int(v))
    return tuple(key)


def build_freq_table(df: pd.DataFrame, Y: np.ndarray, conditioners: list) -> dict:
    """Build frequency table from training data.

    Returns dict: key -> np.array of shape (n_drugs,) with P(drug=1 | key)
    Also returns marginal as fallback for unseen keys.
    """
    counts = {}   # key -> [pos_count_per_drug]
    totals = {}   # key -> n_samples

    for i, (_, row) in enumerate(df.iterrows()):
        key = get_key(row, conditioners)
        if key not in counts:
            counts[key] = np.zeros(len(DRUGS))
            totals[key] = 0
        counts[key] += Y[i]
        totals[key] += 1

    table = {}
    for key in counts:
        n = totals[key]
        # Laplace smoothing: add 0.5 to avoid 0/1 probabilities
        table[key] = (counts[key] + 0.5) / (n + 1.0)

    # Marginal fallback
    total_pos = Y.sum(axis=0)
    n_total = len(Y)
    marginal = (total_pos + 0.5) / (n_total + 1.0)

    return table, marginal


def predict_from_table(df: pd.DataFrame, table: dict, marginal: np.ndarray,
                       conditioners: list) -> list:
    """For each patient, look up probabilities and return top-3 drug combos."""
    results = []
    n = len(DRUGS)
    masks = np.arange(1 << n, dtype=np.int32)
    binary = ((masks[:, None] >> np.arange(n)[None, :]) & 1).astype(np.float32)

    for _, row in df.iterrows():
        key = get_key(row, conditioners)
        p = table.get(key, marginal)
        p = np.clip(p, 1e-9, 1 - 1e-9)

        log_p = np.log(p)
        log_1mp = np.log(1 - p)
        scores = binary @ log_p + (1 - binary) @ log_1mp

        top3_idx = np.argsort(scores)[-3:][::-1]
        preds = []
        for idx in top3_idx:
            mask = masks[idx]
            drug_set = [DRUGS[b] for b in range(n) if (mask >> b) & 1]
            preds.append(sorted(drug_set))

        results.append({
            "pid": row["pid"],
            "cohort": row["cohort"],
            "visit_num": int(row["visit_num"]),
            "top3": preds,
        })
    return results


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def exact_match(pred_set: list, gt: list) -> bool:
    return sorted(pred_set) == sorted(gt)


def jaccard(pred_set: list, gt: list) -> float:
    a, b = set(pred_set), set(gt)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def evaluate(predictions: list, labels: dict, count_empty_gt: bool = False) -> dict:
    """Evaluate predictions against GT.

    If count_empty_gt=True, patients with no GT count as wrong (denom includes them).
    If count_empty_gt=False (default), patients with no GT are skipped.
    """
    em_any = 0
    em_top1 = 0
    jaccards = []
    n = 0

    for rec in predictions:
        key = f"{rec['pid']}__v{rec['visit_num']}"
        gt = sorted(labels.get(key, []))
        if not gt:
            if count_empty_gt:
                n += 1
                jaccards.append(0.0)
            continue
        top3 = rec["top3"]
        n += 1
        if top3 and exact_match(top3[0], gt):
            em_top1 += 1
        if any(exact_match(t, gt) for t in top3):
            em_any += 1
        best_jac = max(jaccard(t, gt) for t in top3) if top3 else 0.0
        jaccards.append(best_jac)

    return {
        "n": n,
        "em_top1": em_top1 / n if n else 0,
        "em_any3": em_any / n if n else 0,
        "jaccard": sum(jaccards) / n if n else 0,
    }


# ---------------------------------------------------------------------------
# Print table
# ---------------------------------------------------------------------------

def print_freq_table(table: dict, conditioners: list):
    """Pretty-print the frequency table."""
    drug_abbrev = [d[:5] for d in DRUGS]
    header = " | ".join(f"{c[:8]:>8}" for c in conditioners) + " || " + \
             " ".join(f"{a:>6}" for a in drug_abbrev) + "  | n_samples"
    print(header)
    print("-" * len(header))

    # Sort keys for readability
    for key in sorted(table.keys()):
        cond_str = " | ".join(f"{int(k):>8}" for k in key) if key else "(global)"
        prob_str = " ".join(f"{p:6.3f}" for p in table[key])
        print(f"{cond_str} || {prob_str}")


def run_cv(df: pd.DataFrame, Y: np.ndarray, labels: dict,
           conditioners: list, n_folds: int = 5, seed: int = 42) -> dict:
    strata = patient_strata(df, labels)
    pids = df["pid"].unique()
    pid_strata_arr = np.array([strata[p] for p in pids])

    from sklearn.model_selection import StratifiedKFold
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)

    all_preds = []
    fold_tables = []
    fold_metrics = []

    for fold, (tr_idx, te_idx) in enumerate(skf.split(pids, pid_strata_arr)):
        tr_pids = set(pids[tr_idx])
        te_pids = set(pids[te_idx])

        tr_mask = df["pid"].isin(tr_pids).values
        te_mask = df["pid"].isin(te_pids).values

        df_tr = df[tr_mask].reset_index(drop=True)
        df_te = df[te_mask].reset_index(drop=True)
        Y_tr = Y[tr_mask]

        table, marginal = build_freq_table(df_tr, Y_tr, conditioners)
        fold_tables.append(table)
        preds = predict_from_table(df_te, table, marginal, conditioners)
        all_preds.extend(preds)
        fold_metrics.append(evaluate(preds, labels))

    metrics = evaluate(all_preds, labels)
    return metrics, fold_tables, fold_metrics, all_preds


def evaluate_by_visit(predictions: list, labels: dict) -> dict:
    """Break down EM@1 by visit number."""
    by_visit = {}
    for rec in predictions:
        v = rec["visit_num"]
        by_visit.setdefault(v, []).append(rec)
    return {v: evaluate(recs, labels) for v, recs in sorted(by_visit.items())}


def run_longitudinal(df: pd.DataFrame, Y: np.ndarray, labels: dict,
                     conditioners: list) -> dict:
    """Option B: train on visits 1..N-1, test on visit N.
    v1 uses within-v1 5-fold CV (no prior data available).
    """
    results = {}

    # v1: within-v1 CV
    mask_v1 = df["visit_num"] == 1
    df_v1 = df[mask_v1].reset_index(drop=True)
    Y_v1 = Y[mask_v1]
    pids_v1 = df_v1["pid"].unique()
    strata_v1 = patient_strata(df_v1, labels)
    pid_strata_v1 = np.array([strata_v1[p] for p in pids_v1])

    from sklearn.model_selection import StratifiedKFold
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    v1_preds = []
    for tr_idx, te_idx in skf.split(pids_v1, pid_strata_v1):
        tr_pids = set(pids_v1[tr_idx])
        te_pids = set(pids_v1[te_idx])
        tr_mask = df_v1["pid"].isin(tr_pids).values
        te_mask = df_v1["pid"].isin(te_pids).values
        table, marginal = build_freq_table(df_v1[tr_mask].reset_index(drop=True),
                                           Y_v1[tr_mask], conditioners)
        v1_preds.extend(predict_from_table(df_v1[te_mask].reset_index(drop=True),
                                           table, marginal, conditioners))
    results[1] = evaluate(v1_preds, labels)

    # v2, v3, v4: train on all prior visits, test on current
    for v in [2, 3, 4]:
        train_mask = df["visit_num"] < v
        test_mask = df["visit_num"] == v
        if test_mask.sum() == 0:
            continue
        df_tr = df[train_mask].reset_index(drop=True)
        df_te = df[test_mask].reset_index(drop=True)
        Y_tr = Y[train_mask]
        table, marginal = build_freq_table(df_tr, Y_tr, conditioners)
        preds = predict_from_table(df_te, table, marginal, conditioners)
        results[v] = evaluate(preds, labels)

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def evaluate_by_cohort_visit(predictions: list, labels: dict) -> dict:
    """Break down by (cohort, visit) → metrics dict.
    CSV patients: empty GT counts as wrong (divide by all patients).
    PDF patients: empty GT skipped (divide by gradeable only).
    """
    buckets = {}
    for rec in predictions:
        key = (rec["cohort"], rec["visit_num"])
        buckets.setdefault(key, []).append(rec)
    result = {}
    for k, recs in sorted(buckets.items()):
        count_empty = (k[0] == "csv")
        result[k] = evaluate(recs, labels, count_empty_gt=count_empty)
    return result


def to_standard_format(predictions: list) -> list:
    """Convert to the format expected by scripts/evaluate.py."""
    out = []
    for rec in predictions:
        options = {}
        for rank, drug_list in enumerate(rec["top3"], 1):
            options[f"option_{rank}"] = {
                "drugs": {d: "start" for d in drug_list},
            }
        out.append({
            "pid": rec["pid"],
            "cohort": rec["cohort"],
            "visit_num": rec["visit_num"],
            "trace": {"final_regimen": options},
        })
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["unigram", "bigram", "trigram", "fourgram"],
                        default="bigram")
    parser.add_argument("--visits", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--print-table", action="store_true",
                        help="Print frequency table from full dataset (no CV)")
    parser.add_argument("--save-table", action="store_true",
                        help="Save frequency table as CSV to classical/outputs/freq_table_{mode}.csv")
    parser.add_argument("--all-modes", action="store_true",
                        help="Run all 4 modes and compare")
    args = parser.parse_args()

    print("Loading data...")
    df = load_features(args.visits)
    labels = load_labels()

    # Filter to evaluation set:
    #   CSV (Cohort A): all 332 patients, denominator always 332
    #   PDF (Cohort B): 343 fixed PIDs (present in all V1-V3)
    from datasets import load_dataset as _load_ds
    from scripts.evaluate import get_fixed_pids
    _ds = _load_ds("kartiksharma4/consilium", split="train")
    all_csv = {r["pid"] for r in _ds if r["cohort"] == "csv"}
    fixed_pdf = get_fixed_pids("pdf")
    eval_pids = all_csv | fixed_pdf
    before = len(df)
    df = df[df["pid"].isin(eval_pids)].reset_index(drop=True)
    print(f"  Eval PIDs: {len(all_csv)} csv + {len(fixed_pdf)} pdf = {len(eval_pids)}")
    print(f"  Filtered {before} → {len(df)} rows, {df['pid'].nunique()} patients")

    Y = build_label_matrix(df, labels)
    print(f"  {len(df)} rows, {df['pid'].nunique()} patients")

    if args.print_table or args.save_table:
        conditioners = CONDITIONERS[args.mode]
        table, marginal = build_freq_table(df, Y, conditioners)

        if args.print_table:
            print(f"\nFrequency table — {args.mode} (conditioners: {conditioners})")
            print(f"Built from full dataset ({len(df)} rows)\n")
            print_freq_table(table, conditioners)
            print(f"\nMarginal (fallback): {' '.join(f'{p:.3f}' for p in marginal)}")
            print(f"Drugs:               {' '.join(d[:5] for d in DRUGS)}")

        if args.save_table:
            LABEL_MEANINGS = {
                "SeizureType":       {-1: "unknown", 0: "focal", 1: "generalized_non_motor", 2: "generalized_motor"},
                "SeizureFreq":       {-1: "unknown", 0: "seizure_free", 1: "infrequent_lt1perMonth", 2: "monthly", 3: "weekly", 4: "daily"},
                "CognitivePriority": {0: "none", 1: "mild_moderate", 2: "severe"},
            }

            rows = []
            for key in sorted(table.keys()):
                row = {}
                for i, c in enumerate(conditioners):
                    v = int(key[i])
                    row[c] = v
                    row[f"{c}_label"] = LABEL_MEANINGS[c].get(v, str(v))
                for j, drug in enumerate(DRUGS):
                    row[f"P_{drug}"] = round(float(table[key][j]), 4)
                rows.append(row)

            # Marginal fallback row
            marginal_row = {}
            for c in conditioners:
                marginal_row[c] = "marginal"
                marginal_row[f"{c}_label"] = "fallback_for_unseen_cells"
            for j, drug in enumerate(DRUGS):
                marginal_row[f"P_{drug}"] = round(float(marginal[j]), 4)
            rows.append(marginal_row)

            out_path = os.path.join(_OUTPUT_DIR, f"freq_table_{args.mode}.csv")
            pd.DataFrame(rows).to_csv(out_path, index=False)
            print(f"Saved → {out_path}")
        return

    if args.all_modes:
        modes = ["unigram", "bigram", "trigram", "fourgram"]
    else:
        modes = [args.mode]

    for mode in modes:
        conditioners = CONDITIONERS[mode]
        metrics, _, fold_metrics, all_preds = run_cv(df, Y, labels, conditioners, n_folds=args.folds)

        # Per-cohort, per-visit breakdown
        cv_breakdown = evaluate_by_cohort_visit(all_preds, labels)

        print(f"\n{'='*60}")
        print(f"  FREQ TABLE — {mode}  |  {args.folds}-fold patient-stratified CV")
        print(f"  Overall: n={metrics['n']}  EM@3={metrics['em_any3']:.1%}  Jac={metrics['jaccard']:.3f}")
        print(f"{'='*60}")

        # Print in the same layout as paper tables
        cohort_map = {"csv": "A", "pdf": "B"}
        for cohort in ["csv", "pdf"]:
            label = cohort_map[cohort]
            print(f"\n  Cohort {label}:")
            for v in args.visits:
                m = cv_breakdown.get((cohort, v))
                if m:
                    print(f"    V{v}: n={m['n']:3d}  EM@3={m['em_any3']:.1%}  Jac={m['jaccard']:.3f}")

        # Mono/poly breakdown
        mono_preds = [r for r in all_preds
                      if len(labels.get(f"{r['pid']}__v{r['visit_num']}", [])) == 1]
        poly_preds = [r for r in all_preds
                      if len(labels.get(f"{r['pid']}__v{r['visit_num']}", [])) > 1]

        print(f"\n  Monotherapy (n={len(mono_preds)}):")
        mono_by_cv = evaluate_by_cohort_visit(mono_preds, labels)
        for cohort in ["csv", "pdf"]:
            label = cohort_map[cohort]
            vals = []
            for v in args.visits:
                m = mono_by_cv.get((cohort, v))
                vals.append(f"V{v}={m['em_any3']:.1%}" if m else f"V{v}=---")
            print(f"    Cohort {label}: {', '.join(vals)}")

        print(f"\n  Polytherapy (n={len(poly_preds)}):")
        poly_by_cv = evaluate_by_cohort_visit(poly_preds, labels)
        for cohort in ["csv", "pdf"]:
            label = cohort_map[cohort]
            vals = []
            for v in args.visits:
                m = poly_by_cv.get((cohort, v))
                vals.append(f"V{v}={m['em_any3']:.1%}" if m else f"V{v}=---")
            print(f"    Cohort {label}: {', '.join(vals)}")

        # Save standard-format predictions
        std_preds = to_standard_format(all_preds)
        out_path = os.path.join(_OUTPUT_DIR, f"freq_predictions_{mode}.json")
        with open(out_path, "w") as f:
            json.dump(std_preds, f, indent=2)
        print(f"\n  Saved → {out_path}")

    print()


if __name__ == "__main__":
    main()
