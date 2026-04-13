"""Evaluate R7 self-learning agents on held-out test patients.

Excludes the 70 patients used in the SL loop (50 train + 20 eval).
Evaluates on the remaining patients across cohort A (csv) and cohort B (pdf).

Produces numbers for Table 1 (EM@3 + Jaccard) and Table 2 (mono/poly breakdown).

Usage:
    uv run python self_learning/eval_test.py
"""

from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from scripts.loader import load_ground_truth
from self_learning.sampler import stratified_split

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_EVAL_DIR = os.path.join(_HERE, "multi", "outputs", "eval_full")

_FILES = {
    ("csv", 1): "sl_r7_openai_gpt-oss-120b_csv_v1_20260413_0936.json",
    ("csv", 2): "sl_r7_openai_gpt-oss-120b_csv_v2_20260413_0955.json",
    ("csv", 3): "sl_r7_openai_gpt-oss-120b_csv_v3_20260413_1010.json",
    ("pdf", 1): "sl_r7_openai_gpt-oss-120b_pdf_v1_20260413_0939.json",
    ("pdf", 2): "sl_r7_openai_gpt-oss-120b_pdf_v2_20260413_0958.json",
    ("pdf", 3): "sl_r7_openai_gpt-oss-120b_pdf_v3_20260413_1014.json",
}

# ---------------------------------------------------------------------------
# Drug extraction (mirrors scripts/evaluate.py)
# ---------------------------------------------------------------------------

def _drugs_from_option(option: dict) -> set[str]:
    drugs = option.get("drugs", {})
    if isinstance(drugs, list):
        return set(d["drug"].lower() for d in drugs if d.get("action") in ("continue", "start"))
    return set(drug.lower() for drug, action in drugs.items() if action in ("continue", "start"))


