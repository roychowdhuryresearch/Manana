# Doctor Evaluation: Consilium vs Self-Learning (Buffer Multi)

Reviewer: Raj (neurologist). 20 patients — 10 CSV (cohort A), 10 PDF (cohort B), each shown across 3 visits for both systems. 5 questions per case.

**Questions:**

1. `seizure_type` — Was the seizure type correctly identified? (Yes / Partially / No)
2. `seizure_activity` — Was the current seizure burden/severity accurately assessed? (Yes / Partially / No)
3. `medications` — Were the patient's current medications correctly accounted for? (Yes / Partially / No)
4. `circumstances` — Was the drug selection reasoning clinically sound for this patient? (Yes / Partially / No)
5. `usefulness` — How useful was this system? (Very useful / Somewhat useful / Not useful)

Note: Q4 and Q5 were not completed for several CSV cases (see per-table denominators).

---

## Q1–Q3: Clinical accuracy (all 30 visits answered per cell)

Denominator = 30 for all cells.


| System    | Cohort | seizure_type (Yes) | seizure_activity (Yes) | medications (Yes) |
| --------- | ------ | ------------------ | ---------------------- | ----------------- |
| Consilium | CSV    | 30/30              | 30/30                  | 30/30             |
| Self      | CSV    | 29/30              | 30/30                  | 30/30             |
| Consilium | PDF    | 30/30              | 30/30                  | 30/30             |
| Self      | PDF    | 30/30              | 30/30                  | 30/30             |


The one non-Yes: Self / CSV — `39_Najjemba Christine` V2, seizure_type = **Partially**.

---

## Q4: Drug selection reasoning clinically sound?

CSV cells were only partially answered (Q4 was left blank for 8/10 CSV Consilium patients and 5/10 CSV Self patients).


| System    | Cohort | Answered | Yes   | Partially | No  |
| --------- | ------ | -------- | ----- | --------- | --- |
| Consilium | CSV    | 6/30     | 6/6   | 0         | 0   |
| Self      | CSV    | 15/30    | 15/15 | 0         | 0   |
| Consilium | PDF    | 30/30    | 30/30 | 0         | 0   |
| Self      | PDF    | 30/30    | 30/30 | 0         | 0   |


---

## Q5: Usefulness

Same missing-data pattern as Q4 for CSV.


| System    | Cohort | Answered | Very useful | Somewhat useful | Not useful |
| --------- | ------ | -------- | ----------- | --------------- | ---------- |
| Consilium | CSV    | 6/30     | 6           | 0               | 0          |
| Self      | CSV    | 15/30    | 14          | 1               | 0          |
| Consilium | PDF    | 30/30    | 28          | 1               | 1          |
| Self      | PDF    | 30/30    | 29          | 1               | 0          |


Exceptions:

- Self / CSV: `153_Kakande Huzaifa` V2 → Somewhat useful
- Consilium / PDF: `ATWONGYEIRE_ISRAEL_2` V1 → Not useful; V3 → Somewhat useful
- Self / PDF: `SHALOM_KEEZA` V2 → Somewhat useful

---

## Comment-by-Comment Analysis

Leakage comments excluded (see leakage note below). All others documented in order.

---

### CSV — Consilium (System A)

**39_Najjemba Christine, V3**

> "risperidone and methylphenidate are not AED, so there is no reason to recommend."

Risperidone and methylphenidate are already in this patient's regimen for behavioral/ADHD management — not drugs consilium invented. Consilium addressed them (recommended tapering risperidone, continuing methylphenidate). Raj's objection is about **scope**: the system should stay focused on ASMs and not comment on non-epilepsy drugs, even if clinically relevant.

---

**135_Best Betina, V1**

> "Baseline seizure frequency is not available. unclear from the chart note, how the patient is doing — but could be assumed that the seizures are uncontrolled. Thus, optimization of VPA is ideal."

Raj is supplying the correct clinical inference: when seizure frequency is ambiguous, assume uncontrolled and optimize the current ASM. Implies consilium either ranked VPA optimization too low or did not make this inference explicitly.

