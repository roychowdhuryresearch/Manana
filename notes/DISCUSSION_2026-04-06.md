# Paper Discussion — 2026-04-06

## Abstract Framing

### What we tried first
- Original abstract led with "LLMs fail when populations differ" and described Consilium as decomposing into complementary perspectives. Too generic — could describe any multi-agent paper.

### Key criticisms of v1 abstract
1. Third paragraph was vague and hand-wavy ("more grounded and practically useful" — says who?)
2. Buried the lede — the interesting OOD/LMIC angle wasn't mentioned
3. "91.4% across three visits" was confusing (unclear aggregation)
4. Too long (3 dense paragraphs)
5. No differentiation from MDAgents/MedAgentBoard
6. Uncertainty/disagreement claim tacked on with no evidence

### Core message debate

**Rejected framing: "Multi-agent corrects Western bias"**
- Problem: invites "why not just prompt it to act in an LMIC setting?" — which is essentially what each agent does
- The single-agent baseline already has LMIC context in its prompt and still fails

**Rejected framing: "Multi-agent corrects distribution-dependent failures"**  
- Better, but still reactive (defined in terms of what others got wrong)
- User didn't like opening the abstract by responding to MedAgentBoard

**Accepted framing: "Clinician-informed multi-agent decomposition"**
- Narrative arc: try LLM on real task → discover systematic Western bias → work with clinicians to identify failure modes → design specialist agents targeting each → structured debate resolves conflicts → validated by neurologists
- Story of discovery, not just system description
- Preempts "why not just prompt better?" — answer: we worked with doctors to identify what's missing, not just engineering prompts
- The agents aren't arbitrary role-play — they're clinician-designed to target specific failure modes

### Final abstract structure
1. Gap: existing work does QA benchmarks or structured-code drug rec, not real clinical tasks from free text
2. Motivation: valuable in low-resource settings where coding infrastructure doesn't exist
3. Setting: 699 patients, longitudinal, Uganda
4. Finding: single-agent shows systematic Western bias (specific examples)
5. Solution: clinician-informed specialist agents + debate
6. Results: 66→80% V1, 76→91% V3, +34pp polytherapy
7. Validation: ablations + neurologist blinded evaluation + two cohorts
8. Takeaway: clinician-informed multi-agent decomposition corrects distributional biases

## Positioning / Related Work

### Literature landscape — confirmed no overlap with our work
Four buckets, none covering our combination:
1. **Drug prediction from structured codes** (FLAME, DrugRec, SafeDrug, MICRON, LAMO) — all need ICD/ATC codes, all MIMIC, no reasoning
2. **LLM clinical QA** (MDAgents, MedAgentBoard) — benchmarks, not real patients
3. **LLM clinical deployment** (Penda Health Kenya, Singapore ED) — error detection or binary decisions, not drug prediction
4. **Epilepsy ML** (Hakeem, Park, Goldenholz) — drug response prediction, not drug selection

### FLAME deep dive
- Fine-tunes Llama3.1-Aloe-Beta-8B with step-wise GRPO on MIMIC-III
- Requires ICD diagnosis codes + ATC medication codes + procedure codes + clinical notes
- Two-stage: binary classifier filters candidates → list-wise policy does add/remove edits
- Jaccard 0.484 on 131 ATC-3 drug classes — not comparable to our exact match on 10 named drugs
- Cannot work without structured codes → cannot apply to our setting

### LAMO
- Also requires ICD codes alongside discharge summaries
- Fine-tuned LLaMA-2-7B with LoRA
- No reasoning traces

### Key differentiator confirmed
No paper predicts drug regimens from free-text clinical notes using LLMs on real patient data. The structured-code requirement is the wall — and it's exactly the infrastructure that doesn't exist in LMIC clinics.

### ICD/ATC codes matter because
They pre-solve the hard part. FLAME never has to figure out what the patient has or what drugs they're on — that's pre-extracted into clean vectors. Our model must read and understand messy clinical narrative, extract information, reason about it, then recommend. The reading comprehension IS the task.

## NeurIPS Strategy

### Track: Main Conference, Use-Inspired
- Datasets & Benchmarks rejected because dataset release needs institutional approval (timeline uncertain)
- Use-Inspired fits: novel methods for real-world applications

### What makes it NeurIPS-worthy
- Not the architecture (role-prompting + debate isn't new)
- Not the dataset alone (can't release it yet)
- The empirical finding: clinician-informed multi-agent reasoning corrects distribution-dependent failures, and the correction is attributable, predictable, and clinically validated
- Directly responds to MedAgentBoard (NeurIPS 2025) finding that multi-agent doesn't consistently help

### Vulnerability
- Single model backbone — need at least partial second-model results
- "Why not just prompt better?" — addressed by clinician-designed agents narrative
- Architecture isn't methodologically novel — mitigated by framing as empirical finding, not system paper

## Numbers (from overleaf tables, EM@3)

### Cohort A
| Visit | Single-agent | Consilium | Delta |
|-------|-------------|-----------|-------|
| V1    | 66.0        | 79.5      | +13.5 |
| V2    | 74.4        | 88.0      | +13.6 |
| V3    | 75.6        | 91.0      | +15.4 |

### Polytherapy Cohort A
| Visit | Single-agent | Consilium | Delta |
|-------|-------------|-----------|-------|
| V1    | 13.4        | 29.9      | +16.5 |
| V2    | 40.5        | 63.3      | +22.8 |
| V3    | 41.8        | 75.5      | +33.7 |

### Cohort B
| Visit | Single-agent | Consilium | Delta |
|-------|-------------|-----------|-------|
| V1    | 65.9        | 71.5      | +5.6  |
| V2    | 70.1        | 83.0      | +12.9 |
| V3    | 71.8        | 86.8      | +15.0 |
