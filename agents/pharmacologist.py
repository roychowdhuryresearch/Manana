"""Clinical Pharmacologist — adversarial safety review."""

from agents.base import BaseAgent
from schemas.patient import PatientCase
from schemas.responses import AgentResponse


class PharmacologistAgent(BaseAgent):
    name = "pharmacologist"
    role = "Clinical Pharmacologist"
    description = (
        "Adversarial safety review of the epileptologist's plan. "
        "Identifies drug interactions, dosing errors, contraindications, "
        "and dangerous combinations."
    )
    key_question = "What could go wrong with this plan?"
    phase = 3
    prompt_file = "pharmacologist.txt"
    always_active = True

    async def run(self, patient: PatientCase, context: dict | None = None) -> AgentResponse:
        """Pharmacologist runs at temperature=0 for deterministic reviews."""
        user_content = self.build_user_prompt(patient, context)
        thinking, raw_output = await self.llm.call(self.system_prompt, user_content, temperature=0.0)
        return self.parse_response(raw_output, thinking)

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
                        parts.append(f"=== {response.agent_role} ===\n{response.raw_output}")

            # Epileptologist's plan
            epi_response = context.get("epileptologist_response")
            if epi_response:
                parts.append("\n\n--- EPILEPTOLOGIST'S PROPOSED PLAN ---")
                if isinstance(epi_response, AgentResponse):
                    parts.append(epi_response.raw_output)
                elif isinstance(epi_response, str):
                    parts.append(epi_response)

        return "\n\n".join(parts)
