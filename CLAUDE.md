# Consilium — Multi-Agent Epilepsy Drug Prediction

## Project Overview
Multi-agent LLM system for epilepsy drug prediction targeting NeurIPS. 7 specialist agents reason independently, then debate and synthesize treatment recommendations for Ugandan epilepsy patients.

## Architecture
- `schemas/` — Dataclasses: PatientCase, AgentResponse, ReasoningTrace, FinalRecommendation
- `agents/` — 7 specialist agents inheriting from BaseAgent ABC. Prompts in `agents/prompts/`
- `orchestrator/` — 4-phase pipeline: parallel assessment → conflict detection → prescription → debate → synthesis
- `llm/` — Async LLM client via AWS Bedrock (Converse API), default model: `openai.gpt-oss-120b-1:0`
- `data/loader.py` — Loads pre-computed pipeline outputs into PatientCase objects
- `pipeline/` — Data cleaning pipeline (from existing work, copy as-is)
- `baseline/` — Single-agent 7-stage reasoning baseline for comparison
- `evaluation/` — Grading, error detection, trace quality, disagreement analysis, ablation runner

## Dependencies
Managed with [uv](https://docs.astral.sh/uv/). Run `uv sync` to install.

## Key Commands
```bash
# Run multi-agent pipeline
uv run python run_pipeline.py --visit 1 --limit 5

# Run single-agent baseline
uv run python run_baseline.py --visit 1

# Run evaluation
uv run python run_evaluation.py --predictions outputs/predictions/consilium_*.json --visit 1

# Run ablations (9 configs)
uv run python run_ablation.py --visit 1 --limit 5
```

## Data
- Raw patient CSV: `data/combined_dataset.csv` (279 patients, semicolon-delimited)
- Pre-computed pipeline outputs in `data/processed/` (split_results, clean_output, drug_gt, visit_counts)
- Doctor feedback in `data/feedback/` (feedback_Raj.csv, feedback_JP.csv — 60 visit-level entries each)
- 10 tracked ASMs: carbamazepine, clobazam, clonazepam, ethosuximide, lamotrigine, levetiracetam, phenobarbital, phenytoin, topiramate, valproate

## Environment
```bash
cp .env.example .env  # Configure AWS region (credentials via standard AWS chain)
uv sync              # Install dependencies
```

## Execution Flow
```
Patient → Phase 1 (parallel: diagnostician, treatment_analyst, pediatrician, [tropical_medicine], formulary)
        → Phase 1.5 (programmatic conflict detection)
        → Phase 2 (epileptologist sees all Phase 1 outputs)
        → Phase 3 (pharmacologist adversarial review)
        → Phase 3.5 (structured debate if concerns raised, max 2 rounds)
        → Phase 4 (rule-based synthesis, single LLM call for formatting only)
```

## Design Principles
1. Agents = real doctors (diagnostician, not "seizure_classifier")
2. Conflict resolution is rule-based, not another LLM black box
3. Pharmacologist advises, doesn't veto
4. Every agent sees full patient history independently
5. Reasoning traces ARE the deliverable
