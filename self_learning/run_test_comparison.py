"""Compare best-single-round vs rank-prior ensemble on fresh test cases.

Uses cases NOT in train or eval — a true held-out test set.

Usage:
    uv run python self_learning/run_test_comparison.py --n-test 50
"""

import argparse
import asyncio
import json
import math
import os
import random
from collections import Counter
from datetime import datetime

from llm.client import LLMClient, DEFAULT_MODEL
from core.regimen_parser import parse_regimen
from self_learning.sampler import stratified_split
from scripts.loader import load_cases, load_ground_truth

_HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(_HERE, "prompts")

# Empirical rank prior from training data
RANK_PRIOR = {"option_1": 0.85, "option_2": 0.11, "option_3": 0.04}


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


async def run_comparison(
    n_test: int = 50,
    top_k: int = 5,
    cohort: str = "csv",
    loop_dir: str | None = None,
    model: str = DEFAULT_MODEL,
    seed: int = 42,
):
    if loop_dir is None:
        loop_dirs = sorted(
            [d for d in os.listdir(os.path.join(_HERE, "outputs")) if d.startswith("loop_")],
            reverse=True,
        )
        loop_dir = os.path.join(_HERE, "outputs", loop_dirs[0])

    output_dir = os.path.join(_HERE, "outputs", "test_comparison",
                              f"test_{datetime.now().strftime('%Y%m%d_%H%M')}")
    os.makedirs(output_dir, exist_ok=True)

    # Load round data
    with open(os.path.join(loop_dir, "eval_progression.json")) as f:
        eval_prog = json.load(f)
    with open(os.path.join(loop_dir, "full_run.json")) as f:
        full_run = json.load(f)

    # Select top-K rounds (linear weights)
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
        })
    rounds_sorted = sorted(rounds, key=lambda x: x["top3_rate"], reverse=True)
    selected = rounds_sorted[:top_k]

    total_score = sum(s["top3_rate"] for s in selected)
    for s in selected:
        s["weight"] = s["top3_rate"] / total_score

    best_round = selected[0]

    # Build test set
    split = stratified_split(cohort="csv", seed=seed)
    used_pids = set(c.patient_id for c in split["train_cases"]) | set(c.patient_id for c in split["eval_cases"])

    if cohort == "pdf":
        # PDF cohort — entirely separate, no overlap filtering needed
        gt_data = load_ground_truth(cohort="pdf")
        all_cases = load_cases(cohort="pdf")
        remaining = [c for c in all_cases
                     if gt_data.get(get_gt_key(c), {}).get("prescribed")]
    else:
        # CSV cohort — exclude train/eval patients
        gt_data = load_ground_truth(cohort="csv")
        all_cases = load_cases(cohort="csv")
        remaining = [c for c in all_cases
                     if c.patient_id not in used_pids
                     and gt_data.get(get_gt_key(c), {}).get("prescribed")]

    random.seed(seed)
    random.shuffle(remaining)
    test_cases = remaining[:n_test]

    poly_n = sum(1 for c in test_cases if len(gt_data.get(get_gt_key(c), {}).get("prescribed", [])) > 1)
    print(f"\n{'='*60}")
    print(f"TEST COMPARISON: Best Round vs Ensemble")
    print(f"{'='*60}")
    print(f"Cohort:        {cohort}")
    print(f"Test cases:    {len(test_cases)} (mono={len(test_cases)-poly_n}, poly={poly_n})")
    print(f"Best round:    R{best_round['round']} ({best_round['top3_rate']:.0%} on eval)")
    print(f"Ensemble:      top-{top_k} rounds, rank prior (0.85/0.11/0.04), deduped")
    print(f"{'='*60}\n")

    client = LLMClient(model=model)
    predictor_template = load_prompt("predictor_v0.txt")

    results = []

    for case_idx, case in enumerate(test_cases):
        gt_entry = gt_data.get(get_gt_key(case))
        gt_drugs = frozenset(d.lower() for d in gt_entry["prescribed"])

        patient_input = case.build_input_text()

        # Run all K rounds in parallel
        tasks = []
        for s in selected:
            prompt = build_predictor_prompt(predictor_template, s["learnings"])
            tasks.append(client.call(prompt, patient_input))

        responses = await asyncio.gather(*tasks)

        # --- Best single round (R13 = selected[0]) ---
        best_raw = responses[0][1] if responses[0][1] else ""
        best_regimen = parse_regimen(best_raw)
        best_top1 = drugs_from_regimen(best_regimen, "option_1")
        best_top3 = any(
            drugs_from_regimen(best_regimen, f"option_{n}") == gt_drugs
            for n in [1, 2, 3]
        )

        # --- Ensemble with rank prior (deduplicated within round) ---
        ballots = []
        for i, (_, raw) in enumerate(responses):
            if not raw:
                continue
            regimen = parse_regimen(raw)
            round_weight = selected[i]["weight"]

            # Deduplicate: each unique regimen from this round gets credited
            # once, at its highest rank prior
            seen_in_round = {}  # regimen -> best rank prior
            for opt_key in ["option_1", "option_2", "option_3"]:
                drug_set = drugs_from_regimen(regimen, opt_key)
                if drug_set:
                    rank_p = RANK_PRIOR[opt_key]
                    if drug_set not in seen_in_round or rank_p > seen_in_round[drug_set]:
                        seen_in_round[drug_set] = rank_p

            # Redistribute: unique regimens share the round's weight
            # proportional to their rank priors
            total_rank = sum(seen_in_round.values())
            for drug_set, rank_p in seen_in_round.items():
                ballot_weight = round_weight * (rank_p / total_rank)
                ballots.append((drug_set, ballot_weight))

        regimen_votes = Counter()
        for drug_set, weight in ballots:
            regimen_votes[drug_set] += weight

        if regimen_votes:
            ens_winner, ens_winner_votes = regimen_votes.most_common(1)[0]
            ens_total_votes = sum(regimen_votes.values())
            ens_confidence = ens_winner_votes / ens_total_votes
        else:
            ens_winner = frozenset()
            ens_confidence = 0.0

        ens_match = (ens_winner == gt_drugs)
        ens_any = gt_drugs in regimen_votes

        # Top-3 from ensemble (top 3 voted regimens)
        ens_top3_match = any(r == gt_drugs for r, _ in regimen_votes.most_common(3))

        results.append({
            "patient_id": case.patient_id,
            "visit": int(case.current_visit.split("_")[1]),
            "gt": sorted(gt_drugs),
            "is_poly": len(gt_drugs) > 1,
            "best_round_pred": sorted(best_top1),
            "best_round_top3": best_top3,
            "ens_pred": sorted(ens_winner),
            "ens_match": ens_match,
            "ens_top3": ens_top3_match,
            "ens_any": ens_any,
            "ens_confidence": round(ens_confidence, 3),
        })

        if (case_idx + 1) % 10 == 0:
            print(f"  Processed {case_idx + 1}/{len(test_cases)}...")

    await client.close()

    # Metrics
    n = len(results)
    best_top3_n = sum(1 for r in results if r["best_round_top3"])
    ens_top1_n = sum(1 for r in results if r["ens_match"])
    ens_top3_n = sum(1 for r in results if r["ens_top3"])
    ens_any_n = sum(1 for r in results if r["ens_any"])

    mono = [r for r in results if not r["is_poly"]]
    poly = [r for r in results if r["is_poly"]]

    # Confidence analysis
    correct = [r for r in results if r["ens_match"]]
    wrong = [r for r in results if not r["ens_match"]]
    correct_confs = sorted([r["ens_confidence"] for r in correct]) if correct else []
    wrong_confs = sorted([r["ens_confidence"] for r in wrong]) if wrong else []

    # Selective prediction
    sorted_by_conf = sorted(results, key=lambda r: r["ens_confidence"], reverse=True)
    coverage_acc = []
    running = 0
    for i, r in enumerate(sorted_by_conf, 1):
        if r["ens_match"]:
            running += 1
        coverage_acc.append({"cov": i/n, "acc": running/i, "conf": r["ens_confidence"]})

    # Save
    with open(os.path.join(output_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Print
    print(f"\n{'='*60}")
    print(f"RESULTS ON {n} FRESH TEST CASES")
    print(f"{'='*60}")

    print(f"\n  {'Method':<30} {'Top-1':>8} {'Top-3':>8}")
    print(f"  {'-'*48}")
    print(f"  {'Best round (R'+str(best_round['round'])+')':<30} {'—':>8} {best_top3_n}/{n} ({best_top3_n/n:.0%})")
    print(f"  {'Ensemble (rank prior)':<30} {ens_top1_n}/{n} ({ens_top1_n/n:.0%}) {ens_top3_n}/{n} ({ens_top3_n/n:.0%})")
    print(f"  {'Ensemble (any voted)':<30} {'—':>8} {ens_any_n}/{n} ({ens_any_n/n:.0%})")

    print(f"\n  Mono: best={sum(1 for r in mono if r['best_round_top3'])}/{len(mono)}  ens={sum(1 for r in mono if r['ens_match'])}/{len(mono)}")
    print(f"  Poly: best={sum(1 for r in poly if r['best_round_top3'])}/{len(poly)}  ens={sum(1 for r in poly if r['ens_match'])}/{len(poly)}")

    print(f"\n  Confidence (ensemble):")
    if correct_confs:
        print(f"    Correct: mean={sum(correct_confs)/len(correct_confs):.3f}  median={correct_confs[len(correct_confs)//2]:.3f}")
    if wrong_confs:
        print(f"    Wrong:   mean={sum(wrong_confs)/len(wrong_confs):.3f}  median={wrong_confs[len(wrong_confs)//2]:.3f}")

    print(f"\n  Precision at confidence thresholds:")
    print(f"  {'Threshold':<12} {'Correct':<10} {'Wrong':<10} {'Precision':<12} {'Coverage':<10}")
    print(f"  {'-'*55}")
    for t in [0.95, 0.90, 0.85, 0.80, 0.70, 0.50]:
        c = sum(1 for x in correct_confs if x >= t)
        w = sum(1 for x in wrong_confs if x >= t)
        tot = c + w
        prec = c / tot if tot else 0
        print(f"  {t:<12.2f} {c:<10} {w:<10} {prec:<12.0%} {tot}/{n} ({tot/n:.0%})")

    print(f"\n  Selective prediction:")
    for target in [0.25, 0.50, 0.75, 1.0]:
        idx = min(int(target * n) - 1, len(coverage_acc) - 1)
        if idx >= 0:
            ca = coverage_acc[idx]
            print(f"    {ca['cov']:.0%} coverage → {ca['acc']:.0%} accuracy")

    print(f"\nOutput: {output_dir}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-test", type=int, default=100)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--cohort", type=str, default="csv", choices=["csv", "pdf"])
    parser.add_argument("--loop-dir", type=str, default=None)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    asyncio.run(run_comparison(
        n_test=args.n_test,
        top_k=args.top_k,
        cohort=args.cohort,
        loop_dir=args.loop_dir,
        model=args.model,
        seed=args.seed,
    ))
