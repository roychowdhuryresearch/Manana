# Consilium: Multi-Agent Epilepsy Drug Prediction — Design Document

## Overview

A multi-agent LLM system that simulates a clinical team meeting to predict antiepileptic drug prescriptions for Ugandan epilepsy patients. Multiple specialist agents reason independently from different clinical lenses, then their perspectives are synthesized through structured debate and rule-based conflict resolution.

**Target venue:** NeurIPS

**Core contribution:** Multi-perspective clinical reasoning — addresses anchoring bias in single-agent sequential reasoning. Grounded in 120 clinical reviews from two neurologists identifying 7 systematic failure categories.

---

## Part 1: Data Pipeline (Pre-computed)

### Raw Data
- **Source:** `data/combined_dataset.csv` — 279 Ugandan epilepsy patients, semicolon-delimited, 3 visits each (0, 6, 12 months)

### Pipeline Steps
1. **Input/Output Split** (`pipeline/split_input_output.py` → `data/processed/split_results.json`): Splits clinical text into observations (input) vs prescription (output) per visit using LLM
2. **Clean Prescription** (`pipeline/build_clean_output.py` → `data/processed/clean_output.json`): Merges output_text + output_columns into single clean prescription per visit
3. **Ground Truth Extraction** (`pipeline/build_drug_gt.py` → `data/processed/drug_gt.json`): Extracts structured `{prescribed, stopped}` per visit
4. **Prediction Input** (`data/loader.py`): Deterministic construction — prior visits show notes + prescription, current visit shows notes only (no leakage)

---

## Part 2: Agent Architecture

### 7 Specialist Agents

| # | Agent | Phase | Role | Always/Conditional |
|---|-------|-------|------|--------------------|
| 1 | Seizure Diagnostician | 1 (parallel) | Syndrome classification, focal vs generalized, EEG | Always |
| 2 | Treatment Response Analyst | 1 (parallel) | Is current regimen working? Between-visit change detection | Always |
| 3 | Pediatric Specialist | 1 (parallel) | Weight-based dosing, developmental context, age safety | Always |
| 4 | ID/Tropical Medicine | 1 (parallel) | Infectious etiology differential, antimalarial interactions | Conditional |
| 5 | Formulary Specialist | 1 (parallel) | Drug availability, cost, setting constraints | Always |
| 6 | Prescribing Epileptologist | 2 (serial) | Treatment plan integrating Phase 1 inputs | Always |
| 7 | Clinical Pharmacologist | 3 (serial) | Adversarial safety review of prescription | Always |

### Why These Agents?

Analysis of 120 visit-level feedback entries from neurologists JP and Raj revealed systematic failures:

| Failure Pattern | Frequency | Agent That Addresses It |
|---|---|---|
| Seizure type/syndrome misclassification | Most common | Diagnostician |
| De-escalating working regimens | Most common | Treatment Analyst |
| Weight-based dosing errors in children | Common | Pediatrician |
| Drug-seizure type contraindications | Common | Pharmacologist |
| Missing infectious etiologies | Occasional | Tropical Medicine |
| Ignoring drug availability constraints | Occasional | Formulary |
| Drug-drug interactions | Common | Pharmacologist |

### Execution Flow

```
Patient Input
    │
    ▼
PHASE 1: Independent Parallel Assessment
    ├── Seizure Diagnostician
    ├── Treatment Response Analyst
    ├── Pediatric Specialist
    ├── ID/Tropical Medicine (conditional)
    └── Formulary Specialist
                │
    PHASE 1.5: Programmatic Conflict Detection
                │
                ▼
PHASE 2: Informed Prescription
    └── Prescribing Epileptologist
        (sees patient + ALL Phase 1 outputs + detected conflicts)
                │
                ▼
PHASE 3: Adversarial Review
    └── Clinical Pharmacologist
        (sees patient + Phase 1 + epileptologist's plan)
                │
    PHASE 3.5: Structured Debate (if concerns flagged)
        Pharmacologist concern → Epileptologist rebuttal → Pharmacologist verdict
        (max 2 rounds, unresolved = uncertainty markers)
                │
                ▼
PHASE 4: Rule-Based Synthesis
    - Apply safety vetoes (critical concerns → drug excluded)
    - Apply debate modifications
    - Apply availability preferences (soft)
    - Single LLM call for natural language formatting only
```

### Conflict Resolution Protocol

Resolution hierarchy (strongest to weakest):
1. **Safety veto** — critical pediatric safety or drug interaction → drug excluded, cannot be overridden
2. **Domain authority** — seizure type defers to diagnostician if confidence > 0.6
3. **Treatment continuity** — if treatment analyst says "responding well" with high confidence → epileptologist must justify any change
4. **Practical constraints** — availability/cost modifies options but doesn't veto clinical necessity
5. **Debate resolution** — for pharmacologist vs epileptologist disagreements

### Debate Mechanism

- Max 2 rounds (diminishing returns beyond)
- Pharmacologist presents structured concerns: {severity, category, affected_drugs, recommendation}
- Epileptologist rebuts: {accept/reject/modify, justification, modified_plan}
- Pharmacologist evaluates: {resolved/unresolved, rationale}
- Unresolved concerns → explicit uncertainty markers (valuable signal, not failure)

---

## Part 3: Output Schema

Each patient produces a `ReasoningTrace` containing:
- Which agents ran and why (activation reasons)
- Each agent's structured findings and concerns
- Detected conflicts and their resolutions
- Debate transcript (if triggered)
- 3 ranked drug options with full provenance
- Inter-agent agreement score

This trace IS the paper's deliverable.

---

## Part 4: Evaluation Framework

### Metrics

| Metric | What It Measures | Source |
|--------|-----------------|--------|
| Exact match (top-3) | Drug set accuracy | drug_gt.json |
| Partial match (Jaccard) | Per-drug accuracy | drug_gt.json |
| Error detection rate | Did the right agent catch known errors? | 7 error categories from feedback |
| Disagreement-difficulty correlation | Does conflict signal hard cases? | traces + grading |
| Ablation delta | Contribution of each agent | leave-one-out experiments |

### Ablation Configurations (9)

1. `full_system` — all 7 agents + debate
2. `no_debate` — all agents, no debate
3. `no_diagnostician` — remove seizure diagnostician
4. `no_treatment_analyst` — remove treatment response analyst
5. `no_pediatrician` — remove pediatrician
6. `no_formulary` — remove formulary specialist
7. `no_tropical_medicine` — remove ID specialist
8. `epileptologist_only` — single epileptologist with multi-agent-style prompt
9. `single_agent_baseline` — original 7-stage prompt

---

## Part 5: Clinical Context

- ~279 Ugandan epilepsy patients, 3 visits (0, 6, 12 months)
- Predominantly pediatric population
- Seizure differential broader than Western settings: epilepsy, cerebral malaria, NCC, HIV-related CNS
- Limited formulary — 10 tracked ASMs: carbamazepine, clobazam, clonazepam, ethosuximide, lamotrigine, levetiracetam, phenobarbital, phenytoin, topiramate, valproate
- Neurologist collaborators provide ground truth validation and feedback

---

## Part 6: Baseline Comparison

Single-agent baseline (existing): 66.4% exact match, 72% mono, 23% poly

The multi-agent system should improve:
- Poly-therapy accuracy (currently 23% — biggest gap)
- Error detection rate vs doctor feedback
- Reasoning trace quality (new metric)
