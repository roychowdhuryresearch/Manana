"""Load PDF-patient cohort into PatientCase objects.

Reads from pdf_pats/outputs/ only — no CSV needed.
output_text from split_results serves as the prescription for prior visits.
"""

import os
import json

from schemas.patient import PatientCase, VisitData, MedicationHistory

_HERE = os.path.dirname(os.path.abspath(__file__))
_OUTPUTS_DIR = os.path.join(_HERE, "outputs")


def load_raw_data() -> tuple[dict, dict]:
    with open(os.path.join(_OUTPUTS_DIR, "split_results.json"), encoding="utf-8") as f:
        split_results = json.load(f)
    with open(os.path.join(_OUTPUTS_DIR, "drug_gt.json"), encoding="utf-8") as f:
        drug_gt = json.load(f)
    return split_results, drug_gt


def build_patient_case(
    pid: str,
    visit_name: str,
    split_results: dict,
    drug_gt: dict,
) -> PatientCase | None:
    patient_data = split_results.get(pid, {})
    if visit_name not in patient_data:
        return None
    if not patient_data[visit_name].get("input_text", "").strip():
        return None

    all_visits = sorted(patient_data.keys())  # Visit_1, Visit_2, ...
    current_idx = all_visits.index(visit_name)
    visits_to_include = all_visits[: current_idx + 1]

    case = PatientCase(
        patient_id=pid,
        current_visit=visit_name,
    )

    for vname in visits_to_include:
        is_current = vname == visit_name
        input_text = patient_data[vname].get("input_text", "")
        prescription = "" if is_current else patient_data[vname].get("output_text", "")
        n = vname.split("_")[1]

        case.visits.append(VisitData(
            visit_name=vname,
            visit_label=f"Visit {n}",
            input_text=input_text,
            prescription=prescription,
            is_current=is_current,
        ))

        gt_data = drug_gt.get(pid, {}).get(vname, {})
        if gt_data and not is_current:
            case.medication_history[vname] = MedicationHistory(
                prescribed=gt_data.get("prescribed", []),
                stopped=gt_data.get("stopped", []),
            )

    return case


def load_all_cases(visit_num: int = 1, limit: int | None = None) -> list[PatientCase]:
    """Load all PDF-cohort cases for a given visit number.

    Skips patients that don't have that visit.
    """
    split_results, drug_gt = load_raw_data()
    visit_name = f"Visit_{visit_num}"

    pids = list(split_results.keys())
    if limit:
        pids = pids[:limit]

    cases = []
    for pid in pids:
        case = build_patient_case(pid, visit_name, split_results, drug_gt)
        if case is not None:
            cases.append(case)

    return cases
