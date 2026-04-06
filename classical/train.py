"""Train XGBoost drug prediction baseline.

Loads extracted features from classical/outputs/features_v*.json,
loads GT labels from HuggingFace, builds feature matrix, runs
5-fold patient-stratified CV with per-drug hyperparameter search.

Saves:
  classical/outputs/probs.json     — raw per-drug probabilities for all patients
  classical/outputs/predictions.json — formatted for scripts/evaluate.py

Usage:
    conda run -n global_llm python classical/train.py
    conda run -n global_llm python classical/train.py --visits 1 2 3 4
"""

import argparse
import json
import os
import sys
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.model_selection import StratifiedKFold, RandomizedSearchCV
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from classical.data import (
    DRUGS, load_features as _load_features, load_labels,
    build_label_matrix, patient_strata, _OUTPUT_DIR,
)

FEATURE_COLS = [
    "Age_Years", "Gender", "OnsetAgeYears", "SeizureFreq",
    "CognitivePriority", "SeizureType",
    "drug_clobazam", "drug_clonazepam", "drug_valproate", "drug_ethosuximide",
    "drug_levetiracetam", "drug_lamotrigine", "drug_phenobarbital",
    "drug_phenytoin", "drug_topiramate", "drug_carbamazepine",
]


def load_features(visits: list[int]) -> pd.DataFrame:
    return _load_features(visits, FEATURE_COLS)

FAST_XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 3,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 1,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
}

XGBPARAMS = {
    "n_estimators":      [100, 200, 300],
    "max_depth":         [2, 3, 4],
    "learning_rate":     [0.05, 0.1],
    "subsample":         [0.8, 1.0],
    "colsample_bytree":  [0.8, 1.0],
    "min_child_weight":  [1, 5],
    "reg_alpha":         [0.0, 0.5],
    "reg_lambda":        [1.0, 2.0],
}


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def hypersearch_drug(
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    seed: int,
    *,
    search_iter: int,
    search_cv: int,
    no_search: bool,
    min_pos_for_search: int,
) -> XGBClassifier:
    positives = int(y_tr.sum())

    base = XGBClassifier(
        eval_metric="logloss",
        random_state=seed,
        n_jobs=1,
        tree_method="hist",
        verbosity=0,
        base_score=0.5,
        **FAST_XGB_PARAMS,
    )
    if len(np.unique(y_tr)) < 2:
        base.fit(X_tr, y_tr)
        return base

    if no_search or positives < min_pos_for_search:
        base.fit(X_tr, y_tr)
        return base

    search = RandomizedSearchCV(
        base,
        XGBPARAMS,
        n_iter=search_iter,
        scoring="f1_macro",
        cv=search_cv,
        random_state=seed,
        n_jobs=1,
        refit=True,
    )
    search.fit(X_tr, y_tr)
    return search.best_estimator_


# ---------------------------------------------------------------------------
# Per-drug training (module-level for joblib pickling)
# ---------------------------------------------------------------------------

