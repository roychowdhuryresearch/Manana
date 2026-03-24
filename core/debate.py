"""V2 Debate: epileptologist <-> pharmacologist rounds.

max_rounds controls how many epi revisions happen after the initial pharma critique.

  max_rounds=0: epi -> pharma -> epi (1 revision) -> done
  max_rounds=1: epi -> pharma -> epi -> pharma -> epi -> done
  max_rounds=N: ... always ends on epi

Each round: epi revises (sees pharma critique + prior plan), then pharma re-critiques.
Final entry always has epileptologist output (may not have pharmacologist if it's the last).
"""

from __future__ import annotations

from schemas.patient import PatientCase
from schemas.responses import AgentResponse
from agents.base import BaseAgent
from core.regimen_parser import parse_regimen


def has_concerns(pharm_output: str) -> bool:
    """Check if pharmacologist output indicates remaining concerns."""
    return "verdict: no_concerns" not in pharm_output.lower().replace(" ", "")


async def run_debate(
    patient: PatientCase,
    epileptologist: BaseAgent,
    pharmacologist: BaseAgent,
    epi_response: AgentResponse,
    pharm_response: AgentResponse,
    phase1_responses: dict[str, AgentResponse],
    max_rounds: int = 0,
) -> list[dict]:
    """Run debate rounds. Always ends on epi.

    Round 0 (always runs): epi revises after initial pharma critique.
    Round 1..N: pharma re-critiques, then epi revises again.

    Returns:
        List of round dicts. Each has "epileptologist" and "epileptologist_regimen".
        All except the last also have "pharmacologist".
    """
    rounds = []
    current_pharm_output = pharm_response.raw_output
    current_epi_output = epi_response.raw_output

    for round_num in range(max_rounds + 1):
        # Epi revision: sees pharma critique + own prior plan
        epi_context = {
            "phase1_responses": phase1_responses,
            "pharmacologist_critique": current_pharm_output,
            "prior_plan": current_epi_output,
        }
        epi_revised = await epileptologist.run(patient, epi_context)
        current_epi_output = epi_revised.raw_output

        round_entry = {
            "round": round_num,
            "epileptologist": current_epi_output,
            "epileptologist_regimen": parse_regimen(current_epi_output),
        }

        # Pharma re-critique (skip on last round — we end on epi)
        if round_num < max_rounds:
            pharm_context = {
                "phase1_responses": phase1_responses,
                "epileptologist_response": epi_revised,
            }
            pharm_recritique = await pharmacologist.run(patient, pharm_context)
            current_pharm_output = pharm_recritique.raw_output
            round_entry["pharmacologist"] = current_pharm_output

            # Early exit if pharma has no concerns
            if not has_concerns(current_pharm_output):
                rounds.append(round_entry)
                break

        rounds.append(round_entry)

    return rounds
