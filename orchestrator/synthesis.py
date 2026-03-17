"""Rule-based synthesis + trace compilation.

Phase 4: NOT another LLM black box. Applies rules deterministically,
then uses a single LLM call only for natural language formatting.
"""

from __future__ import annotations
import re
import os

from schemas.patient import PatientCase
from schemas.responses import AgentResponse, Severity
from schemas.trace import ReasoningTrace, DebateRound
from schemas.output import (
    FinalRecommendation, DrugOption, DrugAction,
    DRUG_COLUMNS, ALLOWED_ACTIONS,
)
from llm.client import LLMClient

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agents", "prompts")


def parse_epileptologist_options(raw_output: str) -> list[DrugOption]:
    """Parse the epileptologist's 3 ranked options from raw output."""
    options = []

    block_pattern = re.compile(
        r'Option\s+(\d)\s*:\s*(.+?)(?=Option\s+\d\s*:|$)',
        re.DOTALL | re.IGNORECASE,
    )

    for m in block_pattern.finditer(raw_output):
        num = int(m.group(1))
        if num not in (1, 2, 3):
            continue

        block_lines = m.group(2).strip().split('\n')
        label = block_lines[0].strip() if block_lines else ""
        drugs = []
        rationale_parts = []
        in_rationale = False

        for line in block_lines[1:]:
            s = line.strip()
            if not s:
                continue
            rat = re.match(r'Rationale\s*:\s*(.*)', s, re.IGNORECASE)
            if rat:
                in_rationale = True
                rationale_parts.append(rat.group(1).strip())
                continue
            if in_rationale:
                rationale_parts.append(s)
                continue
            dm = re.match(r'-\s*(\w+)\s*:\s*(\w+)', s)
            if dm:
                drug = dm.group(1).lower()
                action = dm.group(2).lower()
                if drug in DRUG_COLUMNS and action in ALLOWED_ACTIONS:
                    drugs.append(DrugAction(drug=drug, action=action))

        options.append(DrugOption(
            rank=num,
            label=label,
            drugs=drugs,
            rationale=" ".join(rationale_parts),
        ))

    return options


def apply_synthesis_rules(
    options: list[DrugOption],
    safety_vetoes: set[str],
    debate_rounds: list[DebateRound],
    phase1_responses: dict[str, AgentResponse],
) -> tuple[list[DrugOption], list[str], list[str], list[str]]:
    """Apply rule-based synthesis to the epileptologist's options.

    Returns:
        (modified_options, safety_notes, debate_notes, availability_notes)
    """
    safety_notes = []
    debate_notes = []
    availability_notes = []

    # 1. Apply safety vetoes — remove vetoed drugs from all options
    for opt in options:
        vetoed_in_option = [d for d in opt.drugs if d.drug in safety_vetoes and d.action != "stop"]
        if vetoed_in_option:
            for d in vetoed_in_option:
                d.action = "stop"
                d.rationale = "Safety veto applied"
                d.provenance = "safety_veto"
            safety_notes.append(
                f"Option {opt.rank}: safety veto applied to {', '.join(d.drug for d in vetoed_in_option)}"
            )
            opt.uncertainty_markers.append("Safety veto modified this option")

    # 2. Apply debate modifications
    for round in debate_rounds:
        for action in round.rebuttal_actions:
            if action.get("action") in ("accept", "modify"):
                modified_drugs = action.get("modified_drugs", [])
                if modified_drugs:
                    debate_notes.append(
                        f"Debate round {round.round_number}: "
                        f"concern {action.get('concern_index', '?')+1} {action['action']}ed — "
                        f"modified drugs: {', '.join(str(d) for d in modified_drugs)}"
                    )
        # Add unresolved concerns as uncertainty markers
        for unresolved in round.unresolved_concerns:
            for opt in options:
                opt.uncertainty_markers.append(f"Unresolved: {unresolved}")

    # 3. Apply availability preferences (soft — doesn't veto)
    formulary = phase1_responses.get("formulary")
    if formulary:
        for concern in formulary.concerns:
            if concern.affected_drugs:
                availability_notes.append(
                    f"Availability concern: {', '.join(concern.affected_drugs)} — {concern.description}"
                )

    return options, safety_notes, debate_notes, availability_notes


