# Consilium — NeurIPS TODO

Target: NeurIPS 2026 (deadline ~30 days)

---

## P0 — Must Have Before Submission

### 1. Statistical Rigor

- Bootstrap 95% CIs on all main results (resample patients 1000x)
- Paired bootstrap or McNemar significance tests vs main baseline
- Cluster-bootstrap by patient if pooling V1+V2+V3

### 2. Baselines

- **Copy-previous-regimen** — trivial heuristic: repeat last visit's prescription. ~80% of patients don't change, so this will be strong. Reviewers WILL ask for it.
- Zero-shot — "What drugs should this patient get?" (no pipeline, no stages)
- CoT — "Think step by step, then prescribe"
- CoT-SC (self-consistency) — CoT 5x at temp=0.7, majority vote on drug set
- single_agent baseline (done)
- all_agents_combined baseline (done)
- Classical methods (XGBoost/RF) — include if comparison is fair and we clearly beat them

### 3. Analysis Scripts (scripts/)

- `disagreement.py` — inter-agent disagreement analysis. Where do agents disagree? Does disagreement predict errors?
- `trace_quality.py` — reasoning trace quality metrics
- `error_detection.py` — map wrong predictions to agent-level errors, build error taxonomy

### 4. Hard Subset Benchmarkization

- Polytherapy patients (formal subset)
- Changed-regimen visits (doctor switched drugs)
- Short-gap follow-ups (<4 months)
- Later visits with more longitudinal history

### 5. Doctor Validation

- Blinded clinician trace/regimen evaluation (in progress)
- "Which trace is more clinically useful, safer, or better justified?"
- Formalize as inter-rater agreement study

### 6. No-Leakage Statement

- Explicit statement: Ugandan clinic data, not in any known LLM training corpus, zero overlap with standard medical QA benchmarks

---

## P1 — Very Strong If Time Allows

### 7. Multi-Model (2-3 models)

- Run pipeline + key baselines on 2-3 models (e.g. one smaller, one larger)
- Single script with `--model` sweep
- Don't need every ablation on every model — just full system + baseline + best ablation

### 8. Cost / Latency / Token Accounting

- Tokens per patient (input/output) for each method
- $/patient for each method
- Wall-clock time per patient
- Performance vs cost tradeoff plot (vs own baselines, not external papers)

### 9. Targeted Ablations

- **No pharmacologist** — not in current configs, add it
- **Debate rounds** (0, 1, 2, 3) — already have the flag
- **No routing** — all specialists always active, skip orchestrator decisions
- **No longitudinal history** — truncate to current visit notes only
- **Same-budget single-agent** — give single agent same total tokens as multi-agent

### 10. Regimen-Change Detection Metric

- Binary metric: did the system correctly predict THAT a change should happen?
- Separate from which drug — sharper clinical failure mode analysis

### 11. Hospital-Split Robustness

- Separate results by hospital (2 sites)
- Supplementary table, not headline

### 12. No-Leakage Details

- Already handled — formalize in paper methods section

---

## P2 — Nice To Have

### 13. Temperature Robustness

- 3 seeds at temp=0.3 or 0.5 for key configs
- Separate experiment, not main table (main = temp=0 deterministic)

### 14. Additional Prompt Variants

- Few-shot with in-distribution examples
- Only if cheap

### 15. RAG Baseline

- Skip unless clean, clinically justified retrieval source
- Our task is LMIC prescription prediction, not textbook QA

### 16. Exotic Agent Variants

- Low priority unless almost free to test

---

## Already Done

- Multi-agent pipeline (5 specialists + epi + pharma)
- Single-agent baseline (single_agent.txt)
- all_agents_combined baseline
- Agent-level ablation (all no_X and only_X configs)
- V1/V2/V3 longitudinal results (279 patients)
- Mono/poly breakdown
- Visit-gap analysis
- Regimen-change accuracy split
- Temperature fix (phase1=default, epi/pharma/orchestrator=0)
- Pre-pharma vs post-pharma comparison
- Streamlit trace viewer

