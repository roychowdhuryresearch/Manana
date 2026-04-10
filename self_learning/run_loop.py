"""Self-learning loop with held-out evaluation.

Splits data into train and eval sets. Runs batches through:
1. Predictor predicts (with current shared learnings)
2. Inspector diagnoses errors
3. Architect updates shared learnings
4. Evaluate on held-out eval set (same learnings, no feedback)
5. Repeat

Usage:
    uv run python self_learning/run_loop.py --train 30 --eval 20 --batch-size 5 --visit 1 --cohort csv
"""

import argparse
import asyncio
import json
import os
import re
import random
from datetime import datetime

from llm.client import LLMClient, DEFAULT_MODEL
from scripts.loader import load_cases, load_ground_truth
from core.regimen_parser import parse_regimen
from tqdm import tqdm

_HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(_HERE, "prompts")


def load_prompt(name: str) -> str:
    with open(os.path.join(PROMPTS_DIR, name), encoding="utf-8") as f:
        return f.read()


def build_predictor_prompt(template: str, shared_learnings: list[str]) -> str:
    if shared_learnings:
        block = "SHARED LEARNINGS (patterns discovered from prior patients):\n"
        for i, learning in enumerate(shared_learnings, 1):
            block += f"  {i}. {learning}\n"
    else:
        block = ""
    return template.replace("{shared_learnings}", block)


def drugs_from_regimen(regimen: dict, option_key: str = "option_1") -> set[str]:
    opt = regimen.get(option_key, {})
    drugs = opt.get("drugs", {})
    return {d for d, action in drugs.items() if action in ("continue", "start")}


def parse_architect_learnings(architect_output: str) -> list[str]:
    """Extract the UPDATED_LEARNINGS list from Architect output."""
    match = re.search(r'UPDATED_LEARNINGS\s*:', architect_output, re.IGNORECASE)
    if not match:
        return []

    text = architect_output[match.end():]
    learnings = []
    for line in text.split('\n'):
        line = line.strip()
        m = re.match(r'(?:\d+[\.\)]\s*|[-•]\s*)(.*)', line)
        if m and m.group(1).strip():
            learning = m.group(1).strip().strip('"').strip("'")
            if learning and len(learning) > 10:
                learnings.append(learning)

    return learnings


async def run_eval(
    client: LLMClient,
    predictor_prompt: str,
    eval_cases: list,
    gt_data: dict,
    visit_num: int,
) -> dict:
    """Run predictor on eval set (no Inspector, no learning — just measure accuracy)."""
    correct_top1 = 0
    correct_top3 = 0
    total = 0
    per_case = []

    for case in eval_cases:
        gt_key = f"{case.patient_id}__v{visit_num}"
        gt_entry = gt_data.get(gt_key)
        if not gt_entry:
            continue
        gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
        if not gt_drugs:
            continue

        total += 1
        patient_input = case.build_input_text()
        _, pred_raw = await client.call(predictor_prompt, patient_input)
        pred_regimen = parse_regimen(pred_raw)
        pred_drugs = drugs_from_regimen(pred_regimen, "option_1")

        top1_match = pred_drugs == gt_drugs
        top3_match = any(
            drugs_from_regimen(pred_regimen, f"option_{n}") == gt_drugs
            for n in [1, 2, 3]
        )

        if top1_match:
            correct_top1 += 1
        if top3_match:
            correct_top3 += 1

        per_case.append({
            "patient_id": case.patient_id,
            "gt": sorted(gt_drugs),
            "pred": sorted(pred_drugs),
            "top1_match": top1_match,
            "top3_match": top3_match,
        })

    return {
        "total": total,
        "top1_correct": correct_top1,
        "top3_correct": correct_top3,
        "top1_rate": correct_top1 / total if total else 0,
        "top3_rate": correct_top3 / total if total else 0,
        "per_case": per_case,
    }


