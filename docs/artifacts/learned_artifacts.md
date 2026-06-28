# Learned Artifacts Across Optimization Methods

These are representative text artifacts from high-performing runs discussed in the arXiv paper. They are examples of what each adaptation method produces, not hand-written prompts.

The paper keeps the interpretation in the appendix and points here for the full text, so the arXiv PDF does not need to carry long prompt-like listings.

## TextGrad

TextGrad learns by rewriting a global instruction variable. In this setting, its artifacts can become highly specific numeric and resource-threshold rules.

```text
- Primary generalized tonic-clonic seizures in Ugandan children are treated first-line with valproate monotherapy; dose 15-30 mg/kg/day, max 60 mg/kg/day, with baseline liver-function tests before any dose change and repeat testing at 2 weeks then every 3 months.

- For children >15 kg use 200 mg valproate tablets; for <=15 kg use 100 mg/5 mL syrup, keeping volume <=5 mL per dose.

- Focal-onset seizures are treated first-line with carbamazepine; start 5-10 mg/kg/day divided BID, titrate to <=30 mg/kg/day, and limit to <=15 mg/kg/day in children with generalized hypertonia or cerebral palsy.

- Levetiracetam is a modest-penalty adjunct after documented valproate failure, defined as >=2 breakthrough seizures in 30 days on therapeutic valproate; start 0.2 mg/kg/day BID, titrate to 5-10 mg/kg/day, and obtain renal function before initiation.

- Pill-burden constraint: total tablets per dose <=2 and <=4 tablets per day; liquid formulations count as a single dose; exceed only for life-threatening seizure frequency.

- Resource availability: valproate tablets stocked nationwide; syrup limited to referral hospitals; carbamazepine tablets widely available; levetiracetam often stock-out at peripheral clinics; phenobarbital universally stocked.

- Cost hierarchy: zero-penalty agents are valproate, carbamazepine, and phenobarbital; modest-penalty agents are levetiracetam and lamotrigine; high-penalty agents are clobazam, clonazepam, ethosuximide, phenytoin, and topiramate.

- Monitoring schedule: valproate requires baseline LFT, repeat 2 weeks after change, then every 3 months; carbamazepine requires trough level after any dose increase >5 mg/kg/day or after breakthrough; phenobarbital requires platelet count and LFT every 6 months.
```

## ExpeL

ExpeL produces a ranked experience memory: recurring verbal lessons are stored with support counts and retrieved at inference time.

```text
1. When several guideline-appropriate first-line drugs are suitable for initiation, select the medication most commonly used locally, considering safety, patient-specific factors, and documented physician preference.

2. When no current antiepileptic medication is documented, choose the appropriate first-line drug based on seizure type, epilepsy classification, age-specific safety, weight-based dosing, and the locally endorsed treatment hierarchy: formulary, cost, and common prescribing patterns.

3. When multiple drug actions are clinically justified, such as adverse effect, ineffectiveness, or need for addition, combine all necessary actions in a single option; otherwise limit each option to one clearly justified action.

4. Prioritize continuation of a drug that is already prescribed unless the notes explicitly indicate ineffectiveness, adverse effects, or a need for change.

5. For pediatric patients, calculate the antiepileptic dose using the most recent weight measurement, apply the recommended mg/kg range, and round to the nearest available tablet or syrup strength.

6. Before stopping a medication, verify that it has been initiated for at least 4 weeks without reported adverse effects or lack of efficacy; recent initiation without issues warrants continuation unless the notes explicitly advise otherwise.
```

## DSPy-GEPA

DSPy-GEPA produces an optimized instruction for the DSPy program rather than a persistent clinical memory.

