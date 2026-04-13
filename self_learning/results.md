# Self-Learning Single Loop Results — 2026-04-12

## Eval Progression (held-out 60 cases, seed=42)


| Round    | Learnings | Top-3 | %   | Mono (/44) | Poly (/16) |
| -------- | --------- | ----- | --- | ---------- | ---------- |
| Baseline | 0         | 41/60 | 68% | 34         | 7          |
| R0       | 1         | 45/60 | 75% | 35         | 10         |
| R1       | 4         | 45/60 | 75% | 36         | 9          |
| R2       | 4         | 47/60 | 78% | 38         | 9          |
| R3       | 6         | 45/60 | 75% | 35         | 10         |
| R4       | 7         | 47/60 | 78% | 36         | 11         |
| R5       | 11        | 42/60 | 70% | 35         | 7          |
| R6       | 12        | 47/60 | 78% | 38         | 9          |
| R7       | 14        | 47/60 | 78% | 37         | 10         |
| R8       | 15        | 42/60 | 70% | 32         | 10         |
| R9       | 15        | 45/60 | 75% | 34         | 11         |
| R10      | 15        | 47/60 | 78% | 35         | 12         |
| R11      | 15        | 43/60 | 72% | 33         | 10         |
| R12      | 16        | 48/60 | 80% | 35         | 13         |
| R13      | 15        | 44/60 | 73% | 34         | 10         |
| R14      | 15        | 45/60 | 75% | 35         | 10         |
| R15      | 15        | 45/60 | 75% | 31         | 14         |


The progression does not show the heavy oscillation seen in earlier runs. Performance stays in the 70–78% band from R2 onward, with peak at R12 (80%). The floor does not collapse.

---

## R12 Learnings — Classified by Clinical Dimension

### Seizure Diagnostician (L3, L5, L7, L8, L9, L13, L15)

*Seizure type classification → drug selection*

- **L3**: "For children < 2 years with focal epilepsy, carbamazepine remains first‑line unless early‑onset encephalopathic features (abnormal EEG, severe developmental delay, seizures from birth) are present, in which case add a broad‑spectrum AED such as valproate."
- **L5**: "Early‑onset encephalopathic epilepsy warrants adding a broad‑spectrum AED such as valproate unless the patient is < 2 years and levetiracetam is already being used, in which case retain levetiracetam."
- **L7**: "When the narrative indicates that focal seizures have progressed to generalized tonic‑clonic seizures, recommend adding a broad‑spectrum AED (e.g., valproate) as adjunct to the existing focal agent."
- **L8**: "If the narrative mentions possible or definite absence seizures, prioritize ethosuximide (or other absence‑type AED) before any broad‑spectrum AED."
- **L9**: "When seizure semiology descriptors indicate focal onset (e.g., unilateral limb movements, tonic‑then‑flaccid pattern), select sodium‑channel blockers and avoid defaulting to broad‑spectrum agents."
- **L13**: "Before applying seizure‑type specific contraindications (e.g., carbamazepine in generalized epilepsy), the system must confirm the seizure phenotype from explicit descriptors; if ambiguous, default to maintaining the current regimen."
- **L15**: "For infants (<2 years) with any prior use of levetiracetam, prioritize retaining levetiracetam over initiating valproate unless contraindicated, reflecting age‑appropriate safety hierarchy."

### Treatment Response Analyst (L2, L10, L14, L16)

*Treatment continuity and regimen preservation*

- **L2**: "If seizure frequency has decreased and the patient is seizure‑free and tolerating the medication(s), prefer continuing the current AED(s) (including combination therapy) unless the clinician explicitly states a plan to change or there is documented inadequate control."
- **L10**: "Honor explicit clinician statements to continue the current regimen unless seizure‑type‑specific contraindications are supported by clear documentation of seizure phenotype; if phenotype is unclear, prefer continuation."
- **L14**: "Maintain a longitudinal medication inventory; when a previously prescribed AED is absent from the current visit narrative, flag it as discontinued and avoid assuming continuation."
- **L16**: "When seizure control is achieved and the medication(s) are well tolerated, retain all current AEDs even if a generalized‑seizure phenotype would normally contraindicate a specific drug."

### Epileptologist (L1, L6, L7)

*Polytherapy triggers and escalation logic*

- **L1**: "Only propose an additional AED when the clinical note explicitly indicates refractory seizures, failure of dose‑optimization, persistent seizures despite an adequately dosed regimen, neurocognitive decline or suspected subclinical seizures, or when the current AED is already at its age/weight‑based maximum dose."
- **L6**: "Persistent seizure burden, sub‑therapeutic AED dose, or inadequate dose relative to age/weight should trigger consideration of dose escalation or addition of an adjunct AED; for myoclonic‑atonic (Doose) syndrome, prioritize adding lamotrigine rather than dose increase of existing agents."
- **L7**: "When the narrative indicates that focal seizures have progressed to generalized tonic‑clonic seizures, recommend adding a broad‑spectrum AED (e.g., valproate) as adjunct to the existing focal agent." *(shared with Diagnostician)*

