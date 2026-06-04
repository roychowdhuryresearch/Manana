# MIMIC-IV Pipeline

This folder prepares the MIMIC-IV epilepsy reproducibility dataset used by the
release. Raw MIMIC files are credentialed PhysioNet data and are not
distributed with this repository.

## Sources

- MIMIC-IV v3.1 hospital tables: https://physionet.org/content/mimiciv/
- MIMIC-IV-Note v2.2 discharge summaries:
  https://physionet.org/content/mimic-iv-note/2.2/

Place the required files in `mimic/data/`:

| File | Used by |
| --- | --- |
| `diagnoses_icd.csv.gz` | epilepsy ICD filter |
| `services.csv.gz` | Neurology service filter |
| `discharge.csv.gz` | discharge note extraction; from MIMIC-IV-Note |
| `admissions.csv.gz` | admission/discharge times and race |
| `prescriptions.csv.gz` | ground-truth drug extraction |
| `patients.csv.gz` | age and sex |

## Pipeline

Run from the repository root:

```bash
uv run python mimic/filter.py
uv run python mimic/gt.py
uv run python mimic/clean.py
uv run python mimic/export_cases.py
```

Outputs are written to `mimic/filtered/`:

```text
filtered_ids.csv
discharge_notes.parquet
gt_drugs.parquet
cleaned_notes.parquet
cases.jsonl
```

`cases.jsonl` is the Case JSONL file consumed by `configs/mimic.yaml`.
In the exported JSONL, `pid` is `subject_id` for patient-level splitting,
`visit_num` is the admission rank for that patient, and `hadm_id` is retained
as ignored metadata.

## Cohort Construction

The released pipeline follows the paper:

- Primary epilepsy ICD code: ICD-9 `345.x` or ICD-10 `G40.x` at `seq_num=1`.
- First managing service is Neurology (`NMED`).
- Longest discharge summary retained per admission.
- Ground truth is extracted from prescriptions, not from the note.
- A target ASM must be oral/enteral, scheduled, active at discharge, and newly
  started during the admission.
- Fosphenytoin is excluded.
- Cleaned notes remove discharge-side treatment leakage before export.
- Manually audited leaky admissions are excluded in `mimic/loader.py`.

Final paper cohort:

- 1,977 admissions from 1,257 patients.
- 625 monotherapy admissions (31.6%).
- 1,352 polytherapy admissions (68.4%).
- Maximum target regimen size 4.

MIMIC action space:

- levetiracetam
- lamotrigine
- lacosamide
- zonisamide
- phenytoin
- valproate
- oxcarbazepine
- lorazepam
- gabapentin
- clobazam
- topiramate
- clonazepam
- carbamazepine
- pregabalin
- phenobarbital

## Note Cleaning

Discharge summaries are retrospective and can leak the treatment decision. The
cleaning step calls an LLM with `mimic/prompts/clean_note.txt` and then applies
a small regex cleanup in `mimic/loader.py`.

The cleaner removes discharge-side sections, discharge medication intent, and
current-admission treatment decisions while preserving pre-admission and
admission-evidence text such as chief complaint, seizure narrative, PMH,
diagnostics, exam, and medications on admission.

## Run Manana

After `mimic/filtered/cases.jsonl` exists:

```bash
uv run python -m manana.run --config configs/mimic.yaml --system single
uv run python -m manana.run --config configs/mimic.yaml --system multi
```

`configs/mimic.yaml` uses 150 training cases and 60 validation cases with
split seed 42, implemented as one admission per selected patient.
