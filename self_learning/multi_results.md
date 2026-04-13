# Self-Learning Multi-Agent Loop Results — 2026-04-12

## Eval Progression (held-out 60 cases, seed=42)


| Round    | Agents | Top-3       | Mono (/44) | Poly (/16) |
| -------- | ------ | ----------- | ---------- | ---------- |
| Baseline | 0      | 40/60 (66%) | 34/44      | 6/16       |
| R0       | 1      | 42/60 (70%) | 34/44      | 8/16       |
| R1       | 2      | 41/60 (68%) | 32/44      | 9/16       |
| R2       | 3      | 44/60 (73%) | 35/44      | 9/16       |
| R3       | 3      | 43/60 (72%) | 33/44      | 10/16      |
| R4       | 4      | 44/60 (73%) | 36/44      | 8/16       |
| R5       | 4      | 45/60 (75%) | 36/44      | 9/16       |
| R6       | 4      | 47/60 (78%) | 36/44      | 11/16      |
| R7       | 4      | 48/60 (80%) | 38/44      | 10/16      |
| R8       | 4      | 44/60 (73%) | 34/44      | 10/16      |
| R9       | 4      | 46/60 (77%) | 35/44      | 11/16      |
| R10      | 5      | 45/60 (75%) | 35/44      | 10/16      |
| R11      | 5      | 46/60 (77%) | 36/44      | 10/16      |
| R12      | 5      | 46/60 (77%) | 36/44      | 10/16      |
| R13      | 5      | 43/60 (72%) | 35/44      | 8/16       |
| R14      | 5      | 38/60 (63%) | 34/44      | 4/16       |
| R15      | 5      | 44/60 (73%) | 36/44      | 8/16       |


Peak: 80% at R6 (4 agents). Floor: 63% at R14. Stable band 72–80% from R5 onward.

---

## Agent Spawn Progression

### R0 — SeizureBurdenWatcher (Epileptologist)

First error pattern: over-prescribing add-on AEDs in 3 patients despite notes clearly documenting low or absent recent seizures. First agent spawned surfaces seizure burden as a gating signal — is the load actually high enough to warrant action? Same gating function the Epileptologist exercises: don't escalate unless the clinical picture demands it.

### R1 — SeizureSemiologyMapper (Seizure Diagnostician)

Wrong drug choice because the predictor missed semiology cues pointing to sodium-channel blocker efficacy (carbamazepine omitted entirely). SeizureSemiologyMapper added to surface seizure type from clinical descriptors. Corresponds directly to the Seizure Diagnostician — the system independently discovered that seizure type classification is its own orthogonal dimension.

*Note: by R2 the inspector flagged SeizureSemiologyMapper was over-stepping — suggesting drug classes rather than observations. Edited to remove drug references.*

### R2 — TreatmentIntentDetector (Treatment Response Analyst)

Two patients had explicit "continue" or "no change" directives that the predictor ignored. TreatmentIntentDetector added to surface clinician intent from the note. Corresponds to the Treatment Response Analyst — respecting what the clinician already decided.

### R4 — PriorMedicationExtractor (Treatment Response Analyst + Pharmacologist)

Errors from missing implicit prior AED use — drugs the patient was on but not named in the current note. PriorMedicationExtractor added to reconcile the current regimen from all mentions within the visit. Sits at the intersection of Treatment Response Analyst (continuity) and Pharmacologist (knowing exactly what the patient is taking).

### R10→R14 — MedicationChangeTracker → LongitudinalMedicationReconciler (Treatment Response Analyst)

R10: MedicationChangeTracker spawned to handle cross-visit medication inference. R14: architect pruned it (flagging changes that weren't there) and replaced with LongitudinalMedicationReconciler — same dimension, narrower and more conservative. Both correspond to the longitudinal tracking role of the Treatment Response Analyst.

---

## Final Agents (5)


| Agent                            | Consilium Equivalent                        | Role                                                                                                      |
| -------------------------------- | ------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| SeizureBurdenWatcher             | Epileptologist                              | Surfaces recent seizure frequency and seizure-free periods to suppress unnecessary add-on recommendations |
| SeizureSemiologyMapper           | Seizure Diagnostician + Formulary Specialist | Identifies seizure type from clinical descriptors (focal, generalized, absence, myoclonic)                |
| TreatmentIntentDetector          | Treatment Response Analyst                  | Detects explicit clinician continuation, addition, or change directives from the note                     |
| PriorMedicationExtractor         | Pharmacologist + Treatment Response Analyst | Reconciles the current AED regimen from all mentions in the current visit note                            |
| LongitudinalMedicationReconciler | Pediatrician                                | Infers current AED regimen from prior visits when the current note is ambiguous                           |


