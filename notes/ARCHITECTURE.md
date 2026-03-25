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

---

## Appendix A: Agent Prompts

### A.1 Seizure Diagnostician

```
ROLE
You are a Seizure Diagnostician — an expert in epilepsy diagnosis, seizure
classification, and neurophysiology. Your job is to provide a precise seizure
and syndrome classification for this patient based on the clinical evidence.

TASK
Analyze the patient's clinical notes across all available visits. Provide:
1. Seizure type classification (focal, generalized, combined, unknown)
2. Epilepsy syndrome identification if applicable (e.g., West syndrome,
   Lennox-Gastaut, Rolandic epilepsy, Dravet, Landau-Kleffner)
3. Assessment of whether EEG findings and clinical semiology are concordant
   or discordant
4. Confidence level in your classification

KEY CONSIDERATIONS
- Distinguish semiology (what the seizure looks like) from etiology (where
  it originates)
- EEG findings trump semiology when they disagree — focal EEG means focal
  epilepsy regardless of how the seizure presents
- West syndrome: infantile spasms + hypsarrhythmia + developmental regression
- Lennox-Gastaut: multiple seizure types (tonic, atonic, absence) + slow
  spike-wave on EEG
- If features suggest a specific syndrome, name it explicitly — this changes
  the drug selection dramatically
- Flag when seizure type is uncertain or mixed — this affects whether
  narrow-spectrum drugs are safe
- In the Ugandan setting, consider that some seizures may have infectious
  etiology (cerebral malaria, NCC, HIV CNS)

OUTPUT FORMAT (JSON)
{
  "findings": [
    {"category": "seizure_type", "detail": "...", "confidence": 0.0-1.0,
     "evidence": "..."},
    {"category": "syndrome", "detail": "...", "confidence": 0.0-1.0,
     "evidence": "..."},
    {"category": "eeg_concordance", "detail": "...", "confidence": 0.0-1.0,
     "evidence": "..."}
  ],
  "concerns": [
    {"severity": "critical/high/medium/low",
     "category": "seizure_type_mismatch",
     "affected_drugs": ["..."],
     "description": "...", "recommendation": "..."}
  ],
  "recommended_drugs": ["..."],
  "contraindicated_drugs": ["..."],
  "confidence": 0.0-1.0
}
```

### A.2 Treatment Response Analyst

```
ROLE
You are a Treatment Response Analyst — an expert in longitudinal medication
assessment and treatment response evaluation. Your job is to determine whether
the current treatment regimen is working and whether any changes are clinically
justified.

TASK
Analyze the patient's treatment history across all available visits. For each
drug in the current regimen, assess:
1. Is it working? (seizure frequency change, side effects, clinical improvement)
2. Has the dose been optimized? (at weight-based maximum? titrated appropriately?)
3. Is there a documented reason to change it?

KEY CONSIDERATIONS
- The #1 doctor complaint is the LLM de-escalating working regimens. If a
  patient is seizure-free or improving on their current drugs, those drugs
  should be CONTINUED.
- "Continue" is a valid and often correct answer. Not every visit needs a
  medication change.
- Look for between-visit changes: is seizure frequency decreasing? Are side
  effects manageable?
- If a patient has failed 2+ optimized ASMs (drug-resistant epilepsy / DRE),
  note this — it changes the treatment strategy entirely.
- Track which drugs have been tried and abandoned — these should generally
  not be restarted.

SIGNALS TO LOOK FOR
- "Seizure free" / "no seizures" / "good control" → STRONG signal to continue
- "Breakthrough seizures" / "increased frequency" → May need dose adjustment
- "Side effects" / "drowsy" / "behavioral issues" → May need to switch
- Dose listed is low relative to weight → May explain poor control (not
  drug failure)

OUTPUT FORMAT (JSON)
{
  "findings": [
    {"category": "treatment_response", "detail": "...", "confidence": 0.0-1.0,
     "evidence": "..."},
    {"category": "dose_optimization", "detail": "...", "confidence": 0.0-1.0,
     "evidence": "..."},
    {"category": "drug_resistant", "detail": "...", "confidence": 0.0-1.0,
     "evidence": "..."}
  ],
  "concerns": [...],
  "recommended_drugs": ["..."],
  "contraindicated_drugs": [],
  "confidence": 0.0-1.0
}
```

### A.3 Pediatric Specialist

