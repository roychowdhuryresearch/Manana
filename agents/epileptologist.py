"""Prescribing Epileptologist — integrates specialist inputs into treatment plan."""

import re
from agents.base import BaseAgent
from schemas.patient import PatientCase
from schemas.responses import AgentResponse
from schemas.output import DRUG_COLUMNS, ALLOWED_ACTIONS


class EpileptologistAgent(BaseAgent):
    name = "epileptologist"
    role = "Prescribing Epileptologist"
    description = (
        "Integrates all specialist inputs into a ranked treatment plan "
        "with 3 regimen options. Addresses disagreements between "
        "specialists and justifies departures from their recommendations."
    )
    key_question = "What should the prescription be?"
    phase = 2
    prompt_file = "epileptologist.txt"
    always_active = True

    async def run(self, patient: PatientCase, context: dict | None = None) -> AgentResponse:
        """Epileptologist runs at temperature=0 for deterministic prescriptions."""
        user_content = self.build_user_prompt(patient, context)
        thinking, raw_output = await self.llm.call(self.system_prompt, user_content, temperature=0.0)
        return self.parse_response(raw_output, thinking)

    def build_user_prompt(self, patient: PatientCase, context: dict | None = None) -> str:
        """Epileptologist sees patient + Phase 1 outputs + optional pharma critique + prior plan."""
        parts = [patient.build_input_text()]

        if context:
            # Phase 1 agent outputs
            phase1_responses = context.get("phase1_responses", {})
            if phase1_responses:
                parts.append("\n\n--- SPECIALIST ASSESSMENTS (Phase 1) ---")
                for agent_name, response in phase1_responses.items():
                    if isinstance(response, AgentResponse):
                        parts.append(f"=== {response.agent_role} ===\n{response.raw_output}")
                    elif isinstance(response, str):
                        parts.append(response)

            # Pharmacologist critique (during debate)
            pharm_critique = context.get("pharmacologist_critique")
            if pharm_critique:
                parts.append("\n\n--- PHARMACOLOGIST CRITIQUE ---")
                parts.append(pharm_critique)

            # Epi's own prior plan (during debate revision)
            prior_plan = context.get("prior_plan")
            if prior_plan:
                parts.append("\n\n--- YOUR PRIOR PLAN ---")
                parts.append(prior_plan)

        return "\n\n".join(parts)

    def parse_response(self, raw_output: str, thinking: str = "") -> AgentResponse:
        """Parse epileptologist's output — extract Option 1 drugs for recommended_drugs."""
        response = AgentResponse(
            agent_name=self.name,
            agent_role=self.role,
            raw_output=raw_output,
            reasoning=thinking,
        )

        # Extract drug options and store as recommended drugs from Option 1
        block_pattern = re.compile(
            r'Option\s+(\d)\s*:\s*(.+?)(?=Option\s+\d\s*:|$)',
            re.DOTALL | re.IGNORECASE,
        )
        for m in block_pattern.finditer(raw_output):
            num = int(m.group(1))
            if num == 1:
                for line in m.group(2).split('\n'):
                    dm = re.match(r'-\s*(\w+)\s*:\s*(\w+)', line.strip())
                    if dm:
                        drug = dm.group(1).lower()
                        action = dm.group(2).lower()
                        if action == "discontinue":
                            action = "stop"
                        if drug in DRUG_COLUMNS and action in ALLOWED_ACTIONS:
                            if action != "stop":
                                response.recommended_drugs.append(drug)

        return response
