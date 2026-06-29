"""Base agent abstract class and shared utilities."""

from __future__ import annotations
import os
from abc import ABC, abstractmethod

from lib.patient import PatientCase
from lib.responses import AgentResponse
from lib.llm import LLMClient

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


class BaseAgent(ABC):
    """Abstract base class for specialist agents."""

    name: str = ""
    role: str = ""
    description: str = ""
    key_question: str = ""
    phase: int = 1  # 1, 2, or 3
    prompt_file: str = ""  # Filename in consilium/agents/prompts/
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

    async def run(self, patient: PatientCase, context: dict | None = None) -> AgentResponse:
        """Run this agent on a patient case."""
        user_content = self.build_user_prompt(patient, context)
        thinking, raw_output = await self.llm.call(self.system_prompt, user_content, temperature=0.0)
        return self.parse_response(raw_output, thinking)

    def build_user_prompt(self, patient: PatientCase, context: dict | None = None) -> str:
        """Build the user prompt. Default: patient input text only."""
        return patient.build_input_text()

    def parse_response(self, raw_output: str, thinking: str = "") -> AgentResponse:
        """Parse LLM output into AgentResponse. Override for custom parsing."""
        return AgentResponse(
            agent_name=self.name,
            agent_role=self.role,
            raw_output=raw_output,
            reasoning=thinking,
        )
