"""Reasoning trace data structures for full provenance tracking."""

from __future__ import annotations
from dataclasses import dataclass, field
from schemas.responses import AgentResponse, Concern


@dataclass
class ConflictRecord:
    """A detected conflict between agent assessments."""
    conflict_type: str  # e.g. "seizure_type_disagreement", "treatment_continuity"
    agents_involved: list[str] = field(default_factory=list)
    description: str = ""
    resolution: str = ""  # How it was resolved
    resolution_rule: str = ""  # Which rule was applied
    resolved: bool = False


@dataclass
class DebateRound:
    """A single round of pharmacologist-epileptologist debate."""
    round_number: int
    pharmacologist_concerns: list[Concern] = field(default_factory=list)
    epileptologist_rebuttal: str = ""
    rebuttal_actions: list[dict] = field(default_factory=list)  # {concern_id, action: accept/reject/modify, justification}
    pharmacologist_verdict: str = ""
    resolved_concerns: list[str] = field(default_factory=list)
    unresolved_concerns: list[str] = field(default_factory=list)


@dataclass
class ReasoningTrace:
    """Complete reasoning trace for a patient case. This IS the paper's deliverable."""
    patient_id: str
    visit: str

    # Which agents ran
    agents_activated: list[str] = field(default_factory=list)
    activation_reasons: dict[str, str] = field(default_factory=dict)

    # Phase 1: Independent assessments
    phase1_responses: dict[str, AgentResponse] = field(default_factory=dict)

    # Phase 1.5: Conflicts
    detected_conflicts: list[ConflictRecord] = field(default_factory=list)

    # Phase 2: Epileptologist plan
    epileptologist_response: AgentResponse | None = None

    # Phase 3: Pharmacologist review
    pharmacologist_response: AgentResponse | None = None

    # Phase 3.5: Debate
    debate_triggered: bool = False
    debate_rounds: list[DebateRound] = field(default_factory=list)

    # Phase 4: Final synthesis
    final_recommendation: dict | None = None  # FinalRecommendation as dict

    # Meta
    agreement_score: float = 0.0  # Inter-agent agreement (0-1)
    total_concerns_raised: int = 0
    critical_concerns: int = 0

    def to_dict(self) -> dict:
        """Serialize trace for JSON output."""
        import dataclasses
        from schemas.responses import Severity, ConcernCategory

        def _serialize(obj):
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                return {k: _serialize(v) for k, v in dataclasses.asdict(obj).items()}
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_serialize(v) for v in obj]
            if isinstance(obj, (Severity, ConcernCategory)):
                return obj.value
            return obj

        return _serialize(self)
