"""Multi-agent Manana loop.

Combines:
- Multi-agent dynamics (SPAWN/EDIT/PRUNE agents via architect)
- Buffer memory (candidate learnings accumulate across rounds, architect reads full history)

Flow per round:
  agents run in parallel per patient → predictor synthesizes → inspector reports
  (agent attribution + CANDIDATE_LEARNING extraction) → buffer updated →
  architect sees buffer + current reports → SPAWN/EDIT/PRUNE

Usage:
    uv run python -m manana.run --config configs/mimic.yaml --system multi
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
MAX_ACTIONS_PER_ROUND = 2
MAX_AGENTS = 5


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
    text = re.sub(r'```[a-z]*\n?', '', raw).strip('`').strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            prose_fields = []
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
    if agent_outputs:
        block = "SPECIALIST ANALYSES:\n"
        for name, output in agent_outputs.items():
            block += f"\n[{name.upper()}]\n{clean_agent_output(output)}\n"
        block += "\n"
    else:
        block = ""
    return template.replace("{agent_outputs}", block)


def extract_candidate_learning(inspector_output: str) -> str | None:
    # Handles: CANDIDATE_LEARNING / CANDIDATE LEARNING, with or without colon,
    # with or without markdown bold (**), text on same line or next line.
    match = re.search(
        r'CANDIDATE[_ ]LEARNING\*{0,2}\s*:?\*{0,2}\s*\n?\s*(.+)',
        inspector_output,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    learning = match.group(1).strip()
    # Strip markdown bold/italic, brackets, leading bullets/dashes
    learning = re.sub(r'\*+', '', learning)
    learning = re.sub(r'^\[|\]$', '', learning.strip())
    learning = re.sub(r'^[-•]\s*', '', learning.strip())
    learning = learning.strip()
    return learning if len(learning) > 10 else None


def build_architect_input(
    buffer: dict[int, list[str]],
    batch_results: list[dict],
    agents: dict[str, str],
    batch_idx: int,
) -> str:
    parts = []

    # Candidate learnings from all previous rounds
    parts.append("CANDIDATE BUFFER (all rounds):")
    if buffer:
        for round_idx in sorted(buffer.keys()):
            learnings = buffer[round_idx]
            if learnings:
                parts.append(f"\nRound {round_idx}:")
                for l in learnings:
                    parts.append(f"  - {l}")
    else:
        parts.append("(empty — this is the first batch)")

    # Current round inspector reports
    parts.append(f"\n\nINSPECTOR REPORTS FROM THIS BATCH (Round {batch_idx}):\n")
    for r in batch_results:
        parts.append(f"--- Patient: {r['patient_id']} V{r['visit']} (poly={r['is_poly']}) ---")
        parts.append(f"GT: {r['gt_drugs']} | Match: {r['any_match']}")
        parts.append(r["inspector_report"])
        parts.append("")

    # Current agents
    parts.append("\nCURRENT ACTIVE AGENTS:")
    if agents:
        for name, prompt in agents.items():
            parts.append(f"\n[{name}]\n{prompt}")
        cap_note = "  AT CAP — prune before spawning." if len(agents) >= MAX_AGENTS else ""
        parts.append(f"\nCurrently active: {len(agents)} agents.{cap_note}")
    else:
        parts.append("(none — no agents yet)")

    return "\n".join(parts)


def _extract_prompt(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r'```[a-z]*\n?', '', text)
    text = re.sub(r'```', '', text)
    m = re.match(r'"(.*?)"', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'^[-\s:]+', '', text).strip()
    return text


def parse_architect_actions(architect_output: str) -> list[dict]:
    actions = []
    text = re.sub(r'\*+', '', architect_output)
    actions_match = re.search(r'ACTIONS\s*:(.*?)(?:UPDATED_AGENTS|$)', text, re.DOTALL | re.IGNORECASE)
    if not actions_match:
        return actions
    block = actions_match.group(1)
    chunks = re.split(r'(?=SPAWN_AGENT|EDIT_AGENT|PRUNE_AGENT)', block)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r'PRUNE_AGENT\s+"([^"]+)"', chunk)
        if m:
            actions.append({"type": "PRUNE", "name": m.group(1).strip()})
            continue
        m = re.match(r'SPAWN_AGENT\s+"([^"]+)"\s*:(.*)', chunk, re.DOTALL)
        if m:
            prompt = _extract_prompt(m.group(2))
            if prompt:
                actions.append({"type": "SPAWN", "name": m.group(1).strip(), "prompt": prompt})
            continue
        m = re.match(r'EDIT_AGENT\s+"([^"]+)"\s*:(.*)', chunk, re.DOTALL)
        if m:
            prompt = _extract_prompt(m.group(2))
            if prompt:
                actions.append({"type": "EDIT", "name": m.group(1).strip(), "prompt": prompt})
            continue
    return actions


def _normalize(name: str) -> str:
    """Lowercase + strip all non-alphanumeric chars (handles zero-width spaces etc.)."""
    return re.sub(r'[^a-z0-9]', '', name.lower())


def _resolve_agent_name(name: str, agents: dict[str, str]) -> str | None:
    """Case-insensitive, punctuation-insensitive lookup — returns actual key or None."""
    if name in agents:
        return name
    name_norm = _normalize(name)
    for key in agents:
        if _normalize(key) == name_norm:
            return key
    return None


def apply_architect_actions(agents: dict[str, str], actions: list[dict]) -> dict[str, str]:
    new_agents = dict(agents)
    applied = 0
    for action in actions:
        if applied >= MAX_ACTIONS_PER_ROUND:
            print(f"    [SKIP] action budget reached ({MAX_ACTIONS_PER_ROUND}/round)")
            break
        if action["type"] == "SPAWN":
            if len(new_agents) >= MAX_AGENTS:
                print(f"    [SPAWN SKIP] {action['name']} — at cap ({MAX_AGENTS}); prune first")
                continue
            new_agents[action["name"]] = action["prompt"]
            print(f"    [SPAWN] {action['name']}")
            applied += 1
        elif action["type"] == "EDIT":
            canonical = _resolve_agent_name(action["name"], new_agents)
            if canonical:
                new_agents[canonical] = action["prompt"]
                if canonical != action["name"]:
                    print(f"    [EDIT] {action['name']} (resolved → {canonical})")
                else:
                    print(f"    [EDIT] {canonical}")
                applied += 1
            else:
                print(f"    [EDIT WARN] {action['name']} not found — skipping")
        elif action["type"] == "PRUNE":
            canonical = _resolve_agent_name(action["name"], new_agents)
            if canonical:
                del new_agents[canonical]
                if canonical != action["name"]:
                    print(f"    [PRUNE] {action['name']} (resolved → {canonical})")
                else:
                    print(f"    [PRUNE] {canonical}")
                applied += 1
    return new_agents


async def run_agent(client: LLMClient, agent_prompt: str, patient_notes: str) -> str:
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
    _, pred_raw = await client.call(predictor_prompt, patient_notes)
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

    # Inspector — agent attribution + candidate learning
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
    _, inspector_report = await client.call(inspector_prompt, inspector_input)
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
        "agent_outputs": agent_outputs,
        "predictor_raw": pred_raw,
        "inspector_report": inspector_report,
        "candidate_learning": candidate_learning,
    }


async def run_eval_case(
    client: LLMClient,
    agents: dict[str, str],
    predictor_template: str,
    case,
    gt_data: dict,
) -> dict | None:
    gt_entry = gt_data.get(get_gt_key(case))
    if not gt_entry or not gt_entry["prescribed"]:
        return None

    gt_drugs = set(d.lower() for d in gt_entry["prescribed"])
    patient_notes = case.build_input_text()

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
        output_dir = os.path.join(output_root, "multi", "outputs", tag, model_folder, run_id)
    else:
        output_dir = os.path.join(_HERE, "outputs", tag, model_folder, run_id)
    os.makedirs(output_dir, exist_ok=True)

    client = LLMClient(model=model)

    train_cases = configured.train_cases
    eval_cases = configured.eval_cases
    gt_data = configured.gt_data
    train_label = configured.train_label
    eval_label = configured.eval_label

    predictor_template = load_rendered_prompt("multi", "predictor", configured.config)
    inspector_prompt = load_rendered_prompt("multi", "inspector", configured.config)
    architect_prompt = load_rendered_prompt("multi", "architect", configured.config)

    # State
    agents: dict[str, str] = {}
    buffer: dict[int, list[str]] = {}
    all_rounds = []
    eval_progression = []

    n_batches = (len(train_cases) + batch_size - 1) // batch_size
    if max_rounds is not None:
        n_batches = min(n_batches, max_rounds)

    print(f"\n{'='*60}")
    print(f"BUFFER + MULTI-AGENT MANANA LOOP")
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
    print(f"\n  [Eval] Baseline (0 agents)...")
    baseline_eval = await run_eval(client, {}, predictor_template, eval_cases, gt_data)
    eval_progression.append({
        "round": "baseline",
        "agents": [],
        "buffer_size": 0,
        **{k: v for k, v in baseline_eval.items() if k != "per_case"},
        "per_case": baseline_eval["per_case"],
    })
    mono_str = f"{baseline_eval['mono_top3']}/{baseline_eval['mono_total']}"
    poly_str = f"{baseline_eval['poly_top3']}/{baseline_eval['poly_total']}"
    print(f"  [Eval] top3={baseline_eval['top3_correct']}/{baseline_eval['total']} ({baseline_eval['top3_rate']:.0%})  mono={mono_str}  poly={poly_str}")

    best_top3 = baseline_eval["top3_rate"]
    best_agents: dict[str, str] = {}

    for batch_idx in range(n_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(train_cases))
        batch_cases = train_cases[start:end]

        print(f"\n{'─'*60}")
        print(f"ROUND {batch_idx} — {len(batch_cases)} cases — {len(agents)} agents: {list(agents.keys())}")
        print(f"{'─'*60}")

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
        print(f"  Train: {batch_correct}/{batch_total} ({batch_correct/batch_total:.0%})" if batch_total else "  Train: n/a")

        # Collect candidate learnings from this round (do NOT add to buffer yet —
        # architect sees previous rounds' buffer + current raw reports, not both)
        new_candidates = [r["candidate_learning"] for r in batch_results if r["candidate_learning"]]
        print(f"  Buffer: +{len(new_candidates)} new candidates (previous rounds total: {sum(len(v) for v in buffer.values())})")

        # Architect: sees buffer + current inspector reports + current agents
        print(f"  Running Architect...")
        agents_before = {name: prompt for name, prompt in agents.items()}
        architect_input = build_architect_input(buffer, batch_results, agents, batch_idx)
        _, architect_output = await client.call(architect_prompt, architect_input)

        if architect_output:
            actions = parse_architect_actions(architect_output)
            agents = apply_architect_actions(agents, actions)
            print(f"  Agents: {list(agents.keys())}")
        else:
            print("  [WARN] Architect returned empty output")

        # Buffer always updated regardless of gating
        buffer[batch_idx] = new_candidates
        total_buffer = sum(len(v) for v in buffer.values())

        # Capture candidate agents (post-architect, pre-gating)
        candidate_agents = {name: prompt for name, prompt in agents.items()}

        # Eval
        print(f"  [Eval] Running on held-out set...")
        round_eval = await run_eval(client, agents, predictor_template, eval_cases, gt_data)
        mono_str = f"{round_eval['mono_top3']}/{round_eval['mono_total']}"
        poly_str = f"{round_eval['poly_top3']}/{round_eval['poly_total']}"
        print(f"  [Eval] top3={round_eval['top3_correct']}/{round_eval['total']} ({round_eval['top3_rate']:.0%})  mono={mono_str}  poly={poly_str}")

        # No gating: always accept architect agent changes
        accepted = True
        best_top3 = round_eval["top3_rate"]
        best_agents = dict(agents)

        round_data = {
            "round": batch_idx,
            "accepted": accepted,
            "n_cases": len(batch_cases),
            "agents_before": agents_before,
            "buffer_this_round": new_candidates,
            "architect_output": architect_output,
            "candidate_agents": candidate_agents,
            "agents_after": {name: prompt for name, prompt in agents.items()},
            "results": batch_results,
        }
        all_rounds.append(round_data)
        eval_progression.append({
            "round": batch_idx,
            "accepted": accepted,
            "candidate_top3_rate": round_eval["top3_rate"],
            "best_top3_rate": best_top3,
            "agents": list(agents.keys()),
            "buffer_size": total_buffer,
            **{k: v for k, v in round_eval.items() if k != "per_case"},
            "per_case": round_eval["per_case"],
        })

        with open(os.path.join(output_dir, f"round_{batch_idx}.json"), "w", encoding="utf-8") as f:
            json.dump(round_data, f, indent=2, ensure_ascii=False)

    await client.close()

    with open(os.path.join(output_dir, "full_run.json"), "w", encoding="utf-8") as f:
        json.dump(all_rounds, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, "eval_progression.json"), "w", encoding="utf-8") as f:
        json.dump(eval_progression, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"\n{'Round':<10} {'Acc':>4} {'Agents':<30} {'Buffer':>6} {'Candidate':>12} {'Best':>8} {'Mono':>8} {'Poly':>8}")
    print(f"{'-'*90}")
    for ep in eval_progression:
        rnd = ep["round"] if isinstance(ep["round"], str) else f"R{ep['round']}"
        acc = "—" if "accepted" not in ep else ("Y" if ep["accepted"] else "N")
        ag = str(ep.get("agents", []))[:28]
        buf = ep.get("buffer_size", 0)
        candidate = f"{ep['top3_correct']}/{ep['total']} ({ep['top3_rate']:.0%})"
        best = f"({ep['best_top3_rate']:.0%})" if "best_top3_rate" in ep else "—"
        mono = f"{ep['mono_top3']}/{ep['mono_total']}"
        poly = f"{ep['poly_top3']}/{ep['poly_total']}"
        print(f"{rnd:<10} {acc:>4} {ag:<30} {buf:>6} {candidate:<14} {best:>8} {mono:<8} {poly:<8}")

    print(f"\nFinal agents ({len(agents)}):")
    for name, prompt in agents.items():
        print(f"  - {name}: {prompt[:80]}...")
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
    lines.append(f"| Round | Acc | Agents | Buffer | Candidate | Best | Mono | Poly |")
    lines.append(f"|-------|-----|--------|--------|-----------|------|------|------|")
    for ep in eval_progression:
        rnd = ep["round"] if isinstance(ep["round"], str) else f"R{ep['round']}"
        acc = "—" if "accepted" not in ep else ("Y" if ep["accepted"] else "N")
        ag = ", ".join(ep.get("agents", [])) or "—"
        buf = ep.get("buffer_size", 0)
        candidate = f"{ep['top3_correct']}/{ep['total']} ({ep['top3_rate']:.0%})"
        best = f"({ep['best_top3_rate']:.0%})" if "best_top3_rate" in ep else "—"
        mono = f"{ep['mono_top3']}/{ep['mono_total']}"
        poly = f"{ep['poly_top3']}/{ep['poly_total']}"
        lines.append(f"| {rnd} | {acc} | {ag} | {buf} | {candidate} | {best} | {mono} | {poly} |")
    lines.append(f"\n## Final Agents ({len(agents)})\n")
    for name, prompt in agents.items():
        lines.append(f"### {name}")
        lines.append(f"{prompt}\n")
    with open(os.path.join(output_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-agent Manana loop")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--config", required=True, help="Run YAML config")
    args = parser.parse_args()

    asyncio.run(run_loop(
        batch_size=args.batch_size,
        max_rounds=args.rounds,
        model=args.model,
        seed=args.seed,
        config_path=args.config,
    ))
