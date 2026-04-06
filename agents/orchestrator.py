"""V2 Orchestrator — routes patients to the right Phase 1 agents."""

from __future__ import annotations
import os
import re
from dataclasses import dataclass

from schemas.patient import PatientCase
from llm.client import LLMClient
from agents.base import BaseAgent
from agents.registry import PHASE1_AGENTS

PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "prompts", "orchestrator.txt"
)


@dataclass
class ActivationDecision:
    """Result of orchestrator routing for one agent."""
    agent_name: str
    activated: bool
    reason: str


def _format_agent_block(cls: type[BaseAgent]) -> str:
    """Format a single agent class for the orchestrator prompt."""
    lines = [
        f"- {cls.name} ({cls.role})",
        f"  Key question: {cls.key_question}",
        f"  {cls.description}",
    ]
    return "\n".join(lines)


def _build_system_prompt(available_agents: dict) -> str:
    """Build the orchestrator system prompt with only the available agent classes."""
    with open(PROMPT_PATH, encoding="utf-8") as f:
        template = f.read()

    always_on = [cls for cls in available_agents.values() if cls.always_active]
    conditional = [cls for cls in available_agents.values() if not cls.always_active]

    always_on_text = "\n\n".join(_format_agent_block(cls) for cls in always_on)
    conditional_text = "\n\n".join(_format_agent_block(cls) for cls in conditional)

    prompt = template.replace("{always_on_agents}", always_on_text)
    prompt = prompt.replace("{conditional_agents}", conditional_text)
    return prompt


def _parse_decisions(raw_output: str, conditional_classes: list[type[BaseAgent]]) -> list[ActivationDecision]:
    """Parse orchestrator output into activation decisions for conditional agents."""
    decisions = []

    for cls in conditional_classes:
        pattern = re.compile(
            rf'{re.escape(cls.name)}\s*:\s*(activate|skip)\s*\n\s*reason\s*:\s*(.+)',
            re.IGNORECASE,
        )
        match = pattern.search(raw_output)
        if match:
            action = match.group(1).strip().lower()
            reason = match.group(2).strip()
            decisions.append(ActivationDecision(
                agent_name=cls.name,
                activated=(action == "activate"),
                reason=reason,
            ))
        else:
            # Can't parse — activate by default (safe fallback)
            decisions.append(ActivationDecision(
                agent_name=cls.name,
                activated=True,
                reason="orchestrator output unparseable — activating by default",
            ))

    return decisions


async def run_orchestrator(
    patient: PatientCase,
    llm_client: LLMClient,
    available_agents: dict | None = None,
) -> list[ActivationDecision]:
    """Run the orchestrator to decide which agents to activate.

    available_agents: subset of PHASE1_AGENTS the orchestrator can see and choose from.
    If None, uses all PHASE1_AGENTS.
    """
    agents = available_agents if available_agents is not None else PHASE1_AGENTS
    decisions: list[ActivationDecision] = []

    always_on = {n: c for n, c in agents.items() if c.always_active}
    conditional = {n: c for n, c in agents.items() if not c.always_active}

    for name in always_on:
        decisions.append(ActivationDecision(agent_name=name, activated=True, reason="always active"))

    if conditional:
        system_prompt = _build_system_prompt(agents)
        user_content = patient.build_input_text()
        _, raw_output = await llm_client.call(system_prompt, user_content, temperature=0.0)

        llm_decisions = _parse_decisions(raw_output, list(conditional.values()))
        decisions.extend(llm_decisions)

    return decisions
