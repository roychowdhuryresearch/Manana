# Consilium V2 — Architecture

## Design Principles

1. **LLMs do reasoning, code does routing/bookkeeping/measurement.** No programmatic layer pretends to be clinical intelligence. Code decides which agents run and collects their outputs. LLMs do the thinking.
2. **Free text between agents.** Agents communicate in natural language. No structured parsing between phases. LLMs talking to LLMs should use text.
3. **Debate is central.** Not optional, not theater. The epileptologist must revise its plan in response to adversarial critique. The revised plan IS the final answer.
4. **No programmatic vetoes.** No rule-based overrides, no safety gates, no enforcement layers. The epileptologist has full clinical authority after seeing all specialist inputs and surviving debate.
5. **Minimal architecture.** No extra LLM calls for formatting, summarizing, or validating. Every call is either reasoning or critiquing.
6. **Structure only for measurement.** Structured footers exist for evaluation and analysis only — never fed back into any agent's reasoning or used for pipeline control.

---

## The 10-Drug Universe

All agents reason about exactly these 10 ASMs:

```
carbamazepine | clobazam | clonazepam | ethosuximide | lamotrigine
levetiracetam | phenobarbital | phenytoin | topiramate | valproate
```

Actions: `start`, `continue`, `stop`

The canonical drug list lives in a shared config. Individual agent prompts reference it but do not need to repeat it exhaustively every time.

---

## Pipeline Flow

```
Patient Data (PatientCase)
        │
        ▼
┌─── ORCHESTRATOR (routing only) ─────────────────┐
│                                                  │
│  Sees the case. Decides which agents to          │
│  activate. Records activation reasons.           │
│  Then gets out of the way.                       │
│                                                  │
│  Currently: hardcoded switches                   │
│  (tropical_medicine conditional on keywords,     │
│   all others always active).                     │
│  Future: extensible routing logic here.          │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌─── PHASE 1: Independent Parallel Assessment ───┐
│                                                  │
│  Diagnostician ──┐                               │
│  Treatment Analyst ──┤  All run in parallel.     │
│  Pediatrician ──┤     Each sees ONLY patient     │
│  Tropical Medicine* ──┤  data. No visibility     │
│  Formulary ──┘        into other agents.         │
│                                                  │
│  Output: free text reasoning (+ optional         │
│          structured footer for measurement)      │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌─── PHASE 2: Epileptologist ─────────────────────┐
│                                                  │
│  Sees: patient data                              │
│      + all Phase 1 free text outputs             │
│                                                  │
│  Produces: clinical reasoning (free text)        │
│          + 3 ranked regimen options              │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌─── PHASE 3: Pharmacologist (Adversarial) ───────┐
│                                                  │
│  Sees: patient data                              │
│      + all Phase 1 free text outputs             │
│      + epileptologist's full output              │
│                                                  │
│  Produces: critique (free text)                  │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌─── PHASE 3.5: Debate (Mandatory, N rounds) ─────┐
│                                                   │
│  Each round:                                      │
│                                                   │
│  1. Epileptologist revision                       │
│     Sees: patient data                            │
│         + all Phase 1 outputs                     │
│         + its CURRENT plan (not old versions)     │
│         + LATEST pharmacologist critique          │
│     Produces: revised 3 options + reasoning       │
│                                                   │
│  2. Pharmacologist follow-up                      │
│     Sees: patient data                            │
│         + all Phase 1 outputs                     │
│         + revised plan                            │
│     Produces: remaining concerns                  │
│             OR "no further concerns" → end        │
│                                                   │
│  Context rule: do NOT accumulate old rounds.      │
│  Each round carries only patient + Phase 1        │
│  + current plan + latest critique.                │
│  Old rounds are superseded.                       │
│                                                   │
│  Ends when: no concerns OR max rounds reached.    │
└──────────────────────┬────────────────────────────┘
                       │
                       ▼
┌─── OUTPUT ──────────────────────────────────────┐
│                                                  │
│  Final answer = epileptologist's last output.     │
│                                                  │
│  No orchestrator at the end.                     │
│  No post-processing. No formatting call.         │
│  The last epileptologist output IS the product.  │
└──────────────────────────────────────────────────┘
```

