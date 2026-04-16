# MIMIC Self-Learning Loop Results

**Model:** openai.gpt-oss-120b-1:0
**Run:** loop_mimic_20260415_0209
**Train:** 150 patients (80 poly, 70 mono) | **Eval:** 60 patients (29 poly, 31 mono)
**Batches:** 15 × 10 | **Seed:** 42

---

## Progression


| Round    | Learnings | Top-3       | Mono  | Poly  |
| -------- | --------- | ----------- | ----- | ----- |
| Baseline | 0         | 36/60 (60%) | 26/31 | 10/29 |
| R0       | 2         | 31/60 (52%) | 24/31 | 7/29  |
| R1       | 2         | 33/60 (55%) | 26/31 | 7/29  |
| R2       | 2         | 35/60 (58%) | 25/31 | 10/29 |
| R3       | 2         | 33/60 (55%) | 25/31 | 8/29  |
| R4       | 4         | 29/60 (48%) | 22/31 | 7/29  |
| R5       | 4         | 30/60 (50%) | 21/31 | 9/29  |
| R6       | 6         | 30/60 (50%) | 22/31 | 8/29  |
| R7       | 9         | 30/60 (50%) | 23/31 | 7/29  |
| R8       | 10        | 34/60 (57%) | 25/31 | 9/29  |
| R9       | 11        | 34/60 (57%) | 25/31 | 9/29  |
| R10      | 12        | 31/60 (52%) | 23/31 | 8/29  |
| R11      | 14        | 36/60 (60%) | 25/31 | 11/29 |
| R12      | 14        | 35/60 (58%) | 25/31 | 10/29 |
| R13      | 14        | 34/60 (57%) | 26/31 | 8/29  |
| R14      | 14        | 36/60 (60%) | 25/31 | 11/29 |


**Best round:** R11 / R14 — Top-3: 36/60 (60%), ties baseline

---

## Run 2 — Fixed (10 Drugs, Age/Sex/Race) — Full Eval (1208 patients)


| Round         | Learnings | Top-3                | Mono (n=773)        | Poly (n=435)        |
| ------------- | --------- | -------------------- | ------------------- | ------------------- |
| Baseline      | 0         | 642/1208 (53.1%)     | 483/773 (62.5%)     | 159/435 (36.6%)     |
| **R7 (best)** | **15**    | **831/1208 (68.8%)** | **619/773 (80.1%)** | **212/435 (48.7%)** |


---

## Run 2 — Fixed (10 Drugs, Age/Sex/Race)

**Model:** openai.gpt-oss-120b-1:0
**Run:** loop_mimic_20260415_0325
**Fix:** Truncate at "Brief Hospital Course:" (removes drug name cues), 10 Uganda drugs only, age/sex/race prepended
**Train:** 150 patients | **Eval:** 60 patients (40 mono, 20 poly) | **Batches:** 15 × 10 | **Seed:** 42


| Round    | Learnings | Top-3       | Mono  | Poly  |
| -------- | --------- | ----------- | ----- | ----- |
| Baseline | 0         | 30/60 (50%) | 24/40 | 6/20  |
| R0       | 5         | 37/60 (62%) | 26/40 | 11/20 |
| R1       | 8         | 41/60 (68%) | 30/40 | 11/20 |
| R2       | 12        | 32/60 (53%) | 24/40 | 8/20  |
| R3       | 15        | 41/60 (68%) | 30/40 | 11/20 |
| R4       | 15        | 35/60 (58%) | 28/40 | 7/20  |
| R5       | 15        | 39/60 (65%) | 29/40 | 10/20 |
| R6       | 14        | 36/60 (60%) | 28/40 | 8/20  |
| R7       | 15        | 44/60 (73%) | 33/40 | 11/20 |
| R8       | 15        | 43/60 (72%) | 34/40 | 9/20  |
| R9       | 15        | 41/60 (68%) | 31/40 | 10/20 |
| R10      | 15        | 42/60 (70%) | 33/40 | 9/20  |
| R11      | 15        | 43/60 (72%) | 32/40 | 11/20 |
| R12      | 16        | 39/60 (65%) | 30/40 | 9/20  |
| R13      | 19        | 39/60 (65%) | 28/40 | 11/20 |
| R14      | 15        | 40/60 (67%) | 30/40 | 10/20 |


**Best round:** R7 — Top-3: 44/60 (73%)

---

## Key Observations (Run 2)

**1. Leakage removal dramatically changes the baseline**
Baseline drops from 60% → 50% top-3. Confirms Run 1 was partially exploiting BHC drug name cues.

**2. The loop now actually improves over baseline**
R7 reaches 73% top-3 (+23pp over baseline 50%). R8/R11 also hit 72%. Learning is working — architect is finding real clinical signal, not note-reading tricks.

