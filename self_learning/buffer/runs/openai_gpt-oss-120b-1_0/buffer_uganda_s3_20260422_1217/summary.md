# Run Summary

**Model:** openai.gpt-oss-120b-1:0  
**Dataset:** uganda  
**Seed:** 3  
**Batch size:** 10  
**Rounds:** 16

## Eval Progression

| Round | Acc | Rules | Candidate | Best | Mono | Poly |
|-------|-----|-------|-----------|------|------|------|
| baseline | — | 0 | 44/60 (73%) | — | 35/44 | 9/16 |
| R0 | Y | 0 | 42/60 (70%) | (70%) | 32/44 | 10/16 |
| R1 | Y | 1 | 43/60 (72%) | (72%) | 34/44 | 9/16 |
| R2 | Y | 1 | 48/60 (80%) | (80%) | 37/44 | 11/16 |
| R3 | Y | 3 | 46/60 (77%) | (77%) | 36/44 | 10/16 |
| R4 | Y | 5 | 41/60 (68%) | (68%) | 33/44 | 8/16 |
| R5 | Y | 6 | 44/60 (73%) | (73%) | 34/44 | 10/16 |
| R6 | Y | 8 | 45/60 (75%) | (75%) | 34/44 | 11/16 |
| R7 | Y | 9 | 48/60 (80%) | (80%) | 36/44 | 12/16 |
| R8 | Y | 10 | 43/60 (72%) | (72%) | 33/44 | 10/16 |
| R9 | Y | 11 | 42/60 (70%) | (70%) | 33/44 | 9/16 |
| R10 | Y | 12 | 43/60 (72%) | (72%) | 32/44 | 11/16 |
| R11 | Y | 12 | 46/60 (77%) | (77%) | 34/44 | 12/16 |
| R12 | Y | 12 | 43/60 (72%) | (72%) | 32/44 | 11/16 |
| R13 | Y | 13 | 43/60 (72%) | (72%) | 32/44 | 11/16 |
| R14 | Y | 14 | 43/60 (72%) | (72%) | 32/44 | 11/16 |
| R15 | Y | 15 | 43/60 (72%) | (72%) | 34/44 | 9/16 |

## Final Shared Learnings (15 rules)

1. When a pediatric patient is already on a tolerated antiseizure medication with documented seizure control and no adverse effects, and the clinical note contains no explicit instruction to modify therapy, the appropriate recommendation is to continue the current drug and dose unchanged.
2. In patients with Myoclonic Atonic (Doose) epilepsy who achieve seizure freedom on ethosuximide monotherapy and tolerate the medication, maintain ethosuximide at the current dose as long‑term therapy.
3. For pediatric focal epilepsy where carbamazepine is tolerated and at a therapeutic dose but seizures remain partially controlled, the recommended next step is to add levetiracetam as adjunctive therapy before changing the primary agent.
4. In Lennox‑Gastaut syndrome, when a patient is already receiving valproate and experiences breakthrough seizures, the recommended next step is to add clobazam as an adjunctive agent rather than increase the valproate dose; additionally, carbamazepine should be discontinued if part of the regimen because it can exacerbate drop attacks.
5. For pediatric patients with generalized genetic epilepsy, valproate monotherapy is the preferred first‑line antiseizure medication; if the child is already on valproate, is seizure‑free, and tolerates the drug without side‑effects, the regimen should be continued unchanged, with dose optimization only if breakthrough seizures occur.
6. For pediatric focal epilepsy in children ≥2 years old, a sodium‑channel blocker such as carbamazepine should be selected as the initial (first‑line) antiseizure medication unless contraindicated.
7. In children under 3 years with early‑onset generalized epilepsy—including frequent daily seizures, developmental delay, or suspected Dravet syndrome—valproate monotherapy should be selected as the first‑line treatment unless contraindicated.
8. In infants and young children with focal epilepsy who remain symptomatic on a sodium‑channel blocker (e.g., carbamazepine) or as initial therapy, phenobarbital is an appropriate first‑add‑on antiseizure medication, particularly in low‑resource settings where it is readily available and tolerated.
9. In resource‑limited settings, adding carbamazepine as an adjunct to valproate is an acceptable strategy for children with refractory generalized or multifocal epilepsy when valproate monotherapy does not achieve seizure control.
10. In infants (≤2 years) with early‑onset focal seizures due to epileptic encephalopathy or structural brain injury, valproate monotherapy should be initiated as the preferred first‑line antiseizure medication unless contraindicated or not tolerated.
11. When a medication appears in the current prescription or refill order and the clinical note does not explicitly state to discontinue or modify it, the system should assume continuation of that antiepileptic at the same dose.
12. In children on stable valproate therapy, a solitary fever‑related breakthrough seizure does not warrant dose escalation or medication change; continue the current valproate dose unless the clinician explicitly orders a modification.
13. In children with generalized epilepsy who are on therapeutic-dose valproate, are seizure‑free or have ≤1 seizure per month, and have no significant adverse effects, the appropriate recommendation is to continue the current valproate dose unchanged without dose escalation or addition of other antiseizure medications.
14. If the clinical note explicitly instructs to continue the current antiseizure medication at the same dose, the system should maintain that regimen unchanged, even if seizures are ongoing, unless a contradictory directive to modify therapy is present.
15. When a medication is prescribed with a specific limited duration (e.g., “× 2/52”) or is omitted from the current prescription list without an explicit instruction to continue, assume the drug has been discontinued and do not automatically carry it forward to subsequent visits.