```text
Task: Predict the antiepileptic drug (ASM) prescription for a patient seen at the
Uganda epilepsy clinic, based solely on the free-text clinical notes provided.
The output must be three ranked regimen options, each showing the drug name
followed by an action (continue, start, or stop). The reasoning must be brief.

INPUT FORMAT
The only input the model will receive is a single string called clinical_notes.
The notes contain:
- Patient demographics (age, sex, weight, etc.)
- Clinical history, seizure description, examination findings
- Investigation results (EEG, imaging)
- A "Current drug regimen" section that may list one or more ASMs, sometimes with
  dosing instructions or a date of initiation.
- A separate "Prescription" or "Plan" section that may contain explicit instructions
  such as "start carbamazepine", "stop valproate", "step sodium valproate to 500 mg
  BD", "increase dose", "add clobazam", etc.

OUTPUT FORMAT
The assistant must return exactly three options in the order option_1, option_2,
option_3. Each option is a comma-separated list of <drug>:<action> pairs.
- <drug> must be one of the allowed drug names exactly as written:
  carbamazepine, clobazam, clonazepam, ethosuximide, lamotrigine, levetiracetam,
  phenobarbital, phenytoin, topiramate, valproate
- <action> must be one of: continue, start, stop
No other text, punctuation, or formatting is allowed.

Example:
  option_1: valproate:continue
  option_2: valproate:continue, levetiracetam:start
  option_3: valproate:stop, lamotrigine:start

After the three options, include a short reasoning paragraph (1-2 sentences) that
explains why the options were chosen. The reasoning must not list doses, dates, or
any information that is not needed for the decision.

GENERAL PRINCIPLES FOR GENERATING THE REGIMENS

1. Follow explicit prescription language.
   - "start X", "add X", or "initiate X"           -> <drug>:start
   - "stop X", "discontinue X", or "withdraw X"    -> <drug>:stop
   - "continue X", "maintain X", or the drug appears in the "Current drug regimen"
     without any stop/start directive               -> <drug>:continue

2. Dose-adequacy check (pediatric patients only).
   - When the patient is < 18 years old and the current dose of a drug is clearly
     below the typical therapeutic range (see table below), assume the clinician
     is titrating the dose; do not add another ASM.
   - Only suggest adding a new drug if the notes explicitly describe refractory
     seizures after an adequate dose has been reached, or if a second drug is
     directly mentioned.

3. Weight-based therapeutic ranges (approximate, for dose-adequacy assessment).
   | Drug           | Approx. daily dose range (mg/kg/day) |
   |----------------|--------------------------------------|
   | carbamazepine  | 15-20                                 |
   | clobazam       | 0.2-0.5                               |
   | clonazepam     | 0.01-0.03                             |
   | ethosuximide   | 20-30                                 |
   | lamotrigine    | 5-10                                  |
   | levetiracetam  | 20-40                                 |
   | phenobarbital  | 3-5                                   |
   | phenytoin      | 5-7                                   |
   | topiramate     | 5-9                                   |
   | valproate      | 30-40                                 |

   If the note provides a total daily dose (sum of all administrations) that is
   less than the lower bound of the range multiplied by the patient's weight,
   treat the regimen as "dose-under-titrated".

4. Ranking the three options.
   - Option 1: the regimen that matches the clinician's explicit orders exactly.
   - Option 2: a clinically reasonable alternative only if the clinician's order
     appears to be a dose change or titration (i.e., the drug is being continued
     at a sub-therapeutic dose). Keep the same primary drug and add a second drug
     only if the notes explicitly mention refractory seizures after an adequate
     dose, or a clear need for adjunct therapy.
   - Option 3: a fallback regimen that follows standard practice for the presented
     seizure type when the clinician's intent is ambiguous (e.g., switch to a
     broader-spectrum agent). This option must still respect the "no unnecessary
     polytherapy" rule and must not introduce drugs not mentioned anywhere in the
     notes.

5. Avoid over-prescribing.
   - Never add a drug that is not mentioned in the notes unless it is required by
     the ranking rule (Option 2 or 3) and the clinician has clearly indicated that
     monotherapy is insufficient after an adequate dose.
   - Do not suggest "stop" for a drug unless the notes explicitly request
     discontinuation or indicate a clear switch to another agent.

6. Handling ambiguous or missing information.
   - If no current regimen is described, infer that the patient is drug-naive.
     In that case, the most plausible first-line drug (based on seizure type
     described in the notes) becomes the "start" action in Option 1.
   - If seizure type is not specified, default to valproate as a broad-spectrum
     agent for children, unless contraindicated by the notes.

7. Concise reasoning.
   - Summarize in one or two sentences why the three options were chosen,
     referencing only the key signals (e.g., "physician explicitly instructed
     continuation of carbamazepine; dose appears sub-therapeutic, so a
     titration-only option is offered as option 2; option 3 proposes a
     broader-spectrum switch if refractory").

EXAMPLE (for illustration only -- do not output this)
clinical_notes: "...Current drug regimen: carbamazepine 100 mg od. Prescription:
                 increase to 100 mg bd..."
Output:
  reasoning: The clinician is titrating carbamazepine upward; no second drug is
             mentioned.
  option_1: carbamazepine:continue
  option_2: carbamazepine:continue, levetiracetam:start
  option_3: carbamazepine:stop, valproate:start

Follow these rules exactly to produce the three ranked regimen options and the
brief reasoning.
```

