"""Multi-agent self-learning loop.

Agents are spawned/edited/pruned by the Architect based on Inspector reports.
Each round: agents run in parallel per patient → predictor synthesizes → inspector diagnoses → architect evolves.

Usage:
    uv run python self_learning/multi/run_loop.py --batch-size 10
    uv run python self_learning/multi/run_loop.py --batch-size 4 --rounds 1 --seed 42
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

_HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(_HERE, "prompts")


def load_prompt(name: str) -> str:
    with open(os.path.join(PROMPTS_DIR, name), encoding="utf-8") as f:
        return f.read()


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


def clean_agent_output(raw: str) -> str:
    """Strip JSON wrappers from agent output — extract text fields as prose."""
    # Strip code fences
    text = re.sub(r'```[a-z]*\n?', '', raw).strip('`').strip()
    # Try to parse as JSON and extract text fields
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            prose_fields = []
            # Pull string/list values, skip booleans and nulls
            for k, v in obj.items():
                if isinstance(v, str) and v.strip():
                    prose_fields.append(f"{k}: {v.strip()}")
                elif isinstance(v, list) and v:
                    prose_fields.append(f"{k}: {', '.join(str(x) for x in v)}")
            if prose_fields:
                return '\n'.join(prose_fields)
    except (json.JSONDecodeError, ValueError):
        pass
    return text


def build_predictor_prompt(template: str, agent_outputs: dict[str, str]) -> str:
    """Inject agent outputs into predictor prompt."""
    if agent_outputs:
        block = "SPECIALIST ANALYSES:\n"
        for name, output in agent_outputs.items():
            block += f"\n[{name.upper()}]\n{clean_agent_output(output)}\n"
        block += "\n"
    else:
        block = ""
    return template.replace("{agent_outputs}", block)


def parse_architect_agents(architect_output: str) -> dict[str, str] | None:
    """Parse UPDATED_AGENTS section — returns {name: description} or None if not found."""
    match = re.search(r'UPDATED_AGENTS\s*:', architect_output, re.IGNORECASE)
    if not match:
        return None
    text = architect_output[match.end():]
    agents = {}
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)', line)
        if m:
            agents[m.group(1).strip()] = m.group(2).strip()
    return agents if agents else None


def _extract_prompt(raw: str) -> str:
    """Extract prompt text from various architect output formats."""
    text = raw.strip()
    # Strip code fences
    text = re.sub(r'```[a-z]*\n?', '', text)
    text = re.sub(r'```', '', text)
    # Try quoted string: "prompt"
    m = re.match(r'"(.*?)"', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Strip italic/bold markers, leading bullets/dashes/colons
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'^[-\s:]+', '', text).strip()
    return text


def parse_architect_actions(architect_output: str) -> list[dict]:
    """Parse ACTIONS block into structured list."""
    actions = []
    # Strip markdown bold/italic
    text = re.sub(r'\*+', '', architect_output)

    actions_match = re.search(r'ACTIONS\s*:(.*?)(?:UPDATED_AGENTS|$)', text, re.DOTALL | re.IGNORECASE)
    if not actions_match:
        return actions

    block = actions_match.group(1)

    # Split on action keywords — each chunk belongs to one action
    chunks = re.split(r'(?=SPAWN_AGENT|EDIT_AGENT|PRUNE_AGENT)', block)

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        # PRUNE_AGENT "name"
        m = re.match(r'PRUNE_AGENT\s+"([^"]+)"', chunk)
        if m:
            actions.append({"type": "PRUNE", "name": m.group(1).strip()})
            continue

        # SPAWN_AGENT "name": <prompt in any format>
        m = re.match(r'SPAWN_AGENT\s+"([^"]+)"\s*:(.*)', chunk, re.DOTALL)
        if m:
            prompt = _extract_prompt(m.group(2))
            if prompt:
                actions.append({"type": "SPAWN", "name": m.group(1).strip(), "prompt": prompt})
            continue

        # EDIT_AGENT "name": <prompt in any format>
        m = re.match(r'EDIT_AGENT\s+"([^"]+)"\s*:(.*)', chunk, re.DOTALL)
        if m:
            prompt = _extract_prompt(m.group(2))
            if prompt:
                actions.append({"type": "EDIT", "name": m.group(1).strip(), "prompt": prompt})
            continue

    return actions


def apply_architect_actions(agents: dict[str, str], actions: list[dict]) -> dict[str, str]:
    """Apply spawn/edit/prune actions to agent dict."""
    new_agents = dict(agents)
    for action in actions:
        if action["type"] == "SPAWN":
            new_agents[action["name"]] = action["prompt"]
            print(f"    [SPAWN] {action['name']}")
        elif action["type"] == "EDIT":
            if action["name"] in new_agents:
                new_agents[action["name"]] = action["prompt"]
                print(f"    [EDIT] {action['name']}")
            else:
                print(f"    [EDIT WARN] {action['name']} not found — skipping")
        elif action["type"] == "PRUNE":
            if action["name"] in new_agents:
                del new_agents[action["name"]]
                print(f"    [PRUNE] {action['name']}")
    return new_agents


async def run_agent(client: LLMClient, agent_prompt: str, patient_notes: str) -> str:
    """Run a single specialist agent on a patient."""
    _, output = await client.call(agent_prompt, patient_notes)
    return output or ""


async def run_train_case(
    client: LLMClient,
    agents: dict[str, str],
    predictor_template: str,
    inspector_prompt: str,
    case,
    gt_data: dict,
) -> dict | None:
    """Run agents → predictor → inspector for a single training case."""
    gt_entry = gt_data.get(get_gt_key(case))
    if not gt_entry or not gt_entry["prescribed"]:
        return None

    gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
    patient_notes = case.build_input_text()

    # Run all agents in parallel
    agent_outputs = {}
    if agents:
        agent_tasks = {name: run_agent(client, prompt, patient_notes) for name, prompt in agents.items()}
        results = await asyncio.gather(*agent_tasks.values())
        agent_outputs = dict(zip(agent_tasks.keys(), results))

    # Predictor
    predictor_prompt = build_predictor_prompt(predictor_template, agent_outputs)
    pred_thinking, pred_raw = await client.call(predictor_prompt, patient_notes)
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
    agent_section = ""
    if agent_outputs:
        agent_section = "\nSPECIALIST AGENT OUTPUTS:\n"
        for name, out in agent_outputs.items():
            agent_section += f"\n[{name.upper()}]\n{clean_agent_output(out)}\n"

    inspector_input = f"""PATIENT CLINICAL NOTES:
{patient_notes}
{agent_section}
SYSTEM PREDICTION:
{pred_raw}

