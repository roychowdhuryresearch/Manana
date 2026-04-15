"""DSPy baseline: automated prompt optimization for drug prediction.

Fair comparison with NPCL — same starting knowledge (Uganda, 10 drugs),
same train/eval split, same metric. DSPy optimizes through its compilation
methods (BootstrapFewShot, MIPRO). NPCL optimizes through inspect-diagnose-update.

Usage:
    uv run python self_learning/run_dspy.py
    uv run python self_learning/run_dspy.py --optimizer mipro
"""

import argparse
import asyncio
import json
import os
import re
from datetime import datetime

import dspy

from self_learning.sampler import stratified_split
from core.regimen_parser import parse_regimen

_HERE = os.path.dirname(os.path.abspath(__file__))

DRUG_COLUMNS = [
    "carbamazepine", "clobazam", "clonazepam", "ethosuximide",
    "lamotrigine", "levetiracetam", "phenobarbital", "phenytoin",
    "topiramate", "valproate",
]


def drugs_from_regimen(regimen: dict, option_key: str = "option_1") -> set[str]:
    opt = regimen.get(option_key, {})
    drugs = opt.get("drugs", {})
    return {d for d, action in drugs.items() if action in ("continue", "start")}


def get_gt_key(case) -> str:
    visit_num = int(case.current_visit.split("_")[1])
    return f"{case.patient_id}__v{visit_num}"


# ── DSPy Signature ──

class DrugPrediction(dspy.Signature):
    """Given clinical notes from a clinic in Uganda, predict the doctor's
    anti-seizure medication prescription. Use ONLY these 10 drugs:
    carbamazepine, clobazam, clonazepam, ethosuximide, lamotrigine,
    levetiracetam, phenobarbital, phenytoin, topiramate, valproate.
    For each drug, specify an action: continue, start, or stop."""

    clinical_notes: str = dspy.InputField(desc="Patient clinical notes")
    reasoning: str = dspy.OutputField(desc="Clinical reasoning for the prescription")
    option_1: str = dspy.OutputField(desc="Top prescription option, format: 'drug1:action, drug2:action'")
    option_2: str = dspy.OutputField(desc="Second option, format: 'drug1:action, drug2:action'")
    option_3: str = dspy.OutputField(desc="Third option, format: 'drug1:action, drug2:action'")


def parse_dspy_option(option_str: str) -> set[str]:
    """Parse a DSPy option string like 'valproate:continue, carbamazepine:stop' into active drug set."""
    active = set()
    for part in option_str.lower().replace(";", ",").split(","):
        part = part.strip()
        for drug in DRUG_COLUMNS:
            if drug in part:
                if "stop" not in part and "discontinue" not in part:
                    active.add(drug)
                break
    return active


# ── Metric ──

def drug_match_metric(example, pred, trace=None) -> float:
    """Top-3 exact match metric for DSPy optimization."""
    gt_drugs = set(example.gt_drugs)

    for opt_field in ["option_1", "option_2", "option_3"]:
        opt_str = getattr(pred, opt_field, "")
        pred_drugs = parse_dspy_option(opt_str)
        if pred_drugs == gt_drugs:
            return 1.0

    # Partial credit via Jaccard on best option
    best_jac = 0.0
    for opt_field in ["option_1", "option_2", "option_3"]:
        opt_str = getattr(pred, opt_field, "")
        pred_drugs = parse_dspy_option(opt_str)
        if pred_drugs or gt_drugs:
            jac = len(pred_drugs & gt_drugs) / len(pred_drugs | gt_drugs) if (pred_drugs | gt_drugs) else 0
            best_jac = max(best_jac, jac)

    return best_jac


# ── Build examples ──

def build_examples(cases, gt_data):
    """Convert cases to DSPy Examples."""
    examples = []
    for case in cases:
        gt_entry = gt_data.get(get_gt_key(case))
        if not gt_entry or not gt_entry["prescribed"]:
            continue
        gt_drugs = [d.lower() for d in gt_entry["prescribed"]]
        gt_str = ", ".join(f"{d}:continue" for d in sorted(gt_drugs))

        example = dspy.Example(
            clinical_notes=case.build_input_text(),
            gt_drugs=gt_drugs,
            # For bootstrap: provide target outputs
            reasoning="Based on clinical notes.",
            option_1=gt_str,
            option_2=gt_str,
            option_3=gt_str,
        ).with_inputs("clinical_notes")

        examples.append(example)
    return examples


