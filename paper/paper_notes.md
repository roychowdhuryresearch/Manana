# Consilium — Paper Discussion Notes

## 2026-03-20: Positioning & Novelty

### MDAgents comparison (NeurIPS 2024 oral, arxiv 2404.15155)

MDAgents' angle was **adaptive complexity routing** — not every medical question needs a full team. They showed simple cases do better with 1 agent, complex cases benefit from teams. Evaluated on 10 standardized medical QA benchmarks (MedQA, PubMedQA, JAMA, etc.). All multiple choice. Each case independent. No longitudinal reasoning, no real patients, no clinician validation of agent design.

**Our differentiators vs MDAgents:**
1. **Real clinical data, not QA benchmarks.** We predict actual drug prescriptions for real patients, not multiple choice answers.
2. **Longitudinal reasoning.** Patients have 3-5+ visits over 12+ months. The system tracks treatment response over time, dose optimization as children grow, drug resistance patterns. MDAgents treats each query as independent.
3. **Clinician-validated agent design.** Our 7 agents were derived from 120 clinical reviews by two neurologists who identified 7 systematic failure categories. Each agent addresses a documented failure — not generic role assignment by an LLM recruiter.
4. **Global health / LMIC setting.** Uganda context changes prescribing fundamentally: drug availability, cost, infectious differentials (malaria vs epilepsy). Tension between clinical best practice and practical constraints is novel.
5. **Explicit conflict resolution.** MDAgents uses LLM consensus (black box). We use programmatic conflict detection + structured debate with accept/reject/modify + uncertainty markers.
6. **Reasoning traces as auditable output.** A neurologist can review per-agent reasoning and see where they disagreed.

### MedAgentBench comparison (NeurIPS 2024 D&B, arxiv 2501.14654)

Much less similar. MedAgentBench is a benchmark for LLMs as agents interacting with EHR systems (administrative tasks: retrieve labs, order meds, write referrals). Single agent with tool access, not multi-agent clinical reasoning. Useful as related work context showing the broader trend of medical AI agents, but solving a fundamentally different problem.

### Is there enough novelty for NeurIPS main?

**Honest assessment: borderline as a pure methods paper.** Multi-agent with specialist roles + debate is not new (MDAgents did it). Our specific additions (clinician-validated design, LMIC prompting, structured debate, free-text agents) are good engineering but a reviewer could argue they're prompt engineering.

**What elevates it:**
- The failure analysis IS the insight: naive multi-agent hurts simple cases (V1 results), we diagnosed why (Pediatrician applying Western prescribing logic in LMIC), and fixed it (V2 LMIC-anchored prompts)
- The LMIC context surfaces tensions that don't exist in standard benchmarks
- Longitudinal reasoning is genuinely hard — +18.4% on Visit 2 shows multi-agent helps most when there's history to reason over
- Real doctor feedback as both design input and evaluation closes the loop

### V1 vs V2 results

V1 (our initial implementation, 50 patients):
- Multi-agent underperformed baseline at scale (47.9% vs 59.6% top-1)
- Visit 1 was the big gap: 33% vs 58%
- Root cause: **levetiracetam bias** — Pediatrician agent applying Western prescribing logic, recommending LEV when the Ugandan doctors prescribe VPA/CBZ because they're reliably available
- 8/11 "wrong drug" cases on Visit 1: multi-agent picked levetiracetam when GT was valproate or carbamazepine
- Confirmed by literature: LEV "not available in most African countries due to mainly cost" (Lancet Neurology 2024), Mulago Hospital data shows 73.5% of children on carbamazepine monotherapy

