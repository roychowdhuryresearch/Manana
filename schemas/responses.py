"""Agent response data structures."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class AgentResponse:
    """Structured response from a specialist agent."""
    agent_name: str
    agent_role: str
    recommended_drugs: list[str] = field(default_factory=list)
    reasoning: str = ""
    raw_output: str = ""
