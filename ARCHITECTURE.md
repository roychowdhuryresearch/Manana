# Consilium: Multi-Agent Architecture

## Overview

Consilium is a multi-agent LLM system for epilepsy drug prediction. Seven specialist agents reason independently from different clinical perspectives on the same patient, then their outputs are synthesized through structured debate and rule-based conflict resolution.

The system processes one **patient-visit** at a time: given a patient's clinical history up to visit N, predict the drug prescription for visit N. Prior visit prescriptions are visible; the current visit's prescription is withheld.

---

## Input Construction (No LLM)

A `PatientCase` is built deterministically from pre-computed data files:

- **Demographics** — age, sex, seizure diagnosis, onset, duration (from `combined_dataset.csv`)
- **Clinical notes** — per-visit observations: HPI, exam findings, seizure history, EEG results (from `split_results.json`)
- **Prior prescriptions** — what was decided at earlier visits (from `clean_output.json`)
- **Medication history** — which drugs were prescribed or stopped at each prior visit (from `drug_gt.json`)

### Leak-Free Design

When predicting Visit N:

| Visit | Clinical Notes | Prescription |
|-------|---------------|-------------|
| Prior visits (1 to N-1) | Included | Included |
| Current visit (N) | Included | **Withheld** — this is what we predict |

The model never sees the answer it is trying to produce.

---

## Pipeline Execution

```
                          PATIENT INPUT
                               │
                               ▼
            ┌──────────────────────────────────────┐
            │     PHASE 1: Independent Parallel     │
            │          Assessment (5 agents)         │
            │                                        │
            │  ┌─────────────────────────────────┐  │
            │  │  Seizure Diagnostician           │  │
            │  │  Treatment Response Analyst      │  │
            │  │  Pediatric Specialist            │  │  5 LLM calls
            │  │  ID/Tropical Medicine *          │  │  (in parallel)
            │  │  Formulary Specialist            │  │
            │  └─────────────────────────────────┘  │
            │                                        │
            │  Each agent sees the full patient       │
            │  input independently — no agent         │
            │  sees another's output.                 │
            └───────────────────┬──────────────────┘
                                │
            ┌───────────────────▼──────────────────┐
            │  PHASE 1.5: Conflict Detection        │
            │  (Programmatic — no LLM)              │  0 LLM calls
            │                                        │
            │  Compare agent outputs, flag           │
            │  disagreements, compute safety vetoes  │
            └───────────────────┬──────────────────┘
                                │
            ┌───────────────────▼──────────────────┐
            │  PHASE 2: Informed Prescription       │
            │                                        │
            │  Prescribing Epileptologist sees:      │  1 LLM call
            │  • Full patient input                  │
            │  • All Phase 1 agent summaries         │
            │  • Detected conflicts                  │
            │                                        │
            │  Produces 3 ranked treatment options   │
            └───────────────────┬──────────────────┘
                                │
            ┌───────────────────▼──────────────────┐
            │  PHASE 3: Adversarial Review          │
            │                                        │
            │  Clinical Pharmacologist sees:         │  1 LLM call
            │  • Full patient input                  │
            │  • All Phase 1 summaries               │
            │  • Epileptologist's proposed plan       │
            │                                        │
            │  Flags safety concerns — does NOT       │
            │  rewrite the prescription              │
            └───────────────────┬──────────────────┘
                                │
                        ┌───────▼───────┐
                        │  Concerns?     │
                        └───┬───────┬───┘
                         No │       │ Yes
                            │       ▼
            ┌───────────────│───────────────────────┐
            │  PHASE 3.5:   │  Structured Debate    │
            │               │                        │
            │  Round 1:     │                        │
            │    Pharmacologist presents concerns    │  2-4 LLM calls
            │    Epileptologist rebuts each one      │  (max 2 rounds)
            │    Pharmacologist evaluates rebuttals  │
            │                                        │
            │  Round 2 (if unresolved concerns):     │
            │    Same cycle on remaining concerns    │
            │                                        │
            │  Unresolved concerns become explicit   │
            │  uncertainty markers (not failures)    │
            └───────────────┬───────────────────────┘
                            │
            ┌───────────────▼──────────────────────┐
            │  PHASE 4: Rule-Based Synthesis        │
            │                                        │
            │  Deterministic rules (no LLM):         │  0 LLM calls
            │  1. Apply safety vetoes                │  for decisions
            │  2. Apply debate modifications         │
            │  3. Apply availability preferences     │
            │                                        │
            │  Then 1 LLM call to format the         │  1 LLM call
            │  trace into readable output            │  for formatting
            └───────────────────┬──────────────────┘
                                │
                                ▼
                       FINAL OUTPUT
                  (3 ranked drug options +
                   full reasoning trace)
```

**Total: 8–12 LLM calls per patient-visit**

\* ID/Tropical Medicine is conditional — only activates when infection-related keywords (malaria, fever, HIV, NCC, etc.) appear in the clinical notes.

---

## Phase 1: Specialist Agents

Each agent receives the full patient input and returns a structured response containing findings, concerns, recommended drugs, and contraindicated drugs.

