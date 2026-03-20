"""Main entry point: run V2 multi-agent pipeline on all patients."""

import argparse
import asyncio
import json
import os

from llm.client import LLMClient
from data.loader import load_all_cases
from orchestrator.pipeline import ConsiliumPipeline
from tqdm import tqdm


async def main():
    parser = argparse.ArgumentParser(description="Consilium V2: Multi-Agent Epilepsy Drug Prediction")
    parser.add_argument("--visit", type=int, default=1, choices=[1, 2, 3], help="Visit number (1, 2, or 3)")
    parser.add_argument("--model", type=str, default="openai.gpt-oss-120b-1:0", help="LLM model name")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of patients (for debugging)")
    parser.add_argument("--max-rounds", type=int, default=0, help="Extra debate rounds (0=epi revises once, 1=two revisions, etc.)")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join("outputs", "v2")
    os.makedirs(output_dir, exist_ok=True)

    client = LLMClient(model=args.model)
    pipeline = ConsiliumPipeline(
        llm_client=client,
        max_debate_rounds=args.max_rounds,
    )

    cases = load_all_cases(visit_num=args.visit, limit=args.limit)

    print(f"\n{'='*60}")
    print(f"CONSILIUM V2 — MULTI-AGENT PIPELINE")
    print(f"{'='*60}")
    print(f"Model:    {args.model}")
    print(f"Visit:    {args.visit}")
    print(f"Patients: {len(cases)}")
    print(f"Debate:   max {args.max_rounds} extra rounds (always at least 1 epi revision)")
    print(f"Output:   {output_dir}")
    print(f"{'='*60}\n")

    all_results = {}
    pbar = tqdm(total=len(cases), desc="Processing", unit="patient")

    for case in cases:
        result = await pipeline.run(case)
        all_results[case.patient_id] = result
        pbar.update(1)

    pbar.close()
    await client.close()

    # Save output — patient_id as key, visit in filename
    short_model = args.model.replace("/", "_").replace("-", "")[:20]
    out_path = os.path.join(output_dir, f"consilium_v2_{short_model}_v{args.visit}_d{args.max_rounds}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"DONE! {len(all_results)} patients processed.")
    print(f"  Output: {out_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
