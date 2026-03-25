# Known Bugs & Issues

## Parsing

**1. "discontinue" not mapped to "stop"**
`parse_epileptologist_options()` looks for literal `"stop"` in ALLOWED_ACTIONS but the LLM uses "discontinue". Parser finds "continue" inside "discontinue" and assigns `action: continue` instead of `stop`.
Fix: check for "discontinue" before checking for "continue" in the action scan.

**2. Drug name normalization — full sentences instead of canonical names**
LLMs return `"Sodium Valproate (dose optimized to 20-30 mg/kg/day)"` instead of `"valproate"`. Breaks conflict detection (set intersections miss), agreement score (always 0.0), and safety veto matching.
Fix: strip everything after the first parenthesis/dash, then run through DRUG_ALIASES.

**3. Safety veto case mismatch**
`apply_safety_vetoes()` builds veto set from `concern.affected_drugs` which LLMs return capitalized (`"Carbamazepine"`). Parsed drug names from epileptologist are lowercase. Set lookup fails silently.
Fix: `vetoed.update(drug.lower() for drug in concern.affected_drugs)` — lowercase everywhere.

---

## Debate

**4. Debate modifications never applied to drug options**
`apply_synthesis_rules()` collects `modified_drugs` from rebuttal actions and logs them as text in `synthesis_notes` but never updates the actual `DrugOption` objects. Drug actions in the final output are the same as the epileptologist's original parsed output (minus safety vetoes). The whole debate changes nothing mechanically.
Fix: after parsing rebuttal actions, find matching drugs in all 3 options and update their actions.

**5. Debate is one-sided — epileptologist self-reports resolution**
Epileptologist self-reports accept/reject and controls what carries to Round 2. Pharmacologist verdict is never used to override. In practice epileptologist accepts everything and debate ends in 1 round.
Options: (1) parse pharmacologist verdict and use it to override epileptologist self-report, (2) make rejection the default, (3) ditch back-and-forth entirely — just have epileptologist revise plan once in response to all concerns (one LLM call, cleaner).

**6. Pharmacologist verdict LLM call is wasted**
Second LLM call per round gets RESOLVED/UNRESOLVED verdict — stored as free text, never parsed, never used for filtering. Either parse it and use it, or remove it.

---

## Trace / Output

**7. Epileptologist raw_output overwritten in Phase 4**
`format_trace_output()` overwrites `epileptologist_response.raw_output` with the fully formatted trace summary. Original epileptologist Phase 2 output is lost. The formatted text references pharmacologist and debate which hadn't run yet — misleading when reading traces.
Fix: store formatted output in a separate field (`trace.formatted_output`), don't overwrite epileptologist's raw_output.

**8. Final JSON saving reflects overwritten state**
Saved trace has the Phase 4 formatted summary in the epileptologist field. Original epileptologist output and the real pharmacologist input are not recoverable.
Fix: save original epileptologist raw_output before Phase 4 runs.

**9. agreement_score always 0.0**
`compute_agreement_score()` does pairwise Jaccard on agents' `recommended_drugs` lists but dirty drug names mean every intersection is empty → score = 0 regardless of actual agreement. Same root cause as bug #2.

---

## Conflict Detection

**10. Seizure vs continuity conflict missed due to dirty drug names**
Treatment analyst returns full sentences in `recommended_drugs` so intersection with diagnostician's `contraindicated_drugs` (clean canonical names) is always empty. Conflict never fires even when it should.
Same fix as bug #2.

**11. Pediatric safety conflict missed for same reason**
Pediatrician's `concerns[].affected_drugs` returns capitalized names, other agents' `recommended_drugs` return full sentences. Intersection misses.
Same fix as bugs #2 and #3.
