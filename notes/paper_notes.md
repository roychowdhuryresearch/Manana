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


| Visit   | V2 Agentic | Baseline | Delta |
| ------- | ---------- | -------- | ----- |
| Visit 1 | 68.8%      | 64.6%    | +4.2  |
| Visit 2 | 83.7%      | 65.3%    | +18.4 |
| Visit 3 | 81.6%      | 73.5%    | +8.1  |


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


| Baseline                                | What it tests                                                                                                                                                              |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Single-agent (original 7-stage prompt)  | Existing system without multi-agent                                                                                                                                        |
| **Single-agent (LMIC-anchored prompt)** | Same LMIC anchoring as V2 epileptologist, no specialist agents. Tests whether improvement is from better prompting or from multi-agent. **This is the critical baseline.** |
| Multi-agent without debate              | All agents run, no pharmacologist-epileptologist exchange                                                                                                                  |
| Ablation: remove each Phase 1 agent     | Individual agent contribution                                                                                                                                              |
| MDAgents-style adaptive routing         | Their approach on our task                                                                                                                                                 |


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


| Property           | Dataset 1                 | Dataset 2                                       | Combined                       |
| ------------------ | ------------------------- | ----------------------------------------------- | ------------------------------ |
| Patients           | 279                       | 368 unique                                      | **647**                        |
| Visits             | 837                       | 1,515                                           | **2,352**                      |
| Avg visits/patient | 3.0                       | 4.1                                             | 3.6                            |
| Format             | CSV (semicolon-delimited) | PDF → text (already parsed)                     | Both structured clinical notes |
| Overlap            | —                         | 2 patients                                      | Negligible                     |
| Visit range        | Fixed 3 visits            | 1-10 visits (124 with 4, 67 with 5, 31 with 6+) | Variable                       |


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

---

## 2026-03-23: Progress so-far

### Dataset Construction

#### Source Data

Three patient cohorts, all from Ugandan epilepsy clinics:

1. **CSV cohort — 279 patients** (`data/combined_dataset.csv`): structured spreadsheet exported from the clinic system, semicolon-delimited, one row per patient. Each row had visit data for up to 3 visits (0 months, 6 months, 12 months) spread across many columns — demographics, clinical notes, and prescription all mixed together.
2. **CSV cohort (subset) — 53 patients**: a subset of the same CSV patients who had more than 3 visits. The standard 3-visit columns only captured Visit 1–3; these patients had Visit 4, 5, 6 data buried in additional columns that were ignored by the standard loader. A separate extraction pipeline was run specifically to surface these hidden visits.
3. **PDF cohort — 367 patients**: clinical notes exported from a hospital EMR as PDFs, then converted to plain text. Each patient had a folder of `.txt` files — one per visit — with free-form doctor notes containing both clinical observations and the prescription mixed together in unstructured prose.

#### Cleaning Process

**CSV cohort (279 + 53):**
For each patient and each visit, the raw column text was a mix of clinical observations and the prescription. An LLM was called with a splitting prompt to separate each visit into two clean parts: `input_text` (clinical notes — what the doctor observed) and `output_text` (prescription — what the doctor prescribed). The cleaned prescriptions were saved. Drug names were then extracted from the prescription text into `drug_gt.json` (a list of ASMs prescribed/stopped per visit) using a second LLM call.

For the 53-patient cohort, an additional extraction step first identified and structured the hidden visits (4–6) from the extra columns before the same split-and-clean process was applied.

**PDF cohort (367):**
Each visit `.txt` file was passed to an LLM with a split prompt to separate `input_text` from `output_text`. Visits were sorted chronologically using dates extracted by regex from the raw text (no LLM needed for dating), then assigned Visit_1, Visit_2, ... in date order. Drug GT was extracted the same way as for the CSV cohort.

#### Final Dataset

All three cohorts were merged into a single JSONL file (`consilium_dataset.jsonl`, hosted on HuggingFace at `kartiksharma4/consilium`). Each row is one independent (patient, visit) entry with 7 fields: `pid`, `visit_num`, `cohort` (csv/pdf), `input` (full cumulative clinical context — all prior visits with their prescriptions, plus the current visit notes), `output` (raw prescription text), `prescribed` (list of ASM names), `stopped` (list of ASM names).