*Tropical Medicine is conditional — activates only when infection keywords detected in clinical notes.

---

## Phase 1 Agents

Each agent receives identical input: `patient.build_input_text()` — demographics, clinical notes across visits, prior visit prescriptions (current visit prescription withheld).

Each agent outputs free text reasoning — findings, concerns, recommendations in natural language. Optionally, a structured footer for measurement purposes (parsed only for analysis, never for pipeline control).

### Agent Roles

| Agent | Focus | Key Question |
|-------|-------|-------------|
| **Diagnostician** | Seizure type, syndrome classification, EEG concordance | What kind of epilepsy is this? |
| **Treatment Analyst** | Longitudinal medication assessment, treatment response | Is the current regimen working? |
| **Pediatrician** | Developmental context, weight-based dosing, age safety | Is this safe for this child's body? |
| **Tropical Medicine*** | Infectious differential, ASM-antimicrobial interactions | Are these seizures from an infection, not epilepsy? |
| **Formulary** | Drug availability, cost, setting constraints | Can the patient actually get these drugs? |

---

## Phase 2: Epileptologist

Integrates all specialist perspectives into a treatment plan.

**Input:**
- Patient data
- Full free text output from each Phase 1 agent

**Output:**
- Clinical reasoning addressing each specialist's input
- Exactly 3 ranked regimen options, each listing drugs with actions (start/continue/stop)

**Prompt guidance:**
- Address disagreements between specialists explicitly
- Justify any departure from treatment analyst's continuity recommendation
- List every drug relevant to this visit with an action in each option

**Required output format:** The epileptologist's output (both initial and every revision) must end with a fixed regimen block. This is the only structured element in the pipeline and it's required — not optional — because evaluation depends on reliably parsing the final drug actions. The free text reasoning above it can be any format.

```
REGIMEN:
Option 1: <label>
- <drug>: <start/continue/stop>
- <drug>: <start/continue/stop>
Rationale: <1-2 sentences>

Option 2: <label>
...

Option 3: <label>
...
```

Drug names must use canonical names from the 10-drug list. Actions must be one of: start, continue, stop. This block is trivially parseable and eliminates V1's parsing fragility at the one point where structure actually matters.

---

## Phase 3: Pharmacologist (Adversarial Review)

**Input:**
- Patient data
- All Phase 1 free text outputs
- Epileptologist's full output

**Output:**
- Free text critique: drug interactions, dosing errors, contraindications, formulation concerns, dangerous combinations
- Prioritized concerns with reasoning

**Role:** Advisor, not gatekeeper. Reports problems. Does not rewrite the prescription.

---

## Phase 3.5: Debate

Runs whenever the pharmacologist raises concerns. If the pharmacologist has no concerns, debate is skipped and the epileptologist's initial plan stands. When debate runs, the epileptologist must produce a revised plan that accounts for pharmacologist feedback.

### Context Management (Critical)

Each debate round carries ONLY:
- Patient data
- All Phase 1 raw outputs
- The epileptologist's CURRENT plan (latest version only)
- The LATEST pharmacologist critique

Previous rounds are NOT appended. The current plan supersedes all prior versions. The current critique supersedes all prior critiques. This prevents context bloat and keeps the LLM focused on what matters now.

**Important:** The pharmacologist follow-up must list ALL remaining concerns, not just new ones. Since old rounds are dropped from context, the pharmacologist's latest critique is the single source of truth for what's still unresolved. If round 2 only mentions a new concern, round 1's unresolved concerns silently disappear. The pharmacologist prompt must explicitly require: "List your full set of remaining concerns, including any from prior rounds that were not adequately addressed."

### Round Structure

Each round = 2 LLM calls:

1. **Epileptologist revision** — reads current critique, revises plan. Produces:
   - Response to concerns (accept with changes, or refute with justification)
   - Revised 3 regimen options
   - Reasoning

2. **Pharmacologist follow-up** — reads revised plan. Produces:
   - Remaining concerns, or "no further concerns"
   - If no concerns → debate ends

### Termination

If the pharmacologist's initial Phase 3 critique contains no concerns, Phase 3.5 is skipped entirely — the epileptologist's Phase 2 output is the final answer. No revision call is wasted when there's nothing to revise.

