# Related Work — Competitive Landscape

Comprehensive literature review for NeurIPS submission. Compiled 2026-03-26.

---

## Summary Table


| Paper               | Venue                    | Task                            | Method                                      | Data                              | Drugs      | Longitudinal             | Key Result                                       | Our Edge                                                                            |
| ------------------- | ------------------------ | ------------------------------- | ------------------------------------------- | --------------------------------- | ---------- | ------------------------ | ------------------------------------------------ | ----------------------------------------------------------------------------------- |
| **FLAME**           | NeurIPS 2025             | Med recommendation              | Fine-tuned LLM + GRPO                       | MIMIC-III (6,226 pts)             | 151 ATC-3  | Yes (multi-visit)        | Jaccard 0.484                                    | No reasoning traces, no LMIC, structured data only                                  |
| **DrugRec**         | NeurIPS 2022             | Med recommendation              | Causal debiasing + 2-SAT DDI                | MIMIC-III/IV                      | ~131 ATC-3 | Yes (k=2 visits)         | Jaccard 0.522                                    | No clinical reasoning, claims data, no LMIC                                         |
| **RareAgents**      | AAAI 2025                | Rare disease dx + treatment     | Multi-agent MDT (41 depts) + memory + tools | MIMIC-IV-Ext-Rare (4,760 pts)     | 122        | Yes (3.89 visits avg)    | Jaccard 0.411                                    | Western ICU data, rare diseases not epilepsy, no LMIC                               |
| **Wu et al.**       | arXiv 2025               | Safer therapy recommendation    | Multi-agent conflict-driven MDT             | 4 clinical vignettes              | Handful    | No                       | Single agent = multi-agent                       | Only 4 cases, no longitudinal, no LMIC; our ablations show multi-agent helps on OOD |
| **MDAgents**        | NeurIPS 2024 (Oral)      | Medical QA                      | Adaptive multi-agent (solo/group)           | 10 QA benchmarks                  | N/A        | No                       | Best on 7/10 benchmarks                          | QA benchmarks, not real prescriptions                                               |
| **SafeDrug**        | IJCAI 2021               | Med recommendation              | Dual molecular GNN                          | MIMIC-III                         | ~131 ATC-3 | Yes                      | Jaccard 0.356, 19% DDI reduction                 | Structured codes only, no reasoning                                                 |
| **MICRON**          | IJCAI 2021               | Med *change* prediction         | Recurrent residual networks                 | MIMIC-III                         | ~131 ATC-3 | Yes (change-aware)       | Closest task formulation to ours                 | Still MIMIC, structured codes, no clinical reasoning                                |
| **Hakeem et al.**   | JAMA Neurology 2022      | Predict ASM *response*          | Transformer on 16 features                  | 1,798 pts, 5 centers, 4 countries | 7 ASMs     | No                       | AUROC 0.65 pooled, 0.52-0.60 external            | Different task (response prediction, not drug selection); modest generalization     |
| **Park et al.**     | Sci Reports 2025         | Predict ASM *response* per drug | RF/XGBoost/CatBoost on 84 features          | 2,586 pts, South Korea            | 11 ASMs    | Partial (point outcomes) | AUC 0.686 (VPA best)                             | Response prediction not drug selection; single-center; no LLM reasoning             |
| **Devinsky et al.** | Epilepsy & Behavior 2016 | AED regimen recommendation      | ML on US claims data                        | Large US claims DB                | Unstated   | No                       | AUC 0.72                                         | Claims data only, no clinical detail, US adults only                                |
| **MedAgentBoard**   | NeurIPS 2025 D&B         | Multi-agent benchmark           | Benchmark eval                              | Multiple benchmarks               | N/A        | No                       | Multi-agent doesn't consistently beat single LLM | We show it helps specifically on OOD tasks                                          |


---

## Detailed Paper Analyses

### 1. FLAME — Fine-grained List-wise Alignment for Generative Medication Recommendation

