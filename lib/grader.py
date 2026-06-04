"""Generic medication-regimen grader.

This module is intentionally independent of MIMIC and Manana. It grades
prediction JSON against Case JSONL ground truth:

    uv run python -m lib.grader --predictions preds.json --gt-jsonl data/cases.jsonl
    uv run python -m lib.grader --predictions preds.json --config configs/mimic.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from typing import Any

import yaml

from lib.regimen_parser import parse_regimen

ACTIVE_ACTIONS = {"continue", "start"}


def normalize_drugs(value: Any) -> list[str]:
    """Return a stable, lowercase drug list from common JSON shapes."""
    if value is None:
        return []
    if isinstance(value, dict):
        drugs = [drug for drug, action in value.items() if str(action).lower() in ACTIVE_ACTIONS]
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            drugs = []
        else:
            try:
                parsed = json.loads(text)
                return normalize_drugs(parsed)
            except json.JSONDecodeError:
                drugs = re.split(r"[,;]\s*", text)
    else:
        drugs = list(value)
    return sorted({str(drug).strip().lower() for drug in drugs if str(drug).strip()})


def visit_num_from_record(record: dict[str, Any]) -> int:
    visit = record.get("visit_num", record.get("visit"))
    if visit is None:
        raise ValueError(f"Prediction/GT record missing visit_num: {record}")
    if isinstance(visit, int):
        return visit
    match = re.search(r"\d+", str(visit))
    if not match:
        raise ValueError(f"Could not parse visit number from: {visit}")
    return int(match.group())


def record_key(record: dict[str, Any]) -> str:
    pid = record.get("pid", record.get("patient_id"))
    if pid is None:
        raise ValueError(f"Prediction/GT record missing pid: {record}")
    return f"{str(pid)}__v{visit_num_from_record(record)}"


def case_key(pid: str, visit_num: int) -> str:
    return f"{str(pid)}__v{int(visit_num)}"


def drugs_from_regimen(regimen: dict[str, Any], option_key: str = "option_1") -> list[str]:
    option = regimen.get(option_key) or {}
    return normalize_drugs(option.get("drugs") or {})


def regimen_options(regimen: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a parsed regimen dict into a grader-friendly options list."""
    options = []
    for rank in range(1, 4):
        option_key = f"option_{rank}"
        option = regimen.get(option_key) or {}
        drugs = option.get("drugs") or {}
        options.append(
            {
                "rank": rank,
                "drugs": drugs_from_regimen(regimen, option_key),
                "actions": {str(k).lower(): str(v).lower() for k, v in drugs.items()},
                "label": str(option.get("label") or ""),
                "rationale": str(option.get("rationale") or ""),
            }
        )
    return options


def prediction_options(record: dict[str, Any]) -> list[list[str]]:
    """Extract ranked predicted drug sets from a prediction record."""
    options = record.get("options")
    if isinstance(options, list) and options:
        extracted = []
        for option in options:
            if isinstance(option, dict):
                extracted.append(normalize_drugs(option.get("drugs") or option.get("predicted")))
            else:
                extracted.append(normalize_drugs(option))
        return extracted

    regimen = record.get("regimen") or record.get("parsed_regimen")
    if isinstance(regimen, dict):
        return [drugs_from_regimen(regimen, f"option_{rank}") for rank in range(1, 4)]

    raw = record.get("raw_prediction") or record.get("predictor_raw")
    if isinstance(raw, str) and raw.strip():
        parsed = parse_regimen(raw)
        parsed_options = [drugs_from_regimen(parsed, f"option_{rank}") for rank in range(1, 4)]
        if any(parsed_options):
            return parsed_options

    for key in ("pred_top1", "predicted", "prediction", "pred", "pred_option1_drugs"):
        if key in record:
            return [normalize_drugs(record.get(key))]

    return []


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_ground_truth_jsonl(path: str) -> dict[str, dict[str, Any]]:
    gt = {}
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"GT record must be an object at {path}:{line_no}")
            prescribed = normalize_drugs(record.get("prescribed") or record.get("gt"))
            if not prescribed:
                continue
            key = record_key(record)
            gt[key] = {
                "pid": str(record.get("pid", record.get("patient_id"))),
                "visit_num": visit_num_from_record(record),
                "cohort": str(record.get("cohort") or ""),
                "prescribed": prescribed,
            }
    return gt


def resolve_gt_jsonl_from_config(config_path: str) -> str:
    config_path = os.path.abspath(config_path)
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    path = config.get("cases_path") or (config.get("paths") or {}).get("cases")
    if not path:
        raise ValueError(f"Config does not define cases_path or paths.cases: {config_path}")
    if os.path.isabs(str(path)):
        return str(path)
    return os.path.abspath(os.path.join(os.path.dirname(config_path), str(path)))


