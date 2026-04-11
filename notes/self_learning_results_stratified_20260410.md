# Self-Learning Stratified Experiment Results — 2026-04-10

## Setup

- **Predictor prompt:** Minimal — knows only "clinic in Uganda", 10 drug names, output format. No mention of epilepsy, LMIC, seizure types, formulary, or any clinical reasoning.
- **Inspector prompt:** Knows only "clinic in Uganda". Diagnoses errors after seeing ground truth.
- **Architect prompt:** Reads Inspector reports, discovers patterns, produces shared learnings. Quorum rule: needs 2+ patients supporting a learning. Max 15 active learnings.
- **Model:** openai.gpt-oss-120b-1:0 (AWS Bedrock)
- **Data:** CSV cohort, all visits. Stratified split by patient complexity.
- **Train:** 50 patients, 151 cases (38 poly). Mix: 25 simple + 15 mixed + 10 poly-heavy.
- **Eval:** 20 patients, 60 cases (16 poly). Mix: 10 simple + 6 mixed + 4 poly-heavy.
- **Batch size:** 10 cases per round (16 rounds total)
- **Cases shuffled randomly** — visits from the same patient spread across different batches.
- **Seed:** 42

## Eval Progression (held-out 60 cases, never trained on)

| Round | Learnings | Top-1 | Top-3 | Mono top-3 | Poly top-3 |
|-------|-----------|-------|-------|-----------|-----------|
| Baseline | 0 | 34/60 (57%) | 39/60 (65%) | 32/44 (73%) | 7/16 (44%) |
| R0 | 3 | 37/60 (62%) | 43/60 (72%) | 34/44 (77%) | 9/16 (56%) |
| R1 | 6 | 41/60 (68%) | 47/60 (78%) | 37/44 (84%) | 10/16 (63%) |
| R2 | 8 | 41/60 (68%) | 46/60 (77%) | 35/44 (80%) | 11/16 (69%) |
| R3 | 9 | 40/60 (67%) | 48/60 (80%) | 37/44 (84%) | 11/16 (69%) |
| R4 | 11 | 36/60 (60%) | 45/60 (75%) | 32/44 (73%) | 13/16 (81%) |
| R5 | 13 | 41/60 (68%) | 47/60 (78%) | 36/44 (82%) | 11/16 (69%) |
| R6 | 14 | 43/60 (72%) | 45/60 (75%) | 34/44 (77%) | 11/16 (69%) |
| R7 | 14 | 40/60 (67%) | 47/60 (78%) | 35/44 (80%) | 12/16 (75%) |
| R8 | 14 | 38/60 (63%) | 43/60 (72%) | 33/44 (75%) | 10/16 (63%) |
| R9 | 14 | 36/60 (60%) | 43/60 (72%) | 33/44 (75%) | 10/16 (63%) |
| R10 | 15 | 37/60 (62%) | 41/60 (68%) | 31/44 (70%) | 10/16 (63%) |
| R11 | 15 | 36/60 (60%) | 43/60 (72%) | 33/44 (75%) | 10/16 (63%) |
| R12 | 15 | 40/60 (67%) | 46/60 (77%) | 37/44 (84%) | 9/16 (56%) |
| R13 | 15 | 38/60 (63%) | 50/60 (83%) | 39/44 (89%) | 11/16 (69%) |
| R14 | 15 | 37/60 (62%) | 45/60 (75%) | 34/44 (77%) | 11/16 (69%) |
| R15 | 15 | 37/60 (62%) | 42/60 (70%) | 31/44 (70%) | 11/16 (69%) |

### Key numbers
- **Baseline → Peak improvement:** +18pp top-3 (65% → 83% at R13), +15pp top-1 (57% → 72% at R6)
- **Poly improvement:** 44% → 81% at R4 peak (+37pp), stable around 69%
- **Mono improvement:** 73% → 89% at R13 peak (+16pp)
- **Biggest jump:** R0-R1, from 3 to 6 learnings, +6pp top-3

### Oscillation in later rounds
Performance oscillates after R7 (14-15 learnings). The 15-learning cap causes churn — new learnings displace useful ones. Peak top-3 at R13 (83%) but doesn't hold. Suggests the system would benefit from better learning retention/consolidation.

---

## Learnings Discovered (15 final, grouped by theme)

### Treatment Continuity (5 learnings → maps to Treatment Response Analyst)
1. Explicit continue/refill/start instructions dominate all other signals
4. Maintain real-time inventory of current AEDs from notes
7. If a drug is listed with dose and no stop order, continue it
11. "Did not take" or drug absent from latest list = implicit discontinuation
14. Multiple listed AEDs should all be continued unless explicitly stopped

