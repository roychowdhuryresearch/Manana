# Self-Learning Experiment Results — 2026-04-10

## Setup

- **Predictor prompt:** Zero domain knowledge — knows only "you will be given clinical notes, predict the prescription" and the 10 drug names. No mention of Uganda, LMIC, seizure types, or any clinical reasoning guidance.
- **Inspector prompt:** Knows the setting is Uganda/LMIC with constrained drug availability. Diagnoses errors after seeing ground truth.
- **Architect prompt:** Reads Inspector reports per batch, discovers patterns, produces shared learnings for the Predictor.
- **Model:** openai.gpt-oss-120b-1:0 (AWS Bedrock)
- **Data:** Visit 1, CSV cohort. 30 train patients (6 batches of 5), 19 held-out eval patients.
- **Seed:** 42 (deterministic train/eval split)

## Eval Progression (held-out 19 patients)

| Round | Learnings | Top-1 | Top-3 |
|-------|-----------|-------|-------|
| Baseline | 0 | 7/19 (37%) | 10/19 (53%) |
| R0 | 1 | 11/19 (58%) | 14/19 (74%) |
| R1 | 1 | 11/19 (58%) | 15/19 (79%) |
| R2 | 1 | 12/19 (63%) | 14/19 (74%) |
| R3 | 1 | 11/19 (58%) | 15/19 (79%) |
| R4 | 2 | 10/19 (53%) | 15/19 (79%) |
| R5 | 2 | 10/19 (53%) | 14/19 (74%) |

**Key finding:** A single learning discovered after 5 training patients lifted held-out eval from 37% → 58% top-1 and 53% → 74% top-3 (+21pp both).

## Learnings Discovered

### After Round 0 (1 learning):
1. "When generating antiepileptic recommendations, give priority to drugs that are listed on the Ugandan clinic's essential-medicine formulary (e.g., carbamazepine, phenobarbital, clobazam, valproate) and, if a 'Current drug regimen' section appears, adjust the existing regimen rather than initiating a new, less-available agent."

### After Round 4 (2 learnings):
1. Same as above (refined wording)
2. "When a patient is already on a maximally tolerated, stocked AED and reports breakthrough seizures, suggest adding a previously tolerated, inexpensive adjunct rather than only increasing the dose."

## What the system discovered independently

| Discovered learning | Consilium agent it maps to |
|---|---|
| Prioritize formulary drugs (VPA, CBZ, PB, CLB) | Formulary Specialist |
| Adjust existing regimen rather than starting new agent | Treatment Response Analyst |
| Add affordable adjunct when monotherapy fails | Epileptologist (polytherapy logic) |

## Interpretation

The Inspector (which knows the LMIC context) correctly diagnosed the Predictor's main failure mode — recommending levetiracetam when the clinic prescribes valproate/carbamazepine. The Architect distilled this into a single actionable learning that the Predictor used to immediately improve.

The plateau after R0 suggests remaining errors need more than shared learnings — they likely require dedicated specialist reasoning (seizure classification, pediatric dosing). This motivates the agent spawning step in the full self-learning design.

## Bare-Bones Experiment (preceding the loop)

20 patients, no learning loop, just Predictor + Inspector:
- Top-3 accuracy: 10/19 (52.6%)
- Inspector independently identified the same failure modes: treatment continuity tracking, seizure type classification, LMIC formulary awareness, polytherapy logic

## Comparison (pending)

Consilium pipeline and single-agent baseline running on the same 19 eval patients for direct comparison. Results to follow.

## Output files

- `self_learning/outputs/loop_20260409_2000/` — full loop run
  - `progression.txt` — human-readable evolution
  - `eval_progression.json` — structured eval results per round
  - `round_N.json` — full data per round (predictor COT, inspector COT, architect output)
  - `full_run.json` — everything
- `self_learning/outputs/bare_20260409_1840/` — bare-bones experiment (20 patients)
- `self_learning/outputs/bare_20260409_1854/` — bare-bones with COT (5 patients)
