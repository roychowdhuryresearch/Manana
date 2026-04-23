"""TextGrad prompt optimization — comparison baseline against self-learning loop.

Optimizes the {shared_learnings} slot using TextGrad's automatic differentiation.
The predictor template (role, drugs, format) is frozen in the user message.
Only the clinical learnings (system prompt variable) is updated each round.

Usage:
    uv run python textgrad_opt/run.py
    uv run python textgrad_opt/run.py --batch-size 10
    uv run python textgrad_opt/run.py --model openai.gpt-oss-120b-1:0
    uv run python textgrad_opt/run.py --mimic
"""

import argparse
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import textgrad as tg
from textgrad import Variable
from textgrad.optimizer import TextualGradientDescent
from textgrad.autograd.llm_ops import LLMCall
from textgrad.autograd.function import BackwardContext

from textgrad_opt.engine import BedrockEngine, DEFAULT_MODEL
from self_learning.sampler import stratified_split
from mimic.sampler import mimic_split
from core.regimen_parser import parse_regimen

_HERE = os.path.dirname(os.path.abspath(__file__))


def load_predictor_template(mimic: bool = False) -> str:
    fname = "predictor_mimic.txt" if mimic else "predictor.txt"
    with open(os.path.join(_HERE, "prompts", fname), encoding="utf-8") as f:
        return f.read()


def drugs_from_regimen(regimen: dict, option_key: str = "option_1") -> set[str]:
    opt = regimen.get(option_key, {})
    return {d for d, action in opt.get("drugs", {}).items() if action in ("continue", "start")}


def get_gt_key(case) -> str:
    return f"{case.patient_id}__v{int(case.current_visit.split('_')[1])}"


def build_user_message(template: str, case) -> str:
    return template + "\n" + case.build_input_text()


# ── Parallel IO ──────────────────────────────────────────────────────────────

def _forward_and_loss_one(engine: BedrockEngine, learnings_value: str, template: str,
                          case, gt_data: dict, dataset: str = "uganda") -> dict | None:
    """Predictor call + loss eval call in one thread. Pure IO, no TextGrad graph."""
    gt_entry = gt_data.get(get_gt_key(case))
    if not gt_entry or not gt_entry["prescribed"]:
        return None
    gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
    user_msg = build_user_message(template, case)

    pred_raw = engine.generate(user_msg, system_prompt=learnings_value)
    if not pred_raw:
        return None

    if dataset == "mimic":
        patient_desc = "a US hospital patient"
    else:
        patient_desc = "a Uganda patient"
    loss_instruction = (
        f"Evaluate this epilepsy drug prediction for {patient_desc}. "
        f"The doctor's ground truth prescription was: {sorted(gt_drugs)}. "
        f"Is the prediction correct? If not, explain specifically what clinical knowledge "
        f"was missing or incorrectly applied that caused the error."
    )
    loss_input = f"PATIENT INPUT:\n{user_msg}\n\nPREDICTION:\n{pred_raw}"
    loss_text = engine.generate(loss_input, system_prompt=loss_instruction)

    return {
        "case": case,
        "gt_drugs": gt_drugs,
        "user_msg": user_msg,
        "pred_raw": pred_raw,
        "loss_instruction": loss_instruction,
        "loss_text": loss_text,
    }


def _eval_one(engine: BedrockEngine, learnings_value: str, template: str,
              case, gt_data: dict) -> dict | None:
    """Single eval case. Pure IO, no TextGrad graph."""
    gt_entry = gt_data.get(get_gt_key(case))
    if not gt_entry or not gt_entry["prescribed"]:
        return None
    gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
    user_msg = build_user_message(template, case)
    pred_raw = engine.generate(user_msg, system_prompt=learnings_value)
    if not pred_raw:
        return None
    regimen = parse_regimen(pred_raw)
    pred_drugs = drugs_from_regimen(regimen, "option_1")
    return {
        "patient_id": case.patient_id,
        "gt": sorted(gt_drugs),
        "pred": sorted(pred_drugs),
        "is_poly": len(gt_drugs) > 1,
        "top1_match": pred_drugs == gt_drugs,
        "top3_match": any(drugs_from_regimen(regimen, f"option_{n}") == gt_drugs for n in [1, 2, 3]),
    }


# ── Eval ─────────────────────────────────────────────────────────────────────

