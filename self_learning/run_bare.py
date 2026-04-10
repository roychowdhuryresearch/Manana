"""Bare-bones self-learning experiment: 1 Predictor + 1 Inspector.

Run on a batch of patients:
1. Predictor makes predictions (minimal prompt, no specialist knowledge)
2. Compare against ground truth
3. Inspector diagnoses every error
4. Save Inspector reports for analysis

Usage:
    uv run python self_learning/run_bare.py --limit 20 --visit 1
    uv run python self_learning/run_bare.py --limit 20 --visit 2 --cohort csv
"""

import argparse
import asyncio
import json
import os
from datetime import datetime

from llm.client import LLMClient, DEFAULT_MODEL
from scripts.loader import load_cases, load_ground_truth
from core.regimen_parser import parse_regimen
from tqdm import tqdm

_HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(_HERE, "prompts")


def load_prompt(name: str, shared_learnings: str = "") -> str:
    path = os.path.join(PROMPTS_DIR, name)
    with open(path, encoding="utf-8") as f:
        template = f.read()
    if "{shared_learnings}" in template:
        if shared_learnings.strip():
            block = f"\nSHARED LEARNINGS (from prior patients):\n{shared_learnings}\n"
        else:
            block = ""
        template = template.replace("{shared_learnings}", block)
    return template


def drugs_from_regimen(regimen: dict, option_key: str = "option_1") -> set[str]:
    """Extract active drug set from a parsed regimen option."""
    opt = regimen.get(option_key, {})
    drugs = opt.get("drugs", {})
    return {d for d, action in drugs.items() if action in ("continue", "start")}


def drugs_match(predicted: set[str], ground_truth: set[str]) -> bool:
    return predicted == ground_truth


async def run_experiment(
    visit_num: int = 1,
    cohort: str | None = None,
    limit: int = 20,
    model: str = DEFAULT_MODEL,
):
    output_dir = os.path.join(_HERE, "outputs", f"bare_{datetime.now().strftime('%Y%m%d_%H%M')}")
    os.makedirs(output_dir, exist_ok=True)

    client = LLMClient(model=model)

    # Load data
    cases = load_cases(visit_num=visit_num, cohort=cohort, limit=limit)
    gt_data = load_ground_truth(visit_num=visit_num, cohort=cohort, limit=limit)

    # Load prompts
    predictor_prompt = load_prompt("predictor_v0.txt", shared_learnings="")
    inspector_prompt = load_prompt("inspector.txt")

    print(f"\n{'='*60}")
    print(f"SELF-LEARNING BARE BONES — ROUND 0")
    print(f"{'='*60}")
    print(f"Model:    {model}")
    print(f"Visit:    {visit_num}")
    print(f"Cohort:   {cohort or 'all'}")
    print(f"Patients: {len(cases)}")
    print(f"Output:   {output_dir}")
    print(f"{'='*60}\n")

    results = []
    correct = 0
    total = 0

    pbar = tqdm(total=len(cases), desc="Processing", unit="patient")

    for case in cases:
        gt_key = f"{case.patient_id}__v{visit_num}"
        gt_entry = gt_data.get(gt_key)
        if not gt_entry:
            pbar.update(1)
            continue

        gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
        if not gt_drugs:
            pbar.update(1)
            continue

        total += 1
        patient_input = case.build_input_text()

        # ── STEP 1: Predictor ──
        pred_thinking, pred_raw = await client.call(predictor_prompt, patient_input)
        pred_regimen = parse_regimen(pred_raw)
        pred_drugs = drugs_from_regimen(pred_regimen, "option_1")

        # Check all 3 options
        any_match = False
        best_option = None
        for opt_key in ["option_1", "option_2", "option_3"]:
            opt_drugs = drugs_from_regimen(pred_regimen, opt_key)
            if opt_drugs == gt_drugs:
                any_match = True
                best_option = opt_key
                break

        if any_match:
            correct += 1

        # ── STEP 2: Inspector (runs on every case, not just errors) ──
        inspector_input = f"""PATIENT CLINICAL NOTES:
{patient_input}

SYSTEM PREDICTION:
{pred_raw}

PARSED PREDICTION (Option 1 drugs): {sorted(pred_drugs) if pred_drugs else '(parse failed)'}

GROUND TRUTH (what the doctor prescribed): {sorted(gt_drugs)}

MATCH: {'Yes — ' + best_option if any_match else 'No — none of the 3 options matched'}
"""

        inspector_thinking, inspector_report = await client.call(inspector_prompt, inspector_input)

        entry = {
            "patient_id": case.patient_id,
            "visit": visit_num,
            "gt_drugs": sorted(gt_drugs),
            "pred_option1_drugs": sorted(pred_drugs),
            "any_match": any_match,
            "best_option": best_option,
            "predictor_thinking": pred_thinking,
            "predictor_raw": pred_raw,
            "pred_regimen": pred_regimen,
            "inspector_thinking": inspector_thinking,
            "inspector_report": inspector_report,
        }
        results.append(entry)
        pbar.update(1)

    pbar.close()
    await client.close()

    # ── Save results ──
    results_path = os.path.join(output_dir, "results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # ── Save full reports with CoT for easy reading ──
    reports_path = os.path.join(output_dir, "full_reports.txt")
    with open(reports_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(f"{'='*70}\n")
            f.write(f"PATIENT: {r['patient_id']} | Visit {r['visit']}\n")
            f.write(f"GT: {r['gt_drugs']}  |  Pred: {r['pred_option1_drugs']}  |  Match: {r['any_match']}\n")
            f.write(f"{'='*70}\n")
            if r.get("predictor_thinking"):
                f.write(f"\n--- PREDICTOR COT ---\n{r['predictor_thinking']}\n")
            f.write(f"\n--- PREDICTOR OUTPUT ---\n{r['predictor_raw']}\n")
            if r.get("inspector_thinking"):
                f.write(f"\n--- INSPECTOR COT ---\n{r['inspector_thinking']}\n")
            f.write(f"\n--- INSPECTOR REPORT ---\n{r['inspector_report']}\n")
            f.write(f"\n\n")

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"Total cases:    {total}")
    print(f"Top-1 correct:  {sum(1 for r in results if r['pred_option1_drugs'] and set(r['gt_drugs']) == set(r['pred_option1_drugs']))}/{total}")
    print(f"Top-3 correct:  {correct}/{total} ({correct/total:.1%})")
    print(f"Parse failures: {sum(1 for r in results if not r['pred_option1_drugs'])}")
    print()

    # ── Aggregate inspector "WHAT WOULD HELP" themes ──
    print("Inspector reports saved to:")
    print(f"  {results_path}")
    print(f"  {reports_path}")
    print(f"{'='*60}\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Self-Learning Bare Bones Experiment")
    parser.add_argument("--visit", type=int, default=1, choices=[1, 2, 3, 4, 5, 6])
    parser.add_argument("--cohort", type=str, default=None, choices=["csv", "pdf"])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    args = parser.parse_args()

    asyncio.run(run_experiment(
        visit_num=args.visit,
        cohort=args.cohort,
        limit=args.limit,
        model=args.model,
    ))
