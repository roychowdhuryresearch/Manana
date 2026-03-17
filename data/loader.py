"""Load pre-computed pipeline outputs into PatientCase objects."""

import os
import json
import pandas as pd

from schemas.patient import PatientCase, VisitData, MedicationHistory

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
_PROCESSED_DIR = os.path.join(_DATA_DIR, "processed")

VISIT_LABELS = {
    "Visit_1": "Visit 1 (0 months)",
    "Visit_2": "Visit 2 (6 months)",
    "Visit_3": "Visit 3 (12 months)",
}
VISIT_ORDER = ["Visit_1", "Visit_2", "Visit_3"]


def _safe_get(row, col: str) -> str:
    val = row.get(col, "")
    s = str(val).strip()
    return s if s and s.lower() != "nan" else ""


def _get_pid(row) -> str:
    rid = str(row.get("Record ID", "")).strip() if pd.notna(row.get("Record ID")) else ""
    name = str(row.get("Name: ", "")).strip() if pd.notna(row.get("Name: ")) else ""
    return f"{rid}_{name}" if rid and name else name or rid


def load_raw_data() -> tuple[dict, dict, dict, dict]:
    """Load all pre-computed data files.

    Returns:
        (split_results, clean_output, drug_gt, pid_to_row)
    """
    with open(os.path.join(_PROCESSED_DIR, "split_results.json"), encoding="utf-8") as f:
        split_results = json.load(f)
    with open(os.path.join(_PROCESSED_DIR, "clean_output.json"), encoding="utf-8") as f:
        clean_output = json.load(f)
    with open(os.path.join(_PROCESSED_DIR, "drug_gt.json"), encoding="utf-8") as f:
        drug_gt = json.load(f)

    df = pd.read_csv(
        os.path.join(_DATA_DIR, "combined_dataset.csv"),
        sep=";", engine="python", quotechar='"', doublequote=True, escapechar="\\",
    )
    df = df.drop_duplicates(subset=[
        "Name: ", "Date of visit(0 months)",
        "Date of visit(6 months)", "Date of visit(12 months)",
    ])
    pid_to_row = {_get_pid(row): row for _, row in df.iterrows()}

    return split_results, clean_output, drug_gt, pid_to_row


def build_patient_case(
    pid: str,
    visit_name: str,
    split_results: dict,
    clean_output: dict,
    drug_gt: dict,
    pid_to_row: dict,
) -> PatientCase | None:
    """Build a PatientCase for a specific patient and target visit.

    Returns None if the patient has no input text for the target visit.
    """
    patient_data = split_results.get(pid, {})
    visit_data = patient_data.get(visit_name, {})

    if not visit_data.get("input_text", "").strip():
        return None

    row = pid_to_row.get(pid)

    case = PatientCase(
        patient_id=pid,
        age=_safe_get(row, "Age") if row is not None else "",
        sex=_safe_get(row, "Sex:") if row is not None else "",
        diagnosis=_safe_get(row, "Seizure Diagnosis") if row is not None else "",
        seizure_onset=_safe_get(row, "Age of onset of seizure") if row is not None else "",
        seizure_duration=_safe_get(row, "Duration of Seizure") if row is not None else "",
        current_visit=visit_name,
    )

    # Build visits
    current_idx = VISIT_ORDER.index(visit_name)

    for i, vname in enumerate(VISIT_ORDER[:current_idx + 1]):
        is_current = (vname == visit_name)
        input_text = patient_data.get(vname, {}).get("input_text", "")
        prescription = "" if is_current else clean_output.get(pid, {}).get(vname, "")

        case.visits.append(VisitData(
            visit_name=vname,
            visit_label=VISIT_LABELS[vname],
            input_text=input_text,
            prescription=prescription,
            is_current=is_current,
        ))

        # Medication history from drug_gt
        gt_data = drug_gt.get(pid, {}).get(vname, {})
        if gt_data and not is_current:
            case.medication_history[vname] = MedicationHistory(
                prescribed=gt_data.get("prescribed", []),
                stopped=gt_data.get("stopped", []),
            )

    return case


def load_all_cases(visit_num: int = 1, limit: int | None = None) -> list[PatientCase]:
    """Load all patient cases for a given visit number.

    Args:
        visit_num: 1, 2, or 3.
        limit: Max patients to load (None for all).

    Returns:
        List of PatientCase objects.
    """
    split_results, clean_output, drug_gt, pid_to_row = load_raw_data()
    visit_name = f"Visit_{visit_num}"

    cases = []
    for pid in list(split_results.keys())[:limit]:
        case = build_patient_case(pid, visit_name, split_results, clean_output, drug_gt, pid_to_row)
        if case is not None:
            cases.append(case)

    return cases
