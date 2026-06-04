"""Component ablations for Manana.

Supported ablations match the historical run folders:
- no-buffer
- no-inspector
- no-architect
- no-quorum

Usage:
    uv run python -m manana.ablations.run --config configs/uganda_example.yaml --system single --ablation no-buffer
    uv run python -m manana.ablations.run --config configs/uganda_example.yaml --system multi --ablation no-inspector
"""

from __future__ import annotations

import argparse
import asyncio
import os

from lib.llm import DEFAULT_MODEL, LLMClient
from manana.ablations.common import (
    best_matching_option,
    get_gt_key,
    get_visit_num,
    load_ablation_prompt,
    load_split,
    make_output_dir,
    parsed_options,
    print_header,
    summarize_eval,
    write_json,
)
from manana.prompts import load_rendered_prompt
from manana.single import run_loop as single_loop
from manana.multi import run_loop as multi_loop


COMPONENT_ABLATIONS = ("no-buffer", "no-inspector", "no-architect", "no-quorum")


def build_single_no_buffer_architect_input(
    shared_learnings: list[str],
    batch_results: list[dict],
    batch_idx: int,
) -> str:
    parts = ["CURRENT LEARNINGS:"]
    if shared_learnings:
        parts.extend(f"{i}. {rule}" for i, rule in enumerate(shared_learnings, 1))
    else:
        parts.append("(none yet)")

    parts.append("\nCANDIDATE BUFFER (all previous rounds):")
    parts.append("(disabled for no-buffer ablation)")
    parts.append(f"\n\nINSPECTOR REPORTS FROM THIS BATCH (Round {batch_idx}):\n")
    for r in batch_results:
        parts.append(f"--- Patient: {r['patient_id']} V{r['visit']} (poly={r['is_poly']}) ---")
        parts.append(f"GT: {r['gt_drugs']} | Match: {r['any_match']}")
        parts.append(r["inspector_report"])
        parts.append("")
    return "\n".join(parts)


def build_multi_no_buffer_architect_input(
    batch_results: list[dict],
    agents: dict[str, str],
    batch_idx: int,
) -> str:
    parts = ["CANDIDATE BUFFER (all previous rounds):"]
    parts.append("(disabled for no-buffer ablation)")
    parts.append(f"\n\nINSPECTOR REPORTS FROM THIS BATCH (Round {batch_idx}):\n")
    for r in batch_results:
        parts.append(f"--- Patient: {r['patient_id']} V{r['visit']} (poly={r['is_poly']}) ---")
        parts.append(f"GT: {r['gt_drugs']} | Match: {r['any_match']}")
        parts.append(r["inspector_report"])
        parts.append("")

    parts.append("\nCURRENT ACTIVE AGENTS:")
    if agents:
        for name, prompt in agents.items():
            parts.append(f"\n[{name}]\n{prompt}")
        cap_note = "  AT CAP - prune before spawning." if len(agents) >= multi_loop.MAX_AGENTS else ""
        parts.append(f"\nCurrently active: {len(agents)} agents.{cap_note}")
    else:
        parts.append("(none - no agents yet)")
    return "\n".join(parts)


def build_single_raw_architect_input(
    shared_learnings: list[str],
    batch_results: list[dict],
    batch_idx: int,
) -> str:
    parts = ["CURRENT LEARNINGS:"]
    if shared_learnings:
        parts.extend(f"{i}. {rule}" for i, rule in enumerate(shared_learnings, 1))
    else:
        parts.append("(none yet)")

    parts.append(f"\nRAW CASES FROM THIS BATCH (Round {batch_idx}):\n")
    for r in batch_results:
        parts.append(f"--- Patient: {r['patient_id']} V{r['visit']} (poly={r['is_poly']}) ---")
        parts.append(f"GT: {r['gt_drugs']} | Match: {r['any_match']}")
        parts.append("\nPATIENT CLINICAL NOTES:")
        parts.append(r["patient_notes"])
        parts.append("\nSYSTEM PREDICTION:")
        parts.append(r["predictor_raw"])
        parts.append("")
    return "\n".join(parts)