def run_eval(engine: BedrockEngine, learnings_value: str, template: str,
             eval_cases: list, gt_data: dict) -> dict:
    with ThreadPoolExecutor(max_workers=8) as pool:
        indexed = [(i, pool.submit(_eval_one, engine, learnings_value, template, c, gt_data))
                   for i, c in enumerate(eval_cases)]
    results = {}
    for i, f in indexed:
        try:
            results[i] = f.result()
        except Exception as e:
            print(f"  [WARN] Eval failed for case {i}: {e}")
    per_case = [r for i in sorted(results) if (r := results[i]) is not None]

    total = len(per_case)
    top1 = sum(1 for c in per_case if c["top1_match"])
    top3 = sum(1 for c in per_case if c["top3_match"])
    mono = [c for c in per_case if not c["is_poly"]]
    poly = [c for c in per_case if c["is_poly"]]
    return {
        "total": total,
        "top1_correct": top1,
        "top3_correct": top3,
        "top1_rate": top1 / total if total else 0,
        "top3_rate": top3 / total if total else 0,
        "mono_top3": sum(1 for c in mono if c["top3_match"]),
        "mono_total": len(mono),
        "poly_top3": sum(1 for c in poly if c["top3_match"]),
        "poly_total": len(poly),
        "per_case": per_case,
    }


# ── Main loop ─────────────────────────────────────────────────────────────────

def _sanitize(model: str) -> str:
    name = re.sub(r'[^a-zA-Z0-9-]', '_', model)
    return re.sub(r'_+', '_', name).strip('_').lower()