### Seizure Diagnostician

**Real-world analogue:** Diagnostic neurologist / neurophysiologist

**What it does:**
- Classifies seizure type: focal, generalized, combined, or unknown
- Identifies epilepsy syndromes: West syndrome, Lennox-Gastaut, Rolandic epilepsy, Dravet, Landau-Kleffner
- Assesses whether EEG findings and clinical semiology agree or disagree
- Reports confidence level in the classification

**Why it matters:** Seizure type misclassification was the #1 failure identified by reviewing neurologists. Getting the type wrong cascades into wrong drug selection — carbamazepine is first-line for focal seizures but contraindicated for generalized.

### Treatment Response Analyst

**Real-world analogue:** Longitudinal care physician

**What it does:**
- Evaluates whether the current drug regimen is controlling seizures
- Checks if doses have been optimized (at weight-based maximum? titrated appropriately?)
- Detects between-visit changes in seizure frequency
- Identifies drug-resistant epilepsy (failed 2+ optimized ASMs)

**Why it matters:** The #1 doctor complaint was the LLM de-escalating working regimens. If a patient is seizure-free on their current drugs, those drugs should be continued. This agent's explicit job is to protect working regimens from unnecessary changes.

### Pediatric Specialist

**Real-world analogue:** General pediatrician

**What it does:**
- Developmental assessment: cerebral palsy, global developmental delay, HIE, birth injury
- Weight-based dosing review: children gain weight every ~6 months, so doses drift subtherapeutic
- Age-specific drug safety: phenobarbital sedation in developing children, valproate hepatotoxicity in children under 2
- Formulation concerns: syrup vs tablet, caregiver ability to measure doses

**Why it matters:** Most patients in this dataset are children. A 2-year-old with spastic quadriplegia weighing 8kg has fundamentally different management needs than a 12-year-old with focal seizures.

### ID/Tropical Medicine Specialist (Conditional)

**Real-world analogue:** ID / tropical medicine physician

**What it does:**
- Differentiates epilepsy from infectious seizure causes: cerebral malaria, neurocysticercosis, HIV-related CNS disease
- Assesses whether acute infection is exacerbating seizure control
- Flags drug interactions between ASMs and antimalarials/antiretrovirals

**Why it matters:** In Uganda, the seizure differential is broader than in Western settings. New-onset seizures with fever could be cerebral malaria, not epilepsy — management is completely different.

**Activation rule:** Only runs when infection-related keywords appear in the clinical notes (malaria, fever, HIV, NCC, encephalitis, etc.).

### Formulary Specialist

**Real-world analogue:** Health systems / public health physician

**What it does:**
- Assesses clinical setting and resource level from context clues in the notes
- Flags drugs that may not be available or affordable
- Suggests formulary-appropriate alternatives
- Notes cost considerations

**Why it matters:** The best drug on paper is useless if it's not in stock. In Uganda, valproate and phenobarbital are reliably available on the national formulary; levetiracetam and lamotrigine have inconsistent supply.

---

## Phase 1.5: Conflict Detection

This is **programmatic — no LLM call**. The `conflict.py` module compares all Phase 1 outputs and flags disagreements:

| Conflict Type | Example | Resolution Rule |
|--------------|---------|-----------------|
| Seizure type vs treatment continuity | Diagnostician contraindicates a drug the Treatment Analyst recommends continuing | Diagnostician overrides if confidence > 0.6 |
| Pediatric safety | Pediatrician raises critical concern about a drug another agent recommends | Critical = safety veto (drug excluded). High = flagged for epileptologist. |
| Availability | Formulary flags a drug as unavailable that others recommend | Soft preference — epileptologist should prefer alternatives when clinically equivalent |
| Etiology | Tropical medicine suggests infectious cause, not epilepsy | Flagged for epileptologist to consider both management approaches |

### Conflict Resolution Hierarchy

Resolution follows a fixed priority order (strongest to weakest):

1. **Safety veto** — Critical pediatric safety concern or drug interaction → drug excluded, cannot be overridden
2. **Domain authority** — Seizure type classification defers to the Diagnostician if confidence > 0.6
3. **Treatment continuity** — If Treatment Analyst says "responding well" with high confidence, the Epileptologist must justify any change
4. **Practical constraints** — Availability/cost modifies options but doesn't veto clinical necessity
5. **Debate resolution** — For disagreements not resolved by the rules above

---

## Phase 2: Informed Prescription

The **Prescribing Epileptologist** is the attending physician. It receives:
- The full patient input
- All Phase 1 agent summaries (findings, concerns, recommendations)
- Detected conflicts with their resolution rules

It must:
- Integrate all specialist inputs, stating how each influenced the plan
- Address each detected conflict explicitly
- Reason through the medication history: for each prior drug, decide continue/stop/no action
- Justify any change to a working regimen
- Produce **3 ranked treatment options**, each a complete regimen

### Output Format

Each option lists every relevant drug with an action:
```
Option 1: Monotherapy - valproate
- valproate: continue
- phenobarbital: stop
- carbamazepine: stop
Rationale: Patient responding well on VPA; simplify to monotherapy.
```

