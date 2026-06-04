"""Case JSONL adapter for Manana runs.

Expected JSONL fields:
  pid: stable patient identifier
  visit_num: integer visit/admission number
  cohort: dataset/source label
  input: model input text
  prescribed: list of target medications

Optional fields:
  output: raw target text, if available
  stopped: stopped medications
  split: "train", "eval"/"val"/"validation"/"test"

Split config options:
  strategy: "patient_pool" or "stratified"
  cohort: optional cohort label, or list of labels, to include before splitting
  max_visits: optional cap on earliest visits/cases kept per patient
  strata: optional percentages for stratified splits, e.g. {mono: 0.5, mixed: 0.3, poly: 0.2}
"""

from __future__ import annotations

import json
import os
import random
from collections import defaultdict
from typing import Any

from lib.patient import PatientCase

STRATA = ("mono", "mixed", "poly")


def _resolve_path(config: dict[str, Any], path: str) -> str:
    if os.path.isabs(path):
        return path
    base = os.path.dirname(config.get("_config_path", "")) or os.getcwd()
    return os.path.abspath(os.path.join(base, path))


def _read_jsonl(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"JSONL record must be an object at {path}:{line_no}")
            records.append(obj)
    return records


def _filter_records_by_cohort(
    records: list[dict],
    cohort_filter: Any,
    default_cohort: str,
) -> tuple[list[dict], list[str] | None]:
    if cohort_filter is None:
        return records, None
    if isinstance(cohort_filter, str):
        allowed = {cohort_filter}
    else:
        allowed = {str(cohort) for cohort in cohort_filter}
    filtered = [
        record for record in records
        if str(record.get("cohort") or default_cohort) in allowed
    ]
    if not filtered:
        raise ValueError(f"Cohort filter matched no records: {sorted(allowed)}")
    return filtered, sorted(allowed)


def _case_and_gt(record: dict, default_cohort: str) -> tuple[PatientCase, str, dict]:
    raw_pid = record.get("pid", record.get("patient_id"))
    if raw_pid is None:
        raise ValueError("Case JSONL record missing required field: pid")
    patient_id = str(raw_pid)
    visit_num = int(record.get("visit_num", record.get("visit", 1)))
    current_visit = f"Visit_{visit_num}"
    cohort = str(record.get("cohort") or default_cohort)
    input_text = record.get("input", record.get("clinical_context", record.get("notes")))
    if input_text is None:
        raise ValueError("Case JSONL record missing required field: input")
    prescribed = [str(x).lower() for x in (record.get("prescribed") or record.get("gt") or [])]
    if not prescribed:
        raise ValueError("Case JSONL record missing required field: prescribed")

    case = PatientCase(
        patient_id=patient_id,
        current_visit=current_visit,
        clinical_context=str(input_text),
        cohort=cohort,
    )
    key = f"{patient_id}__v{visit_num}"
    gt = {
        "pid": patient_id,
        "visit_num": visit_num,
        "cohort": cohort,
        "prescribed": prescribed,
        "stopped": [str(x).lower() for x in (record.get("stopped") or [])],
        "output": str(record.get("output") or ""),
    }
    return case, key, gt


def _visit_num(case: PatientCase) -> int:
    return int(case.current_visit.split("_")[1])


def _read_max_visits(split_cfg: dict[str, Any]) -> int | None:
    value = split_cfg.get("max_visits")
    if value is None:
        return None
    max_visits = int(value)
    if max_visits < 1:
        raise ValueError("split.max_visits must be >= 1")
    return max_visits


def _select_patient_cases(
    cases: list[PatientCase],
    max_visits: int | None,
) -> list[PatientCase]:
    ordered = sorted(cases, key=_visit_num)
    if max_visits is None or len(ordered) <= max_visits:
        return ordered
    return ordered[:max_visits]


def _cap_cases_per_patient(
    cases: list[PatientCase],
    max_visits: int | None,
) -> list[PatientCase]:
    if max_visits is None:
        return list(cases)

    by_patient: dict[str, list[PatientCase]] = defaultdict(list)
    order = []
    seen = set()
    for case in cases:
        by_patient[case.patient_id].append(case)
        if case.patient_id not in seen:
            seen.add(case.patient_id)
            order.append(case.patient_id)

    capped = []
    for patient_id in order:
        capped.extend(_select_patient_cases(by_patient[patient_id], max_visits))
    return capped


def _case_is_poly(case: PatientCase, gt_data: dict[str, dict]) -> bool:
    entry = gt_data.get(f"{case.patient_id}__v{_visit_num(case)}", {})
    return len(entry.get("prescribed") or []) > 1


