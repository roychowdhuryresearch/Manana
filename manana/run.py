"""Config-driven public entrypoint for Manana runs."""

from __future__ import annotations

import argparse
import asyncio

from lib.llm import DEFAULT_MODEL
from manana.single import run_loop as single_loop
from manana.multi import run_loop as multi_loop


async def main(args) -> None:
    if args.system == "single":
        await single_loop.run_loop(
            batch_size=args.batch_size,
            max_rounds=args.rounds,
            model=args.model,
            seed=args.seed,
            temperature=args.temp,
            config_path=args.config,
        )
    else:
        await multi_loop.run_loop(
            batch_size=args.batch_size,
            max_rounds=args.rounds,
            model=args.model,
            seed=args.seed,
            config_path=args.config,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run config-driven Manana.")
    parser.add_argument("--config", required=True, help="Run YAML config")
    parser.add_argument("--system", choices=["single", "multi"], required=True)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--temp", type=float, default=None, help="LLM temperature for single-loop calls")
    asyncio.run(main(parser.parse_args()))
