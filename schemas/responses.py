"""Agent response data structures."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    CRITICAL = "critical"   # Safety veto — cannot be overridden
    HIGH = "high"           # Strong recommendation
    MEDIUM = "medium"       # Moderate concern
    LOW = "low"             # Informational


class ConcernCategory(Enum):
    DRUG_INTERACTION = "drug_interaction"
    SEIZURE_TYPE_MISMATCH = "seizure_type_mismatch"
    DOSING_ERROR = "dosing_error"
    AGE_SAFETY = "age_safety"
    AVAILABILITY = "availability"
    TREATMENT_CONTINUITY = "treatment_continuity"
    INFECTIOUS_ETIOLOGY = "infectious_etiology"
    FORMULATION = "formulation"
    PREGNANCY_SAFETY = "pregnancy_safety"
    OTHER = "other"


@dataclass
class Finding:
    """A structured finding from an agent."""
    category: str
    detail: str
    confidence: float = 0.0  # 0.0 to 1.0
    evidence: str = ""  # Supporting text from clinical notes


@dataclass
class Concern:
    """A concern raised by an agent about a drug or plan."""
    severity: Severity
    category: ConcernCategory
    affected_drugs: list[str] = field(default_factory=list)
    description: str = ""
    recommendation: str = ""


@dataclass
class AgentResponse:
    """Structured response from a specialist agent."""
    agent_name: str
    agent_role: str
    findings: list[Finding] = field(default_factory=list)
    concerns: list[Concern] = field(default_factory=list)
    recommended_drugs: list[str] = field(default_factory=list)
    contraindicated_drugs: list[str] = field(default_factory=list)
    reasoning: str = ""
    raw_output: str = ""
    confidence: float = 0.0  # Overall confidence in assessment

    def has_critical_concerns(self) -> bool:
        return any(c.severity == Severity.CRITICAL for c in self.concerns)

    def to_summary(self) -> str:
        """Generate a concise summary for downstream agents."""
        lines = [f"=== {self.agent_role} Assessment ==="]
        if self.findings:
            lines.append("Findings:")
            for f in self.findings:
                conf = f"(confidence: {f.confidence:.1f})" if f.confidence else ""
                lines.append(f"  - [{f.category}] {f.detail} {conf}")
        if self.concerns:
            lines.append("Concerns:")
            for c in self.concerns:
                drugs = ", ".join(c.affected_drugs) if c.affected_drugs else "general"
                lines.append(f"  - [{c.severity.value}] {c.description} (affects: {drugs})")
                if c.recommendation:
                    lines.append(f"    Recommendation: {c.recommendation}")
        if self.recommended_drugs:
            lines.append(f"Recommended drugs: {', '.join(self.recommended_drugs)}")
        if self.contraindicated_drugs:
            lines.append(f"Contraindicated drugs: {', '.join(self.contraindicated_drugs)}")
        return "\n".join(lines)
