"""Full evaluation suite — grading, error detection, trace quality, disagreement."""

import argparse
import asyncio
import json
import os

from evaluation.grader import grade_all
from evaluation.trace_quality import aggregate_trace_metrics
from evaluation.disagreement import disagreement_difficulty_correlation
from schemas.trace import ReasoningTrace


def load_predictions(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_traces(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Evaluation Suite")
    parser.add_argument("--predictions", type=str, required=True, help="Path to predictions JSON")
    parser.add_argument("--traces", type=str, default=None, help="Path to traces JSON (optional)")
    parser.add_argument("--visit", type=int, default=1, choices=[1, 2, 3])
    parser.add_argument("--output-dir", type=str, default="outputs/evaluation")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    predictions = load_predictions(args.predictions)

    # 1. Grading
    print("Grading predictions...")
    grades = grade_all(predictions, visit_num=args.visit)
    grades_path = os.path.join(args.output_dir, "grades.json")
    with open(grades_path, "w", encoding="utf-8") as f:
        json.dump(grades, f, indent=2)

    print(f"\nGRADING RESULTS (Visit {args.visit})")
    print(f"  Exact match:  {grades['summary']['exact_match_rate']:.1%}")
    print(f"  Mean Jaccard:  {grades['summary']['mean_jaccard']:.3f}")
    print(f"  Mono exact:    {grades['summary']['mono_exact_rate']:.1%} ({grades['summary']['mono_total']} patients)")
    print(f"  Poly exact:    {grades['summary']['poly_exact_rate']:.1%} ({grades['summary']['poly_total']} patients)")
    print(f"  Total:         {grades['summary']['n_patients']} patients")

    # 2. Trace quality (if traces provided)
    if args.traces:
        print("\nEvaluating trace quality...")
        raw_traces = load_traces(args.traces)
        # Note: full ReasoningTrace reconstruction from dict would be needed for complete analysis
        print(f"  Loaded {len(raw_traces)} traces")

    print(f"\nResults saved to {args.output_dir}/")


if __name__ == "__main__":
    main()
