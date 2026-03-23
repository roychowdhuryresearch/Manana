"""
Build structured prediction input per patient per visit.

For each patient and each visit N, the input contains:
  - Patient header with demographics from CSV
  - All previous visits: [Clinical Notes] + [Prescription]
  - Current visit: [Clinical Notes] only (no prescription — that's what we predict)

Output: raw_text/pred_input.json
{
  "patient_id": {
    "Visit_1": "<full input string for predicting V1>",
    "Visit_2": "<full input string for predicting V2>",
    "Visit_3": "<full input string for predicting V3>"
  }
}
"""

import os
import json
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

split_results_path = os.path.join(_HERE, 'split_results.json')
clean_output_path = os.path.join(_HERE, 'clean_output.json')
csv_path = os.path.join(_ROOT, 'data', 'combined_dataset.csv')
output_file = os.path.join(_HERE, 'pred_input.json')


def safe_get(row, col):
    val = row.get(col, '')
    s = str(val).strip()
    return s if s and s.lower() != 'nan' else ''


def get_pid(row):
    rid = str(row.get('Record ID', '')).strip() if pd.notna(row.get('Record ID')) else ''
    name = str(row.get('Name: ', '')).strip() if pd.notna(row.get('Name: ')) else ''
    return f"{rid}_{name}" if rid and name else name or rid


def build_patient_header(row) -> str:
    age    = safe_get(row, 'Age')
    sex    = safe_get(row, 'Sex:')
    dx     = safe_get(row, 'Seizure Diagnosis')
    onset  = safe_get(row, 'Age of onset of seizure')
    dur    = safe_get(row, 'Duration of Seizure')

    parts = ["For this patient, here is what you have:\n"]
    demo = " | ".join(x for x in [
        f"Age: {age}" if age else "",
        f"Sex: {sex}" if sex else "",
        f"Diagnosis: {dx}" if dx else "",
    ] if x)
    if demo:
        parts.append(demo)
    detail = " | ".join(x for x in [
        f"Seizure onset: {onset}" if onset else "",
        f"Seizure duration: {dur}" if dur else "",
    ] if x)
    if detail:
        parts.append(detail)
    return "\n".join(parts)


def build_visit_block(visit_label: str, input_text: str, prescription: str = None) -> str:
    lines = [f"[{visit_label} - Clinical Notes]"]
    lines.append(input_text.strip() if input_text.strip() else "(no clinical notes recorded)")
    if prescription is not None:
        lines.append(f"\n[{visit_label} - Prescription]")
        lines.append(prescription.strip() if prescription.strip() else "(no prescription recorded)")
    return "\n".join(lines)


def build_inputs(split_results, clean_output, pid_to_row):
    visit_labels = {
        "Visit_1": "Visit 1 (0 months)",
        "Visit_2": "Visit 2 (6 months)",
        "Visit_3": "Visit 3 (12 months)",
    }
    visit_order = ["Visit_1", "Visit_2", "Visit_3"]

    result = {}

    for pid in split_results:
        row = pid_to_row.get(pid)
        header = build_patient_header(row) if row is not None else "For this patient, here is what you have:"

        patient_inputs = {}
        for i, current_visit in enumerate(visit_order):
            blocks = [header, ""]

            # All previous visits: notes + prescription
            for prev_visit in visit_order[:i]:
                label = visit_labels[prev_visit]
                inp = split_results[pid].get(prev_visit, {}).get("input_text", "")
                pres = clean_output.get(pid, {}).get(prev_visit, "")
                blocks.append(build_visit_block(label, inp, prescription=pres))
                blocks.append("")

            # Current visit: notes only
            label = visit_labels[current_visit]
            inp = split_results[pid].get(current_visit, {}).get("input_text", "")
            blocks.append(build_visit_block(label, inp, prescription=None))

            patient_inputs[current_visit] = "\n".join(blocks).strip()

        result[pid] = patient_inputs

    return result


def main():
    with open(split_results_path, encoding='utf-8') as f:
        split_results = json.load(f)
    with open(clean_output_path, encoding='utf-8') as f:
        clean_output = json.load(f)

    df = pd.read_csv(
        csv_path, sep=';', engine='python',
        quotechar='"', doublequote=True, escapechar='\\',
    )
    df = df.drop_duplicates(subset=[
        'Name: ', 'Date of visit(0 months)',
        'Date of visit(6 months)', 'Date of visit(12 months)'
    ])
    pid_to_row = {get_pid(row): row for _, row in df.iterrows()}

    print(f"Building clean inputs for {len(split_results)} patients...")
    result = build_inputs(split_results, clean_output, pid_to_row)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Saved to {output_file}")


if __name__ == "__main__":
    main()
