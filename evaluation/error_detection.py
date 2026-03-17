"""Error detection rate — do multi-agent traces catch the errors doctors flagged?

Maps 7 systematic failure categories from doctor feedback to agent capabilities.
"""

from __future__ import annotations
import csv
import os
import re

from schemas.trace import ReasoningTrace
from schemas.responses import ConcernCategory

_FEEDBACK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "feedback")

# Map failure categories to the agents that should catch them
FAILURE_TO_AGENT = {
    "seizure_type_misclassification": "diagnostician",
    "weight_dosing_error": "pediatrician",
    "drug_seizure_contraindication": "pharmacologist",
    "de_escalating_working_regimen": "treatment_analyst",
    "missing_infectious_etiology": "tropical_medicine",
    "ignoring_availability": "formulary",
    "drug_interaction": "pharmacologist",
}


def load_feedback(filename: str) -> list[dict]:
    """Load doctor feedback CSV."""
    path = os.path.join(_FEEDBACK_DIR, filename)
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def classify_feedback_error(comment: str) -> list[str]:
    """Classify a doctor's feedback comment into failure categories."""
    comment_lower = comment.lower()
    categories = []

    patterns = {
        "seizure_type_misclassification": [
            r"seizure type", r"focal.*generali[sz]ed", r"syndrome",
            r"west syndrome", r"lennox", r"rolandic", r"eeg",
        ],
        "weight_dosing_error": [
            r"weight.*dos", r"dos.*weight", r"subtherapeutic",
            r"mg/kg", r"weight.*adjust",
        ],
        "drug_seizure_contraindication": [
            r"contraindic", r"worsen", r"aggravat",
            r"cbz.*myoclon", r"cbz.*absence", r"pht.*myoclon",
        ],
        "de_escalating_working_regimen": [
            r"de.?escalat", r"working.*regimen", r"seizure.?free",
            r"continue.*current", r"don.*change", r"responding",
        ],
        "missing_infectious_etiology": [
            r"malaria", r"infection", r"infectious", r"ncc",
            r"hiv", r"fever.*seizure",
        ],
        "ignoring_availability": [
            r"availab", r"formulary", r"not.*available",
            r"cost", r"access",
        ],
        "drug_interaction": [
            r"interaction", r"never.*mix", r"phb.*clobazam",
            r"enzyme.*induc",
        ],
    }

    for category, pats in patterns.items():
        for pat in pats:
            if re.search(pat, comment_lower):
                categories.append(category)
                break

    return categories


def evaluate_error_detection(
    traces: dict[str, ReasoningTrace],
    feedback_file: str = "feedback_JP.csv",
) -> dict:
    """Evaluate whether the multi-agent system catches errors that doctors flagged.

    Returns:
        {
            "overall_detection_rate": float,
            "per_category": {category: {detected, total, rate}},
            "per_patient": {pid: {errors_flagged, errors_detected, details}}
        }
    """
    feedback = load_feedback(feedback_file)

    category_stats = {cat: {"detected": 0, "total": 0} for cat in FAILURE_TO_AGENT}
    patient_stats = {}

    for entry in feedback:
        # Try different possible column names for patient ID and comment
        pid = entry.get("patient_id", entry.get("Patient ID", entry.get("Patient", "")))
        comment = entry.get("comment", entry.get("Comment", entry.get("comments", "")))

        if not comment:
            continue

        errors = classify_feedback_error(comment)
        if not errors:
            continue

        trace = traces.get(pid)
        detected_errors = []

        for error_cat in errors:
            category_stats[error_cat]["total"] += 1
            responsible_agent = FAILURE_TO_AGENT.get(error_cat)

            if trace and responsible_agent:
                agent_resp = trace.phase1_responses.get(responsible_agent)
                if not agent_resp and responsible_agent == "pharmacologist":
                    agent_resp = trace.pharmacologist_response

                if agent_resp and agent_resp.concerns:
                    # Check if agent raised any relevant concern
                    detected = True
                    detected_errors.append(error_cat)
                    category_stats[error_cat]["detected"] += 1

        patient_stats[pid] = {
            "errors_flagged": errors,
            "errors_detected": detected_errors,
            "detection_rate": len(detected_errors) / len(errors) if errors else 0.0,
        }

    # Compute rates
    per_category = {}
    total_detected = 0
    total_errors = 0
    for cat, stats in category_stats.items():
        rate = stats["detected"] / stats["total"] if stats["total"] > 0 else 0.0
        per_category[cat] = {**stats, "rate": rate}
        total_detected += stats["detected"]
        total_errors += stats["total"]

    return {
        "overall_detection_rate": total_detected / total_errors if total_errors else 0.0,
        "per_category": per_category,
        "per_patient": patient_stats,
    }
