"""Reasoning trace quality metrics."""

from __future__ import annotations

from schemas.trace import ReasoningTrace


def evaluate_trace_quality(trace: ReasoningTrace) -> dict:
    """Evaluate the quality of a reasoning trace.

    Metrics:
    - completeness: did all expected agents run and produce output?
    - conflict_detection: were conflicts detected and resolved?
    - debate_depth: if debate triggered, how substantive was it?
    - provenance: can we trace each drug decision back to an agent?
    """
    metrics = {}

    # Completeness
    expected_agents = {"diagnostician", "treatment_analyst", "pediatrician", "formulary"}
    activated = set(trace.agents_activated)
    metrics["agents_activated"] = len(activated)
    metrics["completeness"] = len(activated & expected_agents) / len(expected_agents)

    # All agents produced non-empty output
    agents_with_output = sum(
        1 for r in trace.phase1_responses.values()
        if r.raw_output.strip()
    )
    has_epi = trace.epileptologist_response and trace.epileptologist_response.raw_output.strip()
    has_pharm = trace.pharmacologist_response and trace.pharmacologist_response.raw_output.strip()
    total_with_output = agents_with_output + (1 if has_epi else 0) + (1 if has_pharm else 0)
    metrics["agents_with_output"] = total_with_output

    # Findings coverage
    total_findings = sum(len(r.findings) for r in trace.phase1_responses.values())
    metrics["total_findings"] = total_findings

    # Conflict detection
    metrics["conflicts_detected"] = len(trace.detected_conflicts)
    metrics["conflicts_resolved"] = sum(1 for c in trace.detected_conflicts if c.resolved)

    # Debate metrics
    metrics["debate_triggered"] = trace.debate_triggered
    if trace.debate_triggered:
        metrics["debate_rounds"] = len(trace.debate_rounds)
        total_resolved = sum(len(r.resolved_concerns) for r in trace.debate_rounds)
        total_unresolved = sum(len(r.unresolved_concerns) for r in trace.debate_rounds)
        metrics["debate_concerns_resolved"] = total_resolved
        metrics["debate_concerns_unresolved"] = total_unresolved
    else:
        metrics["debate_rounds"] = 0
        metrics["debate_concerns_resolved"] = 0
        metrics["debate_concerns_unresolved"] = 0

    # Agreement
    metrics["agreement_score"] = trace.agreement_score
    metrics["total_concerns"] = trace.total_concerns_raised
    metrics["critical_concerns"] = trace.critical_concerns

    return metrics


def aggregate_trace_metrics(traces: list[ReasoningTrace]) -> dict:
    """Aggregate trace quality metrics across all patients."""
    if not traces:
        return {}

    all_metrics = [evaluate_trace_quality(t) for t in traces]

    agg = {}
    numeric_keys = [
        "agents_activated", "completeness", "agents_with_output",
        "total_findings", "conflicts_detected", "conflicts_resolved",
        "debate_rounds", "agreement_score", "total_concerns", "critical_concerns",
    ]

    for key in numeric_keys:
        values = [m[key] for m in all_metrics]
        agg[f"mean_{key}"] = sum(values) / len(values)
        agg[f"min_{key}"] = min(values)
        agg[f"max_{key}"] = max(values)

    agg["debate_trigger_rate"] = sum(1 for m in all_metrics if m["debate_triggered"]) / len(all_metrics)
    agg["n_traces"] = len(traces)

    return agg