V2 (colleague's rewrite, 50 patients, top-3):

| Visit | V2 Agentic | Baseline | Delta |
|---|---|---|---|
| Visit 1 | 68.8% | 64.6% | +4.2 |
| Visit 2 | 83.7% | 65.3% | +18.4 |
| Visit 3 | 81.6% | 73.5% | +8.1 |

V2 key changes: free-text agents (no JSON parsing), LMIC-anchored prompts everywhere, simplified debate, removed programmatic conflict detection, proper regimen parser.

---

## 2026-03-20: Paper framing decision

### Two viable angles

**Angle A: "Systems + Analysis" paper**
- Contribution is not "we beat baseline" — it's the architecture + the analysis
- First systematic analysis of when/why multi-agent helps vs hurts in clinical settings
- LMIC prescribing bias discovery as a general finding about LLMs in global health
- Reasoning traces as auditable clinical decision support

**Angle B: Beat baseline + strong evaluation (preferred for NeurIPS main)**
- V2 already beats baseline — run at full scale
- Need LMIC-anchored single-agent baseline for fair comparison (critical)
- Doctor evaluation of traces (unique — no multi-agent paper has this)
- Release as first treatment prediction benchmark

**Decision: Go with Angle B.** Stronger for NeurIPS main.

### Required baselines

| Baseline | What it tests |
|----------|--------------|
| Single-agent (original 7-stage prompt) | Existing system without multi-agent |
| **Single-agent (LMIC-anchored prompt)** | Same LMIC anchoring as V2 epileptologist, no specialist agents. Tests whether improvement is from better prompting or from multi-agent. **This is the critical baseline.** |
| Multi-agent without debate | All agents run, no pharmacologist-epileptologist exchange |
| Ablation: remove each Phase 1 agent | Individual agent contribution |
| MDAgents-style adaptive routing | Their approach on our task |

### Doctor evaluation protocol

Have Raj and JP review traces. Suggested design:
- 40 patients (20 from each dataset)
- Both neurologists review all 40 (inter-rater reliability)
- For each: multi-agent trace, single-agent output, ground truth (blinded)
- Rate on: clinical accuracy (1-5), reasoning quality (1-5), actionability (1-5), preference (A vs B)

### The autodiscovery question

Colleague proposed using the multi-agent system for clinical hypothesis generation and falsification (inspired by AutoDiscovery/AI2, POPPER, Karpathy autoresearch). **Consensus: this is a separate paper.** It builds on the infrastructure from this paper but is a different contribution. Keep it in the research plan but don't try to squeeze it into the NeurIPS submission.

---

## 2026-03-20: Second dataset discovery

### Dataset 2: PDF-based patient records

Location: `/mnt/SSD1/yigit/global_health_llm/data/all_patient_pdfs/`

| Property | Dataset 1 | Dataset 2 | Combined |
|---|---|---|---|
| Patients | 279 | 368 unique | **647** |
| Visits | 837 | 1,515 | **2,352** |
| Avg visits/patient | 3.0 | 4.1 | 3.6 |
| Format | CSV (semicolon-delimited) | PDF → text (already parsed) | Both structured clinical notes |
| Overlap | — | 2 patients | Negligible |
| Visit range | Fixed 3 visits | 1-10 visits (124 with 4, 67 with 5, 31 with 6+) | Variable |

Same Ugandan epilepsy clinic (SnapPatient system), same drug formulary, same structured format (Patient history → Semiology → Physical exam → Diagnosis with ICD codes → Management → Drugs).

Text already extracted from PDFs. Structure is clean and consistent.

### What this enables

1. **Train/develop on dataset 1, evaluate on dataset 2** — eliminates overfitting concern
2. **Cross-site generalization** — same clinical setting but different patient population and record format
3. **Benchmark release** — "first treatment prediction benchmark on real LMIC longitudinal data, 647 patients, 2,352 visits"
4. **Extended longitudinal reasoning** — dataset 2 patients with 4-7 visits test whether multi-agent advantage grows with more history
5. **Scale** — 2,352 visit-level cases is substantial for clinical AI

### Next steps

1. Parse dataset 2 into pipeline format (split input/output, extract drug GT)
2. Merge cons_v2 into main (or work from that branch)
3. Run V2 on full dataset 1 (279 patients × 3 visits)
4. Run V2 on dataset 2
5. Build LMIC-anchored single-agent baseline
6. Run ablations
7. Design and execute doctor evaluation protocol
8. Write paper