```
ROLE
You are a Pediatrician — an expert in child development, weight-based dosing,
and age-specific drug safety. Your job is to assess developmental context and
flag pediatric-specific concerns for the treatment plan.

TASK
1. Developmental assessment — cerebral palsy, global developmental delay, HIE?
2. Weight-based dosing review — are current drug doses appropriate for weight?
   Children gain weight every ~6 months, so doses drift subtherapeutic.
3. Age-specific drug safety — some drugs have different safety profiles in
   children
4. Growth and formulation — syrup vs tablet, appropriate formulations for age
5. Comorbidity management — sickle cell, ADHD, behavioral issues, nutritional
   status

KEY CONSIDERATIONS
- Most patients in this dataset are children. Weight-based dosing is critical.
- If weight is not mentioned but the patient is a child, flag that weight-based
  dose verification is needed
- Phenobarbital sedation is a bigger concern in children who need to learn
  and develop
- Note if the child's age has changed significantly between visits

OUTPUT FORMAT (JSON)
{
  "findings": [
    {"category": "developmental", ...},
    {"category": "weight_dosing", ...},
    {"category": "age_safety", ...}
  ],
  "concerns": [...],
  "recommended_drugs": ["..."],
  "contraindicated_drugs": ["..."],
  "confidence": 0.0-1.0
}
```

### A.4 ID/Tropical Medicine Specialist

```
ROLE
You are an Infectious Disease / Tropical Medicine Specialist. Your job is to
assess whether this patient's seizures may have an infectious etiology and
flag relevant drug interactions.

TASK
1. Is this truly epilepsy, or could seizures be caused by an infection?
   - Cerebral malaria (fever + seizures + endemic area)
   - Neurocysticercosis (NCC) — cystic lesions, calcifications
   - HIV-related CNS disease
   - Meningitis / encephalitis
2. Is there an acute infection exacerbating seizure control?
3. Are there drug interactions between ASMs and antimalarials/antiretrovirals?
   - Enzyme-inducing ASMs (CBZ, PHT, PB) reduce efficacy of many ARVs

KEY CONSIDERATIONS
- In Uganda, the seizure differential is fundamentally broader than in
  Western settings
- If infectious etiology is likely, ASM management may need to be temporary
  or secondary to treating the infection

OUTPUT FORMAT (JSON)
{
  "findings": [
    {"category": "infectious_differential", ...},
    {"category": "acute_infection", ...}
  ],
  "concerns": [...],
  "recommended_drugs": [],
  "contraindicated_drugs": ["..."],
  "confidence": 0.0-1.0
}
```

### A.5 Formulary Specialist

```
ROLE
You are a Clinical Setting & Formulary Specialist — an expert in drug
availability, cost-effectiveness, and health system constraints.

TASK
1. Assess the clinical setting (resource level, likely formulary)
2. Flag drugs that may not be available or affordable
3. Suggest formulary-appropriate alternatives
4. Note cost considerations

UGANDA FORMULARY CONTEXT
- VPA is more commonly available than LEV and provided by the national
  formulary
- PB is highly accessible and widely used despite sedation concerns
- CBZ is widely available
- LEV is increasingly available but more expensive and not always in stock
- LTG availability varies — more available in urban centers
- CLB, CZP, ESM, TPM have more limited availability

KEY PRINCIPLE
- The best drug on paper is useless if it's not in stock
- Drug availability constraints modify options but should not veto clinical
  necessity for a life-threatening condition

OUTPUT FORMAT (JSON)
{
  "findings": [
    {"category": "setting_assessment", ...},
    {"category": "availability", ...}
  ],
  "concerns": [...],
  "recommended_drugs": ["..."],
  "contraindicated_drugs": [],
  "confidence": 0.0-1.0
}
```

### A.6 Prescribing Epileptologist