def run(batch_size: int = 10, model: str = None, seed: int = 42, temperature: float | None = None, mimic: bool = False):
    model = model or DEFAULT_MODEL
    dataset_tag = "mimic" if mimic else "uganda"
    run_id = f"tg_{dataset_tag}_s{seed}_{datetime.now().strftime('%Y%m%d_%H%M')}"
    output_dir = os.path.join(_HERE, "runs", _sanitize(model), run_id)
    os.makedirs(output_dir, exist_ok=True)

    engine = BedrockEngine(model=model, temperature=temperature)
    tg.set_backward_engine(engine)

    template = load_predictor_template(mimic=mimic)

    if mimic:
        split = mimic_split(shuffle_seed=seed)
        train_cases = split["train_cases"]
        eval_cases  = split["eval_cases"]
        gt_data     = split["gt_data"]
        stats       = split["stats"]
        train_label = f"{stats['train_patients']} patients ({stats['train_poly']} poly)"
        eval_label  = f"{stats['eval_patients']} patients ({stats['eval_poly']} poly)"
    else:
        split = stratified_split(cohort="csv", shuffle_seed=seed)
        train_cases = split["train_cases"]
        eval_cases  = split["eval_cases"]
        gt_data     = split["gt_data"]
        stats       = split["stats"]
        train_label = f"{stats['train_patients']} patients, {stats['train_cases']} cases"
        eval_label  = f"{stats['eval_patients']} patients, {stats['eval_cases']} cases"

    n_batches = (len(train_cases) + batch_size - 1) // batch_size

    print(f"\n{'='*60}")
    print(f"TEXTGRAD PROMPT OPTIMIZATION")
    print(f"{'='*60}")
    print(f"Model:   {model}")
    print(f"Dataset: {dataset_tag}")
    print(f"Train:   {train_label}")
    print(f"Eval:    {eval_label}")
    print(f"Batches: {n_batches} × {batch_size}")
    print(f"Output:  {output_dir}")
    print(f"{'='*60}")

    if mimic:
        patient_context = "US hospital epilepsy patients"
    else:
        patient_context = "Uganda epilepsy patients"

    shared_learnings = Variable(
        "",
        requires_grad=True,
        role_description=f"clinical learnings about {patient_context} — bullet-pointed observations to guide drug prediction",
    )

    optimizer = TextualGradientDescent(
        parameters=[shared_learnings],
        engine=engine,
        constraints=[
            f"Write clinical observations about {patient_context}.",
            "Do not write any format instructions, output format specifications, role descriptions, or drug lists.",
            "Each bullet point should be a concrete clinical pattern (e.g. drug preferences, comorbidities, resistance patterns).",
        ],
    )

    eval_progression = []

    print(f"\n  [Eval] Baseline (empty learnings)...")
    baseline = run_eval(engine, "", template, eval_cases, gt_data)
    eval_progression.append({"round": "baseline", "learnings": "",
                              **{k: v for k, v in baseline.items() if k != "per_case"},
                              "per_case": baseline["per_case"]})
    print(f"  [Eval] top1={baseline['top1_correct']}/{baseline['total']} ({baseline['top1_rate']:.0%})  "
          f"top3={baseline['top3_correct']}/{baseline['total']} ({baseline['top3_rate']:.0%})")

    best_top3 = baseline["top3_rate"]
    best_learnings = ""
    best_eval = baseline

    all_rounds = []

    for batch_idx in range(n_batches):
        batch_cases = train_cases[batch_idx * batch_size : (batch_idx + 1) * batch_size]

        print(f"\n{'─'*60}")
        print(f"ROUND {batch_idx} — {len(batch_cases)} cases")
        print(f"Learnings: {shared_learnings.value[:120] or '(empty)'}")
        print(f"{'─'*60}")

        optimizer.zero_grad()

        # ── Step 1: parallel IO (predictor + loss eval per patient) ──────────
        # Use indexed futures to keep deterministic order (as_completed is arrival-order).
        with ThreadPoolExecutor(max_workers=8) as pool:
            indexed_futures = [(i, pool.submit(_forward_and_loss_one, engine, shared_learnings.value,
                                               template, case, gt_data, dataset_tag))
                               for i, case in enumerate(batch_cases)]
        results_by_idx = {}
        for i, f in indexed_futures:
            try:
                results_by_idx[i] = f.result()
            except Exception as e:
                print(f"  [WARN] Forward failed for case {i}: {e}")
        raw = [r for i in sorted(results_by_idx) if (r := results_by_idx[i]) is not None]

        if not raw:
            print(f"  No gradeable cases, skipping.")
            continue

        # ── Step 2: serial graph building (no engine calls) ──────────────────
        losses = []
        batch_results = []
        for r in raw:
            case      = r["case"]
            gt_drugs  = r["gt_drugs"]
            user_msg  = r["user_msg"]
            pred_raw  = r["pred_raw"]
            loss_instr = r["loss_instruction"]
            loss_text  = r["loss_text"]

            regimen   = parse_regimen(pred_raw)
            pred_drugs = drugs_from_regimen(regimen, "option_1")
            any_match  = any(drugs_from_regimen(regimen, f"option_{n}") == gt_drugs for n in [1, 2, 3])
            batch_results.append({
                "patient_id": case.patient_id,
                "gt": sorted(gt_drugs),
                "pred": sorted(pred_drugs),
                "any_match": any_match,
            })

            # Prediction node — wired to shared_learnings via BackwardContext
            patient_var = Variable(user_msg, requires_grad=False,
                                   role_description="patient case with frozen task instructions")
            prediction = Variable(
                value=pred_raw,
                predecessors=[shared_learnings, patient_var],
                requires_grad=True,
                role_description="epilepsy drug prediction",
            )
            _pred_llm = LLMCall(engine, system_prompt=shared_learnings)
            prediction.set_grad_fn(BackwardContext(
                _pred_llm.backward,
                response=prediction,
                prompt=user_msg,
                system_prompt=shared_learnings.value,
            ))

            # Loss node — wired to prediction
            loss_instr_var = Variable(loss_instr, requires_grad=False,
                                      role_description="loss evaluation instruction")
            loss_var = Variable(
                value=loss_text,
                predecessors=[loss_instr_var, prediction],
                requires_grad=True,
                role_description="loss evaluation",
            )
            _loss_llm = LLMCall(engine, system_prompt=loss_instr_var)
            loss_var.set_grad_fn(BackwardContext(
                _loss_llm.backward,
                response=loss_var,
                prompt=pred_raw,
                system_prompt=loss_instr,
            ))
            losses.append(loss_var)

        batch_correct = sum(1 for r in batch_results if r["any_match"])
        print(f"  Train: {batch_correct}/{len(batch_results)}")

        # ── Step 3: backward (serial, TextGrad handles it) ───────────────────
        print(f"  Backpropagating...")
        total_loss = tg.sum(losses)
        total_loss.backward()

        try:
            optimizer.step()
            print(f"  Updated learnings: {shared_learnings.value[:200]}")
        except IndexError:
            print(f"  [WARN] Optimizer failed to format response (missing tags) — keeping current learnings.")

        # ── Step 4: eval (parallel) ───────────────────────────────────────────
        print(f"  [Eval] Running...")
        candidate_learnings = shared_learnings.value
        round_eval = run_eval(engine, candidate_learnings, template, eval_cases, gt_data)
        mono_str = f"{round_eval['mono_top3']}/{round_eval['mono_total']}"
        poly_str = f"{round_eval['poly_top3']}/{round_eval['poly_total']}"
        print(f"  [Eval] top1={round_eval['top1_correct']}/{round_eval['total']} ({round_eval['top1_rate']:.0%})  "
              f"top3={round_eval['top3_correct']}/{round_eval['total']} ({round_eval['top3_rate']:.0%})  "
              f"mono={mono_str}  poly={poly_str}")

        accepted = round_eval["top3_rate"] > best_top3
        if accepted:
            best_top3 = round_eval["top3_rate"]
            best_learnings = candidate_learnings
            best_eval = round_eval
            print(f"  [Gating] Improved to {best_top3:.0%} — keeping update.")
            selected_learnings = candidate_learnings
            selected_eval = round_eval
        else:
            shared_learnings.value = best_learnings
            print(f"  [Gating] No improvement ({round_eval['top3_rate']:.0%} <= {best_top3:.0%}) — rolled back.")
            selected_learnings = best_learnings
            selected_eval = best_eval

        round_data = {
            "round": batch_idx,
            "accepted": accepted,
            "learnings_before": eval_progression[-1]["learnings"],
            "candidate_learnings": candidate_learnings,
            "rejected_learnings": candidate_learnings if not accepted else "",
            "learnings_after": selected_learnings,
            "train_correct": batch_correct,
            "train_total": len(batch_results),
            "train_results": batch_results,
            **{k: v for k, v in selected_eval.items() if k != "per_case"},
            "per_case": selected_eval["per_case"],
            "candidate_eval": round_eval,
        }
        all_rounds.append(round_data)
        eval_progression.append({"round": batch_idx, "learnings": selected_learnings,
                                  "accepted": accepted,
                                  "candidate_top3_rate": round_eval["top3_rate"],
                                  "best_top3_rate": best_top3,
                                  **{k: v for k, v in selected_eval.items() if k != "per_case"},
                                  "per_case": selected_eval["per_case"]})

        with open(os.path.join(output_dir, f"round_{batch_idx}.json"), "w") as f:
            json.dump(round_data, f, indent=2, ensure_ascii=False)

    with open(os.path.join(output_dir, "full_run.json"), "w") as f:
        json.dump(all_rounds, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, "eval_progression.json"), "w") as f:
        json.dump(eval_progression, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"{'Round':<10} {'Acc':>4} {'Top-1':>10} {'Candidate':>12} {'Best':>8} {'Mono':>8} {'Poly':>8}")
    print(f"{'-'*66}")
    for ep in eval_progression:
        rnd  = ep["round"] if isinstance(ep["round"], str) else f"R{ep['round']}"
        acc  = "—" if "accepted" not in ep else ("Y" if ep["accepted"] else "N")
        mono = f"{ep['mono_top3']}/{ep['mono_total']}" if ep.get("mono_total") else "n/a"
        poly = f"{ep['poly_top3']}/{ep['poly_total']}" if ep.get("poly_total") else "n/a"
        candidate = f"({ep['candidate_top3_rate']:.0%})" if "candidate_top3_rate" in ep else "—"
        best = f"({ep['best_top3_rate']:.0%})" if "best_top3_rate" in ep else "—"
        print(f"{rnd:<10} {acc:>4} {ep['top1_correct']}/{ep['total']} ({ep['top1_rate']:.0%})   "
              f"{candidate:>12} {best:>8} {mono:<8} {poly:<8}")

    print(f"\nFinal learnings:\n{shared_learnings.value}")
    print(f"\nOutput: {output_dir}/")
    print(f"{'='*60}\n")

    lines = []
    lines.append(f"# Run Summary\n")
    lines.append(f"**Model:** {model}  ")
    lines.append(f"**Dataset:** {dataset_tag}  ")
    lines.append(f"**Seed:** {seed}  ")
    lines.append(f"**Batch size:** {batch_size}  ")
    lines.append(f"**Rounds:** {n_batches}\n")
    lines.append(f"## Eval Progression\n")
    lines.append(f"| Round | Acc | Top-1 | Candidate | Best | Mono | Poly |")
    lines.append(f"|-------|-----|-------|-----------|------|------|------|")
    for ep in eval_progression:
        rnd = ep["round"] if isinstance(ep["round"], str) else f"R{ep['round']}"
        acc = "—" if "accepted" not in ep else ("Y" if ep["accepted"] else "N")
        top1 = f"{ep['top1_correct']}/{ep['total']} ({ep['top1_rate']:.0%})"
        candidate = f"({ep['candidate_top3_rate']:.0%})" if "candidate_top3_rate" in ep else "—"
        best = f"({ep['best_top3_rate']:.0%})" if "best_top3_rate" in ep else "—"
        mono = f"{ep['mono_top3']}/{ep['mono_total']}" if ep.get("mono_total") else "n/a"
        poly = f"{ep['poly_top3']}/{ep['poly_total']}" if ep.get("poly_total") else "n/a"
        lines.append(f"| {rnd} | {acc} | {top1} | {candidate} | {best} | {mono} | {poly} |")
    lines.append(f"\n## Final Learnings\n")
    lines.append(shared_learnings.value or "(empty)")
    with open(os.path.join(output_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--temp", type=float, default=None)
    parser.add_argument("--mimic", action="store_true")
    args = parser.parse_args()
    run(batch_size=args.batch_size, model=args.model, seed=args.seed, temperature=args.temp, mimic=args.mimic)