def load_predictions(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = None
        for key in ("predictions", "results", "per_case"):
            if isinstance(data.get(key), list):
                records = data[key]
                break
        if records is None:
            raise ValueError(f"Could not find predictions/results/per_case list in {path}")
    else:
        raise ValueError(f"Prediction JSON must be a list or object: {path}")

    if not all(isinstance(record, dict) for record in records):
        raise ValueError(f"Every prediction must be an object: {path}")
    return records


def score_records(
    predictions: list[dict[str, Any]],
    ground_truth: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    per_case = []
    missing_gt = []
    unparseable = []

    for record in predictions:
        try:
            key = record_key(record)
        except ValueError:
            unparseable.append(record)
            continue

        gt_entry = ground_truth.get(key)
        if not gt_entry:
            missing_gt.append({"key": key, "record": record})
            continue

        options = prediction_options(record)
        if not options:
            unparseable.append(record)
            continue

        gt = set(gt_entry["prescribed"])
        top1 = set(options[0])
        top3 = [set(option) for option in options[:3]]

        per_case.append(
            {
                "pid": gt_entry["pid"],
                "visit_num": gt_entry["visit_num"],
                "cohort": gt_entry.get("cohort", ""),
                "gt": sorted(gt),
                "pred_top1": sorted(top1),
                "pred_options": [sorted(option) for option in top3],
                "n_gt": len(gt),
                "top1_match": top1 == gt,
                "top3_match": any(option == gt for option in top3),
                "jaccard": round(jaccard(top1, gt), 4),
            }
        )

    return {
        "scores": summarize(per_case),
        "per_case": per_case,
        "missing_ground_truth": missing_gt,
        "unparseable_predictions": unparseable,
    }


def summarize(per_case: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(per_case)
    top1 = sum(1 for row in per_case if row["top1_match"])
    top3 = sum(1 for row in per_case if row["top3_match"])
    mean_jaccard = sum(row["jaccard"] for row in per_case) / n if n else 0.0

    def group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(rows)
        hits1 = sum(1 for row in rows if row["top1_match"])
        hits3 = sum(1 for row in rows if row["top3_match"])
        jac = sum(row["jaccard"] for row in rows) / total if total else 0.0
        return {
            "n": total,
            "top1_correct": hits1,
            "top3_correct": hits3,
            "top1_em": round(hits1 / total, 4) if total else 0.0,
            "top3_em": round(hits3 / total, 4) if total else 0.0,
            "jaccard": round(jac, 4),
        }

    by_tier = {}
    rows_by_tier: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in per_case:
        rows_by_tier[int(row["n_gt"])].append(row)
    for n_gt, rows in sorted(rows_by_tier.items()):
        by_tier[str(n_gt)] = group_summary(rows)

    mono = [row for row in per_case if row["n_gt"] == 1]
    poly = [row for row in per_case if row["n_gt"] > 1]

    return {
        "n": n,
        "top1_correct": top1,
        "top3_correct": top3,
        "top1_em": round(top1 / n, 4) if n else 0.0,
        "top3_em": round(top3 / n, 4) if n else 0.0,
        "jaccard": round(mean_jaccard, 4),
        "mono": group_summary(mono),
        "poly": group_summary(poly),
        "by_tier": by_tier,
    }


def grade_files(predictions_path: str, gt_jsonl: str) -> dict[str, Any]:
    predictions = load_predictions(predictions_path)
    ground_truth = load_ground_truth_jsonl(gt_jsonl)
    result = score_records(predictions, ground_truth)
    result["predictions_path"] = os.path.abspath(predictions_path)
    result["gt_jsonl"] = os.path.abspath(gt_jsonl)
    return result


def print_scores(scores: dict[str, Any]) -> None:
    print(f"Cases:      {scores['n']}")
    print(f"Top-1 EM:   {scores['top1_em'] * 100:.1f}% ({scores['top1_correct']}/{scores['n']})")
    print(f"Top-3 EM:   {scores['top3_em'] * 100:.1f}% ({scores['top3_correct']}/{scores['n']})")
    print(f"Jaccard:    {scores['jaccard']:.3f}")
    print(f"Mono Top-3: {scores['mono']['top3_em'] * 100:.1f}% (n={scores['mono']['n']})")
    print(f"Poly Top-3: {scores['poly']['top3_em'] * 100:.1f}% (n={scores['poly']['n']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade prediction JSON against Case JSONL ground truth.")
    parser.add_argument("--predictions", required=True, help="Prediction JSON file")
    parser.add_argument("--gt-jsonl", default=None, help="Case JSONL containing prescribed ground truth")
    parser.add_argument("--config", default=None, help="YAML config with paths.cases")
    parser.add_argument("--out", default=None, help="Optional output JSON path for scores and per-case results")
    args = parser.parse_args()

    if not args.gt_jsonl and not args.config:
        raise SystemExit("Provide --gt-jsonl or --config")

    gt_jsonl = args.gt_jsonl or resolve_gt_jsonl_from_config(args.config)
    result = grade_files(args.predictions, gt_jsonl)
    print_scores(result["scores"])
    if result["missing_ground_truth"]:
        print(f"Missing GT: {len(result['missing_ground_truth'])}")
    if result["unparseable_predictions"]:
        print(f"Unparseable predictions: {len(result['unparseable_predictions'])}")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