### Seizure Classification → Drug Selection (6 learnings → maps to Diagnostician)
2. Head injury / focal lesion descriptors → classify as focal
3. Don't auto-exclude carbamazepine for generalized — check EEG first
10. Doose (myoclonic-atonic) epilepsy → ethosuximide first-line
11. Absence seizures → ethosuximide
12. Focal semiology even with generalized label → consider carbamazepine
13. Verify drug indication matches documented seizure type before continuing

### LMIC / Formulary (3 learnings → maps to Formulary Specialist)
5. Don't let "levetiracetam is preferred" override patient-specific evidence
6. Carbamazepine first-line for focal in Ugandan pediatric epilepsy
8. Don't let age-based defaults override explicit prescriptions

### Polytherapy Triggers (2 learnings → maps to Epileptologist logic)
6. High seizure burden → consider adjunct or switch
15. Poor appetite + multifocal EEG → specific combination patterns

---

## Comparison with Hand-Designed System

| Discovered theme | Count | Consilium agent | Agent designed from |
|-----------------|-------|----------------|-------------------|
| Treatment continuity | 5 | Treatment Response Analyst | Doctor complaint: "LLM de-escalates working regimens" |
| Seizure classification | 6 | Seizure Diagnostician | Doctor complaint: "seizure type misclassification" |
| LMIC formulary | 3 | Formulary Specialist | Doctor complaint: "ignoring drug availability" |
| Polytherapy logic | 2 | Epileptologist | Prescribing integration |

The self-learning system independently converged on the same decomposition that two neurologists identified from 120 clinical reviews. Treatment continuity received the most learnings (5/15), consistent with our finding that the Treatment Analyst is the highest-impact agent.

---

## Prior experiment comparison (same eval set as Visit-1-only run)

From the earlier Visit-1-only experiment on 19 eval patients:

| System | Top-1 | Top-3 |
|--------|-------|-------|
| Zero-knowledge predictor | 7/19 (37%) | 10/19 (53%) |
| Self-learning (1 learning) | 11/19 (58%) | 14/19 (74%) |
| Single-agent baseline | 10/19 (53%) | 13/19 (68%) |
| Consilium (full pipeline) | 8/19 (42%) | 13/19 (68%) |

Note: Consilium underperformed on this specific 19-patient V1 subset. Full-scale Consilium results across all visits are stronger (77-90% top-3 on Cohort A).

---

## Interpretation

### The convergence finding
The core result is not the accuracy numbers — it's the convergence. Two independent paths (top-down from doctor feedback, bottom-up from task feedback) arrive at the same clinical reasoning decomposition. This suggests the decomposition reflects genuine structure in epilepsy prescribing, not an artifact of prompt design.

### What the feedback loop can and cannot discover
**Discovered automatically:**
- Which drugs dominate (VPA, CBZ) — from repeated GT observations
- Seizure type → drug mapping — from Inspector analyzing errors
- Treatment continuity as the default — from pattern of "doctor continued" in GT
- LMIC formulary preferences — Inspector inferred from Uganda context + GT patterns
- Specific syndrome → drug mappings (Doose → ESM, absence → ESM)

**Required as input (dataset-level metadata):**
- The setting is Uganda (couldn't be inferred from individual notes)
- The 10 drug names (output vocabulary)

**NOT discovered (would need more data or explicit teaching):**
- Safety constraints (PB + clobazam dangerous) — never appears in GT because doctors already avoid it
- Weight-based dosing details — rarely the distinguishing factor in GT match
- Drug interaction specifics — same absence-of-evidence issue

### Limitations
- 50 train patients is small — more data would likely improve and stabilize
- The 15-learning cap causes churn in later rounds
- No agent spawning yet — all learning is through shared text, not structural changes
- Performance oscillates rather than monotonically improving
- Single model (gpt-oss-120b) — results may vary with other models

---

## Output Files

- `self_learning/outputs/loop_20260410_1846/` — full stratified run
  - `progression.txt` — human-readable evolution table
  - `eval_progression.json` — structured eval per round with mono/poly breakdown
  - `round_N.json` — full data per round (predictor COT, inspector COT, architect output)
  - `full_run.json` — everything
- `self_learning/sampler.py` — stratified patient sampler
- `self_learning/prompts/predictor_v0.txt` — minimal predictor (Uganda + 10 drugs only)
- `self_learning/prompts/inspector.txt` — error diagnostician (Uganda only)
- `self_learning/prompts/architect.txt` — learning updater
