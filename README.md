# Consilium

A multi-agent LLM system for epilepsy drug prediction. Multiple specialist agents reason independently from different clinical lenses on the same patient, then their perspectives are synthesized through structured debate between the prescribing epileptologist and an adversarial pharmacologist.

**Target venue:** NeurIPS

**Core contribution:** Multi-perspective clinical reasoning — addresses anchoring bias in single-agent sequential reasoning. Grounded in 120 clinical reviews from two neurologists identifying 7 systematic failure categories that map to distinct medical specializations.

## Motivation

Single-agent LLM reasoning suffers from anchoring bias — a single model trying to simultaneously be a diagnostician, pharmacologist, pediatrician, and formulary expert performs poorly across all of them. Analysis of 120 clinical reviews from two neurologists identified 7 systematic failure categories that map to distinct medical specializations.

Consilium addresses this with **multi-perspective clinical reasoning**: 7 specialist agents, each focused on one domain, whose outputs are integrated by a prescribing epileptologist and stress-tested through adversarial pharmacologist review.

The LMIC (low- and middle-income country) setting is critical — Uganda changes prescribing fundamentally: drug availability, cost, infectious differentials (malaria vs epilepsy). Tension between clinical best practice and practical constraints surfaces failure modes invisible in standard benchmarks.

## Architecture

Eight agents execute in a 4-phase pipeline:


| Agent                 | Role                            | Phase | Description                                                                                                                             |
| --------------------- | ------------------------------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **Orchestrator**      | Gatekeeper                      | 0     | Reads the patient case and decides which Phase 1 agents to activate.                                                                    |
| **Diagnostician**     | Seizure Diagnostician           | 1     | Classifies seizure type and epilepsy syndrome from clinical semiology and EEG findings.                                                 |
| **Treatment Analyst** | Treatment Response Analyst      | 1     | Evaluates longitudinal medication response across visits. Assesses whether current drugs are working and whether changes are justified. |
| **Pediatrician**      | Pediatric Specialist            | 1     | Assesses developmental context, weight-based dosing, and age-specific drug safety.                                                      |
| **Tropical Medicine** | ID/Tropical Medicine Specialist | 1     | Evaluates infectious etiology (cerebral malaria, neurocysticercosis, HIV-related, meningitis). Flags ASM-antimicrobial interactions.    |
| **Formulary**         | Formulary Specialist            | 1     | Assesses drug availability, cost, and health system constraints in Uganda.                                                              |
| **Epileptologist**    | Prescribing Epileptologist      | 2     | Sees all Phase 1 outputs + full patient context. Synthesizes specialist input into a ranked 3-option regimen.                           |
| **Pharmacologist**    | Clinical Pharmacologist         | 3     | Adversarial reviewer. Critiques the epileptologist's regimen for drug interactions, contraindications, and dosing errors.               |


### Execution Flow

```
Patient Input
    |
    v
PHASE 0: Orchestrator
    +-- Decides which Phase 1 agents to activate
                |
                v
PHASE 1: Independent Parallel Assessment
    |-- Seizure Diagnostician        (syndrome classification, focal vs generalized)
    |-- Treatment Response Analyst   (is the current regimen working?)
    |-- Pediatric Specialist         (weight-based dosing, developmental context)
    |-- ID/Tropical Medicine         (infectious etiology differential)
    +-- Formulary Specialist         (drug availability, cost constraints)
                |
                v
PHASE 2: Informed Prescription
    +-- Prescribing Epileptologist    (sees patient + ALL Phase 1 outputs)
                |
                v
PHASE 3: Adversarial Review
    +-- Clinical Pharmacologist       (sees patient + Phase 1 + epileptologist's plan)
                |
    DEBATE: Structured Exchange       [only if concerns raised]
        Pharma critique → Epi revises → Pharma responds → Epi finalises
        (max rounds configurable, always ends on epileptologist)
                |
                v
FINAL REGIMEN: Last epileptologist output → 3 ranked options
```

### Design Principles

- Every agent sees the full patient history independently — no information hiding between Phase 1 agents.
- The pharmacologist advises but does not veto — the epileptologist always has final say.
- Debate is skipped entirely if the pharmacologist raises no concerns.
- Output is a ranked 3-option regimen.
- Ablation = same pipeline, disabled agents invisible to orchestrator.

## Data

- **HuggingFace dataset:** `[kartiksharma4/consilium](https://huggingface.co/datasets/kartiksharma4/consilium)` — 2,549 entries across 699 unique patients
- **Three cohorts:**
  - CSV cohort: 279 patients, 3 visits each (0, 6, 12 months)
  - CSV extraction cohort: 53 patients, 3–6 visits (additional visits surfaced from hidden columns)
  - PDF cohort: 367 patients, 1–10 visits (clinic PDFs converted to text)