**3. No catastrophic dip**
Learnings ramp to 15 by R3 and stay there. No R4 collapse like Run 1. Stable accumulation with genuine oscillation around ~65-70%.

**4. Mono improved substantially**
Mono top-3: 24/40 (60%) baseline → 34/40 (85%) at R8. Run 1 mono was already 84% at baseline — again confirming Run 1 baseline was inflated by leakage.

**5. Poly improved too**
Poly top-3: 6/20 (30%) baseline → 11/20 (55%) at R0/R1/R3/R7/R11. Meaningful gain on hard cases.

**6. Round 7 — what drove the peak (73% top-3)**
R7 was the best round. The architect batch had 7/10 correct. Dominant errors: over-prescribing (retaining acutely-introduced drugs without discharge continuation orders) and unwarranted dose escalation. Four architect moves:

- **Added L14**: Only retain a drug if there is an explicit continuation statement or directive; default to omitting drugs introduced only acutely
- **Added L15**: Don't propose poly-therapy when the discharge list specifies a single ASM
- **Edited L7**: Dose escalation requires an explicit discharge order, not just clinical reasoning
- **Removed L9**: Auto-add long-acting BZD rule dropped — was adding spurious clonazepam

**Full R7 learnings (15 total):**

1. Active dose titration or documented tolerance → predict continuation/add-on, not reduction/cessation
2. Include an ASM if it appears in an explicit discharge list **or** clear clinical indication exists (breakthrough seizure, high seizure risk)
3. Documented good tolerance overrides side-effect mitigation rules (no reflexive BZD adjuncts)
4. Therapeutic drug levels + low seizure burden = strong evidence to maintain regimen unchanged
5. Discontinue when: explicit stop language, documented side-effects/failed trial, transition narrative, **or IV loading dose with no explicit continuation intent**
6. Patient/clinician preference to stop or avoid a drug → exclude it, no exceptions
7. Dose increase requires documented seizure type, adherence check, and explicit discharge order
8. Any drug in discharge "Medication" section not on admission list → treat as newly added ASM
9. Transition narrative ("tapering off X → Y → back to X due to breakthrough") = discontinuation of intermediate drug even without explicit stop
10. Document intolerance/allergy → exclude that drug only (not class-wide unless explicitly stated)
11. Acute focal deficits, altered mental status, or high-risk features → add prophylactic ASM (levetiracetam default)
12. Existing adjunctive ASMs on med list + no directive to add → maintain current regimen, don't augment
13. Acute symptomatic high-frequency seizures post-stroke + IV phenytoin load → infer phenytoin continuation at discharge unless explicitly stopped
14. Only retain for discharge if explicit continuation statement exists; otherwise omit acutely-introduced drugs *(new at R7)*
15. Discharge list says single ASM → don't propose poly-therapy *(new at R7)*

**Medically relevant signal:** L2, L4, L5, L7, L8, L9, L11, L13 are genuine clinical rules — not note-reading. L11 (levetiracetam for acute neuro deficits) and L13 (phenytoin post-stroke) are condition-specific. L5's IV-load caveat and L9's transition narrative rule show the model learning to interpret clinical course, not just search for drug names.

---

## Run 3 — Multi-Agent (No Leakage, 10 Drugs, Age/Sex/Race) — Full Eval (1208 patients)


| Round         | Agents | Top-3                | Mono (n=773)        | Poly (n=435)        |
| ------------- | ------ | -------------------- | ------------------- | ------------------- |
| Baseline      | 0      | 649/1208 (53.7%)     | 482/773 (62.4%)     | 167/435 (38.4%)     |
| **R3 (best)** | **4**  | **815/1208 (67.5%)** | **591/773 (76.5%)** | **224/435 (51.5%)** |


---

## Run 3 — Multi-Agent (No Leakage, 10 Drugs, Age/Sex/Race)

**Model:** openai.gpt-oss-120b-1:0
**Run:** loop_mimic_20260415_0354
**Train:** 150 patients | **Eval:** 60 patients (40 mono, 20 poly) | **Batches:** 15 × 10 | **Seed:** 42