def _classify_patients(
    by_patient: dict[str, list[PatientCase]],
    gt_data: dict[str, dict],
) -> dict[str, list[str]]:
    strata = {name: [] for name in STRATA}
    for patient_id, patient_cases in by_patient.items():
        poly_count = sum(1 for case in patient_cases if _case_is_poly(case, gt_data))
        total = len(patient_cases)
        if poly_count == 0:
            strata["mono"].append(patient_id)
        elif poly_count >= total / 2:
            strata["poly"].append(patient_id)
        else:
            strata["mixed"].append(patient_id)
    return strata


def _read_strata_ratios(split_cfg: dict[str, Any]) -> dict[str, float]:
    raw = split_cfg.get("strata") or {"mono": 0.5, "mixed": 0.3, "poly": 0.2}
    ratios = {name: float(raw.get(name, 0.0)) for name in STRATA}
    total = sum(ratios.values())
    if total <= 0:
        raise ValueError("split.strata must contain at least one positive value")
    return {name: value / total for name, value in ratios.items()}


def _allocate_strata_counts(total: int, ratios: dict[str, float]) -> dict[str, int]:
    exact = {name: total * ratios[name] for name in STRATA}
    counts = {name: int(exact[name]) for name in STRATA}
    remaining = total - sum(counts.values())
    order = sorted(STRATA, key=lambda name: (exact[name] - counts[name]), reverse=True)
    for name in order[:remaining]:
        counts[name] += 1
    return counts


def _stratified_patient_split(
    by_patient: dict[str, list[PatientCase]],
    gt_data: dict[str, dict],
    split_cfg: dict[str, Any],
    split_seed: int,
    seed: int,
    n_train: int,
    n_eval: int,
) -> tuple[list[str], list[str], list[str], dict[str, Any]]:
    ratios = _read_strata_ratios(split_cfg)
    train_counts = _allocate_strata_counts(n_train, ratios)
    eval_counts = _allocate_strata_counts(n_eval, ratios)
    pool_counts = {name: train_counts[name] + eval_counts[name] for name in STRATA}

    strata = _classify_patients(by_patient, gt_data)
    split_rng = random.Random(split_seed)
    for patient_ids in strata.values():
        split_rng.shuffle(patient_ids)

    pool_by_stratum: dict[str, list[str]] = {}
    test_pids = []
    for name in STRATA:
        available = strata[name]
        required = pool_counts[name]
        if len(available) < required:
            raise ValueError(
                f"Not enough {name} patients for stratified split: "
                f"need {required}, got {len(available)}"
            )
        pool_by_stratum[name] = available[:required]
        test_pids.extend(available[required:])

    run_rng = random.Random(seed)
    train_pids = []
    eval_pids = []
    for name in STRATA:
        patient_ids = list(pool_by_stratum[name])
        run_rng.shuffle(patient_ids)
        train_n = train_counts[name]
        eval_n = eval_counts[name]
        train_pids.extend(patient_ids[:train_n])
        eval_pids.extend(patient_ids[train_n:train_n + eval_n])

    split_meta = {
        "strata_ratios": ratios,
        "available_strata": {name: len(strata[name]) for name in STRATA},
        "pool_strata": pool_counts,
        "train_strata": train_counts,
        "eval_strata": eval_counts,
        "test_strata": {
            name: max(0, len(strata[name]) - pool_counts[name])
            for name in STRATA
        },
    }
    return train_pids, eval_pids, test_pids, split_meta


def _stats(
    train_cases: list[PatientCase],
    eval_cases: list[PatientCase],
    test_cases: list[PatientCase],
    gt_data: dict,
    extra: dict,
) -> dict:
    def is_poly(case: PatientCase) -> bool:
        visit_num = int(case.current_visit.split("_")[1])
        entry = gt_data.get(f"{case.patient_id}__v{visit_num}", {})
        return len(entry.get("prescribed") or []) > 1

    return {
        **extra,
        "train_patients": len({c.patient_id for c in train_cases}),
        "train_cases": len(train_cases),
        "train_poly": sum(1 for c in train_cases if is_poly(c)),
        "eval_patients": len({c.patient_id for c in eval_cases}),
        "eval_cases": len(eval_cases),
        "eval_poly": sum(1 for c in eval_cases if is_poly(c)),
        "test_patients": len({c.patient_id for c in test_cases}),
        "test_cases": len(test_cases),
        "test_poly": sum(1 for c in test_cases if is_poly(c)),
    }