def compute_agreement_score(phase1_responses: dict[str, AgentResponse]) -> float:
    """Compute inter-agent agreement score (0-1).

    Based on overlap of recommended and contraindicated drugs across agents.
    """
    if len(phase1_responses) < 2:
        return 1.0

    all_recs = [set(r.recommended_drugs) for r in phase1_responses.values() if r.recommended_drugs]
    if not all_recs:
        return 0.5  # No recommendations to compare

    # Pairwise Jaccard similarity
    scores = []
    for i in range(len(all_recs)):
        for j in range(i + 1, len(all_recs)):
            union = all_recs[i] | all_recs[j]
            if union:
                scores.append(len(all_recs[i] & all_recs[j]) / len(union))
            else:
                scores.append(1.0)

    return sum(scores) / len(scores) if scores else 1.0


def build_final_recommendation(
    patient: PatientCase,
    trace: ReasoningTrace,
    safety_vetoes: set[str],
) -> FinalRecommendation:
    """Build the final recommendation from the reasoning trace."""
    # Parse options from epileptologist output
    options = []
    if trace.epileptologist_response:
        options = parse_epileptologist_options(trace.epileptologist_response.raw_output)

    # Apply synthesis rules
    options, safety_notes, debate_notes, avail_notes = apply_synthesis_rules(
        options,
        safety_vetoes,
        trace.debate_rounds,
        trace.phase1_responses,
    )

    # Build synthesis notes
    synthesis_parts = []
    if safety_notes:
        synthesis_parts.append("Safety vetoes: " + "; ".join(safety_notes))
    if debate_notes:
        synthesis_parts.append("Debate modifications: " + "; ".join(debate_notes))
    if avail_notes:
        synthesis_parts.append("Availability: " + "; ".join(avail_notes))

    return FinalRecommendation(
        patient_id=patient.patient_id,
        visit=patient.current_visit,
        options=options,
        synthesis_notes="\n".join(synthesis_parts),
        safety_vetoes_applied=safety_notes,
        debate_modifications=debate_notes,
        availability_adjustments=avail_notes,
    )


async def format_trace_output(
    trace: ReasoningTrace,
    recommendation: FinalRecommendation,
    llm_client: LLMClient,
) -> str:
    """Use a single LLM call to format the trace into natural language.

    This is the ONLY LLM call in synthesis — everything else is rule-based.
    """
    with open(os.path.join(PROMPTS_DIR, "orchestrator.txt"), encoding="utf-8") as f:
        system_prompt = f.read()

    # Build structured summary for formatting
    parts = [f"Patient: {trace.patient_id}, Visit: {trace.visit}\n"]

    parts.append("AGENT SUMMARIES:")
    for agent_name, resp in trace.phase1_responses.items():
        parts.append(f"\n{resp.to_summary()}")

    if trace.epileptologist_response:
        parts.append(f"\n{trace.epileptologist_response.to_summary()}")

    if trace.pharmacologist_response:
        parts.append(f"\n{trace.pharmacologist_response.to_summary()}")

    if trace.detected_conflicts:
        parts.append("\nCONFLICTS:")
        for c in trace.detected_conflicts:
            parts.append(f"  - [{c.conflict_type}] {c.description} → {c.resolution}")

    if trace.debate_triggered:
        parts.append(f"\nDEBATE: {len(trace.debate_rounds)} rounds")
        for r in trace.debate_rounds:
            parts.append(f"  Round {r.round_number}: {len(r.resolved_concerns)} resolved, {len(r.unresolved_concerns)} unresolved")

    parts.append("\nFINAL OPTIONS:")
    for opt in recommendation.options:
        drugs_str = "; ".join(f"{d.drug}:{d.action}" for d in opt.drugs)
        parts.append(f"  Option {opt.rank}: {opt.label} — {drugs_str}")
        parts.append(f"    Rationale: {opt.rationale}")

    if recommendation.synthesis_notes:
        parts.append(f"\nSYNTHESIS NOTES:\n{recommendation.synthesis_notes}")

    user_content = "\n".join(parts)
    _, formatted = await llm_client.call(system_prompt, user_content)
    return formatted
