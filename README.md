# Consilium

Clinical LLM systems for epilepsy antiseizure medication (ASM) regimen
prediction.

This repository has two main systems:

- `manana`: self-learning prompt memory over clinical cases, plus Bayesian
  Prompt Averaging (BPA) for uncertainty-aware deferral.
- `consilium`: fixed expert-designed multi-agent reference system.

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
        v
manana.run
        |
        +--> single  Predictor -> Inspector -> Buffer -> Architect
        +--> multi   Agents -> Predictor -> Inspector -> Buffer -> Architect
        +--> BPA     ensemble over learned trajectory -> deferral
        |
        v
manana.evaluate / lib.grader

consilium.run uses the fixed expert-designed agents through consilium.loader.
```

## Setup

```bash
uv sync
cp .env.example .env
```

Model calls use AWS Bedrock through `lib.llm.LLMClient`; configure AWS access
through the standard local environment.

## Data

Manana uses Case JSONL. Each line is one prediction case.

Required fields:

- `pid` or `patient_id`
- `input`, `clinical_context`, or `notes`
- `prescribed` or `gt`

Recommended fields:

- `visit_num` or `visit` (defaults to `1`)

Optional fields:

- `cohort` (defaults to the config `name`; include it when mixing cohorts or
  using a cohort filter)
- `output`
- `stopped`
- `split` (`train`, `eval`/`val`/`validation`, or `test`)

Example:

```json
{"pid":"p001","visit_num":1,"input":"clinical note...","prescribed":["levetiracetam"],"stopped":[]}
```

Use `configs/jsonl_example.yaml` for the generic template and
`configs/mimic.yaml` for the MIMIC-IV export.

## Manana

Run self-learning:

```bash
uv run python -m manana.run --config configs/jsonl_example.yaml --system single
uv run python -m manana.run --config configs/jsonl_example.yaml --system multi
```

Evaluate a saved run:

```bash
uv run python -m manana.evaluate \
  --config configs/jsonl_example.yaml \
  --run-dir manana/single/outputs/<dataset>/<model>/<run_id> \
  --split test \
  --round best

uv run python -m lib.grader \
  --predictions manana/single/outputs/<dataset>/<model>/<run_id>/evaluations/test_r<round>_predictions.json \
  --config configs/jsonl_example.yaml
```

Ablations:

```bash
uv run python -m manana.ablations.run --config configs/jsonl_example.yaml --system single --ablation no-buffer
uv run python -m manana.ablations.run --config configs/jsonl_example.yaml --system multi --ablation no-inspector
uv run python -m manana.ablations.icl.run --config configs/jsonl_example.yaml
uv run python -m manana.ablations.rewrite.run --config configs/jsonl_example.yaml --system single
```

## Bayesian Prompt Averaging (BPA)

BPA turns a completed multi-agent Manana run into an uncertainty-aware,
deferral-capable predictor. It treats the learned prompt trajectory as an
ensemble: it selects the top rounds by validation top-3 rate, re-runs each as an
ensemble member, and combines their ranked regimens into a weighted vote over
complete regimens. The winner's normalized vote mass is a per-case confidence
used for selective prediction — auto-handle the high-confidence cases, defer the
low-confidence ones to a specialist.

It needs a finished multi-agent run directory containing `eval_progression.json`
and the per-round prompts:

```bash
uv run python -m manana.bpa.run \
  --config configs/jsonl_example.yaml \
  --run-dir manana/multi/outputs/<dataset>/<model>/<run_id> \
  --num 5 --weighting softmax --split test
```

This writes a `lib.grader`-compatible predictions JSON (so scoring is unchanged)
and prints exact-match scores plus a selective-prediction (coverage -> precision)
table. Defaults match the paper: `--num 5`, `--weighting softmax`, `--tau 5`.

## MIMIC-IV

Prepare the MIMIC-IV local export:

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
