"""Main entry point: run multi-agent pipeline on all patients."""

import argparse
import asyncio
import json
import os

from llm.client import LLMClient
from data.loader import load_all_cases
from orchestrator.pipeline import ConsiliumPipeline
from tqdm import tqdm


async def main():
    parser = argparse.ArgumentParser(description="Consilium: Multi-Agent Epilepsy Drug Prediction")
    parser.add_argument("--visit", type=int, default=1, choices=[1, 2, 3], help="Visit number (1, 2, or 3)")
    parser.add_argument("--model", type=str, default="openai.gpt-oss-120b-1:0", help="LLM model name")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of patients (for debugging)")
    parser.add_argument("--no-debate", action="store_true", help="Disable pharmacologist-epileptologist debate")
    parser.add_argument("--no-format", action="store_true", help="Skip LLM formatting of output trace")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join("outputs", "predictions")
    traces_dir = os.path.join("outputs", "traces")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(traces_dir, exist_ok=True)

    client = LLMClient(model=args.model)
    pipeline = ConsiliumPipeline(
        llm_client=client,
        enable_debate=not args.no_debate,
        format_output=not args.no_format,
    )

    cases = load_all_cases(visit_num=args.visit, limit=args.limit)

    print(f"\n{'='*60}")
    print(f"CONSILIUM — MULTI-AGENT PIPELINE")
    print(f"{'='*60}")
    print(f"Model:    {args.model}")
    print(f"Visit:    {args.visit}")
    print(f"Patients: {len(cases)}")
    print(f"Debate:   {'enabled' if not args.no_debate else 'disabled'}")
    print(f"Output:   {output_dir}")
    print(f"{'='*60}\n")

    all_predictions = {}
    all_traces = {}

    pbar = tqdm(total=len(cases), desc="Processing", unit="patient")

    for case in cases:
        recommendation, trace = await pipeline.run(case)

        all_predictions[case.patient_id] = {
            f"option_{opt.rank}": opt.to_comparable()
            for opt in recommendation.options
        }
        all_traces[case.patient_id] = trace.to_dict()

        pbar.update(1)

    pbar.close()
    await client.close()

    # Save predictions
    short_model = args.model.replace("/", "_").replace("-", "")[:20]
    pred_path = os.path.join(output_dir, f"consilium_{short_model}_v{args.visit}.json")
    with open(pred_path, "w", encoding="utf-8") as f:
        json.dump(all_predictions, f, indent=2, ensure_ascii=False)

    # Save traces
    trace_path = os.path.join(traces_dir, f"traces_{short_model}_v{args.visit}.json")
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(all_traces, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"DONE! {len(all_predictions)} patients processed.")
    print(f"  Predictions: {pred_path}")
    print(f"  Traces:      {trace_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
