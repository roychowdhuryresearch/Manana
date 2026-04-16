# MIMIC-IV — Epilepsy Cohort for Consilium Self-Learning

MIMIC-IV is a de-identified EHR database from Beth Israel Deaconess Medical Center (Boston, USA).
We use it as a pretraining corpus for the Consilium self-learning loop — teaching the system
general epilepsy drug recommendation before adapting on the Uganda dataset.

---

## Patient Cohort

We filter for hospital admissions where a neurologist actively managed a patient
admitted specifically for epilepsy. Concretely, both conditions must hold:

1. **Primary diagnosis is epilepsy** — the ICD code ranked first (`seq_num=1`) for
   this admission is an epilepsy code (ICD-9: `345.x`, ICD-10: `G40.x`). Epilepsy
   as a secondary comorbidity does not qualify.

2. **Neurology is the managing service** — the clinical team assigned to the patient
   is the neurology team (service code `NMED`). General medicine or surgical teams
   maintaining a patient's existing AEDs do not qualify.

This gives admissions where a neurologist looked at this patient's seizure history,
current medications, and clinical presentation, and made a deliberate AED prescribing
decision — structurally equivalent to a visit at the Uganda epilepsy clinic.

**Result: 2,857 admissions, 2,282 with a discharge summary.**

That `2,282` count is **not** the final working cohort used by the current
MIMIC loader. The runtime benchmark applies additional filters on top of the
raw discharge-summary pool and ends at **1,208 cases**.

### Runtime Filter Chain (`2282 -> 1208`)

Starting from the `2,282` admissions in `discharge_notes.parquet`:

1. **Require a truncatable note marker** — keep only notes containing
   `"Discharge Medications:"` so the loader can cut off the answer-bearing tail.
   - Count: `2,282 -> 2,237`  (drop `45`)
   - Code: `mimic/loader.py::_load_usable()` / `_truncate_note()`

2. **Require prescriptions-derived ground truth** — keep only admissions with at
   least one qualifying discharge ASM extracted from `prescriptions.csv.gz`.
   GT extraction rules are:
   - drug matches a tracked AED alias
   - oral route only
   - active at discharge (`stoptime >= dischtime`)
   - started during this admission (`starttime > admittime`)
   - exclude fosphenytoin
   - Raw GT pool size: `2,117`
   - Code: `mimic/gt.py`

3. **Intersect note + GT requirements**
   - Count: `2,237 ∩ 2,117 = 2,075`
   - Relative to the `2,282` discharge-summary pool:
     - `42` fail only the `"Discharge Medications:"` check
     - `162` fail only the GT-drug check
     - `3` fail both
   - Code: `mimic/loader.py::_load_usable()`

4. **Keep first admission per patient only**
   - We collapse repeated admissions and keep the chronologically earliest
     admission (`visit_num = 1`) for each patient.
   - Count: `2,075 -> 1,326`  (drop `749` repeat admissions)
   - This `749` is purely arithmetic: `2,075 admissions - 1,326 unique patients`.
     It means the current loader discards **all** non-first admissions.
   - Note: this is **not** the older `<= 365 day gap` / `max 3 visits` logic.
     Some stale comments still mention that older policy, but it is not what the
     current code does.
   - Code: `mimic/loader.py::_load_usable()`

5. **Restrict GT to the 10 Uganda-shared ASMs**
   - Keep only admissions whose discharge GT still contains at least one of:
     `carbamazepine, clobazam, clonazepam, ethosuximide, lamotrigine,
     levetiracetam, phenobarbital, phenytoin, topiramate, valproate`
   - Count: `1,326 -> 1,208`  (drop `118`)
   - The dropped cases are mostly MIMIC-only AEDs such as
     `oxcarbazepine`, `lacosamide`, and `zonisamide`
   - Code: `mimic/loader.py::_load_usable()`

**Final runtime cohort: 1,208 admissions / 1,208 patients**

- `773` monotherapy
- `435` polytherapy

### How To Read The Math

The cohort shrinks in two different ways:

1. **Admission-level filters** remove admissions outright
   - Example: notes without `"Discharge Medications:"`
   - Example: admissions whose prescriptions never yield a qualifying GT ASM

2. **Patient-level collapsing** removes repeat visits
   - The current loader keeps only the **first** qualifying admission per patient
   - So if a patient had 4 usable admissions, 3 of them are dropped

For the current runtime cohort:

- Start from the discharge-summary pool: `2,282`
- After note + GT filters: `2,075`
- After collapsing to first admission per patient: `1,326`
- After restricting to the 10 Uganda-shared ASMs: `1,208`

If you apply the older mental model of “keep later visits only when the gap to
the previous visit is <= 365 days, and cap at 3 visits per patient,” the same
`2,075` admissions would shrink to `1,467` instead of `1,326` before the final
10-drug restriction.

So the key distinction is:

- **Current code:** first admission only, then 10-drug restriction
- **Older interpretation:** keep some short-gap repeat visits, up to 3 total

---

## Raw Data Files (`mimic/data/`)

| File | Rows | Granularity | Key Columns | Description |
|------|------|-------------|-------------|-------------|
| `patients.csv.gz` | 364K | 1 per patient | subject_id, gender, anchor_age, dod | Demographics |
| `admissions.csv.gz` | 546K | 1 per hospital stay | subject_id, hadm_id, admittime, dischtime, admission_type | Each hospital visit |
| `services.csv.gz` | 593K | 1 per service transfer | subject_id, hadm_id, curr_service | Managing clinical team (NMED=Neurology, MED=Medicine, NSURG=Neurosurgery) |
| `transfers.csv.gz` | 2.4M | 1 per ward move | subject_id, hadm_id, careunit, intime, outtime | Movement within hospital |
| `diagnoses_icd.csv.gz` | 6.4M | N per stay | subject_id, hadm_id, seq_num, icd_code, icd_version | ICD codes; seq_num=1 is primary diagnosis |
| `d_icd_diagnoses.csv.gz` | 112K | 1 per ICD code | icd_code, icd_version, long_title | Lookup: ICD code → human-readable name |
| `procedures_icd.csv.gz` | 860K | N per stay | subject_id, hadm_id, icd_code | Procedures performed during admission |
| `d_icd_procedures.csv.gz` | 86K | 1 per ICD code | icd_code, icd_version, long_title | Lookup: procedure code → name |
| `prescriptions.csv.gz` | 20.3M | N per stay | subject_id, hadm_id, drug, route, starttime, stoptime | Every drug order |
| `omr.csv.gz` | 7.8M | N per patient | subject_id, chartdate, result_name, result_value | Outpatient vitals (BP, weight, etc.) |
| `discharge.csv.gz` | ~99M lines | 1 per stay | subject_id, hadm_id, note_type, text | Free-text discharge summaries (note_type=DS) |

### Join Keys

All files link via `subject_id` (patient) and `hadm_id` (single hospital admission):

```
patients          (subject_id)
    └── admissions        (subject_id, hadm_id)
            ├── diagnoses_icd     → decoded by d_icd_diagnoses
            ├── procedures_icd    → decoded by d_icd_procedures
            ├── prescriptions     (drug orders during this stay)
            ├── services          (which team: NMED, MED, ...)
            ├── transfers         (movement within hospital)
            └── discharge         (free-text note for the stay)

omr              (subject_id, chartdate)   ← outpatient only, not tied to admissions
```

---

## Filtered Outputs (`mimic/filtered/`)

`filter.py` reads the raw data files and produces:

| File | Description |
|------|-------------|
| `filtered_ids.csv` | `(subject_id, hadm_id)` for all 2,857 qualifying admissions |
| `discharge_notes.parquet` | `(subject_id, hadm_id, text)` for the 2,282 with a discharge summary |
| `gt_drugs.parquet` | `(hadm_id, gt_drugs)` for the 2,117 admissions with qualifying discharge AEDs from prescriptions |

Loading at runtime:

```python
import pandas as pd

ids   = pd.read_csv("mimic/filtered/filtered_ids.csv")
notes = pd.read_parquet("mimic/filtered/discharge_notes.parquet")
df    = ids.merge(notes, on="hadm_id")   # 2,282 admissions with discharge notes
```

Ground truth drug extraction (from `prescriptions.csv.gz`) is handled by
`gt.py`. GT = qualifying oral AEDs that were active at discharge
(`route` is oral, `stoptime >= dischtime`, `starttime > admittime`, exclude
fosphenytoin). The runtime loader then further restricts those GT drugs to the
10 Uganda-shared ASMs.

Current runtime loading is therefore:

```python
from mimic.loader import _load_usable

df = _load_usable()   # 1,208 first-admission cases used by current experiments
```

---

## Relation to Consilium Self-Learning

The self-learning loop (`self_learning/run_loop.py`) currently trains on the
Uganda CSV cohort (~279 patients). MIMIC provides a larger pretraining corpus
for the continual learning experiment:

```
Phase 1 — Pretraining (MIMIC, 1,208 runtime cases)
    Run self-learning loop on MIMIC epilepsy patients.
    Loop discovers general epilepsy → AED reasoning patterns.

Phase 2 — Target adaptation (Uganda, ~279 patients)
    Run self-learning loop on Uganda starting from MIMIC-learned rules.
    Measure how fast the system adapts vs. starting from scratch.
    Delta = transfer learning gain.
```

The claim: a system pretrained on MIMIC reaches Uganda-level performance with
a fraction of the Uganda training cases — because the task structure
(clinical notes → AED prediction) is already understood, only the local
distribution (Ugandan formulary, CBZ+VPA dominance) needs to shift.