---

## Phase 3: Adversarial Review

The **Clinical Pharmacologist** reviews the epileptologist's plan. It receives everything the epileptologist saw, plus the proposed prescription.

It checks for:
- Drug-drug interactions (e.g., never mix phenobarbital and clobazam)
- Drug-seizure type contraindications (e.g., carbamazepine worsening myoclonic seizures)
- Weight-based dosing accuracy
- Formulation issues (e.g., syrup-to-mg conversions)
- Special population safety (pregnancy, hepatic impairment)

Each concern is classified by severity:
- **Critical** — Dangerous combination/dose, should not proceed
- **High** — Strong recommendation to modify
- **Medium** — Worth noting, may be acceptable with monitoring
- **Low** — Informational only

**Key design principle:** The pharmacologist is an **advisor, not a gatekeeper**. It reports flags for the synthesis layer to weigh — it does not rewrite the prescription or veto the epileptologist.

---

## Phase 3.5: Structured Debate

Triggers only if the pharmacologist raised concerns. Maximum 2 rounds (diminishing returns beyond that).

### Round Structure

1. **Pharmacologist presents** structured concerns: severity, category, affected drugs, recommendation
2. **Epileptologist rebuts** each concern with one of:
   - **Accept** — agrees and modifies the plan
   - **Reject** — disagrees with clinical justification
   - **Modify** — partially accepts, proposes alternative approach
3. **Pharmacologist evaluates** each rebuttal: resolved or unresolved

### Handling Unresolved Concerns

Concerns that remain unresolved after 2 rounds are **not failures** — they become explicit **uncertainty markers** attached to the final recommendation. This is valuable signal: it tells the reader "the specialists disagreed on this point and here's why."

---

## Phase 4: Rule-Based Synthesis

Clinical decisions are made **deterministically by rules, not by another LLM**:

1. **Safety vetoes** — Any drug with a critical-severity concern is removed from all options. This cannot be overridden.
2. **Debate modifications** — Accepted changes from the debate are applied to the options.
3. **Availability preferences** — Formulary concerns are noted but do not override clinical necessity.

After rules are applied, a **single LLM call** formats the complete reasoning trace into readable natural language. This formatting call makes no clinical decisions — all decisions are already final.

---

## Output

Each patient-visit produces two outputs:

### FinalRecommendation

Three ranked drug options with full provenance:
```
Option 1: valproate:continue, phenobarbital:stop
Option 2: valproate:continue, levetiracetam:start, phenobarbital:stop
Option 3: carbamazepine:start, phenobarbital:stop
```

Each option includes rationale, confidence score, and uncertainty markers (if any).

### ReasoningTrace

The complete audit trail:
- Which agents were activated and why
- Each agent's structured findings and concerns
- Detected conflicts and how they were resolved
- Debate transcript (if triggered)
- Safety vetoes applied
- Inter-agent agreement score

This trace is the paper's core deliverable — it shows multi-perspective clinical reasoning in action and can be audited by a neurologist.

---

## Comparison with Single-Agent Baseline

The single-agent baseline uses the same input but sends it to a single LLM with a 7-stage reasoning prompt (seizure type → safety → practicality → side effects → medication history → monotherapy preference → output).

| Property | Single-Agent | Multi-Agent (Consilium) |
|----------|-------------|------------------------|
| LLM calls per case | 1 | 8–12 |
| Reasoning | Sequential (one prompt) | Parallel specialists + serial integration |
| Conflict handling | Implicit (model weighs everything internally) | Explicit detection, resolution hierarchy, debate |
| Treatment continuity | Bias toward suggesting changes | Dedicated agent protecting working regimens |
| Auditability | Single reasoning block | Per-agent traces with provenance |
| Failure mode | Anchoring on first interpretation | Diagnostician can override if confident (but can also be wrong) |

### Early Results (5 patients × 3 visits, top-1 exact match)

| Metric | Baseline | Multi-Agent |
|--------|----------|-------------|
| Overall exact match | 5/15 (33%) | 9/15 (60%) |
| Monotherapy cases | 5/10 (50%) | 7/10 (70%) |
| Polytherapy cases | 0/5 (0%) | 2/5 (40%) |
| Mean Jaccard | 0.467 | 0.700 |

---

## Drug Formulary

The system predicts from a fixed set of 10 anti-seizure medications tracked in the dataset:

| Drug | Abbreviation | Spectrum |
|------|-------------|----------|
| Carbamazepine | CBZ | Narrow (focal) |
| Clobazam | CLB | Broad (adjunct) |
| Clonazepam | CZP | Broad (adjunct) |
| Ethosuximide | ESM | Narrow (absence) |
| Lamotrigine | LTG | Broad |
| Levetiracetam | LEV | Broad |
| Phenobarbital | PB | Broad (sedating) |
| Phenytoin | PHT | Narrow (focal) |
| Topiramate | TPM | Broad |
| Valproate | VPA | Broad |

Each drug in a recommendation has an action: **continue** (keep from prior visit), **start** (new addition), or **stop** (discontinue).