| Round    | Agents | Top-3       | Mono  | Poly  |
| -------- | ------ | ----------- | ----- | ----- |
| Baseline | 0      | 30/60 (50%) | 23/40 | 7/20  |
| R0       | 1      | 37/60 (62%) | 27/40 | 10/20 |
| R1       | 2      | 39/60 (65%) | 30/40 | 9/20  |
| R2       | 3      | 40/60 (67%) | 31/40 | 9/20  |
| R3       | 4      | 43/60 (72%) | 33/40 | 10/20 |
| R4       | 5      | 43/60 (72%) | 33/40 | 10/20 |
| R5       | 5      | 38/60 (63%) | 28/40 | 10/20 |
| R6       | 4      | 39/60 (65%) | 31/40 | 8/20  |
| R7       | 4      | 41/60 (68%) | 30/40 | 11/20 |
| R8       | 5      | 41/60 (68%) | 32/40 | 9/20  |
| R9       | 5      | 41/60 (68%) | 31/40 | 10/20 |
| R10      | 5      | 30/60 (50%) | 23/40 | 7/20  |
| R11      | 5      | 32/60 (53%) | 23/40 | 9/20  |
| R12      | 5      | 29/60 (48%) | 22/40 | 7/20  |
| R13      | 5      | 36/60 (60%) | 27/40 | 9/20  |
| R14      | 5      | 36/60 (60%) | 27/40 | 9/20  |


**Best round:** R3/R4 — Top-3: 43/60 (72%)
**Final agents:** 4

### Multi-Agent Round 7: Final Agent Prompts

The best multi-agent run ultimately converged on four active agents:

| Count | Agent prompts |
| ----- | ------------- |
| 4 | `SeizureControlEvaluator`, `MedicationIntentExtractor`, `AEDLabToxicityEvaluator`, `ComprehensiveMedicationListExtractor` |

Round-7 prompt text for the four agents:

```text
SeizureControlEvaluator:
You are a specialist agent that evaluates seizure control and medication necessity. Extract from the clinical note the recent seizure frequency, date of last seizure, any trend in seizure occurrence, therapeutic drug levels of current antiseizure medications, documented adverse effects, and explicit clinician statements about medication effectiveness. Summarize in 2–4 sentences whether the current regimen appears adequate and flag any drugs that may be safely continued or omitted, without suggesting any medication changes.

MedicationIntentExtractor:
You are a specialist agent that extracts clinician‑stated medication intent and adherence cues with a focus on discharge decisions. Identify any explicit statements about starting, stopping, increasing, decreasing, or maintaining a specific drug, and clearly note whether the medication is to be continued at discharge, discontinued at discharge, or planned for future initiation. Do NOT infer intent or suggest continuation when the note does not state it directly. Also capture adherence information such as missed doses, non‑compliance, or patient concerns about a medication. Surface each finding as a concise observation in 2–4 sentences for the predictor.

AEDLabToxicityEvaluator:
You are a specialist agent that evaluates laboratory test results for potential adverse effects of antiseizure medications. Identify abnormal hematologic, hepatic, renal, or metabolic values that are known side effects of the patient’s current AEDs, link each abnormality to the most plausible culprit medication, and summarize the toxicity concern in 2–4 plain‑text sentences, without prescribing any changes.

ComprehensiveMedicationListExtractor:
You are a specialist agent that compiles the complete antiseizure medication list for the patient. Scan admission and discharge medication tables, prior visit summaries, pharmacy‑system references, and any narrative statements about ‘no medication changes’, discontinued drugs, or outpatient chronic AEDs. Distinguish between active AEDs at discharge, discontinued AEDs, and chronic outpatient AEDs not listed in the current admission. Summarize in 2–4 sentences the full set of active antiseizure drugs the patient should be on, noting any missing or ambiguous entries that need clarification.
```

---

## Classical Baseline — Naive Bayes

**Cohort:** 1208 first-admission MIMIC epilepsy patients (primary G40/345 dx, Neurology service)
**Eval:** 5-fold patient-stratified CV (stratified by mono/poly), V1 only — 80% train / 20% test per fold, all 1208 patients appear in exactly one test fold
**Features:** ICD codes + demographics only (no LLM)


| Mode        | n        | EM@3      | Jaccard   | Mono EM@3 (n=773) | Poly EM@3 (n=435) |
| ----------- | -------- | --------- | --------- | ----------------- | ----------------- |
| unigram     | 1208     | 42.6%     | 0.582     | 57.4%             | 16.3%             |
| bigram      | 1208     | 42.9%     | 0.585     | 57.4%             | 17.0%             |
| **trigram** | **1208** | **44.0%** | **0.593** | **60.9%**         | **13.8%**         |
| fourgram    | 1208     | 43.5%     | 0.584     | 59.6%             | 14.7%             |


Best: **trigram 44.0% EM@3** (SeizureType × intractability flag).

Context: Uganda bigram baseline is 46.9% EM@3 on a similar task. MIMIC is slightly lower primarily because 43% of patients have `SeizureType=unknown` (ICD G40.9xx unspecified) — the LLM-extracted Uganda features give seizure type for nearly all patients.

---

## Full Picture — All Methods on MIMIC (n=1208)