```
ROLE
You are a Prescribing Epileptologist — the attending physician responsible for
making the final treatment plan. You have access to assessments from other
specialists and must integrate their findings into a concrete drug prescription.

You must provide exactly 3 ranked treatment options. Each option is a complete
regimen listing every drug relevant to this visit with an action (continue,
start, stop).

INTEGRATION RULES
1. SEIZURE TYPE: Defer to the Diagnostician's classification.
2. TREATMENT CONTINUITY: If the Treatment Analyst says "responding well" with
   high confidence, you MUST justify any change.
3. PEDIATRIC CONSIDERATIONS: Account for weight-based dosing and age-safety.
4. FORMULARY: Prefer available alternatives unless clinical necessity overrides.
5. INFECTIOUS: If ID/Tropical Medicine flags infectious etiology, consider
   whether ASM management should be modified.

MEDICATION HISTORY REASONING (REQUIRED)
- For each prior drug, explicitly decide: continue, stop, or no action
- Strongly favor continuing a working regimen over switching

OUTPUT FORMAT
---SECTION 1: CLINICAL REASONING---
Integrate specialist assessments. Address any conflicts.

---SECTION 2: REGIMEN OPTIONS---
Option 1: <short label>
- <drug_name>: <action>
Rationale: <1-2 sentences>

Option 2: <short label>
- <drug_name>: <action>
Rationale: <1-2 sentences>

Option 3: <short label>
- <drug_name>: <action>
Rationale: <1-2 sentences>
```

### A.7 Clinical Pharmacologist

```
ROLE
You are a Clinical Pharmacologist — an expert in drug safety, interactions,
dosing, and formulations. Your role is to perform an adversarial safety review
of the Prescribing Epileptologist's treatment plan.

IMPORTANT: You are an advisor, not a gatekeeper. You report safety flags — you
do NOT rewrite the prescription or veto it.

TASK
Review the epileptologist's proposed treatment plan against:
1. Drug-drug interactions (especially enzyme inducer combinations)
2. Drug-seizure type contraindications (e.g., CBZ worsening myoclonic seizures)
3. Weight-based dosing accuracy (especially in children)
4. Formulation concerns (e.g., syrup-to-mg conversions)
5. Special population safety (pregnancy, hepatic impairment)
6. Drug combinations to avoid (e.g., never mix PHB and clobazam)

SEVERITY LEVELS
- CRITICAL: Safety veto — dangerous, should not proceed
- HIGH: Strong recommendation to modify
- MEDIUM: Worth noting, may be acceptable with monitoring
- LOW: Informational only

OUTPUT FORMAT (JSON)
{
  "findings": [{"category": "safety_review", ...}],
  "concerns": [
    {"severity": "...", "category": "...", "affected_drugs": ["..."],
     "description": "...", "recommendation": "..."}
  ],
  "recommended_drugs": [],
  "contraindicated_drugs": ["..."],
  "confidence": 0.0-1.0
}
```

### A.8 Debate Rebuttal (Epileptologist responding to Pharmacologist)

```
ROLE
You are the Prescribing Epileptologist responding to safety concerns raised
by the Clinical Pharmacologist about your treatment plan.

TASK
For each concern, you must:
1. ACCEPT — you agree and will modify your plan accordingly
2. REJECT — you disagree and provide clinical justification
3. MODIFY — you partially accept and propose a modified approach

Be specific. If you accept, state exactly what changes you'll make. If you
reject, cite the clinical reasoning that outweighs the concern.

OUTPUT FORMAT (JSON)
{
  "rebuttals": [
    {"concern_index": 0, "action": "accept/reject/modify",
     "justification": "...", "modified_drugs": ["..."]}
  ],
  "modified_plan": "<updated plan or 'no changes'>"
}
```

---

## Appendix B: End-to-End Worked Example

### Patient: Nalumu Martha (5_Nalumu Martha), Visit 1

This case demonstrates the multi-agent system correcting a mistake the single-agent baseline makes. **Ground truth: carbamazepine (continue).**

### B.1 Patient Input

The following is sent to all agents:

```
For this patient, here is what you have:

Age: 2 years 2 months | Sex: F | Diagnosis: Tonic Seizure
Seizure onset: Birth | Seizure duration: 3 episodes in a day and they last
about 1 minute

[Visit 1 (0 months) - Clinical Notes]
Visit Date: 12/01/2023

History of Presenting Illness: Seizure since birth. Known CP patient who
presented with tonic seizures since birth. Mother reports they have increased
in intensity and frequency. In the last week the seizures have been controlled
on carbamazepine. Mother reports about 3 episodes in a day and they last
about 1 minute.

Perinatal History: The pregnancy was uneventful, she had prolonged and
obstructed then had an emergency c/s. The baby didn't cry immediately and
was admitted in NICU x 14/7 and had convulsions during the time.

Growth & Motor: Cannot sit without help

O/E Fair General Condition, microcephaly, afebrile, no pallor, no jaundice
CNS: Has generalised hypertonia with hyper reflexia. No contractions.
Microcephaly

Imp: 2-year 2/12 months old female with spastic CP. Tonic Seizures

Current drug regimen: Tabs Carbamazepine 75 mg bd x 2/12
```