- **Venue:** NeurIPS 2025 (Spotlight candidate). arXiv: 2505.20218
- **Task:** Predict medication set from patient visit history (diagnoses, procedures, clinical notes)
- **Method:** Two-stage: (1) drug-level binary classifier filters candidates, (2) list-wise policy does sequential add/remove edits using step-wise GRPO (Group Relative Policy Optimization) with potential-based reward shaping. Base model: Llama3.1-Aloe-Beta-8B
- **Data:** MIMIC-III: 14,207 visits, 6,226 patients, 151 medications (ATC-3)
- **Results:** Jaccard 0.484, F1 0.641 — SOTA on MIMIC-III medication recommendation
- **Key insight:** Removing clinical notes drops Jaccard from 0.484 to 0.410 — notes matter
- **vs Us:** Fine-tuning on structured Western ICU data. No reasoning traces. No LMIC. 151 generic drug classes vs our 10 specific ASMs. They optimize drug lists; we optimize reasoning quality

### 2. DrugRec — Debiased, Longitudinal and Coordinated Drug Recommendation

- **Venue:** NeurIPS 2022
- **Task:** Multi-label drug prediction from multi-visit EHR
- **Method:** Causal debiasing via front-door adjustment (symptoms → diagnoses/procedures → drugs). DDI control via 2-SAT constraint solving at inference. Models k=2 prior visits
- **Data:** MIMIC-III/IV, ~6,350 patients, ~131 ATC-3 medications, avg 2.59 visits
- **Results:** Jaccard 0.522, F1 0.677, DDI rate 0.060
- **vs Us:** Purely structural/statistical — no clinical reasoning, no free text understanding, no LMIC. Longitudinal but only 2.59 avg visits. The "causal" claims rely on strong untested structural assumptions

### 3. RareAgents — Autonomous Multi-disciplinary Team for Rare Disease Dx + Treatment

