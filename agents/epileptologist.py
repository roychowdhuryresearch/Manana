"""Prescribing Epileptologist — integrates specialist inputs into treatment plan."""

import re
import json
from agents.base import BaseAgent
from schemas.patient import PatientCase
from schemas.responses import AgentResponse
from schemas.output import DRUG_COLUMNS, ALLOWED_ACTIONS


class EpileptologistAgent(BaseAgent):
    name = "epileptologist"
    role = "Prescribing Epileptologist"
    prompt_file = "epileptologist.txt"
    always_active = True

    def build_user_prompt(self, patient: PatientCase, context: dict | None = None) -> str:
        """Epileptologist sees patient input + all Phase 1 outputs + detected conflicts."""
        parts = [patient.build_input_text()]

        if context:
            # Phase 1 agent outputs
            phase1_responses = context.get("phase1_responses", {})
            if phase1_responses:
                parts.append("\n\n--- SPECIALIST ASSESSMENTS (Phase 1) ---")
                for agent_name, response in phase1_responses.items():
                    if isinstance(response, AgentResponse):
                        parts.append(response.to_summary())
                    elif isinstance(response, str):
                        parts.append(response)

            # Detected conflicts
            conflicts = context.get("conflicts", [])
            if conflicts:
                parts.append("\n\n--- DETECTED CONFLICTS ---")
                for conflict in conflicts:
                    parts.append(f"- [{conflict.conflict_type}] {conflict.description}")
                    if conflict.resolution_rule:
                        parts.append(f"  Resolution rule: {conflict.resolution_rule}")

        return "\n\n".join(parts)

    def parse_response(self, raw_output: str, thinking: str = "") -> AgentResponse:
        """Parse epileptologist's structured output with drug options."""
        response = AgentResponse(
            agent_name=self.name,
            agent_role=self.role,
            raw_output=raw_output,
            reasoning=thinking,
        )

        # Extract reasoning section
        sec1 = re.search(
            r'---\s*SECTION\s*1.*?---\s*(.*?)(?=---\s*SECTION\s*2|$)',
            raw_output, re.DOTALL | re.IGNORECASE,
        )
        if sec1:
            response.reasoning = sec1.group(1).strip()

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
                        if drug in DRUG_COLUMNS and action in ALLOWED_ACTIONS:
                            if action != "stop":
                                response.recommended_drugs.append(drug)

        return response
