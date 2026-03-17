"""Run all ablation configurations."""

import argparse
import asyncio
import json
import os

from evaluation.ablation import run_all_ablations


async def main():
    parser = argparse.ArgumentParser(description="Ablation Study")
    parser.add_argument("--visit", type=int, default=1, choices=[1, 2, 3])
    parser.add_argument("--model", type=str, default="openai/gpt-oss-120b")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    results = await run_all_ablations(visit_num=args.visit, model=args.model, limit=args.limit)

    # Save summary
    output_dir = os.path.join("outputs", "ablations")
    os.makedirs(output_dir, exist_ok=True)
    summary_path = os.path.join(output_dir, f"ablation_summary_v{args.visit}.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print("ABLATION SUMMARY")
    print(f"{'='*60}")
    for r in results:
        print(f"  {r['config']:30s} exact={r['grades'].get('exact_match_rate', 0):.1%}  "
              f"jaccard={r['grades'].get('mean_jaccard', 0):.3f}")
    print(f"\nSaved to {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