GROUND TRUTH (what the doctor prescribed): {sorted(gt_drugs)}

MATCH: {'Yes — ' + best_option if any_match else 'No — none of the 3 options matched'}
"""
    inspector_thinking, inspector_report = await client.call(inspector_prompt, inspector_input)
    if not inspector_report:
        print(f"  [WARN] Inspector failure for {case.patient_id} — skipping")
        return None

    return {
        "patient_id": case.patient_id,
        "visit": get_visit_num(case),
        "gt_drugs": sorted(gt_drugs),
        "pred_option1_drugs": sorted(pred_drugs),
        "is_poly": len(gt_drugs) > 1,
        "any_match": any_match,
        "best_option": best_option,
        "agent_outputs": agent_outputs,
        "predictor_raw": pred_raw,
        "inspector_report": inspector_report,
    }


async def run_eval_case(
    client: LLMClient,
    agents: dict[str, str],
    predictor_template: str,
    case,
    gt_data: dict,
) -> dict | None:
    """Run agents → predictor for a single eval case."""
    gt_entry = gt_data.get(get_gt_key(case))
    if not gt_entry or not gt_entry["prescribed"]:
        return None

    gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
    patient_notes = case.build_input_text()

    # Run all agents in parallel
    agent_outputs = {}
    if agents:
        agent_tasks = {name: run_agent(client, prompt, patient_notes) for name, prompt in agents.items()}
        results = await asyncio.gather(*agent_tasks.values())
        agent_outputs = dict(zip(agent_tasks.keys(), results))

    predictor_prompt = build_predictor_prompt(predictor_template, agent_outputs)
    _, pred_raw = await client.call(predictor_prompt, patient_notes)
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
    agents: dict[str, str],
    predictor_template: str,
    eval_cases: list,
    gt_data: dict,
) -> dict:
    """Run eval on all held-out cases in parallel."""
    tasks = [run_eval_case(client, agents, predictor_template, case, gt_data) for case in eval_cases]
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
):
    model_folder = sanitize_model_name(model)
    run_id = f"loop_{datetime.now().strftime('%Y%m%d_%H%M')}"
    output_dir = os.path.join(_HERE, "outputs", model_folder, run_id)
    os.makedirs(output_dir, exist_ok=True)

    client = LLMClient(model=model)

    split = stratified_split(cohort="csv", seed=seed)
    train_cases = split["train_cases"]
    eval_cases = split["eval_cases"]
    gt_data = split["gt_data"]
    stats = split["stats"]

    predictor_template = load_prompt("predictor.txt")
    inspector_prompt = load_prompt("inspector.txt")
    architect_prompt = load_prompt("architect.txt")

    # State
    agents: dict[str, str] = {}  # name → system prompt
    agent_birth_round: dict[str, int] = {}  # name → batch_idx when spawned
    all_rounds = []
    eval_progression = []

    n_batches = (len(train_cases) + batch_size - 1) // batch_size
    if max_rounds is not None:
        n_batches = min(n_batches, max_rounds)

    print(f"\n{'='*60}")
    print(f"MULTI-AGENT SELF-LEARNING LOOP")
    print(f"{'='*60}")
    print(f"Model:      {model}")
    print(f"Train:      {stats['train_patients']} patients, {stats['train_cases']} cases")
    print(f"Eval:       {stats['eval_patients']} patients, {stats['eval_cases']} cases")
    print(f"Batches:    {n_batches} × {batch_size}")
    print(f"Output:     {output_dir}")
    print(f"{'='*60}")

    # Baseline eval (0 agents)
    print(f"\n  [Eval] Baseline (0 agents)...")
    baseline_eval = await run_eval(client, {}, predictor_template, eval_cases, gt_data)
    eval_progression.append({
        "round": "baseline",
        "agents": [],
        **{k: v for k, v in baseline_eval.items() if k != "per_case"},
        "per_case": baseline_eval["per_case"],
    })
    mono_str = f"{baseline_eval['mono_top3']}/{baseline_eval['mono_total']}"
    poly_str = f"{baseline_eval['poly_top3']}/{baseline_eval['poly_total']}"
    print(f"  [Eval] top3={baseline_eval['top3_correct']}/{baseline_eval['total']} ({baseline_eval['top3_rate']:.0%})  mono={mono_str}  poly={poly_str}")

    for batch_idx in range(n_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(train_cases))
        batch_cases = train_cases[start:end]

        print(f"\n{'─'*60}")
        print(f"ROUND {batch_idx} — {len(batch_cases)} cases — {len(agents)} agents: {list(agents.keys())}")
        print(f"{'─'*60}")

        round_data = {
            "round": batch_idx,
            "n_cases": len(batch_cases),
            "agents_before": {name: prompt for name, prompt in agents.items()},
            "results": [],
        }

        # Run batch in parallel
        print(f"  Running batch (parallel)...")
        tasks = [
            run_train_case(client, agents, predictor_template, inspector_prompt, case, gt_data)
            for case in batch_cases
        ]
        results = await asyncio.gather(*tasks)
        batch_results = [r for r in results if r is not None]

        batch_correct = sum(1 for r in batch_results if r["any_match"])
        batch_total = len(batch_results)
        round_data["results"] = batch_results
        print(f"  Train: {batch_correct}/{batch_total} ({batch_correct/batch_total:.0%})" if batch_total else "  Train: n/a")

        # Architect
        print(f"  Running Architect...")
        architect_input = f"ROUND: {batch_idx}\n\nINSPECTOR REPORTS FROM THIS BATCH:\n\n"
        for r in batch_results:
            architect_input += f"--- Patient: {r['patient_id']} V{r['visit']} (poly={r['is_poly']}) ---\n"
            architect_input += f"GT: {r['gt_drugs']} | Match: {r['any_match']}\n"
            architect_input += r["inspector_report"]
            architect_input += "\n\n"

        architect_input += "CURRENT ACTIVE AGENTS:\n"
        if agents:
            for name, prompt in agents.items():
                architect_input += f"\n[{name}]\n{prompt}\n"
            cap_note = "  AT CAP — prune before spawning." if len(agents) >= 5 else ""
            architect_input += f"\nCurrently active: {len(agents)} agents.{cap_note}\n"
        else:
            architect_input += "  (none — this is the first batch)\n"

        _, architect_output = await client.call(architect_prompt, architect_input)

        if architect_output:
            actions = parse_architect_actions(architect_output)
            agents_before_set = set(agents.keys())
            agents = apply_architect_actions(agents, actions)
            # Track birth rounds for newly spawned agents
            for name in set(agents.keys()) - agents_before_set:
                agent_birth_round[name] = batch_idx
            # Remove pruned agents from tracking
            for name in agents_before_set - set(agents.keys()):
                agent_birth_round.pop(name, None)
        else:
            print("  [WARN] Architect returned empty output")

        round_data["architect_output"] = architect_output
        round_data["agents_after"] = {name: prompt for name, prompt in agents.items()}

        print(f"  Agents: {list(agents.keys())}")

        # Eval
        print(f"  [Eval] Running on held-out set...")
        round_eval = await run_eval(client, agents, predictor_template, eval_cases, gt_data)
        eval_entry = {
            "round": batch_idx,
            "agents": list(agents.keys()),
            **{k: v for k, v in round_eval.items() if k != "per_case"},
            "per_case": round_eval["per_case"],
        }
        eval_progression.append(eval_entry)
        mono_str = f"{round_eval['mono_top3']}/{round_eval['mono_total']}"
        poly_str = f"{round_eval['poly_top3']}/{round_eval['poly_total']}"
        print(f"  [Eval] top3={round_eval['top3_correct']}/{round_eval['total']} ({round_eval['top3_rate']:.0%})  mono={mono_str}  poly={poly_str}")

        all_rounds.append(round_data)

        with open(os.path.join(output_dir, f"round_{batch_idx}.json"), "w", encoding="utf-8") as f:
            json.dump(round_data, f, indent=2, ensure_ascii=False)

    await client.close()

    with open(os.path.join(output_dir, "full_run.json"), "w", encoding="utf-8") as f:
        json.dump(all_rounds, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, "eval_progression.json"), "w", encoding="utf-8") as f:
        json.dump(eval_progression, f, indent=2, ensure_ascii=False)

    # Final summary
    print(f"\n{'='*60}")
    print(f"FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"\n{'Round':<10} {'Agents':<30} {'Top-3':>10} {'Mono':>8} {'Poly':>8}")
    print(f"{'-'*70}")
    for ep in eval_progression:
        rnd = ep["round"] if isinstance(ep["round"], str) else f"R{ep['round']}"
        ag = str(ep.get("agents", []))[:28]
        mono = f"{ep['mono_top3']}/{ep['mono_total']}"
        poly = f"{ep['poly_top3']}/{ep['poly_total']}"
        print(f"{rnd:<10} {ag:<30} {ep['top3_correct']}/{ep['total']} ({ep['top3_rate']:.0%}){'':<3} {mono:<8} {poly:<8}")

    print(f"\nFinal agents ({len(agents)}):")
    for name in agents:
        print(f"  - {name}")
    print(f"\nOutput: {output_dir}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent Self-Learning Loop")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--rounds", type=int, default=None, help="Max rounds (default: all)")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    asyncio.run(run_loop(
        batch_size=args.batch_size,
        max_rounds=args.rounds,
        model=args.model,
        seed=args.seed,
    ))
