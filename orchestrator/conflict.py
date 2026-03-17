"""Programmatic conflict detection between agent assessments.

Resolution hierarchy (strongest to weakest):
1. Safety veto — critical pediatric safety concern or drug interaction → drug excluded
2. Domain authority — seizure type defers to diagnostician if confidence > 0.6
3. Treatment continuity — if treatment analyst says "responding well" with high confidence
4. Practical constraints — availability/cost modifies but doesn't veto clinical necessity
5. Debate resolution — for pharmacologist vs epileptologist disagreements
"""

from __future__ import annotations

from schemas.responses import AgentResponse, Severity, ConcernCategory
from schemas.trace import ConflictRecord


def _to_str_set(items: list) -> set[str]:
    """Normalize a list of drug names (which may contain dicts) to a set of strings."""
    result = set()
    for item in items:
        if isinstance(item, str):
            result.add(item.lower().strip())
        elif isinstance(item, dict):
            # Handle cases like {"drug": "valproate", "action": "continue"}
            name = item.get("drug", item.get("name", str(item)))
            result.add(str(name).lower().strip())
    return result


def detect_conflicts(phase1_responses: dict[str, AgentResponse]) -> list[ConflictRecord]:
    """Detect conflicts between Phase 1 agent assessments.

    Returns a list of ConflictRecord objects describing each detected conflict.
    """
    conflicts = []

    diagnostician = phase1_responses.get("diagnostician")
    treatment_analyst = phase1_responses.get("treatment_analyst")
    pediatrician = phase1_responses.get("pediatrician")
    formulary = phase1_responses.get("formulary")
    tropical_medicine = phase1_responses.get("tropical_medicine")

    # 1. Seizure type vs treatment continuity conflict
    if diagnostician and treatment_analyst:
        diag_contras = _to_str_set(diagnostician.contraindicated_drugs)
        treatment_recs = _to_str_set(treatment_analyst.recommended_drugs)
        overlap = diag_contras & treatment_recs
        if overlap:
            conflicts.append(ConflictRecord(
                conflict_type="seizure_type_vs_treatment_continuity",
                agents_involved=["diagnostician", "treatment_analyst"],
                description=(
                    f"Treatment analyst recommends continuing {', '.join(overlap)}, "
                    f"but diagnostician says these are contraindicated for the seizure type."
                ),
                resolution_rule="Domain authority: diagnostician's seizure classification takes precedence if confidence > 0.6",
                resolved=diagnostician.confidence > 0.6,
                resolution=(
                    f"Diagnostician classification (confidence {diagnostician.confidence:.1f}) overrides treatment continuity"
                    if diagnostician.confidence > 0.6
                    else "Diagnostician confidence too low to override — flag for epileptologist to decide"
                ),
            ))

    # 2. Pediatric safety concerns about drugs recommended by others
    if pediatrician:
        for concern in pediatrician.concerns:
            if concern.severity in (Severity.CRITICAL, Severity.HIGH):
                affected = _to_str_set(concern.affected_drugs)
                # Check if any other agent recommends these drugs
                for agent_name, resp in phase1_responses.items():
                    if agent_name == "pediatrician":
                        continue
                    rec_overlap = affected & _to_str_set(resp.recommended_drugs)
                    if rec_overlap:
                        conflicts.append(ConflictRecord(
                            conflict_type="pediatric_safety_conflict",
                            agents_involved=["pediatrician", agent_name],
                            description=(
                                f"Pediatrician raises {concern.severity.value} concern about "
                                f"{', '.join(rec_overlap)}: {concern.description}"
                            ),
                            resolution_rule=(
                                "Safety veto: critical pediatric concern excludes drug"
                                if concern.severity == Severity.CRITICAL
                                else "High-priority pediatric concern — epileptologist must address"
                            ),
                            resolved=concern.severity == Severity.CRITICAL,
                            resolution=(
                                f"Safety veto applied — {', '.join(rec_overlap)} excluded"
                                if concern.severity == Severity.CRITICAL
                                else "Flagged for epileptologist decision"
                            ),
                        ))

    # 3. Availability conflicts
    if formulary:
        unavailable_drugs = set()
        for concern in formulary.concerns:
            if concern.category == ConcernCategory.AVAILABILITY:
                unavailable_drugs.update(_to_str_set(concern.affected_drugs))
        if unavailable_drugs:
            for agent_name, resp in phase1_responses.items():
                if agent_name == "formulary":
                    continue
                rec_overlap = unavailable_drugs & _to_str_set(resp.recommended_drugs)
                if rec_overlap:
                    conflicts.append(ConflictRecord(
                        conflict_type="availability_conflict",
                        agents_involved=["formulary", agent_name],
                        description=(
                            f"Formulary specialist flags {', '.join(rec_overlap)} as potentially "
                            f"unavailable, but {agent_name} recommends them."
                        ),
                        resolution_rule="Practical constraints modify options but don't veto clinical necessity",
                        resolved=False,
                        resolution="Epileptologist should prefer available alternatives when clinically equivalent",
                    ))

    # 4. Infectious etiology changes treatment approach
    if tropical_medicine:
        for finding in tropical_medicine.findings:
            if finding.category == "infectious_differential" and finding.confidence > 0.5:
                if "not epilepsy" in finding.detail.lower() or "infectious" in finding.detail.lower():
                    conflicts.append(ConflictRecord(
                        conflict_type="etiology_conflict",
                        agents_involved=["tropical_medicine", "diagnostician"],
                        description=(
                            f"Tropical medicine specialist suggests possible infectious etiology: "
                            f"{finding.detail}"
                        ),
                        resolution_rule="Infectious etiology assessment modifies but doesn't replace epilepsy management",
                        resolved=False,
                        resolution="Epileptologist must consider both epileptic and infectious management",
                    ))

    return conflicts


def apply_safety_vetoes(
    phase1_responses: dict[str, AgentResponse],
    conflicts: list[ConflictRecord],
) -> set[str]:
    """Return set of drugs that are safety-vetoed and cannot be prescribed.

    Only CRITICAL severity concerns trigger safety vetoes.
    """
    vetoed = set()

    for agent_name, resp in phase1_responses.items():
        for concern in resp.concerns:
            if concern.severity == Severity.CRITICAL:
                vetoed.update(concern.affected_drugs)

    return vetoed