def _train_one_drug(j, drug, X_train, Y_train, X_test, seed, search_iter, search_cv, no_search, min_pos_for_search):
    y_tr = Y_train[:, j]
    clf = hypersearch_drug(
        X_train, y_tr, seed=seed,
        search_iter=search_iter, search_cv=search_cv,
        no_search=no_search, min_pos_for_search=min_pos_for_search,
    )
    proba = clf.predict_proba(X_test)
    p1 = proba[:, 1] if proba.shape[1] == 2 else np.zeros(X_test.shape[0])
    return j, drug, p1


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_top3(probs_records: list[dict]) -> list[dict]:
    """Rank all 2^10 drug combinations by joint log-prob, return top 3 as options."""
    n = len(DRUGS)
    # Precompute (1024, 10) binary matrix — row i = binary repr of i
    masks = np.arange(1 << n)
    binary = ((masks[:, None] >> np.arange(n)[None, :]) & 1).astype(np.float32)  # (1024, 10)

    out = []
    for rec in probs_records:
        p = np.array([rec["probs"][d] for d in DRUGS], dtype=np.float64)
        p = np.clip(p, 1e-9, 1 - 1e-9)
        log_p = np.log(p)
        log_1mp = np.log(1 - p)

        scores = binary @ log_p + (1 - binary) @ log_1mp  # (1024,)
        top3_idx = np.argsort(scores)[-3:][::-1]

        options = {}
        for rank, idx in enumerate(top3_idx, 1):
            drugs = {DRUGS[i]: "start" for i in range(n) if masks[idx] & (1 << i)}
            options[f"option_{rank}"] = {"drugs": drugs}

        out.append({
            "pid": rec["pid"],
            "cohort": rec["cohort"],
            "visit_num": rec["visit_num"],
            "trace": {"final_regimen": options},
        })
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--visits", type=int, nargs="+", default=[1, 2, 3, 4])
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--jobs", type=int, default=4,
                        help="Parallel jobs across drugs. Use a small number to avoid CPU thrash.")
    parser.add_argument("--search-iter", type=int, default=25,
                        help="RandomizedSearchCV iterations per drug/fold.")
    parser.add_argument("--search-cv", type=int, default=2,
                        help="Inner CV folds for hyperparameter search.")
    parser.add_argument("--min-pos-for-search", type=int, default=20,
                        help="Skip hyperparameter search for rare drugs with fewer than this many positives.")
    parser.add_argument("--no-search", action="store_true",
                        help="Disable per-drug hyperparameter search and use fast fixed XGBoost params.")
    parser.add_argument("--cross-cohort", action="store_true",
                        help="Train on CSV cohort, test on PDF cohort (cross-cohort generalization).")
    parser.add_argument("--v1-split", action="store_true",
                        help="Train on 50% of V1 patients, test on other 50% of V1 patients.")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"XGBoost Classical Baseline")
    print(f"Visits: {args.visits}  |  Folds: {args.folds}  |  Seed: {args.seed}")
    print(f"Jobs: {args.jobs}  |  Search iters: {args.search_iter}  |  Search CV: {args.search_cv}")
    if args.no_search:
        print("Hyperparameter search: OFF (fast fixed params)")
    else:
        print(f"Skip search for drugs with < {args.min_pos_for_search} positives in training fold")
    print(f"{'='*60}\n")

    # Load data
    print("Loading features...")
    df = load_features(args.visits)
    print(f"  {len(df)} (patient, visit) pairs from {df['pid'].nunique()} patients")

    print("Loading GT labels from HuggingFace...")
    labels = load_labels()

    X = df[FEATURE_COLS].values.astype(np.float32)
    # Impute missing values with column means
    col_means = np.nanmean(X, axis=0)
    for c in range(X.shape[1]):
        mask = np.isnan(X[:, c])
        X[mask, c] = col_means[c]
    Y = build_label_matrix(df, labels)
    pids = df["pid"].values

    print(f"  Feature matrix: {X.shape}  |  Label matrix: {Y.shape}")
    print(f"  Drug prevalence: { {d: f'{Y[:,i].mean():.2f}' for i,d in enumerate(DRUGS)} }")

    probs_all = {}

    if args.v1_split:
        # Train on 50% of V1 patients, test on other 50% of V1 patients
        df_v1 = df[df["visit_num"] == 1].reset_index(drop=True)
        X_v1 = X[df["visit_num"].values == 1]
        Y_v1 = Y[df["visit_num"].values == 1]
        pids_v1 = df_v1["pid"].values
        unique_v1_pids = df_v1["pid"].unique()
        rng = np.random.default_rng(args.seed)
        rng.shuffle(unique_v1_pids)
        split = len(unique_v1_pids) // 2
        train_pids = set(unique_v1_pids[:split])
        test_pids = set(unique_v1_pids[split:])
        train_mask = np.array([p in train_pids for p in pids_v1])
        test_mask = np.array([p in test_pids for p in pids_v1])
        X_train, Y_train = X_v1[train_mask], Y_v1[train_mask]
        X_test = X_v1[test_mask]
        df_test = df_v1[test_mask].reset_index(drop=True)
        print(f"\nV1 split  —  train: {train_mask.sum()}, test: {test_mask.sum()}")

        results = Parallel(n_jobs=args.jobs)(
            delayed(_train_one_drug)(
                j, drug, X_train, Y_train, X_test,
                seed=args.seed + j,
                search_iter=args.search_iter,
                search_cv=args.search_cv,
                no_search=args.no_search,
                min_pos_for_search=args.min_pos_for_search,
            )
            for j, drug in enumerate(DRUGS)
        )

        fold_probs = np.zeros((test_mask.sum(), len(DRUGS)), dtype=np.float32)
        y_test = Y_v1[test_mask]
        for j, drug, p1 in results:
            fold_probs[:, j] = p1
            if len(np.unique(Y_train[:, j])) > 1 and len(np.unique(y_test[:, j])) > 1:
                auc = roc_auc_score(y_test[:, j], p1)
                print(f"  {drug:20s}  roc_auc={auc:.3f}")
            else:
                print(f"  {drug:20s}  (single class)")

        for i, row in df_test.iterrows():
            key = (row["pid"], int(row["visit_num"]))
            probs_all[key] = {
                "pid": row["pid"], "cohort": row["cohort"],
                "visit_num": int(row["visit_num"]), "fold": 0,
                "probs": {drug: float(fold_probs[i, j]) for j, drug in enumerate(DRUGS)},
            }

    elif args.cross_cohort:
        # Train on CSV, test on PDF — cross-cohort generalization
        cohorts = df["cohort"].values
        train_mask = cohorts == "csv"
        test_mask = cohorts == "pdf"
        X_train, Y_train = X[train_mask], Y[train_mask]
        X_test = X[test_mask]
        df_test = df[test_mask].reset_index(drop=True)
        print(f"\nCross-cohort  —  train(CSV): {train_mask.sum()}, test(PDF): {test_mask.sum()}")

        results = Parallel(n_jobs=args.jobs)(
            delayed(_train_one_drug)(
                j, drug, X_train, Y_train, X_test,
                seed=args.seed + j,
                search_iter=args.search_iter,
                search_cv=args.search_cv,
                no_search=args.no_search,
                min_pos_for_search=args.min_pos_for_search,
            )
            for j, drug in enumerate(DRUGS)
        )

        fold_probs = np.zeros((test_mask.sum(), len(DRUGS)), dtype=np.float32)
        y_test = Y[test_mask]
        for j, drug, p1 in results:
            fold_probs[:, j] = p1
            if len(np.unique(Y[train_mask][:, j])) > 1 and len(np.unique(y_test[:, j])) > 1:
                print(f"  {drug:20s}  roc_auc={roc_auc_score(y_test[:, j], p1):.3f}")

        for i, row in df_test.iterrows():
            key = (row["pid"], int(row["visit_num"]))
            probs_all[key] = {
                "pid": row["pid"], "cohort": row["cohort"],
                "visit_num": int(row["visit_num"]), "fold": 0,
                "probs": {drug: float(fold_probs[i, j]) for j, drug in enumerate(DRUGS)},
            }

    else:
        # Patient-level stratification + 5-fold CV
        strata = patient_strata(df, labels)
        unique_pids = df["pid"].unique()
        pid_strata = np.array([strata[p] for p in unique_pids])
        skf = StratifiedKFold(n_splits=args.folds, shuffle=True, random_state=args.seed)

        for fold, (train_idx, test_idx) in enumerate(skf.split(unique_pids, pid_strata)):
            train_pids = set(unique_pids[train_idx])
            test_pids = set(unique_pids[test_idx])

            train_mask = np.array([p in train_pids for p in pids])
            test_mask = np.array([p in test_pids for p in pids])

            X_train, Y_train = X[train_mask], Y[train_mask]
            X_test = X[test_mask]
            df_test = df[test_mask].reset_index(drop=True)

            print(f"\nFold {fold+1}/{args.folds}  —  train: {train_mask.sum()}, test: {test_mask.sum()}")

            results = Parallel(n_jobs=args.jobs)(
            delayed(_train_one_drug)(
                j, drug, X_train, Y_train, X_test,
                seed=args.seed + fold * 100 + j,
                search_iter=args.search_iter,
                search_cv=args.search_cv,
                no_search=args.no_search,
                min_pos_for_search=args.min_pos_for_search,
            )
                for j, drug in enumerate(DRUGS)
            )

            fold_probs = np.zeros((test_mask.sum(), len(DRUGS)), dtype=np.float32)
            y_test = Y[test_mask]
            for j, drug, p1 in results:
                fold_probs[:, j] = p1
                y_tr = Y_train[:, j]
                if len(np.unique(y_tr)) > 1 and len(np.unique(y_test[:, j])) > 1:
                    auc = roc_auc_score(y_test[:, j], p1)
                    print(f"  {drug:20s}  roc_auc={auc:.3f}")
                else:
                    print(f"  {drug:20s}  (single class in train or test)")

            # Store results
            for i, row in df_test.iterrows():
                key = (row["pid"], int(row["visit_num"]))
                probs_all[key] = {
                    "pid": row["pid"],
                    "cohort": row["cohort"],
                    "visit_num": int(row["visit_num"]),
                    "fold": fold,
                    "probs": {drug: float(fold_probs[i, j]) for j, drug in enumerate(DRUGS)},
                }

    # Save outputs
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    probs_list = sorted(probs_all.values(), key=lambda x: (x["pid"], x["visit_num"]))
    probs_path = os.path.join(_OUTPUT_DIR, "probs.json")
    with open(probs_path, "w") as f:
        json.dump(probs_list, f, indent=2)
    print(f"\nSaved raw probabilities → {probs_path}")

    preds_list = format_top3(probs_list)
    preds_path = os.path.join(_OUTPUT_DIR, "predictions.json")
    with open(preds_path, "w") as f:
        json.dump(preds_list, f, indent=2)
    print(f"Saved predictions (top-3 log-prob ranking) → {preds_path}")
    print(f"\nDone. {len(probs_list)} records saved.\n")


if __name__ == "__main__":
    main()
