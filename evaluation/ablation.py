"""Ablation runner — 9 configurations for contribution analysis."""

from __future__ import annotations
import json
import os
import asyncio
from tqdm import tqdm

from llm.client import LLMClient
from data.loader import load_all_cases
from orchestrator.pipeline import ConsiliumPipeline
from baseline.predict import run_baseline
from evaluation.grader import grade_all

# 9 ablation configurations
ABLATION_CONFIGS = {
    "full_system": {"disabled_agents": set(), "enable_debate": True},
    "no_debate": {"disabled_agents": set(), "enable_debate": False},
    "no_diagnostician": {"disabled_agents": {"diagnostician"}, "enable_debate": True},
    "no_treatment_analyst": {"disabled_agents": {"treatment_analyst"}, "enable_debate": True},
    "no_pediatrician": {"disabled_agents": {"pediatrician"}, "enable_debate": True},
    "no_formulary": {"disabled_agents": {"formulary"}, "enable_debate": True},
    "no_tropical_medicine": {"disabled_agents": {"tropical_medicine"}, "enable_debate": True},
    "epileptologist_only": {
        "disabled_agents": {"diagnostician", "treatment_analyst", "pediatrician", "tropical_medicine", "formulary"},
        "enable_debate": False,
    },
    # single_agent_baseline is handled separately
}


async def run_ablation_config(
    config_name: str,
    visit_num: int = 1,
    model: str = "openai/gpt-oss-120b",
    limit: int | None = None,
    output_dir: str | None = None,
) -> dict:
    """Run a single ablation configuration."""
    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "outputs", "ablations"
        )
    os.makedirs(output_dir, exist_ok=True)

    if config_name == "single_agent_baseline":
        results = await run_baseline(visit_num=visit_num, model=model, limit=limit, output_dir=output_dir)
        grades = grade_all(results, visit_num=visit_num)
        return {"config": config_name, "grades": grades["summary"]}

    config = ABLATION_CONFIGS[config_name]
    client = LLMClient(model=model)
    pipeline = ConsiliumPipeline(
        llm_client=client,
        disabled_agents=config["disabled_agents"],
        enable_debate=config["enable_debate"],
        format_output=False,
    )

    cases = load_all_cases(visit_num=visit_num, limit=limit)

    predictions = {}
    pbar = tqdm(total=len(cases), desc=f"Ablation: {config_name}", unit="patient")

    for case in cases:
        recommendation, trace = await pipeline.run(case)
        predictions[case.patient_id] = {
            f"option_{opt.rank}": opt.to_comparable()
            for opt in recommendation.options
        }
        pbar.update(1)

    pbar.close()
    await client.close()

    # Save predictions
    output_path = os.path.join(output_dir, f"{config_name}_v{visit_num}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2, ensure_ascii=False)

    # Grade
    grades = grade_all(predictions, visit_num=visit_num)

    # Save grades
    grades_path = os.path.join(output_dir, f"{config_name}_v{visit_num}_grades.json")
    with open(grades_path, "w", encoding="utf-8") as f:
        json.dump(grades["summary"], f, indent=2)

    return {"config": config_name, "grades": grades["summary"]}


async def run_all_ablations(
    visit_num: int = 1,
    model: str = "openai/gpt-oss-120b",
    limit: int | None = None,
) -> list[dict]:
    """Run all 9 ablation configurations sequentially."""
    results = []

    all_configs = list(ABLATION_CONFIGS.keys()) + ["single_agent_baseline"]

    for config_name in all_configs:
        print(f"\n{'='*60}")
        print(f"ABLATION: {config_name}")
        print(f"{'='*60}")

        result = await run_ablation_config(
            config_name, visit_num=visit_num, model=model, limit=limit,
        )
        results.append(result)
        print(f"Results: {result['grades']}")

    return results