If debate does start, it ends when:
- Pharmacologist follow-up responds with no remaining concerns, OR
- Max rounds reached (configurable, default 2)

### Key Differences from V1

- Epileptologist actually revises the plan (not self-reporting accept/reject into a JSON)
- No separate pharmacologist "verdict" call — the follow-up IS the verdict
- No programmatic filtering of concerns between rounds
- No parsing of debate output for pipeline control
- Context is managed (no accumulation), not appended blindly
- The epileptologist's last output IS the final answer

---

## What V2 Removes (vs V1)

| V1 Component | Status in V2 | Why |
|---|---|---|
| Phase 1.5 conflict detection | **Removed** | Epileptologist reads agent text directly and is instructed to address disagreements. Programmatic detection was broken by normalization and added no value. |
| Safety vetoes | **Removed** | Over-enforcing. LLM severity labels are poorly calibrated. Vetoes failed silently due to case mismatch anyway. |
| Rule-based synthesis (Phase 4) | **Removed** | Rules applied to dirty LLM outputs. Failed silently. Debate modifications were never applied. The whole phase was broken. |
| Debate self-reporting | **Removed** | Epileptologist no longer says accept/reject into JSON. It revises the plan. The revision speaks for itself. |
| Pharmacologist verdict call | **Removed** | Was a wasted LLM call — stored as free text, never parsed, never used. Replaced by pharmacologist follow-up that naturally continues the debate. |
| format_trace_output() | **Removed** | Overwrote epileptologist's original output with a Phase 4 summary. Destroyed trace integrity. No formatting call needed — raw outputs are the trace. |
| Post-debate orchestrator | **Not needed** | If the orchestrator reasons again at the end, it either duplicates the epileptologist or steals authority from it. Final answer = epileptologist's last output. |

---

## Orchestrator

The orchestrator exists ONLY at the start of the pipeline. Its job:

1. See the patient case
2. Decide which agents to activate (and record why)
3. Get out of the way

Currently this is hardcoded switches (tropical medicine conditional on keywords, all others always active). If more case-dependent routing is needed in the future, this is where it goes — not at the end.

The orchestrator does NOT:
- Synthesize agent outputs
- Apply rules to the final plan
- Make clinical decisions
- Run after the debate

---

## LLM Calls Per Patient

| Phase | Calls | Purpose |
|-------|-------|---------|
| Phase 1 | 4-5 (parallel) | Specialist assessments |
| Phase 2 | 1 | Epileptologist initial plan |
| Phase 3 | 1 | Pharmacologist critique |
| Phase 3.5 | 2-4 (1-2 rounds × 2 calls) | Debate: revision + follow-up |
| **Total** | **8-11** | Every call is reasoning or critiquing. Zero calls for formatting, summarizing, or validating. |

---

## Reasoning Trace

The trace is the full sequence of agent outputs in order. Nothing is overwritten, nothing is summarized by another LLM. What each agent said is exactly what's in the trace.

```
trace = {
    patient_id: "...",
    visit: "...",
    agents_activated: ["diagnostician", "treatment_analyst", ...],
    activation_reasons: { "tropical_medicine": "fever keyword detected", ... },
    phase1: {
        diagnostician: { raw_output: "..." },
        treatment_analyst: { raw_output: "..." },
        pediatrician: { raw_output: "..." },
        tropical_medicine: { raw_output: "..." },  // if activated
        formulary: { raw_output: "..." },
    },
    phase2_initial: { raw_output: "...", options: [...] },
    phase3_critique: { raw_output: "..." },
    debate_rounds: [
        {
            round: 1,
            epileptologist_revision: { raw_output: "...", options: [...] },
            pharmacologist_followup: { raw_output: "..." },
        },
    ],
    final_options: [...],  // parsed from last epileptologist output (for evaluation only)
}
```

---

## Experiments & Ablations

The claim "multi-agent debate improves drug prediction" is defended empirically, not by bolting on a programmatic validator. The experimental matrix isolates what matters.

### Baselines

