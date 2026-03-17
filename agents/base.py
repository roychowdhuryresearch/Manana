"""Base agent abstract class and shared utilities."""

from __future__ import annotations
import json
import re
import os
from abc import ABC, abstractmethod

from schemas.patient import PatientCase
from schemas.responses import (
    AgentResponse, Finding, Concern,
    Severity, ConcernCategory,
)
from llm.client import LLMClient

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


class BaseAgent(ABC):
    """Abstract base class for specialist agents."""

    name: str = ""
    role: str = ""
    prompt_file: str = ""  # Filename in agents/prompts/
    always_active: bool = True  # False for conditional agents

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self._system_prompt: str | None = None

    @property
    def system_prompt(self) -> str:
        if self._system_prompt is None:
            path = os.path.join(PROMPTS_DIR, self.prompt_file)
            with open(path, encoding="utf-8") as f:
                self._system_prompt = f.read()
        return self._system_prompt

    def should_activate(self, patient: PatientCase) -> tuple[bool, str]:
        """Check if this agent should run for a given patient.

        Returns (should_run, reason).
        Always-active agents return True with a standard reason.
        Conditional agents override this.
        """
        if self.always_active:
            return True, "always active"
        return False, "not applicable"

    async def run(self, patient: PatientCase, context: dict | None = None) -> AgentResponse:
        """Run this agent on a patient case.

        Args:
            patient: The patient case to analyze.
            context: Optional dict of prior agent outputs (for Phase 2/3 agents).

        Returns:
            Structured AgentResponse.
        """
        user_content = self.build_user_prompt(patient, context)
        thinking, raw_output = await self.llm.call(self.system_prompt, user_content)
        return self.parse_response(raw_output, thinking)

    def build_user_prompt(self, patient: PatientCase, context: dict | None = None) -> str:
        """Build the user prompt for this agent.

        Default: patient input text. Override for agents that need additional context.
        """
        parts = [patient.build_input_text()]
        if context:
            parts.append("\n\n--- PRIOR SPECIALIST ASSESSMENTS ---")
            for agent_name, response in context.items():
                if isinstance(response, AgentResponse):
                    parts.append(response.to_summary())
                elif isinstance(response, str):
                    parts.append(response)
        return "\n\n".join(parts)

    def parse_response(self, raw_output: str, thinking: str = "") -> AgentResponse:
        """Parse LLM output into structured AgentResponse.

        Default implementation tries JSON parsing, then falls back to
        text extraction. Agents can override for custom parsing.
        """
        response = AgentResponse(
            agent_name=self.name,
            agent_role=self.role,
            raw_output=raw_output,
            reasoning=thinking,
        )

        # Try JSON parsing first
        json_match = re.search(r'\{[\s\S]*\}', raw_output)
        if json_match:
            try:
                data = json.loads(json_match.group())
                response = self._parse_json_response(data, response)
                return response
            except json.JSONDecodeError:
                pass

        # Fall back to text extraction
        response = self._parse_text_response(raw_output, response)
        return response

    def _parse_json_response(self, data: dict, response: AgentResponse) -> AgentResponse:
        """Parse a JSON-structured response."""
        # Findings
        for f in data.get("findings", []):
            response.findings.append(Finding(
                category=f.get("category", ""),
                detail=f.get("detail", ""),
                confidence=float(f.get("confidence", 0.0)),
                evidence=f.get("evidence", ""),
            ))

        # Concerns
        for c in data.get("concerns", []):
            severity = Severity.MEDIUM
            try:
                severity = Severity(c.get("severity", "medium"))
            except ValueError:
                pass
            category = ConcernCategory.OTHER
            try:
                category = ConcernCategory(c.get("category", "other"))
            except ValueError:
                pass
            response.concerns.append(Concern(
                severity=severity,
                category=category,
                affected_drugs=c.get("affected_drugs", []),
                description=c.get("description", ""),
                recommendation=c.get("recommendation", ""),
            ))

        response.recommended_drugs = data.get("recommended_drugs", [])
        response.contraindicated_drugs = data.get("contraindicated_drugs", [])
        response.confidence = float(data.get("confidence", 0.0))

        return response

    def _parse_text_response(self, text: str, response: AgentResponse) -> AgentResponse:
        """Fallback text-based response parsing."""
        # Extract recommended drugs
        rec_match = re.search(
            r'(?:recommend|suggest|prescribe)[^:]*:\s*(.+?)(?:\n|$)',
            text, re.IGNORECASE,
        )
        if rec_match:
            from schemas.output import DRUG_COLUMNS
            for drug in DRUG_COLUMNS:
                if drug in rec_match.group(1).lower():
                    response.recommended_drugs.append(drug)

        # Extract contraindicated drugs
        contra_match = re.search(
            r'(?:contraindicated|avoid|do not use)[^:]*:\s*(.+?)(?:\n|$)',
            text, re.IGNORECASE,
        )
        if contra_match:
            from schemas.output import DRUG_COLUMNS
            for drug in DRUG_COLUMNS:
                if drug in contra_match.group(1).lower():
                    response.contraindicated_drugs.append(drug)

        return response
