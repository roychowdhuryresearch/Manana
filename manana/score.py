"""Score Manana prediction JSON against config-backed ground truth."""

from __future__ import annotations

import argparse
import json
import os

from lib.grader import grade_files, print_scores, resolve_gt_jsonl_from_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Score Manana prediction JSON.")
    parser.add_argument("--predictions", required=True, help="Prediction JSON from `python -m manana.evaluate`")
    parser.add_argument("--config", required=True, help="Run YAML config with paths.cases")
    parser.add_argument("--out", default=None, help="Optional output JSON path for scores and per-case results")
    args = parser.parse_args()

    gt_jsonl = resolve_gt_jsonl_from_config(args.config)
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