Total: **2,549 entries across 699 unique patients** (CSV: 1,040 entries, PDF: 1,509 entries). Visits range from 1–10. No visit sequence gaps. No label leakage.

---

### Multi-Agent Pipeline Design

#### Agents


| Agent                 | Role                            | Phase           | Description                                                                                                                                                   |
| --------------------- | ------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Orchestrator**      | Gatekeeper                      | 0               | Reads the patient case and decides which Phase 1 agents to activate. Conditional agents (e.g. tropical medicine) only run when relevant.                      |
| **Diagnostician**     | Seizure Diagnostician           | 1               | Classifies seizure type and epilepsy syndrome from clinical semiology and EEG findings. Determines focal, generalized, or unknown onset.                      |
| **Treatment Analyst** | Treatment Response Analyst      | 1               | Evaluates longitudinal medication response across visits. Assesses whether current drugs are working, doses are optimized, and whether changes are justified. |
| **Pediatrician**      | Pediatric Specialist            | 1               | Assesses developmental context, weight-based dosing, and age-specific drug safety. Flags drugs contraindicated in children or requiring dose adjustment.      |
| **Tropical Medicine** | ID/Tropical Medicine Specialist | 1 (conditional) | Evaluates whether seizures have an infectious etiology (cerebral malaria, neurocysticercosis, HIV-related, meningitis). Flags ASM-antimicrobial interactions. |
| **Formulary**         | Formulary Specialist            | 1               | Assesses drug availability, cost, and health system constraints in Uganda. Identifies drugs that may not be accessible or affordable.                         |
| **Epileptologist**    | Prescribing Epileptologist      | 2               | Sees all Phase 1 outputs + full patient context. Makes the treatment decision — synthesizes specialist input into a ranked 3-option regimen.                  |
| **Pharmacologist**    | Clinical Pharmacologist         | 3               | Adversarial reviewer. Critiques the epileptologist's regimen for drug interactions, contraindications, and dosing errors. Raises concerns or clears the plan. |


#### Flow

```
pipeline/loader.py
    └── HF dataset → PatientCase (clinical_context)
            │
            ▼
orchestrator/pipeline.py  (ConsiliumPipeline)
    │
    ├── [Phase 0] agents/orchestrator.py
    │       agents/prompts/orchestrator.txt
    │       → decides which Phase 1 agents activate
    │
    ├── [Phase 1] parallel, activated agents only
    │       agents/diagnostician.py      + prompts/diagnostician.txt
    │       agents/treatment_analyst.py  + prompts/treatment_analyst.txt
    │       agents/pediatrician.py       + prompts/pediatrician.txt
    │       agents/tropical_medicine.py  + prompts/tropical_medicine.txt  [conditional]
    │       agents/formulary.py          + prompts/formulary.txt
    │
    ├── [Phase 2] agents/epileptologist.py
    │       agents/prompts/epileptologist.txt
    │       → sees full patient + all Phase 1 outputs
    │       → produces ranked 3-option regimen
    │
    ├── [Phase 3] agents/pharmacologist.py
    │       agents/prompts/pharmacologist.txt
    │       → critiques epileptologist regimen
    │
    ├── [Debate] orchestrator/debate.py        [only if concerns raised]
    │       agents/prompts/debate_rebuttal.txt
    │       → epi revises → pharma responds → epi finalises
    │       → always ends on epileptologist
    │
    └── final_regimen → outputs/predictions/consilium_*.json
```

#### Design Principles

- Every agent sees the full patient history independently — no information hiding between Phase 1 agents.
- Conflict resolution is programmatic, not another LLM call.
- The pharmacologist advises but does not veto — the epileptologist always has final say.
- Debate is skipped entirely if the pharmacologist raises no concerns.
- Output is a ranked 3-option regimen (Option 1 = preferred), not a single prescription, to reflect real clinical uncertainty.

---

### Results

Model: `openai.gpt-oss-120b-1:0` (AWS Bedrock). Phase 1 agents: 200-word response limit.

#### Cohort A: 279-patient CSV cohort (3 visits each)

**Baseline vs Multi-Agent (exact match, top-3)**


| Visit | Baseline | Multi-Agent | Delta   |
| ----- | -------- | ----------- | ------- |
| V1    | 71.3%    | 77.9%       | +6.6pp  |
| V2    | 79.9%    | 87.2%       | +7.3pp  |
| V3    | 80.1%    | 90.4%       | +10.3pp |


