# TextGrad R11 Learnings — Fact Check

Run: `tg_20260417_2032_037e14` | Eval set: 60 cases (44 mono, 16 poly)

---

## Performance Progression


| Round    | Learnings    | Top-3 / 60  | Top-3 % | Mono (top-3) | Poly (top-3) |
| -------- | ------------ | ----------- | ------- | ------------ | ------------ |
| Baseline | 0 lines      | 41 / 60     | 68%     | 32 / 44      | 9 / 16       |
| R0       | 10 lines     | 47 / 60     | 78%     | 36 / 44      | 11 / 16      |
| R1       | 10 lines     | 41 / 60     | 68%     | 32 / 44      | 9 / 16       |
| R2       | 13 lines     | 43 / 60     | 72%     | 37 / 44      | 6 / 16       |
| R3       | 10 lines     | 44 / 60     | 73%     | 36 / 44      | 8 / 16       |
| R4       | 14 lines     | 43 / 60     | 72%     | 36 / 44      | 7 / 16       |
| R5       | 18 lines     | 44 / 60     | 73%     | 38 / 44      | 6 / 16       |
| R6       | 15 lines     | 45 / 60     | 75%     | 35 / 44      | 10 / 16      |
| R7       | 10 lines     | 40 / 60     | 67%     | 31 / 44      | 9 / 16       |
| R8       | 13 lines     | 47 / 60     | 78%     | 38 / 44      | 9 / 16       |
| R9       | 16 lines     | 47 / 60     | 78%     | 39 / 44      | 8 / 16       |
| R10      | 17 lines     | 44 / 60     | 73%     | 36 / 44      | 8 / 16       |
| **R11**  | **17 lines** | **48 / 60** | **80%** | **37 / 44**  | **11 / 16**  |
| R12      | 12 lines     | 46 / 60     | 77%     | 39 / 44      | 7 / 16       |
| R13      | 24 lines     | 47 / 60     | 78%     | 39 / 44      | 8 / 16       |
| R14      | 15 lines     | 46 / 60     | 77%     | 36 / 44      | 10 / 16      |
| R15      | 13 lines     | 39 / 60     | 65%     | 32 / 44      | 7 / 16       |


Peak: **R11 at 80%** (48/60). R15 crashes to 65% — dropped from analysis.

---

## Full Cohort Eval — TG R11 vs All Methods

### Table 1: Overall EM@3 and Jaccard


| Cohort      | Method                 | V1 EM@3  | V1 Jac   | V2 EM@3  | V2 Jac   | V3 EM@3  | V3 Jac   |
| ----------- | ---------------------- | -------- | -------- | -------- | -------- | -------- | -------- |
| **A (CSV)** | Single-agent           | 66.0     | .752     | 74.4     | .837     | 75.6     | .855     |
|             | Consilium              | **79.5** | **.864** | **88.0** | **.945** | **91.0** | **.935** |
|             | Self-learning (single) | 73.4     | .828     | 82.0     | .895     | 82.0     | .898     |
|             | Self-learning (multi)  | 71.8     | .800     | 83.5     | .898     | 85.9     | .921     |
|             | TextGrad R11           | 71.8     | .834     | 80.6     | .893     | 80.6     | .896     |
| **B (PDF)** | Single-agent           | 65.9     | .769     | 70.1     | .826     | 71.8     | .830     |
|             | Consilium              | **71.5** | **.818** | **83.0** | **.903** | **86.8** | **.934** |
|             | Self-learning (single) | 72.0     | .822     | 81.9     | .900     | 81.7     | .885     |
|             | Self-learning (multi)  | 76.2     | .849     | 85.9     | .930     | 88.3     | .937     |
|             | TextGrad R11           | 62.8     | .733     | 78.2     | .884     | 76.9     | .879     |


### Table 2: Monotherapy vs Polytherapy EM@3