def build_multi_raw_architect_input(
    batch_results: list[dict],
    agents: dict[str, str],
    batch_idx: int,
) -> str:
    parts = [f"RAW CASES FROM THIS BATCH (Round {batch_idx}):\n"]
    for r in batch_results:
        parts.append(f"--- Patient: {r['patient_id']} V{r['visit']} (poly={r['is_poly']}) ---")
        parts.append(f"GT: {r['gt_drugs']} | Match: {r['any_match']}")
        parts.append("\nPATIENT CLINICAL NOTES:")
        parts.append(r["patient_notes"])
        if r.get("agent_outputs"):
            parts.append("\nSPECIALIST AGENT OUTPUTS:")
            for name, output in r["agent_outputs"].items():
                parts.append(f"\n[{name}]\n{multi_loop.clean_agent_output(output)}")
        parts.append("\nSYSTEM PREDICTION:")
        parts.append(r["predictor_raw"])
        parts.append("")

    parts.append("\nCURRENT ACTIVE AGENTS:")
    if agents:
        for name, prompt in agents.items():
            parts.append(f"\n[{name}]\n{prompt}")
        cap_note = "  AT CAP - prune before spawning." if len(agents) >= multi_loop.MAX_AGENTS else ""
        parts.append(f"\nCurrently active: {len(agents)} agents.{cap_note}")
    else:
        parts.append("(none - no agents yet)")
    return "\n".join(parts)


async def run_single_raw_case(
    client: LLMClient,
    predictor_template: str,
    shared_learnings: list[str],
    case,
    gt_data: dict,
    temperature: float | None,
) -> dict | None:
    gt_entry = gt_data.get(get_gt_key(case))
    if not gt_entry or not gt_entry["prescribed"]:
        return None

    gt_drugs = {d.lower() for d in gt_entry["prescribed"]}
    patient_notes = case.build_input_text()
    predictor_prompt = single_loop.build_predictor_prompt(predictor_template, shared_learnings)
    _, pred_raw = await client.call(predictor_prompt, patient_notes, temperature=temperature)
    if not pred_raw:
        print(f"  [WARN] Predictor failure for {case.patient_id} - skipping")
        return None

    options = parsed_options(pred_raw)
    best_option = best_matching_option(options, gt_drugs)
    return {
        "patient_id": case.patient_id,
        "visit": get_visit_num(case),
        "gt_drugs": sorted(gt_drugs),
        "pred_options": options,
        "pred_option1_drugs": options["option_1"],
        "is_poly": len(gt_drugs) > 1,
        "any_match": best_option is not None,
        "best_option": best_option,
        "patient_notes": patient_notes,
        "predictor_raw": pred_raw,
    }


async def run_multi_raw_case(
    client: LLMClient,
    agents: dict[str, str],
    predictor_template: str,
    case,
    gt_data: dict,
) -> dict | None:
    gt_entry = gt_data.get(get_gt_key(case))
    if not gt_entry or not gt_entry["prescribed"]:
        return None

    gt_drugs = {d.lower() for d in gt_entry["prescribed"]}
    patient_notes = case.build_input_text()

    agent_outputs = {}
    if agents:
        agent_tasks = {name: multi_loop.run_agent(client, prompt, patient_notes) for name, prompt in agents.items()}
        results = await asyncio.gather(*agent_tasks.values())
        agent_outputs = dict(zip(agent_tasks.keys(), results))

    predictor_prompt = multi_loop.build_predictor_prompt(predictor_template, agent_outputs)
    _, pred_raw = await client.call(predictor_prompt, patient_notes)
    if not pred_raw:
        print(f"  [WARN] Predictor failure for {case.patient_id} - skipping")
        return None

    options = parsed_options(pred_raw)
    best_option = best_matching_option(options, gt_drugs)
    return {
        "patient_id": case.patient_id,
        "visit": get_visit_num(case),
        "gt_drugs": sorted(gt_drugs),
        "pred_options": options,
        "pred_option1_drugs": options["option_1"],
        "is_poly": len(gt_drugs) > 1,
        "any_match": best_option is not None,
        "best_option": best_option,
        "agent_outputs": agent_outputs,
        "patient_notes": patient_notes,
        "predictor_raw": pred_raw,
    }


