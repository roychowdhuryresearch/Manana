# DSPy Optimized Prompts — 2026-04-14

All prompts captured from runs on 50 stratified training patients, seed=42.

---

## 1. BootstrapFewShot — Final Prompt

Bootstrap selects 4 few-shot demos where the unoptimized model got the right answer. The instruction text is unchanged from the original.

### System message (instruction)

```
Your input fields are:
1. `clinical_notes` (str): Patient clinical notes
Your output fields are:
1. `reasoning` (str): Clinical reasoning for the prescription
2. `option_1` (str): Top prescription option, format: 'drug1:action, drug2:action'
3. `option_2` (str): Second option, format: 'drug1:action, drug2:action'
4. `option_3` (str): Third option, format: 'drug1:action, drug2:action'

In adhering to this structure, your objective is:
Given clinical notes from a clinic in Uganda, predict the doctor's
anti-seizure medication prescription. Use ONLY these 10 drugs:
carbamazepine, clobazam, clonazepam, ethosuximide, lamotrigine,
levetiracetam, phenobarbital, phenytoin, topiramate, valproate.
For each drug, specify an action: continue, start, or stop.
```

### Selected demos (4)

**Demo 1:** West syndrome infant on valproate → continue VPA, add levetiracetam
- Reasoning mentions LEV as "well-tolerated in infants" and "frequently used as adjunctive therapy"

**Demo 2:** 4yo CP child, seizure-free on valproate → continue VPA (all 3 options identical)
- Reasoning: "no additional antiseizure medication is indicated"

**Demo 3:** 4yo with drug rash from PB and CBZ → stop both, start levetiracetam
- Reasoning positions LEV as "first-line option for focal seizures in pediatric patients"

**Demo 4:** 2.5yo with uncontrolled seizures on VPA → add levetiracetam
- Reasoning: "levetiracetam is frequently used as an add-on"

**Observation:** 3/4 demos recommend levetiracetam. The "optimization" reinforces Western prescribing bias.

---

## 2. MIPROv2 — Final Prompt

MIPRO generates 3 candidate instructions, evaluates each with different demo combinations via Bayesian optimization, and selects the best.

### Candidate instructions generated

**Instruction 0** (original): "Given clinical notes from a clinic in Uganda, predict the doctor's anti-seizure medication prescription..."

**Instruction 1** (MIPRO-generated, scored highest internally at 82.65%):
```
You are given a string **clinical_notes** that contains one or more visit entries.
Each visit may have a "Prescription" (or "Plan") block that lists the anti-seizure
medicines the doctor prescribed at that visit.

Your task is to:

1. **Identify the most recent prescription block** – i.e., the prescription that
   appears **last** in the whole note.

2. **Extract every drug name** that appears in that latest prescription.
   - Only consider the ten allowed drugs.
   - If a listed drug is not in this list, ignore it.

3. **Assign the action `continue` to each extracted drug** (the dataset's labeling
   rule is: *if a drug appears in the latest prescription, output drug:continue*).

4. **Produce three identical prescription options** (Option 1, Option 2, Option 3).
   - Each option must contain the same comma-separated list of "drug:action" pairs.

5. **Write a short, generic reasoning paragraph** that explains that the regimen was
   taken from the most recent prescription and therefore all listed drugs should be
   continued. The reasoning does not need to reference seizure control, lab values,
   or any other clinical details.
```

**Instruction 2** (MIPRO-generated):
```
You are given the full textual record of a pediatric epilepsy visit (the clinical notes).
Your task is to extract the **current anti-seizure medication regimen** and present it
in a structured way.

1. Locate the most recent prescription block
2. Identify the drugs (only the 10 allowed)
3. Assign the action — the action is always **continue**. No start or stop actions
   are required.
4. Generate the output — the three options may be identical because the rule yields
   a single correct regimen.
```

**Observation:** Both MIPRO-generated instructions discovered the copy-previous-regimen shortcut. They explicitly say "the action is always continue" and "produce three identical options." MIPRO gamed the metric by finding that ~80% of ground truth is continuation — but this fails on the 20% where drugs actually change.

### Selected demos

4 bootstrapped demos similar to BootstrapFewShot, combined with Instruction 1 as the winning configuration.

---

## 3. GEPA — Final Prompt

GEPA used 920 rollouts over 30 iterations with reflection. The optimized instruction is more sophisticated than both Bootstrap and MIPRO — it actually understands the task structure:

```
**Task Overview**

You will receive one block of clinical notes from a Ugandan neurology/paediatric clinic.
The notes may describe several visits and will contain, for the same patient:

* Demographics (age, sex)
* Seizure type(s) and description (focal, generalized, absence, myoclonic, infantile
  spasms, etc.)
* Frequency / recent change of seizures
* Physical-exam findings, comorbidities, infections, laboratory results, or documented
  drug-related adverse events
* Current anti-seizure medication (ASM) list with dosing (you may ignore the dose)

Your job is to propose **one to three** realistic prescription **options** for this patient.
Each option must be expressed only as actions on the **ten allowed ASMs**:

carbamazepine, clobazam, clonazepam, ethosuximide,
lamotrigine, levetiracetam, phenobarbital, phenytoin,
topiramate, valproate

For every drug that appears in an option you must assign **exactly one** of:
* `continue` – the drug is already being taken and should be kept unchanged.
* `start`    – the drug is not in the current regimen and should be initiated.
* `stop`     – the drug is currently being taken and should be discontinued.

**Only list drugs that you are acting on** (i.e., drugs that are being continued,
started, or stopped). Do not list a drug that is absent from the current regimen
unless you are planning to start it.
```

**Observation:** GEPA produced the most reasonable prompt of the three — it correctly understands the task structure (multi-visit notes, extract current meds, assign actions). But it contains zero clinical knowledge:
- No seizure type → drug mapping
- No LMIC/formulary awareness
- No treatment continuity preference
- No polytherapy logic

It tells the model *what format to output* but not *what clinical reasoning to apply*. The model defaults to its training prior (Western guidelines), which is wrong for this setting. Result: 52% — no improvement over baseline despite a well-structured prompt.

This is the core distinction: GEPA optimized the **task interface** (how to read notes, how to format output). NPCL discovered the **domain knowledge** (which drugs this clinic uses, when to continue vs switch, how to classify seizure types). Interface optimization ≠ knowledge discovery.

---

## Comparison: What each method "learned"

| Method | What it produced | Clinical insight? |
|--------|-----------------|-------------------|
| **Bootstrap** | 4 example cases with model-generated reasoning | No — reasoning inherits Western LEV bias |
| **MIPROv2** | "Copy the last prescription" heuristic | No — discovered a statistical shortcut |
| **GEPA** | Rule-based start/continue/stop from visit history | Partial — understands drug transitions but not WHY |
| **NPCL text** | 15 rules: "prioritize formulary drugs, classify seizure type, continue working regimens..." | Yes — interpretable clinical knowledge |
| **NPCL multi** | 5 specialist agents: ContinuityDetector, SeizureSemiologyMapper, etc. | Yes — functional specialists with clinical scope |

DSPy methods optimize the prompt to score well. NPCL discovers knowledge that explains why scores should be what they are.
