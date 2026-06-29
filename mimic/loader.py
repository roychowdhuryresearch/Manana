"""
MIMIC-IV Patient Loader (mimic)
======================================
Loads the LLM-cleaned MIMIC epilepsy cohort from mimic/filtered/.

Notes come from cleaned_notes.parquet (LLM-cleaned to remove in-admission treatment
leakage). A post-hoc regex strips any residual discharge-section headers and
"discharged on <drug>" sentences.

All admissions are kept (not filtered to first-per-patient). The split function
handles patient-level separation to prevent leakage.

Usage:
    from mimic.loader import load_mimic_cases, load_mimic_ground_truth, mimic_split
"""

from __future__ import annotations

import os
import re
import random
import pandas as pd
from lib.patient import PatientCase

MIMIC_DRUGS = {
    "carbamazepine", "clobazam", "clonazepam", "gabapentin", "lacosamide",
    "lamotrigine", "levetiracetam", "lorazepam", "oxcarbazepine", "phenobarbital",
    "phenytoin", "pregabalin", "topiramate", "valproate", "zonisamide",
}

_HERE    = os.path.dirname(os.path.abspath(__file__))
FILT_DIR = os.path.join(_HERE, "filtered")
DATA_DIR = os.path.join(_HERE, "data")

# ── Post-hoc regex cleanup ────────────────────────────────────────────────────

_DISCHARGE_TAIL_RE = re.compile(
    r'Discharge (?:Diagnosis|Condition|Disposition|Instructions|Medications)\s*:|Followup Instructions\s*:',
    re.IGNORECASE,
)

_AED_RE = re.compile(
    r'\b(?:carbamazepine|tegretol|cbz|clobazam|onfi|clonazepam|klonopin|ethosuximide|zarontin'
    r'|lamotrigine|lamictal|ltg|levetiracetam|keppra|lev|phenobarbital|luminal|pb'
    r'|phenytoin|dilantin|pht|topiramate|topamax|valproate|valproic|depakote|vpa|divalproex'
    r'|oxcarbazepine|trileptal|lacosamide|vimpat|zonisamide|zonegran)\b',
    re.IGNORECASE,
)

# ── Leaky hadm_ids (manually audited) ────────────────────────────────────────