async def run_single(args) -> None:
    configured = load_split(args.config, args.seed)
    output_dir = make_output_dir(configured.config, "single", args.ablation, args.model, args.seed, configured.tag)
    client = LLMClient(model=args.model)

    predictor_template = load_rendered_prompt("single", "predictor", configured.config)
    inspector_prompt = load_rendered_prompt("single", "inspector", configured.config)
    architect_prompt = load_rendered_prompt("single", "architect", configured.config)
    if args.ablation == "no-inspector":
        architect_prompt = load_ablation_prompt("architect_no_inspector_single.txt")
    elif args.ablation == "no-quorum":
        architect_prompt = load_ablation_prompt("architect_no_quorum_single.txt")

    shared_learnings: list[str] = []
    buffer: dict[int, list[str]] = {}
    rounds: list[dict] = []
    eval_progression: list[dict] = []

    n_batches = (len(configured.train_cases) + args.batch_size - 1) // args.batch_size
    if args.rounds is not None:
        n_batches = min(n_batches, args.rounds)

    print_header("MANANA COMPONENT ABLATION", [
        ("System:", "single"),
        ("Ablation:", args.ablation),
        ("Config:", args.config),
        ("Train:", configured.train_label),
        ("Eval:", configured.eval_label),
        ("Batches:", f"{n_batches} x {args.batch_size}"),
        ("Output:", output_dir),
    ])

    baseline_eval = await single_loop.run_eval(
        client, predictor_template, shared_learnings, configured.eval_cases, configured.gt_data, args.temp,
    )
    eval_progression.append({
        "round": "baseline",
        "shared_learnings_size": 0,
        "shared_learnings": [],
        **{k: v for k, v in baseline_eval.items() if k != "per_case"},
        "per_case": baseline_eval["per_case"],
    })
    print(f"  [Eval baseline] {summarize_eval(baseline_eval)}")

    for batch_idx in range(n_batches):
        batch_cases = configured.train_cases[batch_idx * args.batch_size:(batch_idx + 1) * args.batch_size]
        print(f"\nROUND {batch_idx} - {len(batch_cases)} cases - {len(shared_learnings)} rules")

        if args.ablation == "no-inspector":
            tasks = [
                run_single_raw_case(client, predictor_template, shared_learnings, case, configured.gt_data, args.temp)
                for case in batch_cases
            ]
        else:
            tasks = [
                single_loop.run_train_case(
                    client, predictor_template, inspector_prompt, shared_learnings, case, configured.gt_data, args.temp,
                )
                for case in batch_cases
            ]
        results = await asyncio.gather(*tasks)
        batch_results = [r for r in results if r is not None]
        new_candidates = [r.get("candidate_learning") for r in batch_results if r.get("candidate_learning")]
        additions: list[str] = []
        architect_output = ""

        if args.ablation == "no-architect":
            seen = {rule.lower() for rule in shared_learnings}
            for candidate in new_candidates:
                key = candidate.lower()
                if key not in seen:
                    shared_learnings.append(candidate)
                    additions.append(candidate)
                    seen.add(key)
        else:
            if args.ablation == "no-buffer":
                architect_input = build_single_no_buffer_architect_input(shared_learnings, batch_results, batch_idx)
            elif args.ablation == "no-inspector":
                architect_input = build_single_raw_architect_input(shared_learnings, batch_results, batch_idx)
            else:
                architect_input = single_loop.build_architect_input(shared_learnings, buffer, batch_results, batch_idx)

            _, architect_output = await client.call(architect_prompt, architect_input, temperature=args.temp)
            if architect_output:
                remaining_slots = max(0, single_loop.MAX_SINGLE_RULES - len(shared_learnings))
                additions = single_loop.parse_architect_additions(architect_output)[:min(1, remaining_slots)]
                shared_learnings.extend(additions)

        if args.ablation not in ("no-buffer", "no-inspector"):
            buffer[batch_idx] = new_candidates

        round_eval = await single_loop.run_eval(
            client, predictor_template, shared_learnings, configured.eval_cases, configured.gt_data, args.temp,
        )
        eval_progression.append({
            "round": batch_idx,
            "shared_learnings_size": len(shared_learnings),
            "shared_learnings": list(shared_learnings),
            "buffer_size": sum(len(v) for v in buffer.values()),
            "additions_this_round": additions,
            **{k: v for k, v in round_eval.items() if k != "per_case"},
            "per_case": round_eval["per_case"],
        })
        print(f"  [Eval] {summarize_eval(round_eval)}")

        round_data = {
            "round": batch_idx,
            "n_cases": len(batch_cases),
            "buffer_this_round": new_candidates,
            "architect_output": architect_output,
            "additions": additions,
            "shared_learnings_after": list(shared_learnings),
            "results": batch_results,
        }
        rounds.append(round_data)
        write_json(os.path.join(output_dir, f"round_{batch_idx}.json"), round_data)

    await client.close()
    write_json(os.path.join(output_dir, "full_run.json"), rounds)
    write_json(os.path.join(output_dir, "eval_progression.json"), eval_progression)
    write_json(os.path.join(output_dir, "final_shared_learnings.json"), shared_learnings)


