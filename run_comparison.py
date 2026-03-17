"""Run multi-agent pipeline + single-agent baseline on N patients × 3 visits.

Outputs side-by-side comparison with per-agent reasoning traces.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

from llm.client import LLMClient, DEFAULT_MODEL
from data.loader import load_all_cases, load_raw_data, build_patient_case, VISIT_ORDER
from orchestrator.pipeline import ConsiliumPipeline
from orchestrator.synthesis import parse_epileptologist_options
from schemas.output import DRUG_COLUMNS, ALLOWED_ACTIONS
from evaluation.grader import load_ground_truth, extract_prescribed_set, extract_prediction_set, jaccard_similarity
from baseline.predict import parse_options

import re


def format_drugs(drugs: list[dict]) -> str:
    return ", ".join(f"{d['drug']}:{d['action']}" for d in drugs)


def print_separator(char="=", width=80):
    print(char * width)


def print_header(text, char="=", width=80):
    print()
    print(char * width)
    print(f"  {text}")
    print(char * width)


async def run_comparison(
    n_patients: int = 5,
    model: str = DEFAULT_MODEL,
):
    output_dir = os.path.join("outputs", "comparison")
    os.makedirs(output_dir, exist_ok=True)

    client = LLMClient(model=model)
    pipeline = ConsiliumPipeline(
        llm_client=client,
        enable_debate=True,
        format_output=False,  # We'll inspect raw agent outputs
    )

    # Load baseline prompt
    baseline_prompt_path = os.path.join("baseline", "prompts", "predict_prompt.txt")
    with open(baseline_prompt_path, encoding="utf-8") as f:
        baseline_system_prompt = f.read()

    # Load ground truth
    gt = load_ground_truth()

    # Load raw data for building cases across all visits
    split_results, clean_output, drug_gt, pid_to_row = load_raw_data()

    # Pick first N patients that have data for all 3 visits
    patient_ids = []
    for pid in split_results:
        has_all = all(
            split_results[pid].get(v, {}).get("input_text", "").strip()
            for v in VISIT_ORDER
        )
        if has_all:
            patient_ids.append(pid)
        if len(patient_ids) >= n_patients:
            break

    print_header(f"CONSILIUM COMPARISON RUN — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Model:    {model}")
    print(f"  Patients: {len(patient_ids)}")
    print(f"  Visits:   3 per patient ({len(patient_ids) * 3} total cases)")
    print(f"  Output:   {output_dir}/")
    print_separator()

    all_results = {}

    for pid in patient_ids:
        all_results[pid] = {}

        for visit_name in VISIT_ORDER:
            visit_num = int(visit_name.split("_")[1])

            case = build_patient_case(
                pid, visit_name, split_results, clean_output, drug_gt, pid_to_row,
            )
            if case is None:
                continue

            print_header(f"PATIENT: {pid} | {visit_name}", char="-")

            # Ground truth
            gt_entry = gt.get(pid, {}).get(visit_name, {})
            gt_drugs = extract_prescribed_set(gt_entry)
            print(f"  Ground truth: {', '.join(sorted(gt_drugs)) if gt_drugs else '(none)'}")
            print()

            # ── Run baseline ──
            print("  [Baseline] Running single-agent prediction...")
            input_text = case.build_input_text()
            baseline_thinking, baseline_raw = await client.call(baseline_system_prompt, input_text)
            baseline_options = parse_options(baseline_raw)

            # ── Run multi-agent ──
            print("  [Multi-agent] Running Consilium pipeline...")
            recommendation, trace = await pipeline.run(case)

            # ── Display results ──
            print()
            print(f"  {'─' * 70}")
            print(f"  PHASE 1 — Independent Specialist Assessments")
            print(f"  {'─' * 70}")

            for agent_name, resp in trace.phase1_responses.items():
                print(f"\n  [{resp.agent_role}]")
                if resp.findings:
                    for f in resp.findings:
                        conf = f"(conf: {f.confidence:.1f})" if f.confidence else ""
                        print(f"    Finding: [{f.category}] {f.detail} {conf}")
                if resp.concerns:
                    for c in resp.concerns:
                        drugs = ", ".join(c.affected_drugs) if c.affected_drugs else "-"
                        print(f"    Concern [{c.severity.value}]: {c.description} (drugs: {drugs})")
                if resp.recommended_drugs:
                    print(f"    Recommends: {', '.join(resp.recommended_drugs)}")
                if resp.contraindicated_drugs:
                    print(f"    Contraindicates: {', '.join(resp.contraindicated_drugs)}")

            # Conflicts
            if trace.detected_conflicts:
                print(f"\n  {'─' * 70}")
                print(f"  PHASE 1.5 — Detected Conflicts")
                print(f"  {'─' * 70}")
                for conflict in trace.detected_conflicts:
                    print(f"    [{conflict.conflict_type}] {conflict.description}")
                    print(f"    Resolution: {conflict.resolution}")

            # Epileptologist
            if trace.epileptologist_response:
                print(f"\n  {'─' * 70}")
                print(f"  PHASE 2 — Epileptologist's Plan")
                print(f"  {'─' * 70}")
                # Extract just the options section
                epi_raw = trace.epileptologist_response.raw_output
                sec2 = re.search(r'---\s*SECTION\s*2.*?---\s*(.*?)$', epi_raw, re.DOTALL | re.IGNORECASE)
                if sec2:
                    for line in sec2.group(1).strip().split('\n')[:20]:
                        print(f"    {line}")
                else:
                    print(f"    {epi_raw[:500]}")

            # Pharmacologist
            if trace.pharmacologist_response:
                print(f"\n  {'─' * 70}")
                print(f"  PHASE 3 — Pharmacologist Review")
                print(f"  {'─' * 70}")
                pharm = trace.pharmacologist_response
                if pharm.concerns:
                    for c in pharm.concerns:
                        drugs = ", ".join(c.affected_drugs) if c.affected_drugs else "-"
                        print(f"    [{c.severity.value}] {c.description}")
                        print(f"      Drugs: {drugs} | Rec: {c.recommendation}")
                else:
                    print(f"    No concerns raised.")

            # Debate
            if trace.debate_triggered:
                print(f"\n  {'─' * 70}")
                print(f"  PHASE 3.5 — Debate ({len(trace.debate_rounds)} rounds)")
                print(f"  {'─' * 70}")
                for rnd in trace.debate_rounds:
                    print(f"    Round {rnd.round_number}:")
                    print(f"      Resolved: {rnd.resolved_concerns or 'none'}")
                    print(f"      Unresolved: {rnd.unresolved_concerns or 'none'}")

            # ── Side-by-side comparison ──
            print(f"\n  {'─' * 70}")
            print(f"  COMPARISON: Baseline vs Multi-Agent")
            print(f"  {'─' * 70}")
            print(f"  Ground truth: {', '.join(sorted(gt_drugs)) if gt_drugs else '(none)'}")
            print()

            # Baseline options
            print(f"  BASELINE (single-agent):")
            for n in [1, 2, 3]:
                opt = baseline_options.get(f"option_{n}", {})
                drugs = opt.get("drugs", [])
                label = opt.get("label", "")
                pred_set = set(d["drug"] for d in drugs if d.get("action") in ("continue", "start"))
                jac = jaccard_similarity(pred_set, gt_drugs) if gt_drugs else 0.0
                exact = "EXACT" if pred_set == gt_drugs and gt_drugs else ""
                print(f"    Option {n}: {label}")
                print(f"      Drugs: {format_drugs(drugs) if drugs else '(none)'}")
                print(f"      Jaccard: {jac:.2f} {exact}")

            # Multi-agent options
            print(f"\n  MULTI-AGENT (consilium):")
            ma_options = parse_epileptologist_options(
                trace.epileptologist_response.raw_output if trace.epileptologist_response else ""
            )
            for opt in ma_options:
                pred_set = set(d.drug for d in opt.drugs if d.action in ("continue", "start"))
                jac = jaccard_similarity(pred_set, gt_drugs) if gt_drugs else 0.0
                exact = "EXACT" if pred_set == gt_drugs and gt_drugs else ""
                drugs_str = ", ".join(f"{d.drug}:{d.action}" for d in opt.drugs)
                print(f"    Option {opt.rank}: {opt.label}")
                print(f"      Drugs: {drugs_str if drugs_str else '(none)'}")
                print(f"      Jaccard: {jac:.2f} {exact}")

            print(f"\n  Agreement score: {trace.agreement_score:.2f}")
            print(f"  Concerns raised: {trace.total_concerns_raised} (critical: {trace.critical_concerns})")
            print(f"  Debate triggered: {trace.debate_triggered}")

            # Store results
            all_results[pid][visit_name] = {
                "gt": sorted(gt_drugs),
                "baseline": baseline_options,
                "multi_agent": {
                    f"option_{opt.rank}": opt.to_comparable()
                    for opt in ma_options
                },
                "trace_summary": {
                    "agents_activated": trace.agents_activated,
                    "conflicts": len(trace.detected_conflicts),
                    "debate_triggered": trace.debate_triggered,
                    "agreement_score": trace.agreement_score,
                    "total_concerns": trace.total_concerns_raised,
                },
            }

    await client.close()

    # Save full results
    results_path = os.path.join(output_dir, "comparison_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    # ── Summary ──
    print_header("SUMMARY")
    baseline_exact = 0
    ma_exact = 0
    baseline_jacs = []
    ma_jacs = []
    total = 0

    for pid, visits in all_results.items():
        for visit_name, data in visits.items():
            gt_drugs = set(data["gt"])
            if not gt_drugs:
                continue
            total += 1

            # Best baseline Jaccard
            best_b_jac = 0.0
            b_exact = False
            for n in [1, 2, 3]:
                opt = data["baseline"].get(f"option_{n}", {})
                pred = set(d["drug"] for d in opt.get("drugs", []) if d.get("action") in ("continue", "start"))
                jac = jaccard_similarity(pred, gt_drugs)
                best_b_jac = max(best_b_jac, jac)
                if pred == gt_drugs:
                    b_exact = True
            if b_exact:
                baseline_exact += 1
            baseline_jacs.append(best_b_jac)

            # Best MA Jaccard
            best_m_jac = 0.0
            m_exact = False
            for key, opt in data["multi_agent"].items():
                pred = set(d["drug"] for d in opt.get("drugs", []) if d.get("action") in ("continue", "start"))
                jac = jaccard_similarity(pred, gt_drugs)
                best_m_jac = max(best_m_jac, jac)
                if pred == gt_drugs:
                    m_exact = True
            if m_exact:
                ma_exact += 1
            ma_jacs.append(best_m_jac)

    print(f"  Total cases: {total}")
    print()
    print(f"  {'Metric':<25s} {'Baseline':>12s} {'Multi-Agent':>12s}")
    print(f"  {'-'*25} {'-'*12} {'-'*12}")
    print(f"  {'Exact match rate':<25s} {baseline_exact/total if total else 0:>11.1%} {ma_exact/total if total else 0:>11.1%}")
    print(f"  {'Mean Jaccard':<25s} {sum(baseline_jacs)/len(baseline_jacs) if baseline_jacs else 0:>12.3f} {sum(ma_jacs)/len(ma_jacs) if ma_jacs else 0:>12.3f}")
    print(f"  {'Exact matches':<25s} {baseline_exact:>12d} {ma_exact:>12d}")
    print()
    print(f"  Results saved to {results_path}")
    print_separator()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Comparison run: multi-agent vs baseline")
    parser.add_argument("--patients", type=int, default=5, help="Number of patients")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    args = parser.parse_args()

    asyncio.run(run_comparison(n_patients=args.patients, model=args.model))
