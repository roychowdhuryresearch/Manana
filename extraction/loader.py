"""Load extraction cohort patients (variable visit counts, 3-6 visits).

Reads from extraction/outputs/ — does not touch data/processed/.
"""

import os
import json
import pandas as pd

from schemas.patient import PatientCase, VisitData, MedicationHistory

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_OUTPUTS_DIR = os.path.join(_HERE, "outputs")
_CSV_PATH = os.path.join(_ROOT, "data", "combined_dataset.csv")


def _safe(row, col: str) -> str:
    val = row.get(col, "")
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none") else ""


def _pid(row) -> str:
    rid = str(row.get("Record ID", "")).strip()
    name = str(row.get("Name: ", "")).strip()
    return f"{rid}_{name}" if rid and name else name or rid


def load_raw_data() -> tuple[dict, dict, dict, dict]:
    with open(os.path.join(_OUTPUTS_DIR, "split_results.json"), encoding="utf-8") as f:
        split_results = json.load(f)
    with open(os.path.join(_OUTPUTS_DIR, "clean_output.json"), encoding="utf-8") as f:
        clean_output = json.load(f)
    with open(os.path.join(_OUTPUTS_DIR, "drug_gt.json"), encoding="utf-8") as f:
        drug_gt = json.load(f)

    df = pd.read_csv(
        _CSV_PATH, sep=";", engine="python", quotechar='"',
        doublequote=True, escapechar="\\", dtype=str,
    )
    df = df.drop_duplicates(subset=[
        "Name: ", "Date of visit(0 months)",
        "Date of visit(6 months)", "Date of visit(12 months)",
    ])
    pid_to_row = {_pid(row): row.to_dict() for _, row in df.iterrows()}

    return split_results, clean_output, drug_gt, pid_to_row


def build_patient_case(
    pid: str,
    visit_name: str,
    split_results: dict,
    clean_output: dict,
    drug_gt: dict,
    pid_to_row: dict,
) -> PatientCase | None:
    patient_data = split_results.get(pid, {})
    if visit_name not in patient_data:
        return None
    if not patient_data[visit_name].get("input_text", "").strip():
        return None

    # All visits up to and including the target, in order
    all_visits = sorted(patient_data.keys())  # Visit_1, Visit_2, ...
    if visit_name not in all_visits:
        return None
    current_idx = all_visits.index(visit_name)
    visits_to_include = all_visits[: current_idx + 1]

    row = pid_to_row.get(pid)

    case = PatientCase(
        patient_id=pid,
        age=_safe(row, "Age") if row else "",
        sex=_safe(row, "Sex:") if row else "",
        diagnosis=_safe(row, "Seizure Diagnosis") if row else "",
        seizure_onset=_safe(row, "Age of onset of seizure") if row else "",
        seizure_duration=_safe(row, "Duration of Seizure") if row else "",
        current_visit=visit_name,
    )

    for vname in visits_to_include:
        is_current = vname == visit_name
        input_text = patient_data.get(vname, {}).get("input_text", "")
        prescription = "" if is_current else clean_output.get(pid, {}).get(vname, "")

        # Generic label: "Visit N"
        n = vname.split("_")[1]
        label = f"Visit {n}"

        case.visits.append(VisitData(
            visit_name=vname,
            visit_label=label,
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
    """Load all extraction-cohort cases for a given visit number.

    Skips patients that don't have that visit (e.g. a 3-visit patient
    when visit_num=4 is requested).

    Args:
        visit_num: 1–6.
        limit: Max patients (None for all).
    """
    split_results, clean_output, drug_gt, pid_to_row = load_raw_data()
    visit_name = f"Visit_{visit_num}"

    cases = []
    pids = list(split_results.keys())
    if limit:
        pids = pids[:limit]

    for pid in pids:
        case = build_patient_case(
            pid, visit_name, split_results, clean_output, drug_gt, pid_to_row
        )
        if case is not None:
            cases.append(case)

    return cases