| Config | Description | What it tests |
|--------|-------------|---------------|
| **Single-agent baseline** | One LLM call with the existing 7-stage prompt (V1 baseline) | Floor performance — no specialization, no debate |
| **Monolithic specialist prompt** | One LLM gets ALL specialist instructions (diagnostician + treatment analyst + pediatrician + formulary + pharmacologist) in a single system prompt, reasons in one shot | Is the gain from specialization or just from more detailed instructions? |
| **Monolithic + self-critique** | Same as above, but the model critiques and revises its own plan in a second call | Is the gain from external critique (pharmacologist) or does self-critique suffice? |

### System Configurations

| Config | Description | What it tests |
|--------|-------------|---------------|
| **Multi-agent, no debate** | Phase 1 specialists + epileptologist, no pharmacologist, no debate | Does parallel specialization alone help? (isolates value of independent reasoning) |
| **Multi-agent + debate (V2 full)** | Full V2 pipeline | The complete system |

### Agent Ablations

Remove each Phase 1 agent individually and measure impact:

| Config | Removed Agent | What it tests |
|--------|--------------|---------------|
| `no_diagnostician` | Diagnostician | Does seizure classification matter for drug selection? |
| `no_treatment_analyst` | Treatment Analyst | Does treatment history analysis prevent unnecessary changes? |
| `no_pediatrician` | Pediatrician | Does pediatric-specific reasoning improve safety/accuracy? |
| `no_formulary` | Formulary | Does availability context change drug selection? |
| `no_tropical_medicine` | Tropical Medicine | Does infectious differential matter (conditional agent)? |
| `epileptologist_only` | All Phase 1 agents | Does the epileptologist need specialists, or can it reason alone? |

### Debate Ablations

| Config | Rounds | What it tests |
|--------|--------|---------------|
| 0 rounds | No pharmacologist, no debate | Baseline: epileptologist alone after Phase 1 |
| 1 round | 1 critique + 1 revision | Is one round of feedback enough? |
| 2 rounds | 2 critique-revision cycles | Do additional rounds help or cause drift? |
| 3 rounds | 3 cycles | Diminishing returns? Regression? |

### Context Ablations

| Config | Context strategy | What it tests |
|--------|-----------------|---------------|
| **Latest only** (default) | Each round: patient + Phase 1 + current plan + latest critique | Focused context, no sludge |
| **Full cumulative** | Each round appends all prior rounds to context | Does history help or hurt? |

### What to Measure

For every configuration, evaluate on all patients × all visits:

**Primary metrics:**
- Top-1 exact match rate (Option 1 drugs == ground truth drugs)
- Top-3 exact match rate (any of the 3 options matches)
- Mean Jaccard similarity (partial credit for overlap)
- Per-drug precision and recall

**Secondary metrics (from structured footers, if used):**
- Inter-agent agreement score per patient
- Correlation between agent disagreement and prediction error
- Which agents the epileptologist follows most often
- How debate changes the final drug selection vs pre-debate plan

**Ablation-specific:**
- Delta in exact match when each agent is removed
- Delta in exact match per debate round count
- Context strategy comparison (latest-only vs cumulative)

### Key Comparisons for the Paper

1. **V2 full vs single-agent baseline** — does the system work at all?
2. **V2 full vs monolithic specialist prompt** — is the gain from multi-agent architecture or just better instructions?
3. **V2 full vs monolithic + self-critique** — is external critique (pharmacologist) better than self-critique?
4. **Multi-agent no-debate vs V2 full** — does debate add value beyond parallel specialization?
5. **Agent ablations** — which specialists contribute most? Is any agent redundant?
6. **Debate round ablations** — what's the optimal number of rounds?
7. **Context ablations** — latest-only vs cumulative, which is better?

If V2 beats the monolithic specialist baseline, the claim is defensible: **independence plus adversarial revision matters, not just a longer prompt.**

---

## Summary

The V2 architecture is:
- Phase 1 parallel specialists (free text) → epileptologist integrates → pharmacologist critiques → epileptologist revises → done.
- Orchestrator routes at the start, then disappears.
- Code does routing and measurement. LLMs do reasoning.
- No programmatic gates, vetoes, conflict resolvers, or synthesis rules.
- The paper's defense is empirical (baselines + ablations), not architectural (fake validators).