FEEDBACK_PIDS = [
    "262_Mutyaba Derrick", "64_Owinyi Golden", "10_Muduku Matthew",
    "288_Agonzibwa Trevor", "95_Lomakol Ives Zane", "90_Odongo Moses",
    "85_Mirembe Mercy", "67_Ssenyonjo Waswa", "320_Nakibirango Calvin",
    "58_Sekyeru Jeremiah", "317_Nantume Shabila", "39_Najjemba Christine",
    "260_Mukisa Elizabeth", "9_Nalukwaago Patience", "8_Tisma Natabi",
    "74_Mukisa Shalom", "131_Muwanguzi Blessed Serugga", "100_Otim Fortunate",
    "227_Muluwaya Arnold", "272_Ogol Jerry",
]


def run_dspy(
    optimizer_name: str = "bootstrap",
    model: str = "bedrock/openai.gpt-oss-120b-1:0",
    seed: int = 42,
    max_bootstrapped: int = 4,
    feedback: bool = False,
):
    mode = "feedback" if feedback else optimizer_name
    run_id = f"dspy_{mode}_{datetime.now().strftime('%Y%m%d_%H%M')}"
    output_dir = os.path.join(_HERE, "outputs", "dspy", run_id)
    os.makedirs(output_dir, exist_ok=True)

    # Configure DSPy
    lm = dspy.LM(model, region_name="us-east-1", max_tokens=4096)
    dspy.configure(lm=lm)

    # Same split as NPCL — eval set always the same
    split = stratified_split(cohort="csv", seed=seed)
    eval_cases = split["eval_cases"]
    gt_data = split["gt_data"]

    if feedback:
        from scripts.loader import load_cases as _load_cases
        import random as _random
        all_cohort_cases = _load_cases(cohort="csv")
        train_cases = [c for c in all_cohort_cases if c.patient_id in set(FEEDBACK_PIDS)]
        _random.Random(seed).shuffle(train_cases)
        train_label = f"feedback patients ({len(set(c.patient_id for c in train_cases))} patients, {len(train_cases)} cases)"
    else:
        train_cases = split["train_cases"]
        train_label = f"{split['stats']['train_patients']} patients, {split['stats']['train_cases']} cases"

    train_examples = build_examples(train_cases, gt_data)
    eval_examples = build_examples(eval_cases, gt_data)

    print(f"\n{'='*60}")
    print(f"DSPY BASELINE — {mode}")
    print(f"{'='*60}")
    print(f"Model:     {model}")
    print(f"Train:     {train_label} ({len(train_examples)} examples)")
    print(f"Eval:      {len(eval_examples)} examples")
    print(f"Optimizer: {optimizer_name}")
    print(f"Output:    {output_dir}")
    print(f"{'='*60}\n")

    # Unoptimized baseline
    predictor = dspy.ChainOfThought(DrugPrediction)

    print("Running unoptimized baseline on eval set...")
    baseline_scores = []
    for ex in eval_examples:
        try:
            pred = predictor(clinical_notes=ex.clinical_notes)
            score = drug_match_metric(ex, pred)
            baseline_scores.append(score)
        except Exception as e:
            print(f"  [WARN] {e}")
            baseline_scores.append(0.0)

    baseline_exact = sum(1 for s in baseline_scores if s == 1.0)
    baseline_mean = sum(baseline_scores) / len(baseline_scores) if baseline_scores else 0
    print(f"Baseline: {baseline_exact}/{len(baseline_scores)} exact ({baseline_exact/len(baseline_scores):.0%}), mean score: {baseline_mean:.3f}\n")

    # Optimize
    print(f"Optimizing with {optimizer_name}...")
    if optimizer_name == "bootstrap":
        optimizer = dspy.BootstrapFewShot(
            metric=drug_match_metric,
            max_bootstrapped_demos=max_bootstrapped,
            max_labeled_demos=max_bootstrapped,
        )
    elif optimizer_name == "mipro":
        optimizer = dspy.MIPROv2(
            metric=drug_match_metric,
            auto="light",
        )
    elif optimizer_name == "gepa":
        def gepa_metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
            """GEPA-compatible metric that returns score + feedback."""
            score = drug_match_metric(gold, pred)
            gt_drugs = set(gold.gt_drugs)
            # Build feedback for GEPA's reflector
            if score == 1.0:
                feedback = "Correct prediction."
            else:
                pred_drugs = set()
                for opt_field in ["option_1", "option_2", "option_3"]:
                    opt_str = getattr(pred, opt_field, "")
                    pred_drugs.update(parse_dspy_option(opt_str))
                missed = gt_drugs - pred_drugs
                extra = pred_drugs - gt_drugs
                parts = []
                if missed:
                    parts.append(f"Missed drugs: {', '.join(sorted(missed))}")
                if extra:
                    parts.append(f"Extra drugs predicted: {', '.join(sorted(extra))}")
                feedback = ". ".join(parts) if parts else "Partial match but not exact."
            return dspy.Prediction(score=score, feedback=feedback)

        reflection_lm = dspy.LM(model, region_name="us-east-1", max_tokens=4096, temperature=1.0)
        optimizer = dspy.GEPA(
            metric=gepa_metric,
            auto="light",
            reflection_lm=reflection_lm,
        )
    else:
        raise ValueError(f"Unknown optimizer: {optimizer_name}")

    optimized = optimizer.compile(predictor, trainset=train_examples)

    # Eval optimized
    print("\nRunning optimized model on eval set...")
    optimized_scores = []
    optimized_results = []
    for ex in eval_examples:
        try:
            pred = optimized(clinical_notes=ex.clinical_notes)
            score = drug_match_metric(ex, pred)
            optimized_scores.append(score)
            optimized_results.append({
                "gt_drugs": ex.gt_drugs,
                "option_1": getattr(pred, "option_1", ""),
                "option_2": getattr(pred, "option_2", ""),
                "option_3": getattr(pred, "option_3", ""),
                "reasoning": getattr(pred, "reasoning", ""),
                "score": score,
            })
        except Exception as e:
            print(f"  [WARN] {e}")
            optimized_scores.append(0.0)
            optimized_results.append({"error": str(e), "score": 0.0})

    opt_exact = sum(1 for s in optimized_scores if s == 1.0)
    opt_mean = sum(optimized_scores) / len(optimized_scores) if optimized_scores else 0

    # Save results
    results = {
        "optimizer": optimizer_name,
        "model": model,
        "seed": seed,
        "train_n": len(train_examples),
        "eval_n": len(eval_examples),
        "baseline_exact": baseline_exact,
        "baseline_total": len(baseline_scores),
        "baseline_rate": baseline_exact / len(baseline_scores) if baseline_scores else 0,
        "optimized_exact": opt_exact,
        "optimized_total": len(optimized_scores),
        "optimized_rate": opt_exact / len(optimized_scores) if optimized_scores else 0,
        "per_case": optimized_results,
    }

    with open(os.path.join(output_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Save the optimized prompt for inspection
    try:
        optimized.save(os.path.join(output_dir, "optimized_program"))
    except Exception:
        pass

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"                  Exact match    Mean score")
    print(f"  Baseline:       {baseline_exact}/{len(baseline_scores)} ({baseline_exact/len(baseline_scores):.0%})         {baseline_mean:.3f}")
    print(f"  Optimized:      {opt_exact}/{len(optimized_scores)} ({opt_exact/len(optimized_scores):.0%})         {opt_mean:.3f}")
    print(f"\nOutput: {output_dir}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DSPy Baseline")
    parser.add_argument("--optimizer", type=str, default="bootstrap", choices=["bootstrap", "mipro", "gepa"])
    parser.add_argument("--model", type=str, default="bedrock/openai.gpt-oss-120b-1:0")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-bootstrapped", type=int, default=4)
    parser.add_argument("--feedback", action="store_true", help="Use neurologist-reviewed patients as train set")
    args = parser.parse_args()

    run_dspy(
        optimizer_name=args.optimizer,
        model=args.model,
        seed=args.seed,
        max_bootstrapped=args.max_bootstrapped,
        feedback=args.feedback,
    )
