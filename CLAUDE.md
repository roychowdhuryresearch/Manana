# Consilium — Multi-Agent Epilepsy Drug Prediction

## Project Overview
Multi-agent LLM system for epilepsy drug prediction targeting NeurIPS. 7 specialist agents reason independently, then debate and synthesize treatment recommendations for Ugandan epilepsy patients.

## Architecture
- `schemas/` — Dataclasses: PatientCase, AgentResponse, FinalRecommendation
- `agents/` — 7 specialist agents inheriting from BaseAgent ABC. Prompts in `agents/prompts/`
- `core/` — 4-phase pipeline execution: pipeline.py, debate.py, regimen_parser.py
- `llm/` — Async LLM client via AWS Bedrock (Converse API), default model: `openai.gpt-oss-120b-1:0`
- `baseline/` — Single-agent 7-stage reasoning baseline for comparison
- `scripts/` — Entry points: run_pipeline.py, run_baseline.py, run_ablation.py, evaluate.py, loader.py

## Dependencies
Run with `conda run -n global_llm python ...`

## Key Commands
```bash
# Run multi-agent pipeline
conda run -n global_llm python scripts/run_pipeline.py --visit 1 --limit 5

# Run single-agent baseline
conda run -n global_llm python scripts/run_baseline.py --visit 1 --limit 5

# Run evaluation
conda run -n global_llm python scripts/evaluate.py --predictions outputs/predictions/consilium_*.json

# Run ablations (7 configs)
conda run -n global_llm python scripts/run_ablation.py --visit 1 --limit 5
```

## Data
- HuggingFace dataset: `kartiksharma4/consilium` (2,549 entries, 3 cohorts: CSV-279, CSV-53, PDF-367)
- Raw source data in `data/` (combined_dataset.csv, processed/, feedback/)
- 10 tracked ASMs: carbamazepine, clobazam, clonazepam, ethosuximide, lamotrigine, levetiracetam, phenobarbital, phenytoin, topiramate, valproate

## Execution Flow
```
Patient → Orchestrator (decides which Phase 1 agents activate)
        → Phase 1 (parallel: diagnostician, treatment_analyst, pediatrician, [tropical_medicine], formulary)
        → Phase 2 (epileptologist sees all Phase 1 outputs)
        → Phase 3 (pharmacologist adversarial review)
        → Debate (if pharmacologist raises concerns, max rounds configurable)
        → Final regimen (last epileptologist output)
```

## TODO
- Write 3 analysis scripts in `scripts/` (from scratch, new JSON format):
  - `trace_quality.py` — reasoning trace quality metrics
  - `disagreement.py` — inter-agent disagreement analysis
  - `error_detection.py` — map doctor feedback to agent errors

## Design Principles
1. Agents = real doctors (diagnostician, not "seizure_classifier")
2. Pharmacologist advises, doesn't veto
3. Every agent sees full patient history independently
4. Reasoning traces ARE the deliverable
5. Ablation = same pipeline, disabled agents invisible to orchestrator