- **Setting:** Ugandan epilepsy clinics (Mulago Hospital and affiliated sites)
- **10 tracked ASMs:** carbamazepine, clobazam, clonazepam, ethosuximide, lamotrigine, levetiracetam, phenobarbital, phenytoin, topiramate, valproate
- **Each entry:** `pid`, `visit_num`, `cohort`, `input` (cumulative clinical context), `output` (raw prescription), `prescribed` (ASM list), `stopped` (ASM list)

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
uv run python scripts/run_pipeline.py --visit 1 --limit 5

# Run single-agent baseline
uv run python scripts/run_baseline.py --visit 1 --limit 5

# Run baseline with different prompt
uv run python scripts/run_baseline.py --visit 1 --prompt all_agents_combined

# Evaluate predictions
uv run python scripts/evaluate.py --predictions outputs/predictions/consilium_*.json

# Run ablation study
uv run python scripts/run_ablation.py --visit 1 --limit 5
```

## Project Structure

```
consilium/
├── CLAUDE.md                           # Dev guidance
├── README.md                           # This file
├── pyproject.toml                      # Dependencies (managed with uv)
├── .env.example                        # AWS/Bedrock config template
│
├── agents/                             # 7 specialist agents + orchestrator
│   ├── base.py                         # BaseAgent ABC + response parsing
│   ├── registry.py                     # Agent registry (name → class)
│   ├── orchestrator.py                 # Phase 0: decides which agents activate
│   ├── diagnostician.py                # Seizure type / syndrome classification
│   ├── treatment_analyst.py            # Treatment response assessment
│   ├── pediatrician.py                 # Pediatric dosing + developmental context
│   ├── tropical_medicine.py            # Infectious etiology (conditional)
│   ├── formulary.py                    # Drug availability + cost
│   ├── epileptologist.py               # Prescribing (integrates Phase 1)
│   ├── pharmacologist.py               # Adversarial safety review
│   └── prompts/                        # System prompts for each agent
│
├── core/                               # Pipeline execution
│   ├── pipeline.py                     # 4-phase pipeline orchestration
│   ├── debate.py                       # Pharmacologist-epileptologist debate
│   └── regimen_parser.py               # Extract structured drug regimen from text
│
├── llm/                                # LLM client
│   └── client.py                       # Async Bedrock client (Converse API)
│
├── schemas/                            # Structured data types
│   ├── patient.py                      # PatientCase dataclass
│   └── output.py                       # Drug columns, allowed actions
│
├── scripts/                            # Entry points
│   ├── run_pipeline.py                 # Run multi-agent pipeline
│   ├── run_baseline.py                 # Run single-agent baseline
│   ├── run_ablation.py                 # Run ablation study (14 configs)
│   ├── evaluate.py                     # Grade predictions vs ground truth
│   └── loader.py                       # HuggingFace dataset loader
│
├── baseline/                           # Single-agent baseline
│   └── prompts/
│       ├── single_agent.txt            # Lean 7-stage reasoning prompt
│       └── all_agents_combined.txt     # Specialist lenses in single prompt
│
└── notes/                              # Research notes + docs
    ├── ARCHITECTURE.md                 # V1 architecture (historical)
    ├── ARCHITECTURE_V2.md              # Current architecture
    ├── DESIGN.md                       # Original design document
    ├── paper_notes.md                  # Paper discussion notes
    ├── RESULTS.md                      # Full results tables
    └── TODO.md                         # NeurIPS submission TODO
```

## Evaluation


| Metric              | Description                                                           |
| ------------------- | --------------------------------------------------------------------- |
| Exact match (top-3) | Does any of the 3 ranked options exactly match ground truth drug set? |
| Jaccard similarity  | Per-drug overlap between prediction and ground truth                  |
| Mono/poly breakdown | Separate accuracy for monotherapy (1 drug) vs polytherapy (2+ drugs)  |
| Ablation delta      | Per-agent contribution via leave-one-out and only-one experiments     |


### Ablation Configurations


| Config                   | Description                            |
| ------------------------ | -------------------------------------- |
| `full_pipeline`          | All agents + debate                    |
| `no_diagnostician`       | Remove seizure diagnostician           |
| `no_treatment_analyst`   | Remove treatment response analyst      |
| `no_pediatrician`        | Remove pediatric specialist            |
| `no_formulary`           | Remove formulary specialist            |
| `no_tropical_medicine`   | Remove ID/tropical medicine specialist |
| `only_diagnostician`     | Diagnostician only in Phase 1          |
| `only_treatment_analyst` | Treatment analyst only in Phase 1      |
| `only_pediatrician`      | Pediatrician only in Phase 1           |
| `only_formulary`         | Formulary only in Phase 1              |
| `only_tropical_medicine` | Tropical medicine only in Phase 1      |


