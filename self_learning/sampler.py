"""Stratified patient sampler for self-learning experiments.

Splits patients into train/eval ensuring both sets have a mix of:
- Simple (all monotherapy visits)
- Mixed (some mono, some poly)
- Poly-heavy (majority polytherapy visits)

Splits by PATIENT, not case — no patient appears in both sets.
"""

from __future__ import annotations
import random
from collections import defaultdict

from scripts.loader import load_cases, load_ground_truth


def stratified_split(
    cohort: str = "csv",
    n_train_patients: int = 50,
    n_eval_patients: int = 20,
    seed: int = 42,
    # Proportions within each set (simple, mixed, poly)
    train_mix: tuple[int, int, int] = (25, 15, 10),
    eval_mix: tuple[int, int, int] = (10, 6, 4),
) -> dict:
    """Create stratified train/eval split.

    Returns:
        {
            "train_cases": [...],
            "eval_cases": [...],
            "train_pids": [...],
            "eval_pids": [...],
            "gt_data": {...},
            "stats": {...},
        }
    """
    all_cases = load_cases(cohort=cohort)
    gt_data = load_ground_truth(cohort=cohort)

    # Group by patient
    patients = defaultdict(list)
    for case in all_cases:
        visit_num = int(case.current_visit.split("_")[1])
        gt_key = f"{case.patient_id}__v{visit_num}"
        gt_entry = gt_data.get(gt_key)
        if not gt_entry or not gt_entry["prescribed"]:
            continue
        is_poly = len(gt_entry["prescribed"]) > 1
        patients[case.patient_id].append({
            "case": case,
            "visit": visit_num,
            "prescribed": gt_entry["prescribed"],
            "is_poly": is_poly,
        })

    # Categorize patients
    simple, mixed, poly = [], [], []
    for pid, visits in patients.items():
        poly_count = sum(1 for v in visits if v["is_poly"])
        total = len(visits)
        if poly_count == 0:
            simple.append(pid)
        elif poly_count >= total / 2:
            poly.append(pid)
        else:
            mixed.append(pid)

    # Shuffle deterministically
    rng = random.Random(seed)
    rng.shuffle(simple)
    rng.shuffle(mixed)
    rng.shuffle(poly)

    # Split
    t_simple, t_mixed, t_poly = train_mix
    e_simple, e_mixed, e_poly = eval_mix

    train_pids = simple[:t_simple] + mixed[:t_mixed] + poly[:t_poly]
    eval_pids = (
        simple[t_simple:t_simple + e_simple]
        + mixed[t_mixed:t_mixed + e_mixed]
        + poly[t_poly:t_poly + e_poly]
    )

    # Shuffle the final lists so batches aren't grouped by type
    rng.shuffle(train_pids)
    rng.shuffle(eval_pids)

    train_cases = [v["case"] for pid in train_pids for v in patients[pid]]
    eval_cases = [v["case"] for pid in eval_pids for v in patients[pid]]

    # Shuffle cases so visits from the same patient are spread across batches
    rng.shuffle(train_cases)
    rng.shuffle(eval_cases)

    # Stats
    train_poly_n = sum(1 for pid in train_pids for v in patients[pid] if v["is_poly"])
    eval_poly_n = sum(1 for pid in eval_pids for v in patients[pid] if v["is_poly"])

    return {
        "train_cases": train_cases,
        "eval_cases": eval_cases,
        "train_pids": train_pids,
        "eval_pids": eval_pids,
        "gt_data": gt_data,
        "stats": {
            "total_patients": len(patients),
            "simple": len(simple),
            "mixed": len(mixed),
            "poly": len(poly),
            "train_patients": len(train_pids),
            "train_cases": len(train_cases),
            "train_poly": train_poly_n,
            "eval_patients": len(eval_pids),
            "eval_cases": len(eval_cases),
            "eval_poly": eval_poly_n,
        },
    }
