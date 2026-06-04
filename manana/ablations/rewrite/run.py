"""Free-rewrite ablation for Manana.

This is a baseline-style ablation:
- single: architect rewrites the complete clinical memory each round
- multi: architect rewrites the complete specialist agent population each round

Usage:
    uv run python -m manana.ablations.rewrite.run --config configs/uganda_example.yaml --system single
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re

from lib.llm import DEFAULT_MODEL, LLMClient
from manana.ablations.common import (
    load_rewrite_prompt,
    load_split,
    make_output_dir,
    parse_json_object,
    print_header,
    summarize_eval,
    write_json,
)
from manana.prompts import load_rendered_prompt
from manana.single import run_loop as single_loop
from manana.multi import run_loop as multi_loop

BASELINE_NAME = "free-rewrite"
MAX_SINGLE_RULES = 15
MAX_MULTI_AGENTS = 5


def parse_clinical_memory(raw: str) -> list[str] | None:
    obj = parse_json_object(raw)
    if obj is None:
        return None
    memory = obj.get("clinical_memory")
    if not isinstance(memory, list):
        return None

    cleaned: list[str] = []
    seen = set()
    for item in memory:
        rule = str(item).strip()
        if not rule:
            continue
        key = re.sub(r"\s+", " ", rule.lower())
        if key in seen:
            continue
        cleaned.append(rule)
        seen.add(key)
        if len(cleaned) >= MAX_SINGLE_RULES:
            break
    return cleaned


def normalize_agent_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_rewritten_agents(raw: str) -> dict[str, str] | None:
    obj = parse_json_object(raw)
    if obj is None:
        return None
    agents = obj.get("agents")
    if not isinstance(agents, list):
        return None

    parsed: dict[str, str] = {}
    seen = set()
    for item in agents:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        prompt = str(item.get("prompt", "")).strip()
        if not name or not prompt:
            continue
        key = normalize_agent_name(name)
        if not key or key in seen:
            continue
        parsed[name] = prompt
        seen.add(key)
        if len(parsed) >= MAX_MULTI_AGENTS:
            break
    return parsed


async def run_single(args) -> None:
    configured = load_split(args.config, args.seed)
    output_dir = make_output_dir(configured.config, "single", BASELINE_NAME, args.model, args.seed, configured.tag)
    client = LLMClient(model=args.model)

    predictor_template = load_rendered_prompt("single", "predictor", configured.config)
    inspector_prompt = load_rendered_prompt("single", "inspector", configured.config)
    architect_prompt = load_rewrite_prompt("architect_rewrite_single.txt")

    shared_learnings: list[str] = []
    buffer: dict[int, list[str]] = {}
    rounds: list[dict] = []
    eval_progression: list[dict] = []

    n_batches = (len(configured.train_cases) + args.batch_size - 1) // args.batch_size
    if args.rounds is not None:
        n_batches = min(n_batches, args.rounds)

    print_header("MANANA FREE-REWRITE ABLATION", [
        ("System:", "single"),
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
        tasks = [
            single_loop.run_train_case(
                client, predictor_template, inspector_prompt, shared_learnings, case, configured.gt_data, args.temp,
            )
            for case in batch_cases
        ]
        results = await asyncio.gather(*tasks)
        batch_results = [r for r in results if r is not None]
        new_candidates = [r["candidate_learning"] for r in batch_results if r.get("candidate_learning")]

        architect_input = single_loop.build_architect_input(shared_learnings, buffer, batch_results, batch_idx)
        _, architect_output = await client.call(architect_prompt, architect_input, temperature=args.temp)
        rewritten = parse_clinical_memory(architect_output) if architect_output else None
        if rewritten is not None:
            shared_learnings = rewritten

        buffer[batch_idx] = new_candidates
        round_eval = await single_loop.run_eval(
            client, predictor_template, shared_learnings, configured.eval_cases, configured.gt_data, args.temp,
        )
        eval_progression.append({
            "round": batch_idx,
            "shared_learnings_size": len(shared_learnings),
            "shared_learnings": list(shared_learnings),
            "buffer_size": sum(len(v) for v in buffer.values()),
            **{k: v for k, v in round_eval.items() if k != "per_case"},
            "per_case": round_eval["per_case"],
        })
        print(f"  [Eval R{batch_idx}] {summarize_eval(round_eval)}")

        round_data = {
            "round": batch_idx,
            "n_cases": len(batch_cases),
            "buffer_this_round": new_candidates,
            "architect_output": architect_output,
            "rewritten_memory": rewritten,
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
    output_dir = make_output_dir(configured.config, "multi", BASELINE_NAME, args.model, args.seed, configured.tag)
    client = LLMClient(model=args.model)

    predictor_template = load_rendered_prompt("multi", "predictor", configured.config)
    inspector_prompt = load_rendered_prompt("multi", "inspector", configured.config)
    architect_prompt = load_rewrite_prompt("architect_rewrite_multi.txt")

    agents: dict[str, str] = {}
    buffer: dict[int, list[str]] = {}
    rounds: list[dict] = []
    eval_progression: list[dict] = []

    n_batches = (len(configured.train_cases) + args.batch_size - 1) // args.batch_size
    if args.rounds is not None:
        n_batches = min(n_batches, args.rounds)

    print_header("MANANA FREE-REWRITE ABLATION", [
        ("System:", "multi"),
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
        tasks = [
            multi_loop.run_train_case(client, agents, predictor_template, inspector_prompt, case, configured.gt_data)
            for case in batch_cases
        ]
        results = await asyncio.gather(*tasks)
        batch_results = [r for r in results if r is not None]
        new_candidates = [r["candidate_learning"] for r in batch_results if r.get("candidate_learning")]

        architect_input = multi_loop.build_architect_input(buffer, batch_results, agents, batch_idx)
        _, architect_output = await client.call(architect_prompt, architect_input)
        rewritten = parse_rewritten_agents(architect_output) if architect_output else None
        if rewritten is not None:
            agents = rewritten

        buffer[batch_idx] = new_candidates
        round_eval = await multi_loop.run_eval(client, agents, predictor_template, configured.eval_cases, configured.gt_data)
        eval_progression.append({
            "round": batch_idx,
            "agents": list(agents.keys()),
            "buffer_size": sum(len(v) for v in buffer.values()),
            **{k: v for k, v in round_eval.items() if k != "per_case"},
            "per_case": round_eval["per_case"],
        })
        print(f"  [Eval R{batch_idx}] {summarize_eval(round_eval)}")

        round_data = {
            "round": batch_idx,
            "n_cases": len(batch_cases),
            "buffer_this_round": new_candidates,
            "architect_output": architect_output,
            "rewritten_agents": rewritten,
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
    parser = argparse.ArgumentParser(description="Run Manana free-rewrite ablation.")
    parser.add_argument("--config", required=True, help="Run YAML config")
    parser.add_argument("--system", choices=["single", "multi"], required=True)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--temp", type=float, default=None, help="LLM temperature for single-system calls")
    asyncio.run(main(parser.parse_args()))
