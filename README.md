# Consilium

A multi-agent LLM system for epilepsy drug prediction. Multiple specialist agents reason independently from different clinical lenses on the same patient, then their perspectives are synthesized through structured debate and rule-based conflict resolution.

## Motivation

Single-agent LLM reasoning suffers from anchoring bias — a single model trying to simultaneously be a diagnostician, pharmacologist, pediatrician, and formulary expert performs poorly across all of them. Analysis of 120 clinical reviews from two neurologists identified 7 systematic failure categories that map to distinct medical specializations.

Consilium addresses this with **multi-perspective clinical reasoning**: 7 specialist agents, each focused on one domain, whose outputs are integrated through an explicit conflict resolution protocol rather than another LLM black box.

## Architecture

Seven specialist agents execute in a 4-phase pipeline:

```
Patient Input
    |
    v
PHASE 1: Independent Parallel Assessment
    |-- Seizure Diagnostician        (syndrome classification, focal vs generalized)
    |-- Treatment Response Analyst   (is the current regimen working?)
    |-- Pediatric Specialist         (weight-based dosing, developmental context)
    |-- ID/Tropical Medicine         (infectious etiology differential — conditional)
    +-- Formulary Specialist         (drug availability, cost constraints)
                |
    PHASE 1.5: Programmatic Conflict Detection
                |
                v
PHASE 2: Informed Prescription
    +-- Prescribing Epileptologist   (integrates all Phase 1 outputs into treatment plan)
                |
                v
PHASE 3: Adversarial Review
    +-- Clinical Pharmacologist      (safety review of proposed prescription)
                |
    PHASE 3.5: Structured Debate     (if concerns flagged, max 2 rounds)
                |
                v
PHASE 4: Rule-Based Synthesis
    +-- Apply safety vetoes, debate modifications, availability preferences
    +-- Single LLM call for natural language formatting only
```

Conflict resolution follows an explicit hierarchy: safety vetoes > domain authority > treatment continuity > practical constraints > debate resolution.

## Data

- 279 Ugandan epilepsy patients, 3 visits each (0, 6, 12 months)
- Predominantly pediatric population in a resource-limited setting
- 10 tracked anti-seizure medications: carbamazepine, clobazam, clonazepam, ethosuximide, lamotrigine, levetiracetam, phenobarbital, phenytoin, topiramate, valproate
- 120 visit-level feedback entries from two reviewing neurologists

## Setup

```bash
# Install dependencies
uv sync

# Configure AWS credentials (Bedrock)
cp .env.example .env
# Edit .env or configure via ~/.aws/credentials / IAM roles
```

## Usage

```bash
# Run multi-agent pipeline
uv run python run_pipeline.py --visit 1 --limit 5

# Run single-agent baseline (for comparison)
uv run python run_baseline.py --visit 1

# Evaluate predictions
uv run python run_evaluation.py --predictions outputs/predictions/consilium_*.json --visit 1

# Run ablation study (9 configurations)
uv run python run_ablation.py --visit 1 --limit 5
```

## Project Structure

