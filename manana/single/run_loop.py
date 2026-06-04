"""Single-system Manana loop.

Single predictor + inspector + architect. No agent spawning.
Inspector proposes candidate learnings → buffer (never flushed).
Architect reads buffer every round → appends to shared_learnings.
Predictor reads shared_learnings.

Usage:
    uv run python -m manana.run --config configs/mimic.yaml --system single
"""

import argparse
import asyncio
import json
import os
import re
from datetime import datetime

from lib.llm import LLMClient, DEFAULT_MODEL
from lib.regimen_parser import parse_regimen
from manana.datasets import load_configured_split, resolve_config_path
from manana.prompts import load_rendered_prompt

_HERE = os.path.dirname(os.path.abspath(__file__))
MAX_SINGLE_RULES = 15


def sanitize_model_name(model: str) -> str:
    name = re.sub(r'[^a-zA-Z0-9-]', '_', model)
    name = re.sub(r'_+', '_', name).strip('_')
    return name.lower()


def drugs_from_regimen(regimen: dict, option_key: str = "option_1") -> set[str]:
    opt = regimen.get(option_key, {})
    drugs = opt.get("drugs", {})
    return {d for d, action in drugs.items() if action in ("continue", "start")}


def get_visit_num(case) -> int:
    return int(case.current_visit.split("_")[1])


def get_gt_key(case) -> str:
    return f"{case.patient_id}__v{get_visit_num(case)}"


def build_predictor_prompt(template: str, shared_learnings: list[str]) -> str:
    if shared_learnings:
        block = "CLINICAL KNOWLEDGE:\n"
        for i, rule in enumerate(shared_learnings, 1):
            block += f"{i}. {rule}\n"
    else:
        block = ""
    return template.replace("{shared_learnings}", block)


