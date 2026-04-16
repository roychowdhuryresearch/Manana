"""MIMIC stratified (random) train/eval split.

Samples 150 train + 60 eval patients from the 1,326 usable MIMIC cases.
Split is by patient (no leakage), seed-fixed for reproducibility.
"""

from __future__ import annotations
import random
from mimic.loader import load_mimic_cases, load_mimic_ground_truth


def mimic_split(
    n_train: int = 150,
    n_eval: int = 60,
    seed: int = 42,
) -> dict:
    cases = load_mimic_cases()
    gt_data = load_mimic_ground_truth()

    # all patient ids (each appears exactly once)
    all_pids = [c.patient_id for c in cases]

    rng = random.Random(seed)
    shuffled = all_pids[:]
    rng.shuffle(shuffled)

    train_pids = set(shuffled[:n_train])
    eval_pids = set(shuffled[n_train:n_train + n_eval])

    train_cases = [c for c in cases if c.patient_id in train_pids]
    eval_cases = [c for c in cases if c.patient_id in eval_pids]

    rng.shuffle(train_cases)
    rng.shuffle(eval_cases)

    train_mono = sum(1 for c in train_cases if len(gt_data[f"{c.patient_id}__v1"]["prescribed"]) == 1)
    eval_mono = sum(1 for c in eval_cases if len(gt_data[f"{c.patient_id}__v1"]["prescribed"]) == 1)

    return {
        "train_cases": train_cases,
        "eval_cases": eval_cases,
        "gt_data": gt_data,
        "stats": {
            "train_patients": len(train_cases),
            "train_mono": train_mono,
            "train_poly": len(train_cases) - train_mono,
            "eval_patients": len(eval_cases),
            "eval_mono": eval_mono,
            "eval_poly": len(eval_cases) - eval_mono,
        },
    }