---

**333_Murungi Isaac, V2**

> "option 2 might be better. it is unclear from the history if the combination treatment would be better than monotherapy of VPA. given pt is stable on current regimen, it should not be changed. This could be in the prompt."

Prioritization error — patient is stable, so the guiding principle is continuity. System ranked options incorrectly. Raj also explicitly suggests this stability principle should be added to the prompt.

---

**10_Muduku Matthew, V2**

> "given the prior regimen was effective, this should be prioritize. Again, the seizure occurred as the medication was unavailable. the other options might be useful, incase drug remains unavailable in stock. There is a utility of the recommendations."

System misread drug unavailability as drug failure and ranked alternatives first. Correct action is to resume the effective prior regimen. Raj acknowledges the alternatives have utility but as fallbacks, not primary options.

---

**10_Muduku Matthew, V3**

> "optimizing current treatment should be prioritized, if it is working."

Same pattern as V2 — system failed to prioritize continuation of a working regimen. Recurring theme across this patient.

---

**157_Odong Raphael, V3**

> "In the output, the dosing should be very clear based on the weight and the titration schedule (step wise weight based escalation) should be clearly stated."

Not a drug choice error — an output format complaint. Raj wants explicit weight-based dosing and a stepwise titration schedule in the recommendation, not just drug names.

---

### CSV — Self (System B)

**39_Najjemba Christine, V2**

> "patient presented after 6 years."

Contextual observation — flagging the unusually long inter-visit gap. Unclear whether this is a criticism or just a note. Ambiguous signal.

---

**47_Mugisha Silver, V1**

> "System B reasoning is easier to follow."

Explicit preference for self over consilium on reasoning clarity. No elaboration on what specifically made it easier.

---

**47_Mugisha Silver, V2**

> "All three options are carbamazepine, which is appropriate as pt responded."

Positive — system correctly anchored all three options on CBZ since the patient had already responded to it. Concordant, coherent options praised.

---

**110_Manozi Angella, V2**

> "patient has been seizure free only for 5 months and dose reduction should not be recommended."

Clinical error by self — recommended de-escalation too early. 5 months seizure-free is insufficient to reduce the dose.

---

**266_Ssebunya Hashim, V1**

> "option 1 through 3 are related and are different scenarios that are considered with the same regimen."

Positive — options are coherent and inter-related rather than presenting divergent drug choices.

---

**266_Ssebunya Hashim, V2**

> "reasoning is coherent and all the options are related."

Same positive note repeated at the next visit — consistent internal logic across options.

---

**153_Kakande Huzaifa, V2**

> "The LLM identified that the CBZ was discontinued in the interim. Given seizure control is not achieved on the current regimen, would optimize the current meds as in option 1. Option 2, while is a correct choice, it is higher risk, given seizure freedom is not achieved yet."

Positive — system caught a mid-visit drug discontinuation. Raj endorses option 1 over option 2 (both acceptable, but option 2 is higher risk without seizure freedom established yet).

---

**153_Kakande Huzaifa, V3**

> "LLM recognizes the seizure type as it becomes clearer in third visit. New semiology is recognized and appropriately seizure type is recognized."

Positive — system updated its syndrome classification correctly as new clinical information accumulated across visits. Good longitudinal reasoning.

---

**202_Kasule Amil, V2**

> "identifies drug regimen discrepancies in what was prescribed and what patient is currently taking."

Positive — system caught the mismatch between what was prescribed and what the patient was actually taking. Clinically important and non-trivial.

---

**202_Kasule Amil, V3**

> "all three recommendations are concordant. This is better than system A, which provides — appropriate but different choices."

Direct head-to-head comparison: self's concordant options explicitly preferred over consilium's divergent options. Raj is not saying consilium's options were wrong — just that they pointed in different directions, which is less useful clinically.

---

### PDF — Consilium (System A)

**JANELLE_ELIZABETH_2, V3**

> "severe cases of drug-refractory epilepsy — on 3 AEDs, usually, pt will likely continue to have seizures and difficult to control."