**Monotherapy**


| Visit | Baseline | Multi-Agent | Delta  |
| ----- | -------- | ----------- | ------ |
| V1    | 86.4%    | 92.0%       | +5.6pp |
| V2    | 93.3%    | 96.2%       | +2.9pp |
| V3    | 91.7%    | 97.4%       | +5.7pp |


**Polytherapy**


| Visit | Baseline | Multi-Agent | Delta   |
| ----- | -------- | ----------- | ------- |
| V1    | 16.9%    | 27.1%       | +10.2pp |
| V2    | 37.9%    | 59.1%       | +21.2pp |
| V3    | 52.5%    | 73.8%       | +21.3pp |


**Pre-Pharma vs Post-Pharma (epileptologist initial vs final regimen)**


| Visit | Pre-Pharma | Post-Pharma | Delta  |
| ----- | ---------- | ----------- | ------ |
| V1    | 79.0%      | 77.9%       | -1.1pp |
| V2    | 87.2%      | 87.2%       | 0.0pp  |
| V3    | 89.3%      | 90.4%       | +1.1pp |


Pharmacologist has minimal net effect on accuracy — slightly helps V3 polytherapy, negligible overall.

**Accuracy by Visit Gap**

Short-gap patients (< 4 months) have the lowest accuracy — not long gaps. These are unstable patients returning early because their meds aren't working.


| Bin     | N   | Multi-Agent | Baseline |
| ------- | --- | ----------- | -------- |
| < 4 mo  | 28  | 67.9%       | 64.3%    |
| 4–9 mo  | 201 | 88.6%       | 81.1%    |
| 9–15 mo | 30  | 96.7%       | 90.0%    |
| > 15 mo | 15  | 86.7%       | 73.3%    |


---

#### Cohort B: 53-patient extraction cohort (3–6 visits, LLM-extracted from CSV)

**Baseline vs Multi-Agent**


| Visit | Baseline | Multi-Agent | Delta   |
| ----- | -------- | ----------- | ------- |
| V1    | 40.9%    | 70.5%       | +29.6pp |
| V2    | 51.0%    | 64.7%       | +13.7pp |
| V3    | 61.5%    | 71.2%       | +9.7pp  |
| V4    | 71.8%    | 84.6%       | +12.8pp |


**Mono vs Poly**


| Visit | BL Mono | MA Mono | BL Poly | MA Poly |
| ----- | ------- | ------- | ------- | ------- |
| V1    | 44.4%   | 80.6%   | 25.0%   | 25.0%   |
| V2    | 63.2%   | 81.6%   | 15.4%   | 15.4%   |
| V3    | 76.5%   | 85.3%   | 33.3%   | 44.4%   |
| V4    | 88.9%   | 96.3%   | 33.3%   | 58.3%   |


---

#### Cohort C: 367-patient PDF cohort (variable visits, LLM-split from clinic PDFs)

1,509 visits total (up to 10 per patient).

**Baseline vs Multi-Agent**


| Visit | Baseline | Multi-Agent | Delta   |
| ----- | -------- | ----------- | ------- |
| V1    | 66.5%    | 68.9%       | +2.4pp  |
| V2    | 70.2%    | 83.4%       | +13.2pp |
| V3    | 71.8%    | 86.8%       | +15.0pp |
| V4    | 71.7%    | 87.7%       | +16.0pp |
| V5    | 73.7%    | 88.4%       | +14.7pp |
| V6    | 65.8%    | 81.6%       | +15.8pp |


**Mono vs Poly**


| Visit | BL Mono | MA Mono | BL Poly | MA Poly |
| ----- | ------- | ------- | ------- | ------- |
| V1    | 77.1%   | 78.8%   | 41.2%   | 45.4%   |
| V2    | 81.6%   | 94.4%   | 49.2%   | 63.3%   |
| V3    | 82.1%   | 95.7%   | 54.8%   | 72.2%   |
| V4    | 86.5%   | 95.2%   | 51.6%   | 77.4%   |
| V5    | 87.1%   | 95.2%   | 48.5%   | 75.8%   |
| V6    | 81.8%   | 100.0%  | 43.8%   | 56.2%   |