async def run_multi(args) -> None:
    configured = load_split(args.config, args.seed)
    output_dir = make_output_dir(configured.config, "multi", args.ablation, args.model, args.seed, configured.tag)
    client = LLMClient(model=args.model)

    predictor_template = load_rendered_prompt("multi", "predictor", configured.config)
    inspector_prompt = load_rendered_prompt("multi", "inspector", configured.config)
    architect_prompt = load_rendered_prompt("multi", "architect", configured.config)
    if args.ablation == "no-inspector":
        architect_prompt = load_ablation_prompt("architect_no_inspector_multi.txt")
    elif args.ablation == "no-quorum":
        architect_prompt = load_ablation_prompt("architect_no_quorum_multi.txt")

    agents: dict[str, str] = {}
    buffer: dict[int, list[str]] = {}
    rounds: list[dict] = []
    eval_progression: list[dict] = []

    n_batches = (len(configured.train_cases) + args.batch_size - 1) // args.batch_size
    if args.rounds is not None:
        n_batches = min(n_batches, args.rounds)

    print_header("MANANA COMPONENT ABLATION", [
        ("System:", "multi"),
        ("Ablation:", args.ablation),
        ("Config:", args.config),
        ("Train:", configured.train_label),
        ("Eval:", configured.eval_label),
        ("Batches:", f"{n_batches} x {args.batch_size}"),
        ("Output:", output_dir),
    ])

    baseline_eval = await multi_loop.run_eval(client, agents, predictor_template, configured.eval_cases, configured.gt_data)
    eval_progression.append({
        "round": "baseline",
        "agents": [],
        "buffer_size": 0,
        **{k: v for k, v in baseline_eval.items() if k != "per_case"},
        "per_case": baseline_eval["per_case"],
    })
    print(f"  [Eval baseline] {summarize_eval(baseline_eval)}")

    for batch_idx in range(n_batches):
        batch_cases = configured.train_cases[batch_idx * args.batch_size:(batch_idx + 1) * args.batch_size]
        print(f"\nROUND {batch_idx} - {len(batch_cases)} cases - {len(agents)} agents")

        if args.ablation == "no-inspector":
            tasks = [run_multi_raw_case(client, agents, predictor_template, case, configured.gt_data) for case in batch_cases]
        else:
            tasks = [
                multi_loop.run_train_case(client, agents, predictor_template, inspector_prompt, case, configured.gt_data)
                for case in batch_cases
            ]
        results = await asyncio.gather(*tasks)
        batch_results = [r for r in results if r is not None]
        new_candidates = [r.get("candidate_learning") for r in batch_results if r.get("candidate_learning")]
        architect_output = ""
        actions: list[dict] = []

        agents_before = dict(agents)
        if args.ablation != "no-architect":
            if args.ablation == "no-buffer":
                architect_input = build_multi_no_buffer_architect_input(batch_results, agents, batch_idx)
            elif args.ablation == "no-inspector":
                architect_input = build_multi_raw_architect_input(batch_results, agents, batch_idx)
            else:
                architect_input = multi_loop.build_architect_input(buffer, batch_results, agents, batch_idx)

            _, architect_output = await client.call(architect_prompt, architect_input)
            if architect_output:
                actions = multi_loop.parse_architect_actions(architect_output)
                agents = multi_loop.apply_architect_actions(agents, actions)

        if args.ablation not in ("no-buffer", "no-inspector"):
            buffer[batch_idx] = new_candidates

        round_eval = await multi_loop.run_eval(client, agents, predictor_template, configured.eval_cases, configured.gt_data)
        eval_progression.append({
            "round": batch_idx,
            "agents": list(agents.keys()),
            "buffer_size": sum(len(v) for v in buffer.values()),
            **{k: v for k, v in round_eval.items() if k != "per_case"},
            "per_case": round_eval["per_case"],
        })
        print(f"  [Eval] {summarize_eval(round_eval)}")

        round_data = {
            "round": batch_idx,
            "n_cases": len(batch_cases),
            "agents_before": agents_before,
            "buffer_this_round": new_candidates,
            "architect_output": architect_output,
            "actions": actions,
            "agents_after": dict(agents),
            "results": batch_results,
        }
        rounds.append(round_data)
        write_json(os.path.join(output_dir, f"round_{batch_idx}.json"), round_data)

    await client.close()
    write_json(os.path.join(output_dir, "full_run.json"), rounds)
    write_json(os.path.join(output_dir, "eval_progression.json"), eval_progression)
    write_json(os.path.join(output_dir, "final_agents.json"), agents)


async def main(args) -> None:
    if args.system == "single":
        await run_single(args)
    else:
        await run_multi(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Manana component ablations.")
    parser.add_argument("--config", required=True, help="Run YAML config")
    parser.add_argument("--system", choices=["single", "multi"], required=True)
    parser.add_argument("--ablation", choices=COMPONENT_ABLATIONS, required=True)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--temp", type=float, default=None, help="LLM temperature for single-system calls")
    asyncio.run(main(parser.parse_args()))