Contextual note about prognosis, not a system error. Raj is observing that this is a hard case regardless of what any system recommends.

---

**SHALOM_KEEZA, V2**

> "up titration is appropriate."

Positive endorsement of consilium's recommendation to titrate up.

---

**ATWONGYEIRE_ISRAEL_2, V1**

> "will not recommend stopping AEDs, given the duration of the seizure freedom is not known. so option 1 is not appropriate."

Clinical error — consilium's option 1 recommended stopping AEDs without knowing how long the patient had been seizure-free. This is the case that received "Not useful."

---

**ATWONGYEIRE_ISRAEL_2, V2**

> "recommending stopping keppra due to side effects."

Positive — correct recommendation. System identified a side effect rationale for stopping Keppra.

---

**ATWONGYEIRE_ISRAEL_2, V3**

> "when patient is seizure free, should continue with the current AED, unless side effects are present."

Clinical error — system recommended a regimen change for a seizure-free patient without a side effect justification. Contradicts the basic principle of not fixing what works.

---

**NAKISEKA_SHALOM, V2**

> "the LLM identifies, adherence issue."

Positive — system correctly flagged non-adherence as the likely cause of breakthrough seizures rather than drug failure.

---

### PDF — Self (System B)

**LINDA ROSEMARY, V2**

> "All three options are inter-related."

Positive — coherent, concordant options across the three recommendations.

---

**SHALOM_KEEZA, V2**

> "one option to increase dose is not provided."

Missing option — self did not include dose escalation as one of the three choices, which Raj considers appropriate for this patient.

---

**NAKISEKA_SHALOM, V2**

> "option 1 is appropriate and has least risk with highest benefit."

Positive endorsement of the system's top-ranked option.

---

## System A vs System B: What the Comments Show

### Direct comparisons (Raj explicitly names both)


| Patient           | Visit | Comment                                                                                                                                                                   |
| ----------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 47_Mugisha Silver | V1    | "System B reasoning is easier to follow" — self wins on readability                                                                                                       |
| 202_Kasule Amil   | V3    | "all three recommendations are concordant. This is better than system A" — self wins on option coherence; consilium's options were individually appropriate but divergent |


### Recurring positives for Self (B)

- **Option coherence**: 266_Ssebunya V1+V2, 47_Mugisha V2, LINDA ROSEMARY V2 — all praised for inter-related, concordant options
- **Longitudinal tracking**: 153_Kakande V2 (caught mid-visit CBZ discontinuation), 153_Kakande V3 (updated semiology), 202_Kasule V2 (caught prescribed vs. actual mismatch)
- **Reasoning clarity**: 47_Mugisha V1 explicit mention

### Recurring issues with Consilium (A)

- **Scope creep**: 39_Najjemba V3 — commented on non-ASM drugs when it shouldn't
- **Prioritization of stable patients**: 333_Murungi V2, 10_Muduku V2+V3 — consistently failed to prioritize continuity when patient is stable or seizure occurred due to unavailability not failure
- **Clinical errors (AED stopping)**: ATWONGYEIRE V1 and V3 — recommended stopping or changing AEDs without adequate justification

### Issues with Self (B)

- **Premature de-escalation**: 110_Manozi V2 — recommended dose reduction after only 5 months seizure-free
- **Incomplete options**: SHALOM_KEEZA V2 — missed the dose-increase option

### Positives for Consilium (A)

- SHALOM_KEEZA V2 (up-titration correct), ATWONGYEIRE V2 (Keppra stop correct), NAKISEKA_SHALOM V2 (adherence catch)

---

## Leakage Note

Three patient-visits had the doctor's plan visible in the input text — model not predicting, just reading:

- `SHALOM_KEEZA` V1 (PDF) — *"Plan to add lamotrigine"* in HPI
- `JANELLE_ELIZABETH_2` V1 (PDF) — *"bring in lamotrigine"* in HPI
- `157_Odong Raphael` V1 (CSV) — *"start on Carbamazepine"* in HPI

These visits should be excluded from accuracy analysis.