| Cohort      | Method                 | Mono V1  | Mono V2  | Mono V3  | Poly V1  | Poly V2  | Poly V3  |
| ----------- | ---------------------- | -------- | -------- | -------- | -------- | -------- | -------- |
| **A (CSV)** | Single-agent           | 79.2     | 85.0     | 89.7     | 13.4     | 40.5     | 41.8     |
|             | Consilium              | **92.1** | **95.7** | **97.4** | 29.9     | **63.3** | **75.5** |
|             | Self-learning (single) | 86.7     | 91.8     | 91.6     | 24.5     | 50.0     | 59.7     |
|             | Self-learning (multi)  | 84.1     | 92.3     | 93.9     | 26.4     | 55.0     | 67.5     |
|             | TextGrad R11           | 83.7     | 89.0     | 90.7     | 23.9     | 52.4     | 57.1     |
| **B (PDF)** | Single-agent           | 76.3     | 80.9     | 82.1     | 41.1     | 50.4     | 54.8     |
|             | Consilium              | 80.0     | **94.1** | **95.7** | **51.1** | 62.8     | **72.2** |
|             | Self-learning (single) | 87.4     | 91.8     | 90.8     | 35.1     | 63.8     | 66.7     |
|             | Self-learning (multi)  | 90.5     | 97.0     | 96.1     | 42.3     | 65.6     | 75.4     |
|             | TextGrad R11           | 72.3     | 91.5     | 88.9     | 36.2     | 53.9     | 57.1     |


---

## Round 11 Learnings

- Age ≤ 5 y with generalized seizure phenotype → valproate first‑line essential AED (dose 15–30 mg/kg/day, target trough 50–100 µg/mL) [ILAE 2022 Guideline][Uganda NSTG 2023].
- Age ≤ 5 y with focal seizure phenotype → carbamazepine first‑line essential AED (dose 15–30 mg/kg/day, target trough 8–12 µg/mL) [ILAE 2022]; carbamazepine is contraindicated in generalized tonic‑clonic or myoclonic seizures because it may exacerbate fast‑in‑fast‑out neuronal firing [ILAE 2022].
- Children ≤ 5 y with myoclonic‑atonic (Doose) syndrome → valproate + ethosuximide combined as essential first‑line regimen (each 15–30 mg/kg/day) [European Consensus 2020][Uganda EML 2022].
- Phenobarbital is acceptable as first‑line alternative for focal seizures only when carbamazepine is contraindicated or unavailable; dose 5–10 mg/kg/day, max 200 mg [WHO EML 2023].
- Add‑on therapy (second essential AED) is permitted only after ≥ 4 breakthrough seizures within a 30‑day window while on a therapeutically dosed first‑line agent [Uganda NSTG 2023].
- Non‑essential agents (levetiracetam, clobazam, topiramate, lamotrigine, etc.) may be introduced only after documented failure of two essential first‑line AEDs or when both carbamazepine and valproate are contraindicated [Uganda NSTG 2023].
- Valproate contraindicated in females of child‑bearing potential unless benefit outweighs teratogenic risk; consider lamotrigine first [WHO 2022].
- Dose‑adjustment rule: if current dose ≤ 18 mg/kg/day and breakthrough seizures persist, prioritize adding an approved adjunct rather than further titration [Uganda NSTG 2023].
- Weight‑based dosing workflow: target dose = Weight (kg) × 15–30 mg/kg/day; round to nearest available tablet strength (e.g., 150 mg, 300 mg) [Uganda NSTG 2023].
- Monitoring feasibility in rural Ugandan settings: serum drug levels (valproate, carbamazepine) are obtainable at district hospitals; if unavailable, rely on clinical seizure frequency and adverse‑event checklist [Uganda STP 2022].
- Routine laboratory monitoring: complete blood count, serum sodium, and liver function tests every 3 months for newly started or dose‑changed carbamazepine or phenobarbital; every 6 months for stable valproate [Uganda NSTG 2023].
- Adverse‑event checklist for AED safety: hyponatraemia, rash/Stevens‑Johnson, elevated transaminases, excessive sedation, behavioral changes [ILAE 2022].
- Cost and availability hierarchy: carbamazepine – low cost, widely stocked; valproate – medium cost, occasional stock‑outs; phenobarbital – lowest cost, ubiquitous; levetiracetam – higher cost, limited availability [Uganda EML 2022].
- Adherence‑friendly dosing: children ≤ 5 y should receive twice‑daily regimens for valproate, carbamazepine, and ethosuximide to match school schedules and improve compliance [Uganda NSTG 2023].
- Risk‑benefit framing template: Benefit = seizure freedom, therapeutic dosing, no observed toxicity; Risk = potential neuro‑cognitive impact (valproate), hepatic toxicity (monitor LFTs), sedation (phenobarbital) [WHO 2022].
- Backup drug for intolerance to essential AEDs: levetiracetam (dose 20–30 mg/kg bid) is preferred second‑line adjunct when valproate or carbamazepine cannot be used, given its favorable safety profile and minimal monitoring requirements [Uganda EML 2022].
- Single‑action decision rule: if patient is seizure‑free ≥ 90 days, dose is within therapeutic window, and no toxicity is documented → continue current monotherapy unchanged; do not consider alternatives unless a contraindication or breakthrough threshold is met [Uganda NSTG 2023].

