"""Self-learning loop with stratified train/eval split.

Splits patients into train/eval (stratified by mono/poly complexity).
Runs batches through: Predictor → Inspector → Architect → Eval.
Tracks progression on held-out eval set after each round.

Usage:
    uv run python self_learning/run_loop.py --batch-size 10
    uv run python self_learning/run_loop.py --batch-size 10 --seed 123
"""

import argparse
import asyncio
import json
import os
import re
from datetime import datetime

from llm.client import LLMClient, DEFAULT_MODEL
from core.regimen_parser import parse_regimen
from self_learning.sampler import stratified_split
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


def get_visit_num(case) -> int:
    return int(case.current_visit.split("_")[1])


def get_gt_key(case) -> str:
    return f"{case.patient_id}__v{get_visit_num(case)}"


def parse_architect_learnings(architect_output: str) -> list[str]:
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
) -> dict:
    """Run predictor on eval set — no Inspector, no learning."""
    correct_top1 = 0
    correct_top3 = 0
    total = 0
    per_case = []

    for case in eval_cases:
        gt_entry = gt_data.get(get_gt_key(case))
        if not gt_entry or not gt_entry["prescribed"]:
            continue

        gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
        total += 1

        _, pred_raw = await client.call(predictor_prompt, case.build_input_text())
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
            "visit": get_visit_num(case),
            "gt": sorted(gt_drugs),
            "pred": sorted(pred_drugs),
            "is_poly": len(gt_drugs) > 1,
            "top1_match": top1_match,
            "top3_match": top3_match,
        })

    # Mono/poly breakdown
    mono_cases = [c for c in per_case if not c["is_poly"]]
    poly_cases = [c for c in per_case if c["is_poly"]]

    return {
        "total": total,
        "top1_correct": correct_top1,
        "top3_correct": correct_top3,
        "top1_rate": correct_top1 / total if total else 0,
        "top3_rate": correct_top3 / total if total else 0,
        "mono_top3": sum(1 for c in mono_cases if c["top3_match"]),
        "mono_total": len(mono_cases),
        "poly_top3": sum(1 for c in poly_cases if c["top3_match"]),
        "poly_total": len(poly_cases),
        "per_case": per_case,
    }


async def run_loop(
    batch_size: int = 10,
    model: str = DEFAULT_MODEL,
    seed: int = 42,
):
    run_id = f"loop_{datetime.now().strftime('%Y%m%d_%H%M')}"
    output_dir = os.path.join(_HERE, "outputs", run_id)
    os.makedirs(output_dir, exist_ok=True)

    client = LLMClient(model=model)

    # Stratified split
    split = stratified_split(cohort="csv", seed=seed)
    train_cases = split["train_cases"]
    eval_cases = split["eval_cases"]
    gt_data = split["gt_data"]
    stats = split["stats"]

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
    print(f"SELF-LEARNING LOOP (STRATIFIED)")
    print(f"{'='*60}")
    print(f"Model:      {model}")
    print(f"Train:      {stats['train_patients']} patients, {stats['train_cases']} cases ({stats['train_poly']} poly)")
    print(f"Eval:       {stats['eval_patients']} patients, {stats['eval_cases']} cases ({stats['eval_poly']} poly)")
    print(f"Batches:    {n_batches} × {batch_size}")
    print(f"Output:     {output_dir}")
    print(f"{'='*60}")

    # ── BASELINE EVAL ──
    print(f"\n  [Eval] Baseline (0 learnings)...")
    baseline_prompt = build_predictor_prompt(predictor_template, [])
    baseline_eval = await run_eval(client, baseline_prompt, eval_cases, gt_data)
    eval_progression.append({
        "round": "baseline",
        "learnings": 0,
        **{k: v for k, v in baseline_eval.items() if k != "per_case"},
        "per_case": baseline_eval["per_case"],
    })
    mono_str = f"{baseline_eval['mono_top3']}/{baseline_eval['mono_total']}" if baseline_eval['mono_total'] else "n/a"
    poly_str = f"{baseline_eval['poly_top3']}/{baseline_eval['poly_total']}" if baseline_eval['poly_total'] else "n/a"
    print(f"  [Eval] top1={baseline_eval['top1_correct']}/{baseline_eval['total']} ({baseline_eval['top1_rate']:.0%})  top3={baseline_eval['top3_correct']}/{baseline_eval['total']} ({baseline_eval['top3_rate']:.0%})  mono={mono_str}  poly={poly_str}")

    for batch_idx in range(n_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(train_cases))
        batch_cases = train_cases[start:end]

        round_data = {
            "round": batch_idx,
            "n_cases": len(batch_cases),
            "shared_learnings_before": list(shared_learnings),
            "results": [],
        }

        print(f"\n{'─'*60}")
        print(f"ROUND {batch_idx} — {len(batch_cases)} cases — {len(shared_learnings)} learnings")
        print(f"{'─'*60}")

        predictor_prompt = build_predictor_prompt(predictor_template, shared_learnings)

        batch_results = []
        batch_correct = 0
        batch_total = 0

        for case in tqdm(batch_cases, desc=f"R{batch_idx} train", unit="case"):
            gt_entry = gt_data.get(get_gt_key(case))
            if not gt_entry or not gt_entry["prescribed"]:
                continue

            gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
            batch_total += 1

            # Predictor
            pred_thinking, pred_raw = await client.call(predictor_prompt, case.build_input_text())
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
{case.build_input_text()}