def load_split(config: dict[str, Any], seed: int) -> dict:
    path = config.get("cases_path") or (config.get("paths") or {}).get("cases")
    if not path:
        raise ValueError("JSONL adapter requires 'cases_path' or 'paths.cases'")
    records = _read_jsonl(_resolve_path(config, str(path)))
    if not records:
        raise ValueError("JSONL dataset is empty")

    default_cohort = str(config.get("name", "jsonl"))
    split_cfg = config.get("split") or {}
    records, cohort_filter = _filter_records_by_cohort(
        records,
        split_cfg.get("cohort", split_cfg.get("cohorts")),
        default_cohort,
    )
    max_visits = _read_max_visits(split_cfg)

    cases = []
    gt_data = {}
    record_splits: dict[str, str] = {}
    skipped_unlabeled = 0
    for record in records:
        if not (record.get("prescribed") or record.get("gt") or []):
            skipped_unlabeled += 1
            continue
        case, key, gt = _case_and_gt(record, default_cohort)
        cases.append(case)
        gt_data[key] = gt
        split_name = str(record.get("split", "")).lower()
        if split_name:
            record_splits[key] = split_name
    if not cases:
        raise ValueError("JSONL dataset has no labeled rows with prescribed/gt")

    split_seed = int(split_cfg.get("split_seed", 42))
    explicit = split_cfg.get("mode") == "explicit" or bool(record_splits)
    if explicit:
        train_cases = []
        eval_cases = []
        test_cases = []
        for case in cases:
            visit_num = int(case.current_visit.split("_")[1])
            split_name = record_splits.get(f"{case.patient_id}__v{visit_num}", "")
            if split_name == "train":
                train_cases.append(case)
            elif split_name in {"eval", "val", "validation"}:
                eval_cases.append(case)
            elif split_name == "test":
                test_cases.append(case)
        if not train_cases or not eval_cases:
            raise ValueError("Explicit split requires non-empty train and eval/val records")
        train_cases = _cap_cases_per_patient(train_cases, max_visits)
        eval_cases = _cap_cases_per_patient(eval_cases, max_visits)
        test_cases = _cap_cases_per_patient(test_cases, max_visits)
        stats = _stats(
            train_cases,
            eval_cases,
            test_cases,
            gt_data,
            {
                "seed": seed,
                "split_seed": split_seed,
                "split_mode": "explicit",
                "cohort_filter": cohort_filter,
                "max_visits": max_visits,
                "skipped_unlabeled": skipped_unlabeled,
            },
        )
        return {
            "train_cases": train_cases,
            "eval_cases": eval_cases,
            "test_cases": test_cases,
            "gt_data": gt_data,
            "stats": stats,
        }

    by_patient: dict[str, list[PatientCase]] = defaultdict(list)
    for case in cases:
        by_patient[case.patient_id].append(case)
    patients = list(by_patient)
    n_train = int(split_cfg.get("train_patients", 50))
    n_eval = int(split_cfg.get("val_patients", split_cfg.get("eval_patients", 20)))
    if len(patients) < n_train + n_eval:
        raise ValueError(
            f"Need at least {n_train + n_eval} patients for requested split, got {len(patients)}"
        )

    strategy = str(split_cfg.get("strategy", "patient_pool")).lower()
    split_meta: dict[str, Any] = {}
    if strategy == "stratified":
        train_pids, eval_pids, test_pids, split_meta = _stratified_patient_split(
            by_patient=by_patient,
            gt_data=gt_data,
            split_cfg=split_cfg,
            split_seed=split_seed,
            seed=seed,
            n_train=n_train,
            n_eval=n_eval,
        )
        pool_patients = n_train + n_eval
    elif strategy in {"patient_pool", "pool"}:
        split_rng = random.Random(split_seed)
        split_rng.shuffle(patients)
        pool = patients[: n_train + n_eval]

        run_rng = random.Random(seed)
        run_rng.shuffle(pool)
        train_pids = pool[:n_train]
        eval_pids = pool[n_train : n_train + n_eval]
        test_pids = patients[n_train + n_eval :]
        pool_patients = len(pool)
    else:
        raise ValueError(f"Unknown split.strategy: {strategy}")

    train_cases = [
        case for pid in train_pids
        for case in _select_patient_cases(by_patient[pid], max_visits)
    ]
    eval_cases = [
        case for pid in eval_pids
        for case in _select_patient_cases(by_patient[pid], max_visits)
    ]
    test_cases = [
        case for pid in test_pids
        for case in _select_patient_cases(by_patient[pid], max_visits)
    ]

    stats = _stats(
        train_cases,
        eval_cases,
        test_cases,
        gt_data,
        {
            "seed": seed,
            "split_seed": split_seed,
            "split_mode": strategy,
            "pool_patients": pool_patients,
            "all_patients": len(patients),
            "cohort_filter": cohort_filter,
            "max_visits": max_visits,
            "skipped_unlabeled": skipped_unlabeled,
            **split_meta,
        },
    )
    return {
        "train_cases": train_cases,
        "eval_cases": eval_cases,
        "test_cases": test_cases,
        "train_pids": train_pids,
        "eval_pids": eval_pids,
        "test_pids": test_pids,
        "gt_data": gt_data,
        "stats": stats,
    }