---

## Part 1: Citation Verification


| Citation in TG Learnings    | Verdict                  | Reality                                                                                                                 |
| --------------------------- | ------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `[Uganda NSTG 2023]`        | **FABRICATED NAME**      | Real doc is "Uganda Clinical Guidelines (UCG) 2023" — "NSTG" is an Indian abbreviation, not Ugandan                     |
| `[Uganda EML 2022]`         | **FABRICATED**           | Real doc is "Essential Medicines and Health Supplies List for Uganda (EMHSLU) 2023" — no 2022 version found             |
| `[Uganda STP 2022]`         | **LIKELY FABRICATED**    | No evidence of a "STP 2022" Uganda document                                                                             |
| `[ILAE 2022 Guideline]`     | **VAGUE / CONFABULATED** | ILAE has various guidelines but no prominent unified "2022" first-line AED guideline — plausible-sounding invented name |
| `[European Consensus 2020]` | **PARTIALLY REAL**       | A Delphi consensus on Doose syndrome was published ~2020, but the specific claim attributed to it is wrong (see Part 2) |
| `[WHO EML 2023]`            | **REAL**                 | WHO Essential Medicines List 2023 exists                                                                                |
| `[WHO 2022]`                | **TOO VAGUE**            | WHO publishes many documents — unverifiable without specifics                                                           |


**Sources:**