- **Venue:** AAAI 2025 (Oral). arXiv: 2412.12475
- **Task:** Rare disease differential diagnosis + medication recommendation
- **Method:** Attending physician agent selects from 41 specialist departments. Iterative MDT discussion. Dynamic long-term memory (retrieves similar past cases + patient's own prior visits). 5 medical tools (Phenomizer, LIRICAL, DrugBank, DDI-Graph, etc.)
- **Data:** RareBench-Public (1,197 cases, 498 diseases) + MIMIC-IV-Ext-Rare (4,760 patients, 18,522 admissions, 122 drugs, avg 3.89 visits)
- **Results:** Hit@1 0.559 (diagnosis), Jaccard 0.411 (treatment). Removing memory causes largest drop (-22.4%)
- **Agents:** 1 attending + dynamic selection from 41 departments (avg 12.5 for dx, 22.2 for treatment)
- **vs Us:** Closest architectural match. But: Western ICU data, 498 diseases vs our 1 disease deeply, no LMIC context, and their memory finding supports our longitudinal approach. We have 7 fixed domain-specific agents vs their 41 generic departments

### 4. Wu et al. — Lessons Learned from LLM Multi-agents in Safer Therapy

- **Venue:** arXiv July 2025 (2507.10911)
- **Task:** Therapy recommendation for chronic multimorbidity patients, resolving medication conflicts (DDIs, contraindications)
- **Method:** Three conditions: (1) Pure single-agent, (2) Single-agent with step-by-step reasoning, (3) Multi-agent with conflict-driven minimal MDT. GP detects conflicts, selectively assembles specialists
- **Data:** 4 clinical vignettes from multimorbidity CIG benchmark
- **LLMs:** GPT-4o, DeepSeek-V3, Qwen2.5, Mistral Small 3
- **Results:** Single-agent with reasoning matched multi-agent in most cases. MAS captured broader info but added unnecessary medications
- **vs Us:** Only 4 cases — too small to conclude. They test in-distribution (Western guidelines). Our claim is multi-agent helps specifically on OOD tasks where the single agent's prior is wrong. Their finding is a challenge we address with our ablation results showing clear multi-agent advantage

### 5. MDAgents — Adaptive Collaboration of LLMs for Medical Decision-Making

- **Venue:** NeurIPS 2024 (Oral). arXiv: 2404.15155
- **Task:** Medical QA across 10 benchmarks (MedQA, PubMedQA, etc.)
- **Method:** Dynamically assigns solo vs group structures (Primary Care, MDT, Integrated Care Team) based on complexity. Uses GPT-4
- **Results:** Best on 7/10 benchmarks, +4.2% over prior methods
- **vs Us:** QA benchmarks, not real patient drug prediction. No longitudinal data. No clinical validation against doctor decisions. Generic medical tasks, not disease-specific

### 6. Hakeem et al. — DL for Predicting Treatment Response in Newly Diagnosed Epilepsy

- **Venue:** JAMA Neurology 2022
- **Task:** Binary prediction: will patient achieve seizure freedom on first ASM? Drug is an INPUT feature, not prediction target
- **Method:** Transformer encoder-decoder on 16 binarized clinical features
- **Data:** 1,798 adults from 5 centers (Scotland, Malaysia, China, Australia). 7 ASMs
- **Results:** AUROC 0.65 pooled, 0.52-0.60 on external validation (barely above chance)
- **Limitations:** Adults only, first ASM only, no longitudinal, modest external generalization
- **vs Us:** Fundamentally different task (response prediction vs drug selection). Their poor external validation (0.52-0.60) supports our argument that tabular DL with small epilepsy cohorts doesn't generalize — LLM reasoning over clinical notes is a viable alternative

### 7. Park et al. — Personalized ASM Response Prediction Based on Clinical Signatures

- **Venue:** Scientific Reports (Nature) 2025
- **Task:** Binary per-drug response prediction (responder vs non-responder) using point outcomes
- **Method:** RF, XGBoost, CatBoost on 84 features (19 clinical + 33 lab + 18 MRI + 14 EEG). Separate model per drug
- **Data:** 2,586 adults from Seoul National University Hospital, South Korea. 11 ASMs mono + combos. 8,874 regimen evaluations
- **Results:** Best monotherapy AUC: VPA 0.686, LEV 0.614, CBZ 0.626. Best dual: LEV+CBM 0.764
- **Limitations:** Retrospective, single-center, no external validation. Small per-drug samples. No genetics
- **vs Us:** Response prediction not drug selection. South Korean adults vs Ugandan pediatric-dominant. No LLM, no reasoning traces. Their drug set overlaps ours but diverges (they have lacosamide/oxcarbazepine/perampanel; we have phenobarbital)

### 8. Devinsky et al. — Treatment Choice in Epilepsy Using Big Data

- **Venue:** Epilepsy & Behavior 2016
- **Task:** Recommend AED regimen with lowest likelihood of treatment change (retention proxy)
- **Method:** ML on US insurance claims data (UCB-IBM collaboration). Algorithm undisclosed
- **Data:** Large US claims database 2006-2011. Adults >16. Exact patient count unstated
- **Results:** AUC 0.72 for retention prediction. Only 13% of real prescriptions matched model
- **vs Us:** Claims data only (no clinical detail), retention ≠ efficacy, US adults only, opaque method. The 13% match rate highlights the gap between model-optimal and real prescribing — we directly predict what doctors prescribe

---

## Remaining Detailed Analyses

### 9. SafeDrug — Dual Molecular Graph Encoders for Safe Drug Combinations

- **Venue:** IJCAI 2021. arXiv: 2105.02711. ~218 citations
- **Task:** Multi-label drug set prediction with DDI minimization
- **Method:** Two molecular encoders: (1) Global MPNN on full molecular graphs, (2) Local bipartite encoder on BRICS substructure decomposition. Two RNNs encode longitudinal diagnosis/procedure sequences. DDI controlled via PID controller that dynamically adjusts loss weighting to hit a target DDI rate
- **Data:** MIMIC-III: 6,350 patients, 14,995 visits (avg 2.37), 131 ATC-3 medications, 448 DDI pairs
- **Results:** Jaccard 0.521, F1 0.677, DDI rate 0.059 (19% below ground truth rate of 0.081). DDI rate tunable from 0.007 to 0.072 via gamma parameter
- **vs Us:** Foundational baseline in the MIMIC med rec space. Requires structured ICD/ATC codes — cannot handle free text. No clinical reasoning. Only binary drug selection (no dosage). US ICU data only

### 10. MICRON — Change Matters: Medication Change Prediction

- **Venue:** IJCAI 2021. arXiv: 2105.01876. ~123 citations
- **Task:** Medication *change* prediction — predicts which drugs to add/remove relative to previous visit. Closest task formulation to our longitudinal setting
- **Method:** Recurrent residual network. Maintains persistent medication vector updated visit-by-visit. Health residual r(t) = h(t) - h(t-1) maps to medication update u(t). Two thresholds control add/remove decisions. Fewest parameters (275K) and fastest training of all baselines
- **Data:** MIMIC-III (6,335 pts, 14,960 visits, 131 drugs) + IQVIA PharMetrics Plus (3,023 pts, 30,794 visits, 155 drugs — private, outpatient)
- **Results:** Jaccard 0.523, F1 0.678, DDI 0.070
- **Longitudinal:** Core design — inherently sequential, maintains medication state across visits
- **vs Us:** Closest conceptual match for longitudinal med management. But: structured codes only, no free text, no clinical reasoning, no LMIC. Their change-prediction framing (add/remove from previous) mirrors how our doctors actually prescribe

### 11. Cho et al. — Pediatric Epilepsy AED Decision Support via Deep Learning

- **Venue:** BMC Medical Informatics and Decision Making 2024. ~7 citations
- **Task:** Per-drug binary response prediction: will vigabatrin / prednisolone / clobazam be effective? Separate CNN per drug. NOT drug selection — drug response prediction
- **Method:** Multi-channel CNN on (1) GloVe-embedded EEG report text, (2) numerical features (age, AED count, dose), (3) categorical (gender)
- **Data:** 1,000 pediatric patients, Severance Children's Hospital, Seoul (2010-2021). 7,507 EEG reports. Only 3 drugs modeled. 81% aged 0-5. Extreme class imbalance: <5% positive rate
- **Results:** Hold-out AUROC 0.93, PPV 0.91-0.97. BUT cross-validation PPV was 0.06-0.17 — massive gap suggesting potential data leakage
- **vs Us:** Only epilepsy-specific DL paper attempting drug recommendation. But: only 3 drugs (none overlapping with our 10), response prediction not selection, suspicious evaluation, single Korean center, no longitudinal, no LLM reasoning

---

## Positioning: What Nobody Has


| Dimension     | Best Existing                         | Consilium                                                 |
| ------------- | ------------------------------------- | --------------------------------------------------------- |
| Data source   | MIMIC-III/IV (Western ICU)            | Mulago Hospital Uganda (LMIC outpatient)                  |
| Patient count | ~6,226 (FLAME)                        | 699 longitudinal                                          |
| Drug space    | 131-151 ATC-3 classes                 | 10 specific ASMs                                          |
| Data type     | Structured ICD/ATC codes              | Free-text clinical notes                                  |
| Ground truth  | Drug codes from EHR                   | Actual doctor prescriptions                               |
| Visits        | 2.59 avg (MIMIC)                      | 3+ per patient, 1+ year                                   |
| Population    | US/EU adults                          | Ugandan, pediatric-dominant                               |
| Method        | Fine-tuned LLM OR generic multi-agent | 7 disease-specific specialist agents + adversarial debate |
| Output        | Drug list                             | Reasoning traces + drug list                              |
| LMIC          | None                                  | Core contribution                                         |


---

## Key Papers to Cite

### Must cite (direct competitors)

- FLAME (NeurIPS 2025) — SOTA LLM medication recommendation
- DrugRec (NeurIPS 2022) — causal debiasing for med rec
- RareAgents (AAAI 2025) — closest multi-agent architecture
- MDAgents (NeurIPS 2024) — adaptive multi-agent medical decisions
- SafeDrug (IJCAI 2021) — foundational GNN med rec
- MICRON (IJCAI 2021) — medication change prediction
- Hakeem (JAMA Neurology 2022) — epilepsy-specific DL baseline

### Must cite (supports our claims)

- Wu et al. (2025) — shows multi-agent doesn't help in-distribution; we show it helps OOD
- MedAgentBoard (NeurIPS 2025) — same finding; we address with ablations
- Nature Medicine 2025 — lack of LLM evidence in African clinical settings

### Should cite (context)

- Park et al. (Sci Reports 2025) — per-drug ASM response prediction
- Devinsky et al. (E&B 2016) — early big-data AED recommendation
- GAMENet (AAAI 2019), COGNet (WWW 2022), MoleRec (WWW 2023) — MIMIC med rec progression