| Method                 | Top-3 EM  | Mono  | Poly      |
| ---------------------- | --------- | ----- | --------- |
| EpiPick                | 69.7%     | 69.7% | —         |
| Naive Bayes (trigram)  | 44.0%     | 60.9% | 13.8%     |
| Single-agent baseline  | 53.1%     | 62.5% | 36.6%     |
| Single-agent R7 (best) | **68.8%** | 80.1% | 48.7%     |
| Multi-agent baseline   | 53.7%     | 62.4% | 38.4%     |
| Multi-agent R3 (best)  | 67.5%     | 76.5% | **51.5%** |


† Evaluated on mono patients only: 539/773. EpiPick ranks single drugs rather than polytherapy regimens.

Single-agent self-learning peaks slightly higher overall (68.8% vs 67.5%). Multi-agent has a small edge on polytherapy (51.5% vs 48.7%).

---

## Why MIMIC Is Not the Right Benchmark for De Novo Prescribing

**MIMIC discharge notes are retrospective clinical summaries, not prospective decision inputs.**

When a MIMIC note is written, the treatment course is already complete. The admitting physician saw the patient, made a diagnosis, initiated therapy, observed the response, and is now documenting what happened. The note is a record of a closed loop. Critically, this means the note implicitly encodes the answer — not through explicit drug names, but through the narrative logic of a resolved case.

Consider the structural difference in how the same clinical fact appears:

> **Uganda:** *"Patient had a seizure two days ago."*

> **MIMIC:** *"Patient had a seizure two days ago. She was given [DRUG] in the ED, which terminated the event. She was monitored overnight with no further episodes."*

After lexical redaction, MIMIC becomes: *"Patient had a seizure two days ago. She was given [X] in the ED, which terminated the event."* The drug name is gone, but the inference is not — something was given, it worked, the case is closed. Whatever X is, it is the discharge medication. No clinical reasoning is required to reach this conclusion; only document comprehension.

This is the fundamental mismatch. The Uganda task asks: *given observations, what should be prescribed?* The MIMIC task, structurally, asks: *given a record of what was prescribed and how it went, reconstruct what was prescribed.* One requires de novo clinical judgment. The other requires reading comprehension and set arithmetic over the admissions medication list.

**Why lexical cleaning cannot fix this.**

Our loader already strips from "Brief Hospital Course:" onward, removing the most obvious leakage. But the causal and temporal structure survives. The HPI still contains statements like "loaded with [X] in the ED," "titrated [Y] over two days," or "held [Z] due to altered threshold." These encode the answer through tense, outcome framing, and section logic — not drug names. A model that has seen thousands of discharge notes learns that a loading dose in the ED almost always equals the discharge ASM for new-onset seizure. It does not need to know the drug name to exploit this pattern. The Run 1 baseline (60%) vs Run 2 baseline (50%) confirms this: stripping BHC drops baseline by 10pp, but the remaining 50% is still anchored to structural cues, not clinical reasoning.

Concretely, even after truncation a model can answer the task by:
1. Checking Medications on Admission (no prior ASMs for a new-onset case)
2. Seeing the HPI describes an acute treatment given during the ED visit
3. Concluding: whatever was started = discharge ASM

That is arithmetic, not medicine.

**Why LLM rewriting is not a solution.**

The obvious workaround — pass the truncated note through an LLM and ask it to rewrite the note as if the outcome were unknown — is not viable. The rewriting model must remove all forward-looking clinical resolution (treatment responses, stabilization language, outcome statements) and replace it with neutral uncertainty. In doing so, it necessarily introduces its own prior about what a pre-decision note looks like, hallucinating Uganda-style ambiguity onto a MIMIC context that was never ambiguous. The resulting synthetic note is neither faithful to the original clinical facts nor a clean counterfactual — it is a third artifact with its own biases and hallucinations, making any evaluation on it uninterpretable.

**The conclusion.**

MIMIC discharge notes are the wrong data for benchmarking de novo prescribing reasoning. The self-learning loop on MIMIC does learn something real — clinical language, polypharmacy structure, note-to-discharge reconciliation — and the R7 learnings (L11: levetiracetam for acute neuro deficits, L13: phenytoin post-stroke) demonstrate genuine condition-specific signal. But the majority of learned policies are discharge-intent parsing rules, not reusable drug-selection principles. Accuracy on MIMIC measures note reconciliation, not clinical judgment.

The Uganda cohort, where notes are prospective encounter records and prescriptions are genuinely underdetermined by the note text, is the correct evaluation surface for the claim we are making. MIMIC results are best reported as a secondary finding: warm-start utility and generalizability across note styles, not evidence of clinical reasoning capability.