def extract_all_options(record: dict) -> list[set[str]]:
    trace = record.get("trace", {})
    source = trace.get("final_regimen", {}) if trace else record
    return [
        _drugs_from_option(source.get("option_1", {})),
        _drugs_from_option(source.get("option_2", {})),
        _drugs_from_option(source.get("option_3", {})),
    ]


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
    exact, jacs = 0, []
    mono_exact = mono_total = poly_exact = poly_total = 0
    skipped = 0

    for record in records:
        pid = record["pid"]
        visit_num = record["visit_num"]
        key = f"{pid}__v{visit_num}"

        gt_entry = gt.get(key)
        if gt_entry is None or not gt_entry.get("prescribed"):
            skipped += 1
            continue

        gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
        options = extract_all_options(record)

        em = any(opts == gt_drugs for opts in options)
        jac = max(jaccard(opts, gt_drugs) for opts in options)

        if em:
            exact += 1
        jacs.append(jac)

        is_poly = len(gt_drugs) > 1
        if is_poly:
            poly_total += 1
            if em:
                poly_exact += 1
        else:
            mono_total += 1
            if em:
                mono_exact += 1

    n = len(jacs)
    return {
        "n": n,
        "skipped": skipped,
        "em": exact / n if n else 0.0,
        "jac": sum(jacs) / n if n else 0.0,
        "mono_em": mono_exact / mono_total if mono_total else 0.0,
        "mono_n": mono_total,
        "poly_em": poly_exact / poly_total if poly_total else 0.0,
        "poly_n": poly_total,
        "mono_exact": mono_exact,
        "poly_exact": poly_exact,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Get the 70 excluded patient IDs (from CSV cohort SL loop)
    split = stratified_split(cohort="csv")
    excluded_pids = set(split["train_pids"]) | set(split["eval_pids"])
    print(f"Excluded pids (SL train+eval): {len(excluded_pids)}")
    print(f"  train: {len(split['train_pids'])}, eval: {len(split['eval_pids'])}")

    # Load ground truth for both cohorts
    gt_csv = load_ground_truth(cohort="csv")
    gt_pdf = load_ground_truth(cohort="pdf")
    gt_by_cohort = {"csv": gt_csv, "pdf": gt_pdf}

    results: dict[tuple[str, int], dict] = {}

    for (cohort, visit), fname in sorted(_FILES.items()):
        fpath = os.path.join(_EVAL_DIR, fname)
        if not os.path.exists(fpath):
            print(f"  WARNING: missing {fname}")
            continue

        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)

        records = data["records"]

        # Filter: exclude SL pids for CSV cohort; PDF cohort is fully held-out
        if cohort == "csv":
            before = len(records)
            records = [r for r in records if r["pid"] not in excluded_pids]
            after = len(records)
            print(f"  csv v{visit}: {before} → {after} records (excluded {before - after})")
        else:
            print(f"  pdf v{visit}: {len(records)} records (all held-out)")

        gt = gt_by_cohort[cohort]
        results[(cohort, visit)] = grade(records, gt)

    # ---------------------------------------------------------------------------
    # Print results
    # ---------------------------------------------------------------------------

    cohort_label = {"csv": "A (csv)", "pdf": "B (pdf)"}

    print()
    print("=" * 72)
    print("TABLE 1 — EM@3 and Jaccard  [Self-Learning R7 agents, test set only]")
    print("=" * 72)
    print(f"{'Cohort':<12}  {'V1 EM':>6}  {'V1 Jac':>7}  {'V2 EM':>6}  {'V2 Jac':>7}  {'V3 EM':>6}  {'V3 Jac':>7}  {'N (V1/V2/V3)':>14}")
    print("-" * 72)
    for cohort in ("csv", "pdf"):
        row = []
        ns = []
        for v in (1, 2, 3):
            r = results.get((cohort, v), {})
            row.append(f"{r.get('em', 0)*100:5.1f}%")
            row.append(f"{r.get('jac', 0):.3f}")
            ns.append(str(r.get("n", 0)))
        print(f"{cohort_label[cohort]:<12}  {row[0]:>6}  {row[1]:>7}  {row[2]:>6}  {row[3]:>7}  {row[4]:>6}  {row[5]:>7}  {'/'.join(ns):>14}")

    print()
    print("=" * 72)
    print("TABLE 2 — Mono / Poly breakdown  [Self-Learning R7 agents, test set]")
    print("=" * 72)
    print(f"{'Cohort':<12}  {'Mono V1':>7}  {'Mono V2':>7}  {'Mono V3':>7}  {'Poly V1':>7}  {'Poly V2':>7}  {'Poly V3':>7}")
    print("-" * 72)
    for cohort in ("csv", "pdf"):
        row = []
        for v in (1, 2, 3):
            r = results.get((cohort, v), {})
            row.append(f"{r.get('mono_em', 0)*100:5.1f}%")
        for v in (1, 2, 3):
            r = results.get((cohort, v), {})
            row.append(f"{r.get('poly_em', 0)*100:5.1f}%")
        print(f"{cohort_label[cohort]:<12}  {row[0]:>7}  {row[1]:>7}  {row[2]:>7}  {row[3]:>7}  {row[4]:>7}  {row[5]:>7}")

    print()
    print("Counts:")
    for cohort in ("csv", "pdf"):
        for v in (1, 2, 3):
            r = results.get((cohort, v), {})
            print(f"  {cohort} v{v}: n={r.get('n',0)}, mono={r.get('mono_n',0)} ({r.get('mono_exact',0)} correct), poly={r.get('poly_n',0)} ({r.get('poly_exact',0)} correct), skipped={r.get('skipped',0)}")

    # ---------------------------------------------------------------------------
    # LaTeX snippet for paper
    # ---------------------------------------------------------------------------

    print()
    print("=" * 72)
    print("LaTeX numbers for Table 1 (Self-Learning row, EM@3 only):")
    print("=" * 72)
    for cohort, label in (("csv", "Cohort A"), ("pdf", "Cohort B")):
        ems = [results.get((cohort, v), {}).get("em", 0) * 100 for v in (1, 2, 3)]
        jacs = [results.get((cohort, v), {}).get("jac", 0) for v in (1, 2, 3)]
        print(f"  {label} & Self-Learning  & {ems[0]:.1f} & {jacs[0]:.3f} & {ems[1]:.1f} & {jacs[1]:.3f} & {ems[2]:.1f} & {jacs[2]:.3f} \\\\")

    print()
    print("LaTeX numbers for Table 2 (Self-Learning row, Mono/Poly):")
    print("=" * 72)
    for cohort, label in (("csv", "Cohort A"), ("pdf", "Cohort B")):
        monos = [results.get((cohort, v), {}).get("mono_em", 0) * 100 for v in (1, 2, 3)]
        polys = [results.get((cohort, v), {}).get("poly_em", 0) * 100 for v in (1, 2, 3)]
        print(f"  {label} & Self-Learning  & {monos[0]:.1f} & {monos[1]:.1f} & {monos[2]:.1f} & {polys[0]:.1f} & {polys[1]:.1f} & {polys[2]:.1f} \\\\")

    print()

    # ---------------------------------------------------------------------------
    # Save results JSON
    # ---------------------------------------------------------------------------

    out = {
        k[0] + f"_v{k[1]}": v for k, v in results.items()
    }
    out_path = os.path.join(_HERE, "multi", "outputs", "test_set_results_r7.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"Results saved → {out_path}")


if __name__ == "__main__":
    main()