```
consilium/
├── DESIGN.md                           # Full architecture document
├── CLAUDE.md                           # Dev guidance
├── pyproject.toml                      # Dependencies (managed with uv)
├── .env.example                        # AWS/Bedrock config template
│
├── agents/                             # 7 specialist agents
│   ├── base.py                         # BaseAgent ABC + response parsing
│   ├── diagnostician.py                # Seizure type / syndrome classification
│   ├── treatment_analyst.py            # Treatment response assessment
│   ├── pediatrician.py                 # Pediatric dosing + developmental context
│   ├── tropical_medicine.py            # Infectious etiology (conditional)
│   ├── formulary.py                    # Drug availability + cost
│   ├── epileptologist.py               # Prescribing (integrates Phase 1)
│   ├── pharmacologist.py               # Adversarial safety review
│   └── prompts/                        # System prompts for each agent
│       ├── diagnostician.txt
│       ├── treatment_analyst.txt
│       ├── pediatrician.txt
│       ├── tropical_medicine.txt
│       ├── formulary.txt
│       ├── epileptologist.txt
│       ├── pharmacologist.txt
│       ├── debate_rebuttal.txt
│       └── orchestrator.txt
│
├── orchestrator/                       # Multi-agent coordination
│   ├── pipeline.py                     # Main 4-phase execution pipeline
│   ├── conflict.py                     # Programmatic conflict detection + rules
│   ├── debate.py                       # Pharmacologist-epileptologist debate
│   └── synthesis.py                    # Rule-based synthesis + trace formatting
│
├── schemas/                            # Structured data types
│   ├── patient.py                      # PatientCase, VisitData, MedicationHistory
│   ├── responses.py                    # AgentResponse, Finding, Concern
│   ├── trace.py                        # ReasoningTrace, ConflictRecord, DebateRound
│   └── output.py                       # FinalRecommendation, DrugOption
│
├── llm/                                # LLM client
│   └── client.py                       # Async Bedrock client (Converse API)
│
├── data/                               # Patient data + loader
│   ├── loader.py                       # Loads pipeline outputs into PatientCase objects
│   ├── combined_dataset.csv            # Raw patient CSV (gitignored)
│   ├── processed/                      # Pre-computed pipeline outputs (gitignored)
│   │   ├── split_results.json
│   │   ├── clean_output.json
│   │   ├── drug_gt.json
│   │   └── visit_counts.json
│   └── feedback/                       # Neurologist reviews (gitignored)
│       ├── feedback_JP.csv
│       └── feedback_Raj.csv
│
├── pipeline/                           # Data cleaning pipeline (upstream preprocessing)
│   ├── split_input_output.py           # Split clinical text into observations vs prescription
│   ├── build_clean_output.py           # Merge outputs into clean prescription per visit
│   ├── build_drug_gt.py                # Extract structured drug decisions
│   ├── build_pred_input.py             # Deterministic input construction
│   ├── predict_drugs_clean.py          # Original single-agent prediction script
│   ├── count_visits.py                 # Visit counting utility
│   ├── rerun_failed.py                 # Rerun failed predictions
│   ├── rerun_split_failed.py           # Rerun failed splits
│   ├── rerun_clean_output.py           # Rerun failed clean outputs
│   └── prompts/
│       ├── split_prompt.txt
│       ├── gt_extract_prompt.txt
│       └── gt_backfill_prompt.txt
│
├── baseline/                           # Single-agent baseline
│   ├── predict.py                      # 7-stage reasoning baseline
│   └── prompts/
│       └── predict_prompt.txt
│
├── evaluation/                         # Evaluation framework
│   ├── grader.py                       # Drug match grading (exact + Jaccard)
│   ├── error_detection.py              # Error detection rate vs doctor feedback
│   ├── trace_quality.py                # Reasoning trace quality metrics
│   ├── disagreement.py                 # Inter-agent disagreement analysis
│   └── ablation.py                     # Ablation runner (9 configs)
│
├── run_pipeline.py                     # Entry point: multi-agent pipeline
├── run_baseline.py                     # Entry point: single-agent baseline
├── run_ablation.py                     # Entry point: ablation study
└── run_evaluation.py                   # Entry point: evaluation suite
```

## Evaluation

| Metric | Description |
|--------|-------------|
| Exact match (top-3) | Does any of the 3 ranked options exactly match ground truth? |
| Jaccard similarity | Per-drug overlap between prediction and ground truth |
| Error detection rate | Does the responsible agent catch errors flagged by neurologists? |
| Disagreement-difficulty correlation | Do hard cases produce more inter-agent conflict? |
| Ablation delta | Per-agent contribution via leave-one-out experiments |

### Ablation Configurations

| Config | Description |
|--------|-------------|
| `full_system` | All 7 agents + debate |
| `no_debate` | All agents, no pharmacologist-epileptologist debate |
| `no_diagnostician` | Remove seizure diagnostician |
| `no_treatment_analyst` | Remove treatment response analyst |
| `no_pediatrician` | Remove pediatric specialist |
| `no_formulary` | Remove formulary specialist |
| `no_tropical_medicine` | Remove ID/tropical medicine specialist |
| `epileptologist_only` | Single epileptologist with no Phase 1 input |
| `single_agent_baseline` | Original 7-stage reasoning prompt |