- [Uganda Clinical Guidelines 2023](https://library.health.go.ug/sites/default/files/resources/Uganda%20Clinical%20Guidelines%202023.pdf)
- [EMHSLU 2023 — WHO](https://www.who.int/publications/m/item/uganda--essential-medicines-and-health-supplies-list-for-uganda-(emhslu)-2023-(english))
- [Delphi Consensus on Doose Syndrome 2020](https://www.sciencedirect.com/science/article/pii/S1059131120303812)
- [ILAE Guidelines index](https://www.ilae.org/guidelines)

---

## Part 2: Medical Claims Verification


| Learning                                                                                       | Verdict                                    | Notes                                                                                                                            |
| ---------------------------------------------------------------------------------------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| VPA first-line generalized epilepsy, 15–30 mg/kg/day, trough 50–100 µg/mL                      | **CORRECT**                                | All three numbers check out across multiple sources                                                                              |
| CBZ first-line focal seizures, trough 8–12 µg/mL                                               | **MOSTLY CORRECT**                         | CBZ therapeutic range is 4–12 µg/mL — the model cited only the upper half                                                        |
| CBZ contraindicated in generalized tonic-clonic or myoclonic seizures                          | **CORRECT for myoclonic, NUANCED for GTC** | Clear contraindication in myoclonic (aggravates); for generalized TC it is not absolute — VPA preferred but CBZ not fully banned |
| Doose syndrome → VPA + ethosuximide combined first-line                                        | **WRONG**                                  | Delphi consensus endorses VPA + **clobazam** first-line; ethosuximide is strongly recommended as **second-line**                 |
| PB 5–10 mg/kg/day, max 200 mg for focal seizures                                               | **PARTIALLY WRONG**                        | Pediatric maintenance is typically 3–5 mg/kg/day; 5–10 mg/kg/day is loading-dose territory                                       |
| Add-on therapy only after ≥ 4 breakthrough seizures in 30-day window                           | **FABRICATED THRESHOLD**                   | No such universal rule exists — the specific number is invented                                                                  |
| Non-essential AEDs (LEV, clobazam, TPM, LTG) only after failure of 2 essential first-line AEDs | **PLAUSIBLE**                              | Reflects step-therapy logic; binary "essential/non-essential" labeling is model-generated, not from a verified Uganda formulary  |
| Dose ≤ 18 mg/kg/day with breakthrough seizures → add adjunct rather than titrate               | **FABRICATED THRESHOLD**                   | "18 mg/kg/day" cutoff does not appear in any guideline — invented specific number                                                |
| VPA contraindicated in women of childbearing potential; consider lamotrigine                   | **CORRECT**                                | Confirmed by WHO, FDA, EMA — well-established                                                                                    |
| CBC, sodium, LFTs every 3 months for CBZ/PB; every 6 months for stable VPA                     | **BROADLY CORRECT**                        | Monitoring principles are real; exact intervals vary by guideline                                                                |
| Adverse-event checklist: hyponatremia, SJS, elevated LFTs, sedation, behavioral changes        | **CORRECT**                                | Standard known toxicities for these AEDs                                                                                         |
| LEV 20–30 mg/kg/day bid as backup second-line adjunct                                          | **LOW-END**                                | Typical range is 20–60 mg/kg/day; 30 is the low end — underdoses many patients                                                   |
| Seizure-free ≥ 90 days + therapeutic dose + no toxicity → continue unchanged                   | **REASONABLE PRINCIPLE**                   | Sensible conservative rule, but "90 days" threshold is not from a specific guideline                                             |


**Sources:**

- [Valproic Acid — StatPearls](https://www.ncbi.nlm.nih.gov/books/NBK559112/)
- [CBZ in Myoclonic/Generalized Seizures — Seizure Journal](https://www.seizure-journal.com/article/S1059-1311(20)30336-8/fulltext)
- [Doose Syndrome Delphi Consensus](https://www.sciencedirect.com/science/article/pii/S1059131120303812)
- [Valproate in Women of Childbearing Potential — WHO](https://www.who.int/news/item/02-05-2023-use-of-valproic-acid-in-women-and-girls-of-childbearing-potential)
- [Phenobarbital Dosing — Drugs.com](https://www.drugs.com/dosage/phenobarbital.html)

---

## Summary

The model's broad pharmacology is sound — it correctly maps seizure types to first-line drugs, flags key contraindications, and identifies monitoring requirements. However it **fabricates specific decision thresholds** ("4 seizures in 30 days", "18 mg/kg/day", "90-day" rule) with false precision, and **gets Doose syndrome wrong** (recommends ethosuximide where the consensus says clobazam).

The citation names for Uganda-specific documents are largely invented — the model knows Uganda has national guidelines and fabricates plausible abbreviations (NSTG, STP, EML 2022) that do not match the real document names or editions.

---

## Failure Modes

1. **Full prompt rewrite every round.** TextGrad replaces the entire learnings string on each optimizer step rather than appending to it. A single bad training batch can silently overwrite rules that were previously correct, with no recovery mechanism. This is the primary driver of the oscillation pattern seen above.
2. **No anti-forgetting guarantee.** Because the prompt is fully rewritten, good knowledge from earlier rounds can simply disappear. In this run, R7 (67%) actually falls *below* baseline (68%) — meaning the optimizer actively made things worse and retained nothing from the six rounds before it.
3. **Fabricated citations.** The optimizer draws on the model's parametric knowledge when rewriting, which causes it to generate confident-looking citations that do not exist or are named incorrectly (Uganda NSTG 2023, Uganda STP 2022, Uganda EML 2022). These look authoritative but cannot be verified or cited in a paper.
4. **Fabricated specific thresholds.** Closely related to the above — the model invents precise-sounding clinical numbers ("≥ 4 breakthrough seizures in 30 days", "≤ 18 mg/kg/day cutoff") that appear in no guideline. The broad pharmacological direction is usually correct, but the specifics are confabulated.
5. **No change transparency.** Since the whole prompt is rewritten each round, there is no record of what was added, removed, or silently modified. It is impossible to audit which rule caused a score change or to roll back a single bad update. The buffer approach maintains an explicit per-round append log by design.

6. **Trained on Cohort A, fails to generalise to Cohort B.** TextGrad was optimised entirely on the CSV cohort (Cohort A). On the held-out PDF cohort (Cohort B), V1 accuracy drops to 62.8% — well below even the no-learning baseline of 68% and 10+ points behind the self-learning buffer on the same cohort. The optimizer has overfit the learnings string to the distribution it was trained on.

7. **The learnings themselves show overfitting.** Reading R11 closely, the rules are written around age ≤ 5 pediatric thresholds, specific mg/kg targets, and cost/availability language that reflects Cohort A's patient mix. There is no mechanism to detect when a rule is too specific to the training distribution — the optimizer just keeps the text that minimised loss on the cases it saw.

8. **No self-correction across distributions.** The buffer loop processes patients from whatever cohort it runs on and builds rules from those errors — it adapts to the data in front of it. TextGrad has no such mechanism: once training ends, the prompt is frozen and cannot respond to new error patterns from a different patient population.

