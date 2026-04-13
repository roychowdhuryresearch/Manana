# Self-Learning Multi-Agent Loop Results — 2026-04-13

## Eval Progression (held-out 60 cases, seed=42)


| Round    | Agents | Top-3       | Mono (/44) | Poly (/16) |
| -------- | ------ | ----------- | ---------- | ---------- |
| Baseline | 0      | 36/60 (60%) | 29/44      | 7/16       |
| R0       | 2      | 40/60 (72%) | 33/44      | 7/16       |
| R1       | 3      | 47/60 (78%) | 36/44      | 11/16      |
| R2       | 4      | 45/60 (75%) | 34/44      | 11/16      |
| R3       | 4      | 43/60 (72%) | 34/44      | 9/16       |
| R4       | 5      | 46/60 (77%) | 36/44      | 10/16      |
| R5       | 5      | 44/60 (73%) | 36/44      | 8/16       |
| R6       | 4      | 43/60 (72%) | 36/44      | 7/16       |


---

## Agent Spawn Progression

### R0 — ContinuityDetector + StructuralAgeValproateFlag

5 of 10 training cases wrong. Two clusters: patients 90 and 95 had explicit "continue current regimen" wording that was ignored, and patient 288 had structural brain injury (cerebral palsy) in a child ≥12 months where valproate was appropriate but missed. Two agents spawned in the same round — one for each cluster. ContinuityDetector surfaces explicit continuation intent; StructuralAgeValproateFlag surfaces the age + structural etiology combination, both without making drug recommendations.

### R1 — AdjunctTherapyDetector (+ StructuralAgeValproateFlag edited)

5 of 10 still wrong. StructuralAgeValproateFlag was overstepping — outputting drug suggestions instead of observations. Edited to remove any medication language. Separately, patients 90 (V1) and 58 (V1, V3) had breakthrough seizures on an existing regimen where adjunct therapy was needed but the system defaulted to monotherapy. AdjunctTherapyDetector spawned to flag persistent seizures despite current AEDs.

### R2 — NoChangeIntentDetector (+ AdjunctTherapyDetector edited)

AdjunctTherapyDetector was over-triggering — flagging adjunct need on generic seizure mentions rather than clear breakthrough evidence. Edited to require explicit uncontrolled-seizure language. Separately, patients 58 (V2), 74 (V1), and 320 (V3) all had implicit continuation intent — same meds, same doses, no change directive — that neither ContinuityDetector nor context alone caught. NoChangeIntentDetector spawned to cover implicit no-change signals via medication-list consistency.

### R3 — no change

No error pattern reached the ≥2-case quorum. Agents held.

### R4 — DoseAdequacyDetector (+ ContinuityDetector edited)

5 of 9 wrong, all from over-prescription. Two sub-patterns: ContinuityDetector was still missing implicit continuation cues (same meds, no directive), edited to explicitly cover that case. Patients 288 (V2) and 8 (V3) had sub-therapeutic doses or adherence problems where the system added a new AED instead of optimising the existing one. DoseAdequacyDetector spawned to flag under-dosing and adherence issues before any add-on is considered.

### R5 — no change

No error pattern reached quorum. Agents held.

### R6 — NoChangeIntentDetector pruned

Only 3 training cases in this final batch; 2 correct. The architect flagged NoChangeIntentDetector as redundant — its role had been absorbed by the edited ContinuityDetector over prior rounds, and it produced no useful output in R6. Pruned.

---

## Final Agents (4)


| Agent                                | Consilium Equivalent                         | Role                                                                                                                               |
| ------------------------------------ | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| ContinuityDetector                   | Treatment Response Analyst                   | Detects explicit and implicit clinician intent to maintain the current AED regimen unchanged                                       |
| StructuralAgeValproateFlag           | Seizure Diagnostician + Formulary Specialist | Flags structural brain etiology in patients ≥12 months to inform valproate suitability in LMIC formulary — no drug recommendations |
| AdjunctTherapyDetector               | Epileptologist                               | Identifies persistent seizures despite optimized therapy and signals genuine need for adjunct AED                                  |
| DoseAdequacyDetector                 | Pharmacologist                               | Flags sub-therapeutic doses or adherence problems before any add-on therapy is considered in LMIC resource-limited settings        |
| NoChangeIntentDetector*(pruned R6)* | Treatment Response Analyst                   | Detected implicit no-change intent via medication-list consistency — made redundant by edited ContinuityDetector                   |