SYSTEM PREDICTION:
{pred_raw}

PARSED PREDICTION (Option 1 drugs): {sorted(pred_drugs) if pred_drugs else '(parse failed)'}

GROUND TRUTH (what the doctor prescribed): {sorted(gt_drugs)}

MATCH: {'Yes — ' + best_option if any_match else 'No — none of the 3 options matched'}
"""
            inspector_thinking, inspector_report = await client.call(inspector_prompt, inspector_input)

            batch_results.append({
                "patient_id": case.patient_id,
                "visit": get_visit_num(case),
                "gt_drugs": sorted(gt_drugs),
                "pred_option1_drugs": sorted(pred_drugs),
                "is_poly": len(gt_drugs) > 1,
                "any_match": any_match,
                "best_option": best_option,
                "predictor_thinking": pred_thinking,
                "predictor_raw": pred_raw,
                "pred_regimen": pred_regimen,
                "inspector_thinking": inspector_thinking,
                "inspector_report": inspector_report,
            })

        round_data["results"] = batch_results
        bc_pct = f"{batch_correct}/{batch_total} ({batch_correct/batch_total:.0%})" if batch_total else "n/a"
        print(f"  Train: {bc_pct}")

        # Architect
        print(f"  Running Architect...")
        architect_input = "INSPECTOR REPORTS FROM THIS BATCH:\n\n"
        for r in batch_results:
            architect_input += f"--- Patient: {r['patient_id']} V{r['visit']} (poly={r['is_poly']}) ---\n"
            architect_input += f"GT: {r['gt_drugs']} | Pred: {r['pred_option1_drugs']} | Match: {r['any_match']}\n"
            architect_input += r["inspector_report"]
            architect_input += "\n\n"

        architect_input += "CURRENT SHARED LEARNINGS:\n"
        if shared_learnings:
            for i, l in enumerate(shared_learnings, 1):
                architect_input += f"  {i}. {l}\n"
        else:
            architect_input += "  (none — this is the first batch)\n"

        if eval_progression:
            prev = eval_progression[-1]
            architect_input += f"\nLAST EVAL: top3={prev['top3_correct']}/{prev['total']} ({prev['top3_rate']:.0%})  mono={prev['mono_top3']}/{prev['mono_total']}  poly={prev['poly_top3']}/{prev['poly_total']}\n"

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

        # Eval
        print(f"  [Eval] Running on held-out set...")
        eval_prompt = build_predictor_prompt(predictor_template, shared_learnings)
        round_eval = await run_eval(client, eval_prompt, eval_cases, gt_data)
        eval_entry = {
            "round": batch_idx,
            "learnings": len(shared_learnings),
            **{k: v for k, v in round_eval.items() if k != "per_case"},
            "per_case": round_eval["per_case"],
        }
        eval_progression.append(eval_entry)

        mono_str = f"{round_eval['mono_top3']}/{round_eval['mono_total']}" if round_eval['mono_total'] else "n/a"
        poly_str = f"{round_eval['poly_top3']}/{round_eval['poly_total']}" if round_eval['poly_total'] else "n/a"
        print(f"  [Eval] top1={round_eval['top1_correct']}/{round_eval['total']} ({round_eval['top1_rate']:.0%})  top3={round_eval['top3_correct']}/{round_eval['total']} ({round_eval['top3_rate']:.0%})  mono={mono_str}  poly={poly_str}")

        all_rounds.append(round_data)

        # Save round
        with open(os.path.join(output_dir, f"round_{batch_idx}.json"), "w", encoding="utf-8") as f:
            json.dump(round_data, f, indent=2, ensure_ascii=False)

    await client.close()

    # Save everything
    with open(os.path.join(output_dir, "full_run.json"), "w", encoding="utf-8") as f:
        json.dump(all_rounds, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, "eval_progression.json"), "w", encoding="utf-8") as f:
        json.dump(eval_progression, f, indent=2, ensure_ascii=False)

    # Progression summary
    with open(os.path.join(output_dir, "progression.txt"), "w", encoding="utf-8") as f:
        f.write(f"SELF-LEARNING LOOP (STRATIFIED) — {run_id}\n")
        f.write(f"Model: {model} | Seed: {seed}\n")
        f.write(f"Train: {stats['train_patients']} patients, {stats['train_cases']} cases ({stats['train_poly']} poly)\n")
        f.write(f"Eval:  {stats['eval_patients']} patients, {stats['eval_cases']} cases ({stats['eval_poly']} poly)\n")
        f.write(f"{'='*70}\n\n")

        f.write(f"{'Round':<10} {'Learn':<6} {'Top-1':>12} {'Top-3':>12} {'Mono':>10} {'Poly':>10}\n")
        f.write(f"{'-'*62}\n")
        for ep in eval_progression:
            rnd = ep["round"] if isinstance(ep["round"], str) else f"R{ep['round']}"
            mono = f"{ep['mono_top3']}/{ep['mono_total']}" if ep['mono_total'] else "n/a"
            poly = f"{ep['poly_top3']}/{ep['poly_total']}" if ep['poly_total'] else "n/a"
            f.write(f"{rnd:<10} {ep['learnings']:<6} {ep['top1_correct']}/{ep['total']} ({ep['top1_rate']:.0%}){'':<3} {ep['top3_correct']}/{ep['total']} ({ep['top3_rate']:.0%}){'':<3} {mono:<10} {poly:<10}\n")

        f.write(f"\n{'='*70}\n\n")

        for rd in all_rounds:
            bc = sum(1 for r in rd["results"] if r["any_match"])
            bt = len(rd["results"])
            f.write(f"{'─'*70}\n")
            f.write(f"ROUND {rd['round']} — Train: {bc}/{bt}\n{'─'*70}\n")
            for r in rd["results"]:
                s = "OK" if r["any_match"] else "MISS"
                poly = "P" if r["is_poly"] else "M"
                f.write(f"  [{s}] {r['patient_id']} V{r['visit']} [{poly}]: GT={r['gt_drugs']} Pred={r['pred_option1_drugs']}\n")
            f.write(f"\n  ARCHITECT:\n")
            for line in (rd.get("architect_output") or "").split('\n'):
                f.write(f"    {line}\n")
            f.write(f"\n  LEARNINGS AFTER ({len(rd.get('shared_learnings_after', []))}):\n")
            for i, l in enumerate(rd.get("shared_learnings_after", []), 1):
                f.write(f"    {i}. {l}\n")
            f.write(f"\n\n")

    # Final summary
    print(f"\n{'='*60}")
    print(f"FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"\n{'Round':<10} {'Learn':<6} {'Top-1':>12} {'Top-3':>12} {'Mono':>10} {'Poly':>10}")
    print(f"{'-'*62}")
    for ep in eval_progression:
        rnd = ep["round"] if isinstance(ep["round"], str) else f"Round {ep['round']}"
        mono = f"{ep['mono_top3']}/{ep['mono_total']}" if ep['mono_total'] else "n/a"
        poly = f"{ep['poly_top3']}/{ep['poly_total']}" if ep['poly_total'] else "n/a"
        print(f"{rnd:<10} {ep['learnings']:<6} {ep['top1_correct']}/{ep['total']} ({ep['top1_rate']:.0%}){'':<3} {ep['top3_correct']}/{ep['total']} ({ep['top3_rate']:.0%}){'':<3} {mono:<10} {poly:<10}")

    print(f"\nFinal learnings ({len(shared_learnings)}):")
    for i, l in enumerate(shared_learnings, 1):
        print(f"  {i}. {l}")
    print(f"\nOutput: {output_dir}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Self-Learning Loop (Stratified)")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    asyncio.run(run_loop(
        batch_size=args.batch_size,
        model=args.model,
        seed=args.seed,
    ))
