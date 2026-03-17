"""Clinical Pharmacologist — adversarial safety review."""

from agents.base import BaseAgent
from schemas.patient import PatientCase
from schemas.responses import AgentResponse


class PharmacologistAgent(BaseAgent):
    name = "pharmacologist"
    role = "Clinical Pharmacologist"
    prompt_file = "pharmacologist.txt"
    always_active = True

    def build_user_prompt(self, patient: PatientCase, context: dict | None = None) -> str:
        """Pharmacologist sees patient + Phase 1 outputs + epileptologist's plan."""
        parts = [patient.build_input_text()]

        if context:
            # Phase 1 agent outputs
            phase1_responses = context.get("phase1_responses", {})
            if phase1_responses:
                parts.append("\n\n--- SPECIALIST ASSESSMENTS (Phase 1) ---")
                for agent_name, response in phase1_responses.items():
                    if isinstance(response, AgentResponse):
                        parts.append(response.to_summary())

            # Epileptologist's plan
            epi_response = context.get("epileptologist_response")
            if epi_response:
                parts.append("\n\n--- EPILEPTOLOGIST'S PROPOSED PLAN ---")
                if isinstance(epi_response, AgentResponse):
                    parts.append(epi_response.raw_output)
                elif isinstance(epi_response, str):
                    parts.append(epi_response)

        return "\n\n".join(parts)
