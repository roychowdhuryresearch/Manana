"""Inter-agent disagreement analysis.

Tests hypothesis: disagreement correlates with case difficulty.
"""

from __future__ import annotations

from schemas.trace import ReasoningTrace


def compute_disagreement_metrics(trace: ReasoningTrace) -> dict:
    """Compute disagreement metrics for a single trace."""
    # Agreement score (already computed in pipeline)
    agreement = trace.agreement_score

    # Concern intensity
    total_concerns = trace.total_concerns_raised
    critical_ratio = trace.critical_concerns / total_concerns if total_concerns else 0.0

    # Debate intensity
    debate_intensity = 0.0
    if trace.debate_triggered:
        total_unresolved = sum(len(r.unresolved_concerns) for r in trace.debate_rounds)
        total_in_debate = sum(
            len(r.resolved_concerns) + len(r.unresolved_concerns)
            for r in trace.debate_rounds
        )
        debate_intensity = total_unresolved / total_in_debate if total_in_debate else 0.0

    # Conflict count
    n_conflicts = len(trace.detected_conflicts)
    n_resolved = sum(1 for c in trace.detected_conflicts if c.resolved)

    return {
        "patient_id": trace.patient_id,
        "visit": trace.visit,
        "agreement_score": agreement,
        "total_concerns": total_concerns,
        "critical_ratio": critical_ratio,
        "debate_triggered": trace.debate_triggered,
        "debate_intensity": debate_intensity,
        "n_conflicts": n_conflicts,
        "n_conflicts_resolved": n_resolved,
        "disagreement_score": 1.0 - agreement,
    }


def disagreement_difficulty_correlation(
    traces: list[ReasoningTrace],
    grades: dict[str, dict],
) -> dict:
    """Correlate disagreement with prediction difficulty.

    Args:
        traces: List of reasoning traces.
        grades: {patient_id: {exact_match, best_jaccard}} from grader.

    Returns:
        Correlation statistics and per-patient data.
    """
    data_points = []

    for trace in traces:
        metrics = compute_disagreement_metrics(trace)
        grade = grades.get(trace.patient_id, {})

        data_points.append({
            **metrics,
            "exact_match": grade.get("exact_match", False),
            "best_jaccard": grade.get("best_jaccard", 0.0),
        })

    if not data_points:
        return {"correlation": None, "data": []}

    # Simple correlation: mean disagreement for correct vs incorrect predictions
    correct = [d for d in data_points if d["exact_match"]]
    incorrect = [d for d in data_points if not d["exact_match"]]

    mean_disagree_correct = (
        sum(d["disagreement_score"] for d in correct) / len(correct) if correct else 0.0
    )
    mean_disagree_incorrect = (
        sum(d["disagreement_score"] for d in incorrect) / len(incorrect) if incorrect else 0.0
    )

    return {
        "mean_disagreement_correct": mean_disagree_correct,
        "mean_disagreement_incorrect": mean_disagree_incorrect,
        "disagreement_gap": mean_disagree_incorrect - mean_disagree_correct,
        "debate_rate_correct": sum(1 for d in correct if d["debate_triggered"]) / len(correct) if correct else 0.0,
        "debate_rate_incorrect": sum(1 for d in incorrect if d["debate_triggered"]) / len(incorrect) if incorrect else 0.0,
        "n_correct": len(correct),
        "n_incorrect": len(incorrect),
        "data": data_points,
    }
