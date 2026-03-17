"""Run single-agent baseline for comparison."""

import argparse
import asyncio

from baseline.predict import run_baseline


async def main():
    parser = argparse.ArgumentParser(description="Single-Agent Baseline Prediction")
    parser.add_argument("--visit", type=int, default=1, choices=[1, 2, 3])
    parser.add_argument("--model", type=str, default="openai/gpt-oss-120b")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    await run_baseline(visit_num=args.visit, model=args.model, limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())
