# Research Plan — Agentic Clinical Discovery on Longitudinal Epilepsy Data

## Current State (2026-03-19)

### V2 Pipeline Results (50 patients, top-3 exact match)

| | Agentic | Baseline | Δ |
|---|---|---|---|
| Visit 1 | 68.8% | 64.6% | +4.2 |
| Visit 2 | 83.7% | 65.3% | +18.4 |
| Visit 3 | 81.6% | 73.5% | +8.1 |

- Debate effect: roughly neutral (±2%). Value is in ranked options, not debate shifting top pick.
- Only 1 parse fail across 150 predictions.

### Core Realization

Ground truth (doctor prescriptions) is imperfect. Even 100% accuracy doesn't prove correctness. The contribution is NOT "multi-agent beats single-agent." That's engineering, not science.

**The real direction: stop imitating doctors, start discovering clinical patterns.**

---

## Two Parallel Tracks

### Track 1: Karpathy-style Autoresearch (background, engineering)

Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) (March 2026). Tight loop:

1. Propose prompt/pipeline edit
2. Run on patient subset
3. Measure top-3 exact match
4. Keep or revert
5. Repeat

Runs independently in the background. Optimizes prediction accuracy. Engineering contribution, not the main paper.

### Track 2: AutoDiscovery — Hypothesis Generation & Falsification (the paper)

Inspired by [AutoDiscovery](https://arxiv.org/abs/2507.00310) (AI2, NeurIPS 2025) and [POPPER](https://arxiv.org/abs/2502.09858).

**Three phases:**

#### Phase 1: Rediscovery (validation)
Can agents independently arrive at KNOWN clinical facts from raw data?
- ILAE drug-resistance criteria (failure of 2+ adequate ASM trials)
- SANAD findings (LTG > CBZ for focal epilepsy, VPA for generalized)
- Standard first-line choices by seizure type
- Known contraindications (VPA + pregnancy risk, PB sedation in children)

If the system can't rediscover known things, we can't trust novel findings.

#### Phase 2: Falsification
Attack each hypothesis with:
- Confounders and alternate explanations
- Subgroup instability (does it hold for CP vs non-CP? age groups?)
- Temporal leakage (does it hold across visit splits?)
- Bootstrap resampling for stability
- Missing-data sensitivity

The difference between "interesting finding" and "robust finding."

#### Phase 3: Novel Discovery
Hypotheses that survive falsification go to real doctors (Raj, JP) for validation. Only then claim novelty.

### Discovery Loop (detailed)

```
1. Agent proposes hypothesis about treatment patterns
2. Agent writes analysis code to test it
3. Run on 332×3 patient data
4. Measure Bayesian surprise (KL divergence prior→posterior)
5. If surprising → branch deeper (MCTS). If not → try elsewhere.
6. Surviving hypotheses get falsification attack
7. Robust findings → doctor validation
```

---

## Dataset

- 332 unique patients × 3+ visits each (~1000 visit-level entries)
- 48 patients have 4+ visits (unscheduled = treatment complications)
- Raw CSV: `data/combined_dataset.csv` (semicolon-delimited)
- Processed: `data/processed/` (drug_gt.json, split_results.json, etc.)
- Doctor feedback: `data/feedback/` (feedback_Raj.csv, feedback_JP.csv — 60 cases each)
- Doctor can rank more cases if needed

### Key Dataset Signals

**Drug patterns:**
- First-line: VPA 48%, CBZ 44% (bimodal, seizure-type driven), PB 2.2%, LEV 1.4%
- 76.3% monotherapy at start, 19% dual, 2.2% triple+
- 81% stay on same monotherapy V1→V2 (high stickiness)
- CBZ+VPA dominates polytherapy (90 instances), VPA in 81% of all combos
- 20.4% escalated, 12.5% de-escalated, 10.4% switched

**Drug resistance:**
- 31 patients tried 3+ different drugs
- 6 started on 3+ drugs at Visit 1

**Comorbidities:**
- 23% cerebral palsy (63 patients) — major signal
- CP patients: 51 mono, 15 poly at baseline

**Doctor agreement (60 cases, 2 reviewers):**
- Agreed appropriate: 81.7%
- Disagreed: 10.0% — clusters on rare diagnoses (West Syndrome), multi-drug resistant patients

---

## Key Papers

### Medical Multi-Agent (competitors)
| Paper | Venue | Key Finding | Gap for Us |
|---|---|---|---|
| MDAgents | NeurIPS 2024 oral | Adaptive complexity routing, +4.2% on QA | QA only, no treatment recommendation, no debate |
| MedAgentBoard | NeurIPS 2025 D&B | Multi-agent doesn't consistently beat single-LLM | No drug selection task |
| MedThink-Bench | npj Digital Medicine 2025 | Accuracy ≠ reasoning quality | Single-LLM only, no multi-agent |

### Evaluation Without Perfect GT
| Paper | Key Idea |
|---|---|
| RPAD/RRAD (arXiv:2509.11941) | Normalize performance against inter-expert disagreement |
| HealthBench | 81.8% of eval variance is case-level noise |
| Jury Learning (CHI 2022) | Model every annotator individually |

### Auto-Research Frontier (2025-2026)
| System | Key Innovation |
|---|---|
| AutoDiscovery (AI2, NeurIPS 2025) | Bayesian surprise + MCTS for hypothesis exploration |
| POPPER (arXiv:2502.09858) | Sequential falsification with error control |
| FIRE-Bench (arXiv:2602.02905) | Rediscovery benchmark for research agents |
| Karpathy autoresearch | Tight edit→run→measure→keep loop, 700 experiments/2 days |
| Kosmos (Edison Scientific) | 42K lines of code per run, reproduced unpublished manuscripts |
| Google AI Co-Scientist | Multi-agent generate→debate→evolve, validated wet-lab discoveries |
| Absolute Zero Reasoner (NeurIPS 2025 spotlight) | Self-evolving curriculum, zero human data |

### Gaps Nobody Has Filled
1. No treatment recommendation benchmark (all QA/diagnosis)
2. AutoDiscovery never applied to clinical/longitudinal data
3. Falsification (POPPER) never applied to medical hypothesis generation
4. No work combining rediscovery + novel discovery on same clinical dataset
5. LMIC epilepsy setting unrepresented in AI literature

---

## What We're NOT Doing
- NOT building a general evaluation system
- NOT claiming "multi-agent is better" as the contribution
- NOT doing counterfactual "what if another drug was given" (needs target trial emulation)
- NOT repackaging existing methods on a medical dataset