def extract_candidate_learning(inspector_output: str) -> str | None:
    """Extract CANDIDATE_LEARNING from inspector output. Returns None if not found."""
    match = re.search(
        r'CANDIDATE[_ ]LEARNING\*{0,2}\s*:?\*{0,2}\s*\n?\s*(.+)',
        inspector_output,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    learning = match.group(1).strip()
    learning = re.sub(r'\*+', '', learning)
    learning = re.sub(r'^\[|\]$', '', learning.strip())
    learning = re.sub(r'^[-•]\s*', '', learning.strip())
    learning = learning.strip()
    return learning if len(learning) > 10 else None


def build_architect_input(
    shared_learnings: list[str],
    buffer: dict[int, list[str]],
    batch_results: list[dict],
    batch_idx: int,
) -> str:
    parts = []

    # Current learnings
    parts.append("CURRENT LEARNINGS:")
    if shared_learnings:
        for i, rule in enumerate(shared_learnings, 1):
            parts.append(f"{i}. {rule}")
    else:
        parts.append("(none yet)")

    # Full candidate buffer grouped by round
    parts.append("\nCANDIDATE BUFFER (all rounds):")
    if buffer:
        for round_idx in sorted(buffer.keys()):
            learnings = buffer[round_idx]
            if learnings:
                parts.append(f"\nRound {round_idx}:")
                for l in learnings:
                    parts.append(f"  - {l}")
    else:
        parts.append("(empty)")

    # Current round inspector reports
    parts.append(f"\n\nINSPECTOR REPORTS FROM THIS BATCH (Round {batch_idx}):\n")
    for r in batch_results:
        parts.append(f"--- Patient: {r['patient_id']} V{r['visit']} (poly={r['is_poly']}) ---")
        parts.append(f"GT: {r['gt_drugs']} | Match: {r['any_match']}")
        parts.append(r["inspector_report"])
        parts.append("")

    return "\n".join(parts)


def parse_architect_additions(architect_output: str) -> list[str]:
    """Parse {"additions": [...]} from architect output."""
    # Strip code fences
    text = re.sub(r'```[a-z]*\n?', '', architect_output).strip('`').strip()
    # Find JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        return []
    try:
        obj = json.loads(match.group())
        additions = obj.get("additions", [])
        if isinstance(additions, list):
            return [str(a).strip() for a in additions if str(a).strip()]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


async def run_train_case(
    client: LLMClient,
    predictor_template: str,
    inspector_prompt: str,
    shared_learnings: list[str],
    case,
    gt_data: dict,
    temperature: float | None = None,
) -> dict | None:
    gt_entry = gt_data.get(get_gt_key(case))
    if not gt_entry or not gt_entry["prescribed"]:
        return None

    gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
    patient_notes = case.build_input_text()

    # Predictor
    predictor_prompt = build_predictor_prompt(predictor_template, shared_learnings)
    _, pred_raw = await client.call(predictor_prompt, patient_notes, temperature=temperature)
    if not pred_raw:
        print(f"  [WARN] Predictor failure for {case.patient_id} — skipping")
        return None

    pred_regimen = parse_regimen(pred_raw)
    pred_drugs = drugs_from_regimen(pred_regimen, "option_1")

    any_match = False
    best_option = None
    for opt_key in ["option_1", "option_2", "option_3"]:
        if drugs_from_regimen(pred_regimen, opt_key) == gt_drugs:
            any_match = True
            best_option = opt_key
            break

    # Inspector
    inspector_input = f"""PATIENT CLINICAL NOTES:
{patient_notes}

SYSTEM PREDICTION:
{pred_raw}

GROUND TRUTH (what the doctor prescribed): {sorted(gt_drugs)}

MATCH: {'Yes — ' + best_option if any_match else 'No — none of the 3 options matched'}
"""
    _, inspector_report = await client.call(inspector_prompt, inspector_input, temperature=temperature)
    if not inspector_report:
        print(f"  [WARN] Inspector failure for {case.patient_id} — skipping")
        return None

    candidate_learning = extract_candidate_learning(inspector_report)

    return {
        "patient_id": case.patient_id,
        "visit": get_visit_num(case),
        "gt_drugs": sorted(gt_drugs),
        "pred_option1_drugs": sorted(pred_drugs),
        "is_poly": len(gt_drugs) > 1,
        "any_match": any_match,
        "best_option": best_option,
        "predictor_raw": pred_raw,
        "inspector_report": inspector_report,
        "candidate_learning": candidate_learning,
    }


async def run_eval_case(
    client: LLMClient,
    predictor_template: str,
    shared_learnings: list[str],
    case,
    gt_data: dict,
    temperature: float | None = None,
) -> dict | None:
    gt_entry = gt_data.get(get_gt_key(case))
    if not gt_entry or not gt_entry["prescribed"]:
        return None

    gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
    patient_notes = case.build_input_text()

    predictor_prompt = build_predictor_prompt(predictor_template, shared_learnings)
    _, pred_raw = await client.call(predictor_prompt, patient_notes, temperature=temperature)
    if not pred_raw:
        return None

    pred_regimen = parse_regimen(pred_raw)
    pred_drugs = drugs_from_regimen(pred_regimen, "option_1")

    top1_match = pred_drugs == gt_drugs
    top3_match = any(
        drugs_from_regimen(pred_regimen, f"option_{n}") == gt_drugs
        for n in [1, 2, 3]
    )

    return {
        "patient_id": case.patient_id,
        "visit": get_visit_num(case),
        "gt": sorted(gt_drugs),
        "pred": sorted(pred_drugs),
        "is_poly": len(gt_drugs) > 1,
        "top1_match": top1_match,
        "top3_match": top3_match,
    }


async def run_eval(
    client: LLMClient,
    predictor_template: str,
    shared_learnings: list[str],
    eval_cases: list,
    gt_data: dict,
    temperature: float | None = None,
) -> dict:
    tasks = [run_eval_case(client, predictor_template, shared_learnings, case, gt_data, temperature) for case in eval_cases]
    results = await asyncio.gather(*tasks)
    per_case = [r for r in results if r is not None]

    total = len(per_case)
    correct_top1 = sum(1 for c in per_case if c["top1_match"])
    correct_top3 = sum(1 for c in per_case if c["top3_match"])
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
    max_rounds: int | None = None,
    model: str = DEFAULT_MODEL,
    seed: int = 42,
    temperature: float | None = None,
    config_path: str | None = None,
):
    if not config_path:
        raise ValueError("config_path is required; run via `python -m manana.run --config ...`.")
    configured = load_configured_split(config_path, seed)
    model_folder = sanitize_model_name(model)
    tag = configured.tag
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = resolve_config_path(configured.config, configured.config.get("output_root"))
    if output_root:
        output_dir = os.path.join(output_root, "single", "outputs", tag, model_folder, run_id)
    else:
        output_dir = os.path.join(_HERE, "outputs", tag, model_folder, run_id)
    os.makedirs(output_dir, exist_ok=True)

    client = LLMClient(model=model)

    train_cases = configured.train_cases
    eval_cases = configured.eval_cases
    gt_data = configured.gt_data
    train_label = configured.train_label
    eval_label = configured.eval_label

    predictor_template = load_rendered_prompt("single", "predictor", configured.config)
    inspector_prompt = load_rendered_prompt("single", "inspector", configured.config)
    architect_prompt = load_rendered_prompt("single", "architect", configured.config)

    # State
    shared_learnings: list[str] = []
    buffer: dict[int, list[str]] = {}
    all_rounds = []
    eval_progression = []

    n_batches = (len(train_cases) + batch_size - 1) // batch_size
    if max_rounds is not None:
        n_batches = min(n_batches, max_rounds)

    print(f"\n{'='*60}")
    print(f"BUFFER MANANA LOOP")
    print(f"{'='*60}")
    print(f"Model:      {model}")
    if config_path:
        print(f"Config:     {config_path}")
    print(f"Train:      {train_label}")
    print(f"Eval:       {eval_label}")
    print(f"Batches:    {n_batches} × {batch_size}")
    print(f"Output:     {output_dir}")
    print(f"{'='*60}")

    # Baseline eval
    print(f"\n  [Eval] Baseline (empty shared_learnings)...")
    baseline_eval = await run_eval(client, predictor_template, shared_learnings, eval_cases, gt_data, temperature)
    eval_progression.append({
        "round": "baseline",
        "shared_learnings_size": 0,
        "shared_learnings": [],
        **{k: v for k, v in baseline_eval.items() if k != "per_case"},
        "per_case": baseline_eval["per_case"],
    })
    mono_str = f"{baseline_eval['mono_top3']}/{baseline_eval['mono_total']}"
    poly_str = f"{baseline_eval['poly_top3']}/{baseline_eval['poly_total']}"
    print(f"  [Eval] top3={baseline_eval['top3_correct']}/{baseline_eval['total']} ({baseline_eval['top3_rate']:.0%})  mono={mono_str}  poly={poly_str}")

    best_top3 = baseline_eval["top3_rate"]
    best_shared_learnings: list[str] = []

    for batch_idx in range(n_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(train_cases))
        batch_cases = train_cases[start:end]

        print(f"\n{'─'*60}")
        print(f"ROUND {batch_idx} — {len(batch_cases)} cases — shared_learnings: {len(shared_learnings)} rules")
        print(f"{'─'*60}")

        # Run batch in parallel
        print(f"  Running batch (parallel)...")
        tasks = [
            run_train_case(client, predictor_template, inspector_prompt, shared_learnings, case, gt_data, temperature)
            for case in batch_cases
        ]
        results = await asyncio.gather(*tasks)
        batch_results = [r for r in results if r is not None]

        batch_correct = sum(1 for r in batch_results if r["any_match"])
        batch_total = len(batch_results)
        print(f"  Train: {batch_correct}/{batch_total} ({batch_correct/batch_total:.0%})" if batch_total else "  Train: n/a")

        # Collect candidate learnings from this round (do NOT add to buffer yet —
        # architect sees previous rounds' buffer + current raw reports, not both)
        new_learnings = [r["candidate_learning"] for r in batch_results if r["candidate_learning"]]
        print(f"  Buffer: +{len(new_learnings)} new candidates (previous rounds total: {sum(len(v) for v in buffer.values())})")

        # Architect
        print(f"  Running Architect...")
        shared_learnings_before_architect = list(shared_learnings)
        architect_input = build_architect_input(shared_learnings, buffer, batch_results, batch_idx)
        _, architect_output = await client.call(architect_prompt, architect_input, temperature=temperature)

        additions = []
        if architect_output:
            remaining_slots = max(0, MAX_SINGLE_RULES - len(shared_learnings))
            additions = parse_architect_additions(architect_output)[:min(1, remaining_slots)]
            shared_learnings.extend(additions)
            if additions:
                print(f"  Added {len(additions)} new learnings → shared_learnings now {len(shared_learnings)} rules")
                for a in additions:
                    print(f"    + {a[:80]}...")
            elif remaining_slots == 0:
                print(f"  Rule cap reached ({MAX_SINGLE_RULES}); no additions this round")
            else:
                print(f"  No additions this round")
        else:
            print("  [WARN] Architect returned empty output")

        # Buffer always updated after Architect sees current raw reports
        buffer[batch_idx] = new_learnings

        # Eval
        print(f"  [Eval] Running on held-out set...")
        candidate_shared_learnings = list(shared_learnings)
        round_eval = await run_eval(client, predictor_template, shared_learnings, eval_cases, gt_data, temperature)
        mono_str = f"{round_eval['mono_top3']}/{round_eval['mono_total']}"
        poly_str = f"{round_eval['poly_top3']}/{round_eval['poly_total']}"
        print(f"  [Eval] top3={round_eval['top3_correct']}/{round_eval['total']} ({round_eval['top3_rate']:.0%})  mono={mono_str}  poly={poly_str}")

        # No gating: always accept architect additions
        accepted = True
        best_top3 = round_eval["top3_rate"]
        best_shared_learnings = list(shared_learnings)

        eval_entry = {
            "round": batch_idx,
            "accepted": accepted,
            "candidate_top3_rate": round_eval["top3_rate"],
            "best_top3_rate": best_top3,
            "shared_learnings_size": len(shared_learnings),
            "shared_learnings": list(shared_learnings),
            "additions_this_round": additions,
            **{k: v for k, v in round_eval.items() if k != "per_case"},
            "per_case": round_eval["per_case"],
        }
        eval_progression.append(eval_entry)

        round_data = {
            "round": batch_idx,
            "accepted": accepted,
            "n_cases": len(batch_cases),
            "shared_learnings_before": shared_learnings_before_architect,
            "buffer_this_round": new_learnings,
            "architect_output": architect_output,
            "additions": additions,
            "candidate_shared_learnings": candidate_shared_learnings,
            "shared_learnings_after": list(shared_learnings),
            "results": batch_results,
        }
        all_rounds.append(round_data)

        with open(os.path.join(output_dir, f"round_{batch_idx}.json"), "w", encoding="utf-8") as f:
            json.dump(round_data, f, indent=2, ensure_ascii=False)

    await client.close()

    with open(os.path.join(output_dir, "full_run.json"), "w", encoding="utf-8") as f:
        json.dump(all_rounds, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, "eval_progression.json"), "w", encoding="utf-8") as f:
        json.dump(eval_progression, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, "final_shared_learnings.json"), "w", encoding="utf-8") as f:
        json.dump(shared_learnings, f, indent=2, ensure_ascii=False)

    # Final summary
    print(f"\n{'='*60}")
    print(f"FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"\n{'Round':<10} {'Acc':>4} {'Rules':>6} {'Candidate':>10} {'Best':>8} {'Mono':>8} {'Poly':>8}")
    print(f"{'-'*62}")
    for ep in eval_progression:
        rnd = ep["round"] if isinstance(ep["round"], str) else f"R{ep['round']}"
        acc = "—" if "accepted" not in ep else ("Y" if ep["accepted"] else "N")
        n_rules = ep.get("shared_learnings_size", 0)
        candidate = f"{ep['top3_correct']}/{ep['total']} ({ep['top3_rate']:.0%})"
        best = f"({ep['best_top3_rate']:.0%})" if "best_top3_rate" in ep else "—"
        mono = f"{ep['mono_top3']}/{ep['mono_total']}"
        poly = f"{ep['poly_top3']}/{ep['poly_total']}"
        print(f"{rnd:<10} {acc:>4} {n_rules:>6} {candidate:<12} {best:>8} {mono:<8} {poly:<8}")

    print(f"\nFinal shared_learnings ({len(shared_learnings)} rules):")
    for i, rule in enumerate(shared_learnings, 1):
        print(f"  {i}. {rule}")
    print(f"\nOutput: {output_dir}/")
    print(f"{'='*60}\n")

    # Write summary.md
    lines = []
    lines.append(f"# Run Summary\n")
    lines.append(f"**Model:** {model}  ")
    lines.append(f"**Tag:** {tag}  ")
    lines.append(f"**Seed:** {seed}  ")
    if config_path:
        lines.append(f"**Config:** {config_path}  ")
    lines.append(f"**Batch size:** {batch_size}  ")
    lines.append(f"**Rounds:** {n_batches}\n")
    lines.append(f"## Eval Progression\n")
    lines.append(f"| Round | Acc | Rules | Candidate | Best | Mono | Poly |")
    lines.append(f"|-------|-----|-------|-----------|------|------|------|")
    for ep in eval_progression:
        rnd = ep["round"] if isinstance(ep["round"], str) else f"R{ep['round']}"
        acc = "—" if "accepted" not in ep else ("Y" if ep["accepted"] else "N")
        n_rules = ep.get("shared_learnings_size", 0)
        candidate = f"{ep['top3_correct']}/{ep['total']} ({ep['top3_rate']:.0%})"
        best = f"({ep['best_top3_rate']:.0%})" if "best_top3_rate" in ep else "—"
        mono = f"{ep['mono_top3']}/{ep['mono_total']}"
        poly = f"{ep['poly_top3']}/{ep['poly_total']}"
        lines.append(f"| {rnd} | {acc} | {n_rules} | {candidate} | {best} | {mono} | {poly} |")
    lines.append(f"\n## Final Shared Learnings ({len(shared_learnings)} rules)\n")
    for i, rule in enumerate(shared_learnings, 1):
        lines.append(f"{i}. {rule}")
    with open(os.path.join(output_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Single Manana loop")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--config", required=True, help="Run YAML config")
    parser.add_argument("--temp", type=float, default=None)
    args = parser.parse_args()

    asyncio.run(run_loop(
        batch_size=args.batch_size,
        max_rounds=args.rounds,
        model=args.model,
        seed=args.seed,
        temperature=args.temp,
        config_path=args.config,
    ))