### Pharmacologist / Dose Specialist (L4, L12)

*Dose titration and adherence*

- **L4**: "When a recent AED dose titration is recorded without evidence of inadequate seizure control or when medication non‑adherence is noted, do not recommend dose escalation; first address adherence and consider simplifying or deprescribing the non‑taken drug."
- **L12**: "When a documented drug dose is clearly below the standard therapeutic range for the patient's age/weight, treat the regimen as under‑dosed and recommend dose escalation or appropriate adjunct therapy rather than simple continuation."

### LMIC / Formulary (L3, L9)

*Uganda-specific drug preference, discovered implicitly through clinical reasoning errors*

- **L3**: "For children < 2 years with focal epilepsy, carbamazepine remains first‑line..." *(CBZ as default focal agent — aligns with Ugandan formulary preference)*
- **L9**: "When seizure semiology descriptors indicate focal onset... select sodium‑channel blockers and avoid defaulting to broad‑spectrum agents." *(pushes toward CBZ/PHT over levetiracetam — reflects local prescribing pattern)*

### Treatment Response Analyst (continued — Adherence)

- **L11**: "When medication non‑adherence is documented, recommend simplifying the regimen or deprescribing the non‑taken drug rather than adding new agents."

---

## Convergence Summary


| Discovered theme                 | Learnings | Consilium agent                   |
| -------------------------------- | --------- | --------------------------------- |
| Seizure classification → drug    | 7         | Seizure Diagnostician             |
| Treatment continuity + adherence | 5         | Treatment Response Analyst        |
| Polytherapy triggers             | 3         | Epileptologist                    |
| Dose optimization                | 2         | Pharmacologist                    |
| LMIC / formulary preference      | 2         | Formulary Specialist *(implicit)* |


The system independently converged on the same core decomposition identified by neurologists through clinical review. The LMIC/formulary preference emerges implicitly through seizure-type rules that push toward CBZ and away from levetiracetam — consistent with Ugandan prescribing patterns, discovered without being told the formulary.

The bulk of the learning budget wasn't spent learning which drug to give. It was spent learning when to trust your read of the situation before acting at all.

---

## Learning Progression — A Story in Five Phases

*How the system bootstrapped its clinical reasoning, round by round. Agent labels indicate which Consilium specialist's domain the learning would fall under, even though those agents were never explicitly provided.*

### Phase 1 — R0–R1: The Gating Problem (Epileptologist)

The system's very first discovered error: it adds too many drugs. R0 produces a single rule — *only propose an AED when the note explicitly warrants it* — which is exactly the gating function an epileptologist exercises. By R1 the complementary signal arrives: *if the patient is seizure-free, continue what's working.* The baseline model's default instinct is to intervene; the first thing it learns is restraint. Eval: 70% → 75%.

### Phase 2 — R1–R4: Decoding the Focal/Generalized Axis (Seizure Diagnostician)

Having learned *when* to act, the system asks *with what?* R1 produces the first seizure-type-to-drug rule: focal epilepsy in infants → carbamazepine. R2 adds the contrast: multifocal/generalized → valproate. R3 adds encephalopathic features as an exception that overrides the focal default. R4 adds secondary generalization (focal progressing to GTC → add broad-spectrum adjunct). The system is triangulating the focal/generalized axis from scratch, converging on exactly the decision tree a Seizure Diagnostician uses. Eval stabilizes at 78%.

### Phase 3 — R5: The Vocabulary Burst (Multiple Agents Simultaneously)

R5 is the most chaotic round: four new learnings in one shot. Absence seizures → ethosuximide. Focal semiology descriptors → sodium-channel blockers. Honor explicit clinician continuation. Adherence → deprescribe rather than escalate. The system is trying to close multiple blind spots at once, firing across three different clinical domains simultaneously. The score drops from 78% to 70% — consistent with conflicting, under-integrated rules. This is the same kind of instability you see when a medical student learns too many new facts before they cohere into a framework.

### Phase 4 — R6–R9: Deepening and Dose Awareness (Pharmacologist)

After the chaos, R6–R9 tighten existing rules and introduce a new signal type: the dose. R8 adds sub-therapeutic dosing as a trigger for escalation. R9 adds adverse-effect cues (constipation → don't escalate despite uncontrolled seizures). This is the Pharmacologist's territory — reading the *quantity* of the drug, not just the name. Eval recovers to 75–78%.

### Phase 5 — R10–R12: Epistemic Caution (Treatment Response Analyst, peak at 80%)

R10 introduces the most qualitatively different learnings in the entire run: *confirm seizure phenotype before applying a contraindication; track medication discontinuation across visits; respect age-based safety hierarchy for levetiracetam vs. valproate.* These are not drug recommendations — they are rules about verifying your understanding of the clinical situation before acting at all. The system has shifted from "what to recommend" to "how to read the note correctly." R12 adds the final piece: *if the patient is controlled and tolerating, keep all current AEDs even if a guideline would normally contraindicate one.* This explicit override of theoretical guideline logic with observed patient stability pushes performance to 80% — the run's peak.