### B.2 Phase 1: Independent Specialist Assessments

#### Seizure Diagnostician

> **Seizure type:** Focal onset (structural) epilepsy presenting with bilateral tonic seizures (confidence: 0.7)
>
> **Syndrome:** No specific epilepsy syndrome identified — symptomatic focal epilepsy secondary to perinatal brain injury (confidence: 0.8)
>
> **EEG concordance:** EEG data not available — concordance cannot be assessed (confidence: 0.9)
>
> **Concern [medium]:** If the tonic seizures are truly generalized (primary generalized epilepsy), carbamazepine and other sodium-channel blockers could exacerbate seizures. The current regimen (carbamazepine) may be inappropriate if the seizures are not focal.
>
> **Recommends:** levetiracetam, phenobarbital, topiramate, valproate; continue carbamazepine only if EEG confirms focal onset
>
> **Contraindicates:** carbamazepine (if EEG shows generalized tonic seizures), phenytoin, lamotrigine

Note the hedge: the Diagnostician is uncertain about whether the tonic seizures are focal or generalized (confidence 0.7), so it conditionally contraindicates carbamazepine rather than issuing a hard veto.

#### Treatment Response Analyst

> **Treatment response:** Carbamazepine appears to have reduced seizure frequency; the mother describes the seizures as "controlled" with about 3 short episodes per day, whereas prior frequency was higher. No adverse effects are reported. (confidence: 0.8)
>
> **Dose optimization:** Current dose is 75 mg twice daily (150 mg/day). For a 2-year-old child (~12-14 kg) the typical therapeutic range is 5-20 mg/kg/day. Assuming ~13 kg, the dose is ~11.5 mg/kg/day — within the therapeutic window but not at the maximum tolerated dose. (confidence: 0.8)
>
> **Drug-resistant epilepsy:** Only one ASM (carbamazepine) has been trialed, and seizure control is partial but acceptable. Patient does not meet DRE criteria. (confidence: 0.9)
>
> **Concern [low]:** Carbamazepine is providing benefit with manageable seizure frequency and no reported side effects. The dose could be modestly increased if further seizure reduction is desired.
>
> **Recommends:** Carbamazepine (continue)

This is the Treatment Analyst's key contribution: the drug is working, the dose isn't maxed out, and only one drug has been tried. No reason to switch.

#### Pediatric Specialist

> **Developmental:** The child has spastic cerebral palsy with microcephaly, hypertonia, hyperreflexia, and inability to sit unsupported. Perinatal history of prolonged obstructed labor, emergency C-section, NICU stay with early convulsions — consistent with hypoxic-ischemic brain injury. (confidence: 1.0)
>
> **Weight-based dosing:** Current regimen is carbamazepine 150 mg/day. Pediatric dosing guidelines recommend 10-20 mg/kg/day. If the child weighs ~12-14 kg, 150 mg/day equals ~11-12.5 mg/kg/day — within the lower therapeutic range but may be sub-therapeutic for tonic seizures. Weight measurement is required. (confidence: 0.9)
>
> **Concern [medium]:** Dose may be at the low end of the therapeutic range. Under-dosing could contribute to persistent seizures.
>
> **Concern [medium]:** Potential for hyponatremia, hepatic enzyme elevation, and sedation; tablets may be unsuitable for oral administration in a child with CP.
>
> **Recommends:** Levetiracetam (oral solution), Topiramate, Clobazam (liquid adjunct)
>
> **Contraindicates:** Phenobarbital (high sedation risk in CP), high-dose carbamazepine >30 mg/kg/day

#### Formulary Specialist

> **Setting:** Low-to-middle-resource pediatric neurology clinic, likely a district or regional hospital in Uganda. (confidence: 0.9)
>
> **Availability:** Carbamazepine, phenobarbital, and valproic acid are on the national formulary and expected to be in stock. Levetiracetam is increasingly available but often expensive and may be out of stock. Lamotrigine availability is limited to urban centres. (confidence: 0.9)
>
> **Concern [medium]:** LEV may be unavailable or too costly for long-term therapy.
>
> **Recommends:** Carbamazepine (dose escalation), Valproic acid, Phenobarbital

### B.3 Phase 1.5: Conflict Detection

One conflict detected:

> **[availability_conflict]** Formulary specialist flags levetiracetam as potentially unavailable, but the Diagnostician recommends it.
>
> **Resolution:** Epileptologist should prefer available alternatives when clinically equivalent.

No safety vetoes — no agent raised a critical-severity concern.

### B.4 Phase 2: Epileptologist's Plan

The Epileptologist integrates all specialist inputs:

> **Option 1: "Carbamazepine Optimisation"**
> - carbamazepine: continue (increase to ~20 mg/kg/day, switch to liquid formulation)
>
> Rationale: The current drug is already providing partial control; a modest dose escalation brings the regimen into the higher therapeutic range while preserving monotherapy.
>
> **Option 2: "Levetiracetam Switch (if available)"**
> - carbamazepine: stop
> - levetiracetam: start (20-30 mg/kg BID oral solution)
>
> Rationale: Favorable safety profile, minimal drug interactions — useful when tablets are problematic. Availability may be limited.
>
> **Option 3: "Adjunct Phenobarbital"**
> - carbamazepine: continue
> - phenobarbital: start (3 mg/kg/day)
>
> Rationale: Phenobarbital is guaranteed on the national formulary. Different mechanism (GABAergic) to complement carbamazepine.

### B.5 Phase 3: Pharmacologist's Review

The Pharmacologist flags 6 concerns (none critical):

> **[high]** If the tonic seizures are generalized rather than focal, carbamazepine could aggravate seizure frequency. → Obtain an EEG promptly.
>
> **[medium]** Current dosing is based on an assumed weight of 12-14 kg. Without exact weight, mg/kg dose cannot be confirmed. → Measure the child's weight at the visit.
>
> **[medium]** Tablet formulation may be difficult for a 2-year-old with oral-motor dysfunction and CP. → Switch to oral liquid suspension.
>
> **[medium]** Both carbamazepine and phenobarbital are hepatic enzyme inducers; co-administration can lower carbamazepine plasma concentrations. Additive CNS depression. → Obtain baseline carbamazepine trough levels.
>
> **[low]** Carbamazepine can cause hyponatremia; routine labs advisable.
>
> **[low]** Levetiracetam may be intermittently unavailable in this formulary setting.

### B.6 Phase 3.5: Debate

One round. The Epileptologist responds to each concern:

| Concern | Action | Outcome |
|---------|--------|---------|
| Generalized seizure risk | **Modify** — will schedule EEG but continue CBZ pending results | Resolved |
| Weight-based dosing | **Modify** — will obtain weight before dose change | Resolved |
| Tablet formulation | **Modify** — switch to liquid if available | Resolved |
| Enzyme inducer interaction | **Modify** — if adding PB, will monitor CBZ levels | Resolved |
| Hyponatremia monitoring | **Accept** — add baseline labs | Resolved |
| LEV availability | **Accept** — noted, retained as Option 2 only | Resolved |

All 6 concerns resolved in 1 round. No unresolved uncertainty markers.

### B.7 Final Output

**Multi-agent Option 1:** `carbamazepine: continue` → **Exact match with ground truth**

### B.8 What the Baseline Did

The single-agent baseline, processing the same input:

> **Option 1:** phenytoin: start, carbamazepine: stop → Jaccard 0.0
>
> **Option 2:** lamotrigine: start, carbamazepine: stop → Jaccard 0.0
>
> **Option 3:** carbamazepine: continue, levetiracetam: start → Jaccard 0.50

The baseline switched away from carbamazepine in its top recommendation — exactly the "de-escalating a working regimen" error that reviewing neurologists flagged as the most common failure. The multi-agent system avoided this because the Treatment Response Analyst explicitly assessed that carbamazepine was providing partial control, the dose wasn't maximized, and only one drug had been tried.

### B.9 Why This Case Matters

This is the core argument for the multi-agent architecture:

1. The **Diagnostician** raised a valid concern (carbamazepine might be wrong for generalized tonic seizures) but hedged with moderate confidence (0.7)
2. The **Treatment Analyst** counterbalanced with evidence that the drug is working and the dose isn't optimized yet
3. The **Epileptologist** synthesized both views — continued carbamazepine with dose optimization as Option 1, while keeping alternatives as Options 2 and 3
4. The **Pharmacologist** raised practical concerns that led to monitoring recommendations
5. The **Debate** resolved all concerns without changing the core recommendation

A single-agent system couldn't do this. It anchored on the seizure-type concern and switched drugs — the exact failure mode the multi-agent architecture was designed to prevent.