## Manana Single

The single-agent variant learns a compact list of global correction rules that are inserted back into the predictor as shared task knowledge.

```text
1. When a pediatric patient is already on a tolerated antiseizure medication with documented seizure control and no adverse effects, and the clinical note contains no explicit instruction to modify therapy, continue the current drug and dose unchanged.

2. For pediatric focal epilepsy where carbamazepine is tolerated and at a therapeutic dose but seizures remain partially controlled, add levetiracetam as adjunctive therapy before changing the primary agent.

3. In Lennox-Gastaut syndrome, when a patient is already receiving valproate and experiences breakthrough seizures, add clobazam as an adjunctive agent rather than increasing the valproate dose; discontinue carbamazepine if it is part of the regimen because it can exacerbate drop attacks.

4. For pediatric patients with generalized genetic epilepsy, valproate monotherapy is the preferred first-line antiseizure medication; if the child is already on valproate, seizure-free, and tolerating the drug, continue the regimen unchanged.

5. In infants and young children with focal epilepsy who remain symptomatic on a sodium-channel blocker, phenobarbital is an appropriate first add-on antiseizure medication, particularly in low-resource settings where it is readily available and tolerated.

6. In children on stable valproate therapy, a solitary fever-related breakthrough seizure does not warrant dose escalation or medication change; continue the current valproate dose unless the clinician explicitly orders a modification.

7. If the clinical note explicitly instructs continuation of the current antiseizure medication at the same dose, maintain that regimen unchanged, even if seizures are ongoing, unless a contradictory directive to modify therapy is present.

8. When a medication is prescribed with a specific limited duration or is omitted from the current prescription list without an explicit instruction to continue, assume the drug has been discontinued and do not automatically carry it forward to subsequent visits.
```

## Manana Multi

The multi-agent variant learns a bounded population of specialist agents. Each agent is prompted to surface a specific clinical signal for the final predictor, rather than directly writing the prescription.

```text
Explicit_Drug_Directive_Agent
Identify every antiepileptic drug mentioned in the current or prior regimen. For each drug, determine whether the clinician explicitly states to continue, increase, decrease, stop, add, or start that drug. If the note contains an explicit continuation directive with no mention of new or discontinued drugs, state that the regimen should be maintained unchanged and do not suggest adjuncts or stops.

Formulary_Adjunct_Agent
Act as a clinical pharmacology specialist aware of the clinic's local formulary and cost considerations. When the note describes uncontrolled seizures despite a first-line antiepileptic and mentions formulary or affordability constraints, assess whether carbamazepine is listed as a recommended adjunct in this setting.

Seizure_Semiology_Agent
Identify whether the note describes focal, generalized, multifocal, or mixed seizures. Note focal components even when the overall diagnosis is multifocal or generalized, and state which seizure-type signals may influence antiepileptic selection.

Carbamazepine_Consideration_Agent
Evaluate carbamazepine or oxcarbazepine as a first-line or adjunct antiepileptic. Examine seizure type, prior drug exposure, local formulary or cost constraints, contraindications, and any statement that a new AED was initiated.

EEG_Broad_Spectrum_Agent
Scan EEG, neuroimaging, and cerebral dysfunction findings. If they indicate generalized, mixed, or diffuse seizure pathology, surface a signal that broad-spectrum antiepileptic coverage such as valproate should be considered.
```

## Interpretation Notes

TextGrad reads like a guideline document, but the supervision signal is only a prescribed drug set. The artifact commits to dose ranges, laboratory schedules, formulation choices, pill-burden constraints, stocking assumptions, and cost hierarchy details that are not recoverable from the training labels alone.

ExpeL captures useful generic prescribing heuristics, such as continuation preference and local first-line selection, but does not name the recurring drug-specific or seizure-specific local patterns that drive the cohort-level errors.

DSPy-GEPA sharpens the predictor interface: explicit-directive parsing, output formatting, dose-adequacy reasoning, and constraints against unnecessary drug additions. It does not create a persistent clinical memory over recurring local patterns.

Manana-Single produces compact, evidence-gated rules. Each rule names specific drugs and clinical situations, which makes the memory auditable.

Manana-Multi turns recurring errors into specialist signal extractors. The learned agents surface clinical signals for the predictor rather than acting as hidden prescribers.