_LEAKY_HADM_IDS = {
    25809882, 22152373, 27800534, 21848913, 22241947, 25332437, 26527923, 22549669,
    22141281, 26880089, 20815123, 27236465, 27646159, 24551594, 21689501, 20287040,
    26695863, 27352128, 23013351, 25211491, 23089468, 20917721, 21458553, 29290473,
    29825539, 29365675, 27060699, 21341439, 20901139, 28893266, 24255175, 23642613,
    20106968, 29528299, 28682698, 21229339, 23195099, 26036013, 20802630, 20787713,
    23077833, 23031343, 20357816, 28977449, 25697683, 23131745, 23406936, 26595120,
    28776275, 24691295, 22382251, 29862485, 28625209, 23680292, 24787140, 24380478,
    22605631, 24663089, 28634171, 25700370, 26543459, 22179059, 25287972, 22855532,
    24760401, 28185450, 22364944, 20040161, 27870905, 20831624, 22201255, 26060113,
    28110943, 22008580, 20535881, 27518928, 27525870, 27055962, 21407548, 26439439,
    23511636, 21571143, 21311906, 24378434, 21584399, 26887073, 21982559, 20794804,
    28061847, 25467763, 28853170, 22506446, 28148781, 26053471, 28859512, 27891306,
    22439163, 26530593, 25025995, 25400239, 27493081, 25227763, 25253189, 29820608,
    28668858, 24852571, 20787688, 20478253, 24708599, 20459106, 27000778, 21327990,
    29680118, 21436775, 21452477, 26840921, 23870571, 29149031,
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _clean_note(text: str) -> str:
    """Post-hoc regex on top of LLM-cleaned notes.

    1. Strip from first structural discharge section header onwards.
    2. Remove lines containing "discharged on <AED>" that the LLM missed.
    """
    m = _DISCHARGE_TAIL_RE.search(text)
    if m:
        text = text[:m.start()]

    lines = text.split('\n')
    cleaned = [
        line for line in lines
        if not (re.search(r'\bdischarged on\b', line, re.IGNORECASE) and _AED_RE.search(line))
    ]
    return '\n'.join(cleaned).strip()


def _load_usable() -> pd.DataFrame:
    """Load all usable admissions (all visits per patient kept).

    Filters:
      1. Has a cleaned note + GT entry
      2. GT filtered to 15 MIMIC drugs; cases with none excluded
      3. Manually flagged leaky hadm_ids excluded
    """
    ids   = pd.read_csv(os.path.join(FILT_DIR, "filtered_ids.csv"))
    notes = pd.read_parquet(os.path.join(FILT_DIR, "cleaned_notes.parquet"))
    gt    = pd.read_parquet(os.path.join(FILT_DIR, "gt_drugs.parquet"))

    valid_hadms = set(notes["hadm_id"]) & set(gt["hadm_id"])
    ids = ids[ids["hadm_id"].isin(valid_hadms)]

    adm = pd.read_csv(
        os.path.join(DATA_DIR, "admissions.csv.gz"),
        usecols=["hadm_id", "admittime", "race"],
        parse_dates=["admittime"],
    )
    df = ids.merge(adm, on="hadm_id")
    df = df.sort_values(["subject_id", "admittime"]).reset_index(drop=True)
    df["visit_num"] = df.groupby("subject_id").cumcount() + 1

    pts = pd.read_csv(
        os.path.join(DATA_DIR, "patients.csv.gz"),
        usecols=["subject_id", "gender", "anchor_age"],
    )
    df = df.merge(pts, on="subject_id")
    df = df.merge(notes[["hadm_id", "cleaned_text"]], on="hadm_id")
    df = df.merge(gt, on="hadm_id")

    df["gt_drugs"] = df["gt_drugs"].apply(
        lambda drugs: [d for d in drugs if d in MIMIC_DRUGS]
    )
    df = df[df["gt_drugs"].apply(len) > 0].reset_index(drop=True)
    df = df[df["gt_drugs"].apply(len) <= 4].reset_index(drop=True)   # exclude refractory (5+ drug) cases
    df = df[~df["hadm_id"].isin(_LEAKY_HADM_IDS)].reset_index(drop=True)

    return df


def _df_to_cases(df: pd.DataFrame) -> list[PatientCase]:
    cases = []
    for _, row in df.iterrows():
        race = str(row.get("race", "")).strip()
        header = f"Age: {int(row['anchor_age'])} | Sex: {row['gender']}"
        if race and race.lower() not in ("nan", "unknown", "unable to obtain", "other"):
            header += f" | Race: {race}"
        cases.append(PatientCase(
            patient_id=str(row["hadm_id"]),
            current_visit=f"Visit_{row['visit_num']}",
            clinical_context=header + "\n\n" + _clean_note(row["cleaned_text"]),
            cohort="mimic",
        ))
    return cases


def _df_to_gt(df: pd.DataFrame) -> dict[str, dict]:
    return {
        f"{row['hadm_id']}__v{row['visit_num']}": {
            "pid": str(row["hadm_id"]),
            "visit_num": row["visit_num"],
            "cohort": "mimic",
            "prescribed": list(row["gt_drugs"]),
            "stopped": [],
        }
        for _, row in df.iterrows()
    }


# ── Public API ────────────────────────────────────────────────────────────────

def load_mimic_cases(limit: int | None = None) -> list[PatientCase]:
    df = _load_usable()
    if limit is not None:
        df = df.head(limit)
    return _df_to_cases(df)


def load_mimic_ground_truth(limit: int | None = None) -> dict[str, dict]:
    df = _load_usable()
    if limit is not None:
        df = df.head(limit)
    return _df_to_gt(df)


def mimic_split(
    n_train: int = 150,
    n_eval: int = 60,
    split_seed: int = 42,
    shuffle_seed: int = 42,
) -> dict:
    """Patient-level train/eval/test split with fixed train/eval case caps.

    split_seed selects the fixed train/eval candidate pool.
    shuffle_seed repartitions that fixed pool into train/eval and shuffles case
    order. Test patients remain outside the fixed train/eval pool.

    Returns keys: train_cases, eval_cases, gt_data, stats.
    Test patients are excluded from the returned split and reserved for final eval.
    """
    df = _load_usable()

    all_patients = list(df["subject_id"].unique())
    rng = random.Random(split_seed)
    rng.shuffle(all_patients)

    train_eval_pool = all_patients[:n_train + n_eval]

    shuffle_rng = random.Random(shuffle_seed)
    shuffle_rng.shuffle(train_eval_pool)

    train_pats = set(train_eval_pool[:n_train])
    eval_pats  = set(train_eval_pool[n_train:n_train + n_eval])

    train_df = df[df["subject_id"].isin(train_pats)]
    eval_df  = df[df["subject_id"].isin(eval_pats)]

    train_cases = _df_to_cases(train_df)
    eval_cases  = _df_to_cases(eval_df)

    # Same seed also controls case ordering within each split.
    shuffle_rng.shuffle(train_cases)
    shuffle_rng.shuffle(eval_cases)
    train_cases = train_cases[:n_train]
    eval_cases = eval_cases[:n_eval]

    gt_data = _df_to_gt(df)  # full GT — covers train + eval + test

    train_mono = sum(1 for c in train_cases if len(gt_data[f"{c.patient_id}__v{int(c.current_visit.split('_')[1])}"]["prescribed"]) == 1)
    eval_mono  = sum(1 for c in eval_cases  if len(gt_data[f"{c.patient_id}__v{int(c.current_visit.split('_')[1])}"]["prescribed"]) == 1)

    return {
        "train_cases": train_cases,
        "eval_cases":  eval_cases,
        "train_pats":  sorted(train_pats),
        "eval_pats":   sorted(eval_pats),
        "gt_data":     gt_data,
        "stats": {
            "split_seed":     split_seed,
            "shuffle_seed":   shuffle_seed,
            "pool_patients":  len(train_eval_pool),
            "train_patients": len(train_pats),
            "train_cases":    len(train_cases),
            "train_mono":     train_mono,
            "train_poly":     len(train_cases) - train_mono,
            "eval_patients":  len(eval_pats),
            "eval_cases":     len(eval_cases),
            "eval_mono":      eval_mono,
            "eval_poly":      len(eval_cases) - eval_mono,
        },
    }


def mimic_stats() -> None:
    df = _load_usable()
    n = len(df)
    n_pats = df["subject_id"].nunique()
    mono = df["gt_drugs"].apply(lambda d: len(d) == 1).sum()
    poly = n - mono
    multi = (df.groupby("subject_id")["hadm_id"].count() > 1).sum()
    print(f"MIMIC cohort (cleaned): {n} admissions, {n_pats} patients ({multi} with 2+ admissions)")
    print(f"  Mono: {mono} ({mono/n:.0%})  Poly: {poly} ({poly/n:.0%})")

    split = mimic_split()
    s = split["stats"]
    print(f"\n  Default split (split_seed=42):")
    print(f"  Train: {s['train_cases']} cases / {s['train_patients']} patients  (mono={s['train_mono']} poly={s['train_poly']})")
    print(f"  Eval:  {s['eval_cases']} cases / {s['eval_patients']} patients  (mono={s['eval_mono']} poly={s['eval_poly']})")
    print(f"  Test:  {n - s['train_cases'] - s['eval_cases']} cases / {n_pats - s['train_patients'] - s['eval_patients']} patients")


if __name__ == "__main__":
    mimic_stats()
