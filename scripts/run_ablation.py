"""Run ablation study across 9 configurations.

Each config disables one or more agents to measure their contribution.
Results saved to outputs/ablations/.

Usage:
    conda run -n global_llm python pipeline/run_ablation.py --visit 1 --limit 10
    conda run -n global_llm python pipeline/run_ablation.py --visit 1
"""

import argparse
import asyncio
import json
import os
import sys

from tqdm import tqdm

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from llm.client import LLMClient
from core.pipeline import ConsiliumPipeline
from scripts.loader import load_cases

_OUTPUT_DIR = os.path.join(_ROOT, "outputs", "ablations")

ABLATION_CONFIGS = {
    "full_system":          {"disabled_agents": set(),                                                                                    "max_debate_rounds": 0},
    "no_diagnostician":     {"disabled_agents": {"diagnostician"},                                                                        "max_debate_rounds": 0},
    "no_treatment_analyst": {"disabled_agents": {"treatment_analyst"},                                                                    "max_debate_rounds": 0},
    "no_pediatrician":      {"disabled_agents": {"pediatrician"},                                                                         "max_debate_rounds": 0},
    "no_formulary":         {"disabled_agents": {"formulary"},                                                                            "max_debate_rounds": 0},
    "no_tropical_medicine": {"disabled_agents": {"tropical_medicine"},                                                                    "max_debate_rounds": 0},
    "epileptologist_only":              {"disabled_agents": {"diagnostician", "treatment_analyst", "pediatrician", "formulary", "tropical_medicine"}, "max_debate_rounds": 0},
    "no_diag_pedi":                     {"disabled_agents": {"diagnostician", "pediatrician"},                                                               "max_debate_rounds": 0},
    "no_diag_pedi_trop":                {"disabled_agents": {"diagnostician", "pediatrician", "tropical_medicine"},                                           "max_debate_rounds": 0},
    "only_diagnostician":               {"disabled_agents": {"treatment_analyst", "pediatrician", "formulary", "tropical_medicine"},                              "max_debate_rounds": 0},
    "only_treatment":                   {"disabled_agents": {"diagnostician", "pediatrician", "formulary", "tropical_medicine"},                              "max_debate_rounds": 0},
    "only_pediatrician":                {"disabled_agents": {"diagnostician", "treatment_analyst", "formulary", "tropical_medicine"},                         "max_debate_rounds": 0},
    "only_formulary":                   {"disabled_agents": {"diagnostician", "treatment_analyst", "pediatrician", "tropical_medicine"},                      "max_debate_rounds": 0},
    "only_tropical_medicine":           {"disabled_agents": {"diagnostician", "treatment_analyst", "pediatrician", "formulary"},                              "max_debate_rounds": 0},
}


async def run_config(
    config_name: str,
    config: dict,
    visit_num: int,
    model: str,
    limit: int | None,
    cohort: str | None,
) -> str:
    """Run one ablation config, save results, return output path."""
    cases = load_cases(visit_num=visit_num, cohort=cohort, limit=limit)
    if not cases:
        print(f"  No cases found, skipping.")
        return ""

    client = LLMClient(model=model)
    pipeline = ConsiliumPipeline(
        llm_client=client,
        disabled_agents=config["disabled_agents"],
        max_debate_rounds=config["max_debate_rounds"],
    )

    pbar = tqdm(total=len(cases), desc=config_name, unit="patient")

    async def _one(case):
        result = await pipeline.run(case)
        pbar.update(1)
        return case, result

    results = await asyncio.gather(*[_one(c) for c in cases], return_exceptions=True)
    pbar.close()
    await client.close()

    records = []
    for item in results:
        if isinstance(item, Exception):
            print(f"[ERROR] {item}")
        else:
            case, result = item
            records.append({
                "pid": case.patient_id,
                "cohort": case.cohort,
                "visit_num": visit_num,
                "trace": result,
            })

    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    short_model = model.replace("/", "_").replace("-", "")[:20]
    suffix = f"_{cohort}" if cohort else ""
    out_path = os.path.join(_OUTPUT_DIR, f"{config_name}_{short_model}_v{visit_num}_d{config['max_debate_rounds']}{suffix}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    return out_path


async def main():
    parser = argparse.ArgumentParser(description="Ablation study")
    parser.add_argument("--visit", type=int, nargs="+", default=None, help="Visit number(s) to run")
    parser.add_argument("--all", action="store_true", help="Run all visits (1-10)")
    parser.add_argument("--cohort", type=str, choices=["csv", "pdf"], default=None)
    parser.add_argument("--model", type=str, default="openai.gpt-oss-120b-1:0")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--config", type=str, default=None, help="Run a single config by name")
    args = parser.parse_args()

    visit_nums = list(range(1, 11)) if args.all else (args.visit or [1])
    configs = {args.config: ABLATION_CONFIGS[args.config]} if args.config else ABLATION_CONFIGS

    print(f"\n{'='*60}")
    print(f"ABLATION STUDY")
    print(f"Model: {args.model}  |  Visits: {visit_nums}  |  Configs: {len(configs)}")
    print(f"{'='*60}\n")

    for name, config in configs.items():
        for v in visit_nums:
            print(f"\n--- {name}  visit {v} ---")
            out_path = await run_config(name, config, v, args.model, args.limit, args.cohort)
            if out_path:
                print(f"  Saved → {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
