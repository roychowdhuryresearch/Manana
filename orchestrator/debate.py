"""Structured debate between Pharmacologist and Epileptologist.

Max 2 rounds. Unresolved concerns become explicit uncertainty markers.
"""

from __future__ import annotations
import json
import os
import re

from schemas.patient import PatientCase
from schemas.responses import AgentResponse, Severity
from schemas.trace import DebateRound
from llm.client import LLMClient

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agents", "prompts")


async def run_debate(
    patient: PatientCase,
    epileptologist_response: AgentResponse,
    pharmacologist_response: AgentResponse,
    llm_client: LLMClient,
    max_rounds: int = 2,
) -> list[DebateRound]:
    """Run structured debate between pharmacologist and epileptologist.

    Returns list of DebateRound objects (1-2 rounds).
    """
    # Only debate if pharmacologist raised concerns
    if not pharmacologist_response.concerns:
        return []

    with open(os.path.join(PROMPTS_DIR, "debate_rebuttal.txt"), encoding="utf-8") as f:
        rebuttal_template = f.read()

    rounds = []

    # Current state of concerns
    active_concerns = list(pharmacologist_response.concerns)
    current_plan = epileptologist_response.raw_output

    for round_num in range(1, max_rounds + 1):
        if not active_concerns:
            break

        # Format concerns for the epileptologist
        concerns_text = "\n".join(
            f"Concern {i+1} [{c.severity.value}]: {c.description} "
            f"(affects: {', '.join(c.affected_drugs)}). "
            f"Recommendation: {c.recommendation}"
            for i, c in enumerate(active_concerns)
        )

        # Build rebuttal prompt
        rebuttal_prompt = rebuttal_template.replace("{concerns}", concerns_text)
        rebuttal_prompt = rebuttal_prompt.replace("{plan}", current_plan)
        rebuttal_prompt = rebuttal_prompt.replace("{patient_input}", patient.build_input_text())

        # Get epileptologist's rebuttal
        _, rebuttal_raw = await llm_client.call(
            "You are the Prescribing Epileptologist responding to pharmacologist concerns.",
            rebuttal_prompt,
        )

        # Parse rebuttal
        rebuttal_actions = []
        resolved = []
        unresolved = []

        json_match = re.search(r'\{[\s\S]*\}', rebuttal_raw)
        if json_match:
            try:
                data = json.loads(json_match.group())
                for reb in data.get("rebuttals", []):
                    idx = reb.get("concern_index", 0)
                    action = reb.get("action", "reject")
                    rebuttal_actions.append({
                        "concern_index": idx,
                        "action": action,
                        "justification": reb.get("justification", ""),
                        "modified_drugs": reb.get("modified_drugs", []),
                    })
                    if action in ("accept", "modify"):
                        resolved.append(f"Concern {idx+1}: {action}")
                    else:
                        unresolved.append(f"Concern {idx+1}: rejected by epileptologist")

                modified_plan = data.get("modified_plan", "")
                if modified_plan and modified_plan != "no changes":
                    current_plan = modified_plan
            except json.JSONDecodeError:
                unresolved = [f"Concern {i+1}: parse error" for i in range(len(active_concerns))]

        debate_round = DebateRound(
            round_number=round_num,
            pharmacologist_concerns=active_concerns,
            epileptologist_rebuttal=rebuttal_raw,
            rebuttal_actions=rebuttal_actions,
            resolved_concerns=resolved,
            unresolved_concerns=unresolved,
        )

        # Get pharmacologist's verdict on rebuttals
        verdict_prompt = (
            f"The epileptologist has responded to your concerns:\n\n{rebuttal_raw}\n\n"
            f"For each of your original concerns, evaluate:\n"
            f"- RESOLVED: The epileptologist's response adequately addresses the concern\n"
            f"- UNRESOLVED: The concern remains valid despite the rebuttal\n\n"
            f"Respond with a brief verdict for each concern."
        )
        _, verdict_raw = await llm_client.call(
            "You are the Clinical Pharmacologist evaluating the epileptologist's response to your safety concerns.",
            verdict_prompt,
        )
        debate_round.pharmacologist_verdict = verdict_raw

        rounds.append(debate_round)

        # Filter to only unresolved concerns for next round
        active_concerns = [
            c for i, c in enumerate(active_concerns)
            if f"Concern {i+1}: rejected" in " ".join(unresolved)
            or f"Concern {i+1}: parse error" in " ".join(unresolved)
        ]

    return rounds
