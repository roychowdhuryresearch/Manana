"""Bayesian ensemble over NPCL rounds — regimen-level voting.

Each round produces 3 ranked prescription options. We collect all
candidates across K rounds (up to 3K ballots) and vote over complete
regimen sets. Uncertainty = concentration of votes on the winning regimen.

Usage:
    uv run python self_learning/run_ensemble.py
    uv run python self_learning/run_ensemble.py --top-k 5 --weighting softmax
"""

import argparse
import asyncio
import json
import math
import os
from collections import Counter
from datetime import datetime

from llm.client import LLMClient, DEFAULT_MODEL
from core.regimen_parser import parse_regimen
from self_learning.sampler import stratified_split
from schemas.output import DRUG_COLUMNS

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


def drugs_from_regimen(regimen: dict, option_key: str = "option_1") -> frozenset[str]:
    opt = regimen.get(option_key, {})
    drugs = opt.get("drugs", {})
    return frozenset(d for d, action in drugs.items() if action in ("continue", "start"))


def get_gt_key(case) -> str:
    visit_num = int(case.current_visit.split("_")[1])
    return f"{case.patient_id}__v{visit_num}"


async def run_ensemble(
    loop_dir: str | None = None,
    top_k: int = 5,
    weighting: str = "linear",
    model: str = DEFAULT_MODEL,
    seed: int = 42,
):
    if loop_dir is None:
        loop_dirs = sorted(
            [d for d in os.listdir(os.path.join(_HERE, "outputs")) if d.startswith("loop_")],
            reverse=True,
        )
        if not loop_dirs:
            print("No loop outputs found")
            return
        loop_dir = os.path.join(_HERE, "outputs", loop_dirs[0])

    output_dir = os.path.join(_HERE, "outputs", "ensemble",
                              f"ens_{datetime.now().strftime('%Y%m%d_%H%M')}")
    os.makedirs(output_dir, exist_ok=True)

    # Load round data
    with open(os.path.join(loop_dir, "eval_progression.json")) as f:
        eval_prog = json.load(f)
    with open(os.path.join(loop_dir, "full_run.json")) as f:
        full_run = json.load(f)

    # Build round info (skip baseline)
    rounds = []
    for ep in eval_prog:
        if isinstance(ep["round"], str):
            continue
        rd_idx = ep["round"]
        rd_data = full_run[rd_idx]
        rounds.append({
            "round": rd_idx,
            "learnings": rd_data.get("shared_learnings_after", []),
            "top3_rate": ep["top3_rate"],
            "top3_correct": ep["top3_correct"],
            "total": ep["total"],
        })

    # Select top-K by eval score
    rounds_sorted = sorted(rounds, key=lambda x: x["top3_rate"], reverse=True)
    selected = rounds_sorted[:top_k]

    # Compute weights
    if weighting == "uniform":
        for s in selected:
            s["weight"] = 1.0 / len(selected)
    elif weighting == "linear":
        total_score = sum(s["top3_rate"] for s in selected)
        for s in selected:
            s["weight"] = s["top3_rate"] / total_score
    elif weighting == "softmax":
        temperature = 5.0
        exp_scores = [math.exp(s["top3_rate"] * temperature) for s in selected]
        exp_sum = sum(exp_scores)
        for s, e in zip(selected, exp_scores):
            s["weight"] = e / exp_sum

    print(f"\n{'='*60}")
    print(f"BAYESIAN ENSEMBLE — REGIMEN-LEVEL VOTING")
    print(f"{'='*60}")
    print(f"Loop:       {loop_dir}")
    print(f"Top-K:      {top_k}")
    print(f"Weighting:  {weighting}")
    print(f"Selected rounds:")
    for s in selected:
        print(f"  R{s['round']}: {s['top3_rate']:.0%} (w={s['weight']:.3f}), {len(s['learnings'])} learnings")
    print(f"{'='*60}\n")

    # Load data
    client = LLMClient(model=model)
    split = stratified_split(cohort="csv", seed=seed)
    eval_cases = split["eval_cases"]
    gt_data = split["gt_data"]
    predictor_template = load_prompt("predictor_v0.txt")

    results = []
    ensemble_correct = 0
    total = 0

    for case_idx, case in enumerate(eval_cases):
        gt_entry = gt_data.get(get_gt_key(case))
        if not gt_entry or not gt_entry["prescribed"]:
            continue

        gt_drugs = frozenset(d.lower() for d in gt_entry["prescribed"])
        total += 1

        # Run predictor with each round's learnings (parallel)
        tasks = []
        for s in selected:
            prompt = build_predictor_prompt(predictor_template, s["learnings"])
            tasks.append(client.call(prompt, case.build_input_text()))

        responses = await asyncio.gather(*tasks)

        # Collect all regimen ballots with empirical rank prior
        # P(correct = Opt1) = 0.85, P(Opt2) = 0.11, P(Opt3) = 0.04
        RANK_PRIOR = {"option_1": 0.85, "option_2": 0.11, "option_3": 0.04}

        ballots = []  # list of (regimen_frozenset, weight)
        round_details = []

        for i, (_, raw) in enumerate(responses):
            if not raw:
                continue
            regimen = parse_regimen(raw)
            round_weight = selected[i]["weight"]
            round_opts = {}

            for opt_key in ["option_1", "option_2", "option_3"]:
                drug_set = drugs_from_regimen(regimen, opt_key)
                if drug_set:  # skip empty parses
                    ballot_weight = round_weight * RANK_PRIOR[opt_key]
                    ballots.append((drug_set, ballot_weight))
                    round_opts[opt_key] = sorted(drug_set)

            round_details.append({
                "round": selected[i]["round"],
                "weight": round_weight,
                **round_opts,
            })

        # Weighted vote over complete regimen sets
        regimen_votes = Counter()
        for drug_set, weight in ballots:
            regimen_votes[drug_set] += weight

        # Winner = highest weighted vote
        if regimen_votes:
            winner, winner_votes = regimen_votes.most_common(1)[0]
            total_votes = sum(regimen_votes.values())
            confidence = winner_votes / total_votes
        else:
            winner = frozenset()
            confidence = 0.0
            total_votes = 0.0

        ensemble_match = (winner == gt_drugs)
        if ensemble_match:
            ensemble_correct += 1

        # Any match — does GT appear anywhere in the ballots?
        any_match = gt_drugs in regimen_votes

        # Uncertainty metrics
        n_unique = len(regimen_votes)

        if (case_idx + 1) % 10 == 0:
            print(f"  Processed {case_idx + 1}/{len(eval_cases)}...")

        results.append({
            "patient_id": case.patient_id,
            "visit": int(case.current_visit.split("_")[1]),
            "gt": sorted(gt_drugs),
            "ensemble_pred": sorted(winner),
            "ensemble_match": ensemble_match,
            "any_match": any_match,
            "confidence": round(confidence, 3),
            "n_unique_regimens": n_unique,
            "vote_distribution": {
                str(sorted(k)): round(v, 3)
                for k, v in regimen_votes.most_common()
            },
            "is_poly": len(gt_drugs) > 1,
            "round_details": round_details,
        })

    await client.close()

    # Metrics
    any_match_total = sum(1 for r in results if r["any_match"])
    mono = [r for r in results if not r["is_poly"]]
    poly = [r for r in results if r["is_poly"]]

    # Calibration by confidence
    high_conf = [r for r in results if r["confidence"] >= 0.5]
    med_conf = [r for r in results if 0.3 <= r["confidence"] < 0.5]
    low_conf = [r for r in results if r["confidence"] < 0.3]

    # Selective abstention: sort by confidence, compute accuracy at each coverage level
    sorted_by_conf = sorted(results, key=lambda r: r["confidence"], reverse=True)
    coverage_accuracy = []
    running_correct = 0
    for i, r in enumerate(sorted_by_conf, 1):
        if r["ensemble_match"]:
            running_correct += 1
        coverage_accuracy.append({
            "coverage": round(i / total, 3),
            "accuracy": round(running_correct / i, 3),
            "confidence": r["confidence"],
        })

    # Save
    output = {
        "config": {
            "top_k": top_k,
            "weighting": weighting,
            "loop_dir": loop_dir,
        },
        "summary": {
            "total": total,
            "ensemble_correct": ensemble_correct,
            "ensemble_rate": round(ensemble_correct / total, 3) if total else 0,
            "any_match": any_match_total,
            "any_match_rate": round(any_match_total / total, 3) if total else 0,
        },
        "results": results,
        "coverage_accuracy": coverage_accuracy,
    }
    with open(os.path.join(output_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'='*60}")
    print(f"RESULTS — {weighting} weighting, top-{top_k} rounds")
    print(f"{'='*60}")
    print(f"Total cases: {total}")
    print(f"\n  Ensemble (majority regimen):  {ensemble_correct}/{total} ({ensemble_correct/total:.0%})")
    print(f"  Any-voted match:              {any_match_total}/{total} ({any_match_total/total:.0%})")
    print(f"  Best single round (R{selected[0]['round']}):      {selected[0]['top3_correct']}/{selected[0]['total']} ({selected[0]['top3_rate']:.0%})")

    print(f"\n  Mono: {sum(1 for r in mono if r['ensemble_match'])}/{len(mono)}")
    print(f"  Poly: {sum(1 for r in poly if r['ensemble_match'])}/{len(poly)}")

    print(f"\n  Calibration by confidence:")
    for label, cases in [("High (>=0.5)", high_conf), ("Med (0.3-0.5)", med_conf), ("Low (<0.3)", low_conf)]:
        if cases:
            acc = sum(1 for c in cases if c["ensemble_match"]) / len(cases)
            print(f"    {label}: {len(cases)} cases, accuracy {acc:.0%}")

    print(f"\n  Selective prediction (coverage → accuracy):")
    for target_cov in [0.25, 0.50, 0.75, 1.0]:
        idx = min(int(target_cov * total) - 1, len(coverage_accuracy) - 1)
        if idx >= 0:
            ca = coverage_accuracy[idx]
            print(f"    {ca['coverage']:.0%} coverage → {ca['accuracy']:.0%} accuracy (conf>={ca['confidence']:.2f})")

    print(f"\n  Mean confidence: {sum(r['confidence'] for r in results)/len(results):.3f}")
    print(f"  Mean unique regimens: {sum(r['n_unique_regimens'] for r in results)/len(results):.1f}")

    print(f"\nOutput: {output_dir}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bayesian Ensemble over NPCL Rounds")
    parser.add_argument("--loop-dir", type=str, default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--weighting", type=str, default="linear", choices=["uniform", "linear", "softmax"])
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    asyncio.run(run_ensemble(
        loop_dir=args.loop_dir,
        top_k=args.top_k,
        weighting=args.weighting,
        model=args.model,
        seed=args.seed,
    ))