async def run_loop(
    n_train: int = 30,
    n_eval: int = 20,
    batch_size: int = 5,
    visit_num: int = 1,
    cohort: str | None = None,
    model: str = DEFAULT_MODEL,
    seed: int = 42,
):
    run_id = f"loop_{datetime.now().strftime('%Y%m%d_%H%M')}"
    output_dir = os.path.join(_HERE, "outputs", run_id)
    os.makedirs(output_dir, exist_ok=True)

    client = LLMClient(model=model)

    # Load all data
    all_cases = load_cases(visit_num=visit_num, cohort=cohort, limit=n_train + n_eval)
    gt_data = load_ground_truth(visit_num=visit_num, cohort=cohort, limit=n_train + n_eval)

    # Split into train and eval
    random.seed(seed)
    indices = list(range(len(all_cases)))
    random.shuffle(indices)

    eval_indices = set(indices[:n_eval])
    train_indices = [i for i in indices if i not in eval_indices][:n_train]

    train_cases = [all_cases[i] for i in train_indices]
    eval_cases = [all_cases[i] for i in eval_indices]

    # Load prompt templates
    predictor_template = load_prompt("predictor_v0.txt")
    inspector_prompt = load_prompt("inspector.txt")
    architect_prompt = load_prompt("architect.txt")

    # State
    shared_learnings: list[str] = []
    all_rounds = []
    eval_progression = []

    n_batches = (len(train_cases) + batch_size - 1) // batch_size

    print(f"\n{'='*60}")
    print(f"SELF-LEARNING LOOP WITH EVAL")
    print(f"{'='*60}")
    print(f"Model:      {model}")
    print(f"Visit:      {visit_num}")
    print(f"Cohort:     {cohort or 'all'}")
    print(f"Train:      {len(train_cases)} patients ({n_batches} batches of {batch_size})")
    print(f"Eval:       {len(eval_cases)} patients (held-out, never trained on)")
    print(f"Output:     {output_dir}")
    print(f"{'='*60}")

    # ── BASELINE EVAL (before any learning) ──
    print(f"\n  [Eval] Baseline (0 learnings)...")
    baseline_prompt = build_predictor_prompt(predictor_template, [])
    baseline_eval = await run_eval(client, baseline_prompt, eval_cases, gt_data, visit_num)
    eval_progression.append({
        "round": "baseline",
        "learnings": 0,
        "top1": baseline_eval["top1_rate"],
        "top3": baseline_eval["top3_rate"],
        "top1_n": baseline_eval["top1_correct"],
        "top3_n": baseline_eval["top3_correct"],
        "total": baseline_eval["total"],
        "per_case": baseline_eval["per_case"],
    })
    print(f"  [Eval] Baseline: top1={baseline_eval['top1_correct']}/{baseline_eval['total']} ({baseline_eval['top1_rate']:.0%})  top3={baseline_eval['top3_correct']}/{baseline_eval['total']} ({baseline_eval['top3_rate']:.0%})")

    cumulative_correct = 0
    cumulative_total = 0

    for batch_idx in range(n_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(train_cases))
        batch_cases = train_cases[start:end]

        round_data = {
            "round": batch_idx,
            "patients": [c.patient_id for c in batch_cases],
            "shared_learnings_before": list(shared_learnings),
            "results": [],
        }

        print(f"\n{'─'*60}")
        print(f"ROUND {batch_idx} — {len(batch_cases)} train patients — {len(shared_learnings)} learnings")
        print(f"{'─'*60}")

        predictor_prompt = build_predictor_prompt(predictor_template, shared_learnings)

        batch_results = []
        batch_correct = 0
        batch_total = 0

        for case in tqdm(batch_cases, desc=f"R{batch_idx} train", unit="pt"):
            gt_key = f"{case.patient_id}__v{visit_num}"
            gt_entry = gt_data.get(gt_key)
            if not gt_entry:
                continue
            gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
            if not gt_drugs:
                continue

            batch_total += 1
            patient_input = case.build_input_text()

            # Predictor
            pred_thinking, pred_raw = await client.call(predictor_prompt, patient_input)
            pred_regimen = parse_regimen(pred_raw)
            pred_drugs = drugs_from_regimen(pred_regimen, "option_1")

            any_match = False
            best_option = None
            for opt_key in ["option_1", "option_2", "option_3"]:
                if drugs_from_regimen(pred_regimen, opt_key) == gt_drugs:
                    any_match = True
                    best_option = opt_key
                    break

            if any_match:
                batch_correct += 1

            # Inspector
            inspector_input = f"""PATIENT CLINICAL NOTES:
{patient_input}

SYSTEM PREDICTION:
{pred_raw}

PARSED PREDICTION (Option 1 drugs): {sorted(pred_drugs) if pred_drugs else '(parse failed)'}

GROUND TRUTH (what the doctor prescribed): {sorted(gt_drugs)}

MATCH: {'Yes — ' + best_option if any_match else 'No — none of the 3 options matched'}
"""
            inspector_thinking, inspector_report = await client.call(inspector_prompt, inspector_input)

            batch_results.append({
                "patient_id": case.patient_id,
                "gt_drugs": sorted(gt_drugs),
                "pred_option1_drugs": sorted(pred_drugs),
                "any_match": any_match,
                "best_option": best_option,
                "predictor_thinking": pred_thinking,
                "predictor_raw": pred_raw,
                "pred_regimen": pred_regimen,
                "inspector_thinking": inspector_thinking,
                "inspector_report": inspector_report,
            })

        round_data["results"] = batch_results
        cumulative_correct += batch_correct
        cumulative_total += batch_total

        print(f"  Train: {batch_correct}/{batch_total} ({batch_correct/batch_total:.0%})" if batch_total else "")

        # Architect
        print(f"  Running Architect...")
        architect_input = "INSPECTOR REPORTS FROM THIS BATCH:\n\n"
        for r in batch_results:
            architect_input += f"--- Patient: {r['patient_id']} ---\n"
            architect_input += f"GT: {r['gt_drugs']} | Pred: {r['pred_option1_drugs']} | Match: {r['any_match']}\n"
            architect_input += r["inspector_report"]
            architect_input += "\n\n"

        architect_input += "CURRENT SHARED LEARNINGS:\n"
        if shared_learnings:
            for i, l in enumerate(shared_learnings, 1):
                architect_input += f"  {i}. {l}\n"
        else:
            architect_input += "  (none — this is the first batch)\n"

        if batch_idx > 0 and eval_progression:
            prev_eval = eval_progression[-1]
            architect_input += f"\nPREVIOUS EVAL (held-out set): top3={prev_eval['top3_n']}/{prev_eval['total']} ({prev_eval['top3']:.0%})\n"

        architect_thinking, architect_output = await client.call(architect_prompt, architect_input)

        new_learnings = parse_architect_learnings(architect_output)
        if new_learnings:
            shared_learnings = new_learnings

        round_data["architect_thinking"] = architect_thinking
        round_data["architect_output"] = architect_output
        round_data["shared_learnings_after"] = list(shared_learnings)

        print(f"  Learnings: {len(round_data['shared_learnings_before'])} → {len(shared_learnings)}")
        for i, l in enumerate(shared_learnings, 1):
            print(f"    {i}. {l[:90]}{'...' if len(l) > 90 else ''}")

        # ── EVAL after this round ──
        print(f"  [Eval] Running on held-out set...")
        eval_prompt = build_predictor_prompt(predictor_template, shared_learnings)
        round_eval = await run_eval(client, eval_prompt, eval_cases, gt_data, visit_num)
        eval_progression.append({
            "round": batch_idx,
            "learnings": len(shared_learnings),
            "top1": round_eval["top1_rate"],
            "top3": round_eval["top3_rate"],
            "top1_n": round_eval["top1_correct"],
            "top3_n": round_eval["top3_correct"],
            "total": round_eval["total"],
            "per_case": round_eval["per_case"],
        })
        print(f"  [Eval] top1={round_eval['top1_correct']}/{round_eval['total']} ({round_eval['top1_rate']:.0%})  top3={round_eval['top3_correct']}/{round_eval['total']} ({round_eval['top3_rate']:.0%})")

        all_rounds.append(round_data)

        # Save round snapshot
        round_path = os.path.join(output_dir, f"round_{batch_idx}.json")
        with open(round_path, "w", encoding="utf-8") as f:
            json.dump(round_data, f, indent=2, ensure_ascii=False)

    await client.close()

    # ── Save everything ──
    full_path = os.path.join(output_dir, "full_run.json")
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(all_rounds, f, indent=2, ensure_ascii=False)

    eval_path = os.path.join(output_dir, "eval_progression.json")
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(eval_progression, f, indent=2, ensure_ascii=False)

    # ── Save progression summary ──
    summary_path = os.path.join(output_dir, "progression.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"SELF-LEARNING LOOP — {run_id}\n")
        f.write(f"Model: {model} | Visit: {visit_num} | Cohort: {cohort}\n")
        f.write(f"Train: {len(train_cases)} | Eval: {len(eval_cases)} | Batch: {batch_size}\n")
        f.write(f"{'='*70}\n\n")

        f.write("EVAL PROGRESSION:\n")
        f.write(f"{'Round':<10} {'Learnings':<10} {'Top-1':>10} {'Top-3':>10}\n")
        f.write(f"{'-'*40}\n")
        for ep in eval_progression:
            rnd = ep["round"] if isinstance(ep["round"], str) else f"R{ep['round']}"
            f.write(f"{rnd:<10} {ep['learnings']:<10} {ep['top1_n']}/{ep['total']} ({ep['top1']:.0%}){'':<3} {ep['top3_n']}/{ep['total']} ({ep['top3']:.0%})\n")
        f.write(f"\n{'='*70}\n\n")

        for rd in all_rounds:
            bc = sum(1 for r in rd["results"] if r["any_match"])
            bt = len(rd["results"])
            f.write(f"{'─'*70}\n")
            f.write(f"ROUND {rd['round']} — Train: {bc}/{bt}\n")
            f.write(f"{'─'*70}\n")
            for r in rd["results"]:
                s = "OK" if r["any_match"] else "MISS"
                f.write(f"  [{s}] {r['patient_id']}: GT={r['gt_drugs']} Pred={r['pred_option1_drugs']}\n")
            f.write(f"\n  ARCHITECT:\n")
            for line in (rd.get("architect_output") or "").split('\n'):
                f.write(f"    {line}\n")
            f.write(f"\n  LEARNINGS AFTER:\n")
            for i, l in enumerate(rd.get("shared_learnings_after", []), 1):
                f.write(f"    {i}. {l}\n")
            f.write(f"\n\n")

    # ── Final summary ──
    print(f"\n{'='*60}")
    print(f"FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"\nEval progression (held-out {len(eval_cases)} patients):")
    print(f"{'Round':<12} {'Learnings':<10} {'Top-1':>12} {'Top-3':>12}")
    print(f"{'-'*48}")
    for ep in eval_progression:
        rnd = ep["round"] if isinstance(ep["round"], str) else f"Round {ep['round']}"
        print(f"{rnd:<12} {ep['learnings']:<10} {ep['top1_n']}/{ep['total']} ({ep['top1']:.0%}){'':<4} {ep['top3_n']}/{ep['total']} ({ep['top3']:.0%})")

    print(f"\nFinal learnings ({len(shared_learnings)}):")
    for i, l in enumerate(shared_learnings, 1):
        print(f"  {i}. {l}")

    print(f"\nOutput: {output_dir}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Self-Learning Loop with Eval")
    parser.add_argument("--train", type=int, default=30, help="Number of training patients")
    parser.add_argument("--eval", type=int, default=20, help="Number of held-out eval patients")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--visit", type=int, default=1, choices=[1, 2, 3, 4, 5, 6])
    parser.add_argument("--cohort", type=str, default=None, choices=["csv", "pdf"])
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    asyncio.run(run_loop(
        n_train=args.train,
        n_eval=args.eval,
        batch_size=args.batch_size,
        visit_num=args.visit,
        cohort=args.cohort,
        model=args.model,
        seed=args.seed,
    ))
