# Consilium

Clinical LLM systems for epilepsy antiseizure medication (ASM) regimen
prediction.

This repository has two main systems:

- `manana`: self-learning prompt memory over clinical cases.
- `consilium`: fixed expert-designed multi-agent reference system.

Private Uganda data, raw MIMIC files, credentials, and generated runs are not
part of the repository.

## Repository Design

```text
consilium/
  consilium/              Fixed expert-designed multi-agent system
  manana/                 Self-learning single/multi systems and ablations
  prompts/                Manana prompt templates
  configs/                Dataset/run YAML configs
  data_adapters/          Generic Case JSONL adapter
  lib/                    Shared LLM, parser, patient, and grader utilities
  mimic/                  MIMIC-IV preprocessing and export recipe
  baseline/               Lightweight baseline code kept for this release
```

Runtime flow:

```text
Case JSONL / MIMIC export
        |
        v
configs/*.yaml
        |
        v
data_adapters.jsonl:load_split
        |
        +-------------------------------+
        |                               |
        v                               v
  manana.run                     consilium.run
        |                               |
        |                               +--> fixed specialists
        |                               +--> epileptologist
        |                               +--> pharmacologist debate
        |
        +--> single
        |     Predictor -> Inspector -> Buffer -> Architect -> learned rules
        |
        +--> multi
              Agents -> Predictor -> Inspector -> Buffer -> Architect -> agent edits
        |
        v
manana.evaluate / lib.grader
```

## Setup

```bash
uv sync
cp .env.example .env
```

Model calls use AWS Bedrock through `lib.llm.LLMClient`. Configure credentials
through `.env`, `~/.aws/credentials`, `AWS_PROFILE`, or an IAM role. The `.env`
file is ignored.

## Data

Manana uses Case JSONL. Each line is one prediction case.

Required fields:

- `pid`
- `visit_num`
- `cohort`
- `input`
- `prescribed`

Optional fields:

- `output`
- `stopped`
- `split`

Example:

```json
{"pid":"p001","visit_num":1,"cohort":"local","input":"clinical note...","prescribed":["levetiracetam"],"stopped":[]}
```

Configs:

- `configs/uganda_anon.yaml`: anonymized Uganda JSONL recipe.
- `configs/jsonl_example.yaml`: generic Case JSONL template.
- `configs/mimic.yaml`: MIMIC-IV export recipe.

The Uganda config points to `data/uganda_cases_anon.jsonl`; `data/` is ignored
so the dataset can be swapped before release.

## Manana

Run self-learning:

```bash
uv run python -m manana.run --config configs/uganda_anon.yaml --system single
uv run python -m manana.run --config configs/uganda_anon.yaml --system multi
```

Evaluate a saved run:

```bash
uv run python -m manana.evaluate \
  --config configs/uganda_anon.yaml \
  --run-dir manana/single/outputs/uganda_anon/openai_gpt-oss-120b-1_0/<run_id> \
  --split test \
  --round best

uv run python -m lib.grader \
  --predictions manana/single/outputs/uganda_anon/openai_gpt-oss-120b-1_0/<run_id>/evaluations/test_r<round>_predictions.json \
  --config configs/uganda_anon.yaml
```

Ablations:

```bash
uv run python -m manana.ablations.run --config configs/uganda_anon.yaml --system single --ablation no-buffer
uv run python -m manana.ablations.run --config configs/uganda_anon.yaml --system multi --ablation no-inspector
uv run python -m manana.ablations.icl.run --config configs/uganda_anon.yaml
uv run python -m manana.ablations.rewrite.run --config configs/uganda_anon.yaml --system single
```

## MIMIC-IV

MIMIC is a credentialed-access reproducibility setting. Raw files are not
included.

Prepare the local export:

```bash
uv run python mimic/filter.py
uv run python mimic/gt.py
uv run python mimic/clean.py
uv run python mimic/export_cases.py
```

Then run Manana:

```bash
uv run python -m manana.run --config configs/mimic.yaml --system single
uv run python -m manana.run --config configs/mimic.yaml --system multi
```

`configs/mimic.yaml` uses 150 training cases and 60 validation cases with one
admission per selected patient. Full preprocessing details are in
`mimic/README.md`.

## Consilium Reference System

Run the fixed expert-designed council:

```bash
uv run python -m consilium.run --visit 1 --limit 5
uv run python -m consilium.single_agent.run --visit 1 --limit 5
uv run python -m consilium.single_agent.run --visit 1 --prompt all_agents_combined
uv run python -m consilium.ablation --visit 1 --limit 5
```

Optional analysis utilities live in `consilium/analysis/`.

## Outputs

Generated outputs are ignored under `outputs/`, `runs/`, `runs_old/`,
`baseline/*/outputs/`, `manana/*/outputs/`, and `mimic/test_results/`.
