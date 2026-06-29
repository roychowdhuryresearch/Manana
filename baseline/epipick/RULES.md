# EpiPick Rules

This is a readable summary of the local EpiPick implementation in `algorithm.py`.

Source: Asadi-Pooya et al., "A pragmatic algorithm to select appropriate antiseizure medications in patients with epilepsy", Epilepsia, 2020.

## Inputs

EpiPick uses five structured inputs:

- `seizure_type`: one of `UNCERTAIN`, `FOCAL`, `ABSENCE`, `MYOCLONIC`, `MYOCLONIC_ABSENCE`, `GTCS`, `GTCS_MYOCLONIC`, `GTCS_ABSENCE`, `GTCS_MYOCLONIC_ABSENCE`.
- `age`: current patient age in years.
- `gender`: `male` or `female`.
- `menopausal`: `pre` or `post`; use `post` for male patients.
- `modifiers`: documented comorbidities or medication-context booleans.

## Medication Abbreviations

| Abbrev | Medication |
| --- | --- |
| ACT | acetazolamide |
| BRV | brivaracetam |
| CBZ | carbamazepine |
| CEN | cenobamate |
| CLB | clobazam |
| CLN | clonazepam |
| ESL | eslicarbazepine acetate |
| ETS | ethosuximide |
| GBP | gabapentin |
| LCM | lacosamide |
| LEV | levetiracetam |
| LTG | lamotrigine |
| NTR | nitrazepam |
| OXC | oxcarbazepine |
| PB | phenobarbital |
| PER | perampanel |
| PGB | pregabalin |
| PHT | phenytoin |
| TPM | topiramate |
| VPA | valproate |
| ZNS | zonisamide |

## Base Seizure-Type Groups

Group 1 is most preferred. Group 2 and Group 3 are lower-ranked options. Medications not listed for a seizure type are not recommended by the base table before modifiers.

| Seizure type | Group 1 | Group 2 | Group 3 |
| --- | --- | --- | --- |
| ABSENCE | VPA, ETS | LTG | LEV, ZNS, ACT, CLB, CLN |
| MYOCLONIC | VPA, LEV, CLN | CLB | TPM, ZNS, PB, NTR |
| GTCS | VPA | LTG, LEV, LCM, PER | TPM, ZNS, CLB, PB, OXC, CBZ, PHT, BRV |
| GTCS_MYOCLONIC | VPA | LEV | LTG, TPM, ZNS, CLB, CLN, PB, LCM, PER, PHT, BRV |
| GTCS_ABSENCE | VPA | LTG, LEV | TPM, ZNS, CLB, PB, LCM, PER |
| GTCS_MYOCLONIC_ABSENCE | VPA | LTG, LEV | TPM, ZNS, CLB, CLN, PB, LCM, PER |
| MYOCLONIC_ABSENCE | VPA, ETS | LTG, LEV | TPM, ZNS, CLB, CLN |
| FOCAL | LTG, LEV, LCM, OXC, CBZ, ESL | VPA, TPM, ZNS, PER, PHT, BRV, CEN | CLB, PB, GBP, PGB |
| UNCERTAIN, age >= 21 | LTG, LEV, LCM, OXC, CBZ, ESL | VPA, TPM, ZNS, CLB, PER, PHT, BRV, CEN | PB, GBP, PGB |
| UNCERTAIN, age < 21 | VPA, LTG, LEV | CLB, LCM, OXC, PER, CBZ, ESL, CEN | TPM, ZNS, PB |

## Modifier Rules

Modifiers move medications up or down by class. A worsening by 1 means the medication is less preferred by one group; an improvement by 1 means it is more preferred by one group. Removed medications fall outside the ranked groups.

| Condition | Rule |
| --- | --- |
| Female and premenopausal | PB worsens by 1. For non-GTCS/non-focal seizures, VPA, ZNS, and TPM become Group 3 and cannot be upgraded. For GTCS, VPA becomes Group 2; LTG and LEV become Group 1. For focal seizures, VPA, ZNS, and TPM are removed. |
| Age > 65 | LTG, LEV, LCM, and GBP improve by 1. |
| Daily non-ASM medication | For non-focal/non-uncertain seizures: ETS, LEV, LCM, LTG, ZNS, PER improve by 1; CBZ, PHT, PB worsen by 1. For focal/uncertain seizures: LEV, LCM, GBP, LTG, BRV, ZNS, PER improve by 1; CBZ, PHT, PB worsen by 1. |
| Hormonal contraceptive | TPM and PER worsen by 1; CBZ, PB, PHT, OXC, ESL worsen by 2. |
| Brain tumor requiring chemotherapy/radiation | CBZ, OXC, ESL, PHT, PB worsen by 2. |
| Hepatic failure | LEV, LCM, GBP improve by 1; VPA worsens by 2. |
| Obesity | PGB and GBP worsen by 1. VPA worsens by 2 for focal/uncertain seizures, otherwise by 1. |
| Diabetes | VPA, PHT, CBZ, PER worsen by 1. |
| Bleeding/coagulopathy | VPA worsens by 2 for focal/uncertain seizures, otherwise by 1. |
| Neutropenia | CBZ and PHT worsen by 1. |
| Renal stone | TPM, ZNS, ACT worsen by 1. |
| Drug allergy | LTG, PHT, CBZ, OXC, ESL, PB, ZNS, CEN worsen by 1. |
| Depression | LTG improves by 1; LEV, PB, CLB, CLN, NTR worsen by 1. |
| Aggression/irritability | TPM, PB, LEV, PER worsen by 1. |
| Migraine | TPM and VPA improve by 1. |
| Renal failure | CLB, ETS, LTG, CBZ, PHT improve by 1. VPA, LEV, TPM, ZNS, ACT, CLN, PB, NTR, LCM, OXC, PER, ESL, GBP, BRV, PGB worsen by 1. |

## Post-Processing Rules

After modifiers, classes are normalized into Groups 1 through 4. Then these final adjustments are applied:

- For `GTCS_MYOCLONIC` or `GTCS_MYOCLONIC_ABSENCE`, CLN is moved from Group 1/2 to Group 3.
- For premenopausal female patients, VPA is moved from Group 1/2 to Group 3.
- For focal seizures, CLB is moved from Group 1/2 to Group 3.
- For myoclonic or uncertain seizures, CLB is moved from Group 1 to Group 2.
- For GTCS or GTCS plus myoclonic seizures, PHT is moved to Group 3.

## Interpretation

EpiPick is a rule-based monotherapy recommendation algorithm. It returns medication groups, not a learned patient-specific regimen and not an exact multi-drug prescription. In comparisons, use it as a clinical rule baseline and be explicit about the metric, such as whether the ground-truth monotherapy appears in Group 1.
