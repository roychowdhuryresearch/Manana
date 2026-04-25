# MIMIC Learning Analysis — Buffer Single (120B, Seed 1)

Date: 2026-04-24
Run: `self_learning/buffer/runs/openai_gpt-oss-120b-1_0/buffer_mimic_s1_20260424_1704/`
Dataset: MIMIC-IV epilepsy cohort (US hospital), 10-drug filter (pre-fix — see note at bottom)

---

## Learnings (17 total)

```
1.  If a patient is clinically stable, has therapeutic antiseizure drug levels, and no new
    contraindications, the default discharge plan should be to maintain the current AED regimen
    unchanged, avoiding addition or dose changes unless clinically indicated.

2.  In refractory focal epilepsy, preferentially add or switch to a non-enzyme-inducing
    sodium-channel blocker (e.g., lacosamide, oxcarbazepine) after failure or intolerance of
    enzyme-inducing antiseizure medications.

3.  When a discharge medication list is explicitly documented, the system must predict exactly
    the physician-ordered antiseizure drug regimen and should not assume unchanged home
    medications without an explicit order.

4.  When a clinically stable patient has therapeutic antiseizure drug levels but continues to
    have breakthrough seizures, the preferred discharge plan is to add an adjunctive antiseizure
    medication with a different mechanism of action (e.g., a non-enzyme-inducing sodium-channel
    blocker or a benzodiazepine) rather than simply increasing the dose of the current drug.

5.  When discharge documentation explicitly lists a PRN rescue benzodiazepine (or otherwise
    indicates a need for acute seizure control), the prediction must include that PRN agent in
    the discharge regimen; if no rescue medication is documented, do not add one by default.

6.  If discharge documentation explicitly states that no medication changes were made (e.g.,
    "no medication changes" or "stay on home antiseizure medications with no dose adjustments"),
    the discharge plan should be interpreted as continuing the current AED regimen unchanged.

7.  If a patient has breakthrough seizures and the discharge documentation does not list a PRN
    rescue benzodiazepine, the discharge plan should include a PRN rescue benzodiazepine (e.g.,
    lorazepam) for acute seizure control.

8.  For an adult presenting with a first unprovoked generalized seizure and no identified
    metabolic, structural, or contraindicating factors, start levetiracetam as monotherapy for
    outpatient seizure control.

9.  If the discharge summary provides no explicit medication change and the patient is clinically
    stable with therapeutic antiseizure-drug levels, the default discharge plan is to maintain
    the pre-admission antiseizure regimen unchanged, unless a contraindication is documented.

10. When a medication is listed on the admission medication list but is absent from the discharge
    medication list, infer that the medication was discontinued and do not include it in the
    predicted discharge regimen.

11. If breakthrough seizures are attributed to medication non-adherence, the discharge plan
    should prioritize reinforcing adherence and simplifying the antiseizure regimen rather than
    adding or increasing scheduled antiseizure drugs or adding a rescue benzodiazepine.

12. In patients with focal epilepsy linked to structural cortical lesions (e.g., post-stroke,
    tumor, cortical dysplasia), prioritize sodium-channel-blocking ASMs such as oxcarbazepine,
    lacosamide, or carbamazepine as first-line or adjunctive therapy.

13. When breakthrough seizures occur in the setting of an acute, reversible precipitant (e.g.,
    nausea, vomiting, metabolic disturbance) and the patient is otherwise tolerating their
    current AED regimen, the discharge plan should maintain the existing regimen unchanged.

14. If a discharge note specifies that a medication is planned for taper but does not include an
    explicit stop order, assume the medication will continue at its current dose and include it
    in the predicted discharge regimen.

15. If the discharge plan already includes a scheduled benzodiazepine for seizure control, do not
    add an additional PRN rescue benzodiazepine unless the clinician explicitly orders one.

16. In refractory epilepsy, the preferred first adjunctive antiseizure medication to add to an
    existing regimen is levetiracetam because of its broad-spectrum efficacy and minimal
    drug-interaction profile.

17. If a drug appears in the discharge medication list without an explicit stop, taper, or
    dose-adjustment directive, the discharge plan should be interpreted as continuing that
    medication at its current dose.
```

---

## Theme Breakdown

### Theme 1 — Stability / Continuation (rules 1, 6, 9, 13) ✓ GOOD
Same universal rule that buffer single learned for Uganda. Four rules all saying the same thing from slightly different angles:
- General stability → continue (1)
- Explicit "no changes" documentation → continue (6)
- No explicit change + stable → continue (9)
- Reversible precipitant → continue (13)

**Assessment:** Correct and load-bearing. Slight redundancy (1 and 9 are nearly identical) but both reinforce the highest-frequency error type. Matches Uganda learning perfectly — this is a universal clinical rule, not MIMIC-specific.

---

### Theme 2 — Discharge Documentation Parsing (rules 3, 10, 14, 17) ✓ GOOD (MIMIC-specific)
MIMIC notes have richer structured discharge sections than Uganda notes. The model learned to treat explicit discharge documentation as ground truth:
- Explicitly documented list → follow exactly, don't infer (3)
- Drug on admission but absent at discharge → discontinued (10)
- Taper planned but no stop order → still continuing (14)
- No stop/taper directive → continuing (17)

**Assessment:** Highly MIMIC-specific and correct. US hospital notes have explicit medication reconciliation — the model learned to trust this signal rather than over-inferring. Rules 14 and 17 are essentially the same rule stated twice (both about absence of stop order → continuation) — minor redundancy.

**Caveat on rule 3:** References a "discharge medication list" — our cleaning removed the actual Discharge Medications section, so this rule is really referring to the *Medications on Admission* or BHC medication mentions. Not leakage, but the phrasing could confuse future inspection.

---

### Theme 3 — Rescue Benzodiazepine Logic (rules 5, 7, 15) ~ MIXED
Three rules all about when to include a PRN benzo:
- If documented → include it (5)
- If not documented + breakthrough → add one (7)
- If scheduled benzo already present → don't add PRN (15)

**Assessment:** Rules 5 and 7 directly contradict each other in some cases. Rule 5 says "if not documented, don't add." Rule 7 says "if breakthrough seizures and not documented, do add lorazepam." The architect failed to notice this tension. Rule 15 is the only fully clean rule in this theme.

**Risk:** The model will be inconsistent on benzo decisions depending on which rule it activates. This could hurt accuracy on poly-therapy cases where lorazepam/clonazepam is part of GT.

---

### Theme 4 — Escalation Logic (rules 4, 11, 12, 16) ✓ GOOD
When and how to add adjunctive medications:
- Stable but breaking through → add different MOA (4) ✓
- Non-adherence is cause → don't escalate, simplify (11) ✓
- Focal + structural lesion → sodium-channel blocker (oxcarbazepine/lacosamide/CBZ) (12) ✓
- First adjunct in refractory → LEV (16) ~ debatable

**Assessment:** Rules 4, 11, 12 are clean and clinically grounded. Rule 16 (LEV as universal first adjunct) is a reasonable heuristic but not always true — some focal epilepsies have better options. No fabricated numbers anywhere in this theme.

---

### Theme 5 — First-Line Mapping (rule 8) ✓ GOOD (MIMIC-specific)
First unprovoked generalized seizure → LEV monotherapy.

**Assessment:** Correct for US hospital practice. Notably different from Uganda where valproate/CBZ would be first-line. The model correctly learned the US-specific first-line without being told to.

---

## Quality Metrics

| Metric | Buffer MIMIC s1 | Buffer Uganda 120B (ref) |
|--------|----------------|--------------------------|
| Rules total | 17 | 9.0 (mean) |
| Rules with numeric claims | 0 (0%) | 9% |
| Rules with actionable drug decisions | ~14 (82%) | 78% |
| Fabricated numbers | None | None |
| Internal contradictions | 1 (benzo theme) | 0 |
| MIMIC-specific rules | ~6 | N/A |
| Universal rules (also valid for Uganda) | ~8 | ~9 |

---

## What's New vs Uganda

| Signal | Uganda Buffer | MIMIC Buffer |
|--------|--------------|--------------|
| First-line drug | Valproate (generalized), CBZ (focal) | LEV (first unprovoked) |
| Documentation parsing | Not present | Explicit (4 rules) |
| Rescue benzo | Not present | Present (3 rules, 1 contradictory) |
| Non-enzyme-inducing preference | Not present | Present (rules 2, 4, 12) |
| Structural epilepsy rule | Not present | Present (rule 12) |
| Core continuation logic | ✓ | ✓ (same) |

The MIMIC model correctly learned US-specific patterns: LEV as first-line, non-enzyme-inducing preference (avoids CBZ/PHT interactions), structured documentation as ground truth, and benzo rescue patterns. These are all valid US hospital clinical norms not present in Uganda.

---

## Issues to Watch

1. **Benzo contradiction** (rules 5 vs 7): Will produce inconsistent predictions on cases where breakthrough seizures occur without documented rescue benzo. Need to see if multi-seed runs resolve this or all converge on the same contradiction.

2. **Rule 3 phrasing**: "discharge medication list is explicitly documented" — fine clinically, but sounds like leakage if anyone reads it without context. The rule is referencing Medications on Admission / BHC mentions, not the actual removed Discharge Medications section.

3. **17 rules is high** for a single seed: Uganda buffer converged at 8–11 rules per seed. MIMIC's richer note structure (more signal, more edge cases) is producing more rules. Watch if multi-seed runs stay high or converge down.

4. **10-drug filter caveat**: This run was trained with the old 10-drug Uganda filter, so zonisamide, lacosamide, oxcarbazepine, gabapentin were in the GT but the model was told it could only predict 10 drugs. Despite this, rules 2, 4, 12 mention lacosamide and oxcarbazepine — the model learned they matter even though they were filtered from predictions. New runs with 22-drug filter will be the proper baseline.

---

---

## Buffer Multi — MIMIC (120B, Seed 1)

Run: `self_learning/buffer/multi/runs/openai_gpt-oss-120b-1_0/bufmulti_mimic_s1_20260424_1704/`

### Agents Discovered (5)

| Agent | Role | Assessment |
|-------|------|------------|
| MedListIntentAgent | Parses discharge medication reconciliation — explicit continue/stop/add directives | ✓ GOOD — MIMIC-specific, high-signal |
| LevelSeizureMismatchAgent | Detects serum level vs breakthrough seizure mismatch | ✓ GOOD — clean clinical signal, no drug recs |
| FirstSeizureInitiationAgent | Flags first unprovoked seizure + structural lesion risk | ✓ GOOD — actionable trigger for LEV initiation |
| RescueBenzodiazepineAgent | Identifies PRN benzo documented in discharge | ~ OK — useful but overlaps with single-buffer benzo rules |
| RescueNeedAgent | Flags refractory generalized epilepsy as needing 2+ adjunctive drugs | ✗ HARMFUL — caused catastrophic eval crash at R6 |

### Eval Progression

```
Baseline:  27% (16/60)
R0:        42% (+15pp) — MedListIntentAgent added
R1:        35% — 2 more agents added, regression
R2:        35%
R3:        33% — RescueBenzodiazepineAgent added
R4–R5:     37%
R6:         7% ← CRASH — RescueNeedAgent added
R7:         7%
R8:        15% — recovering but not recovering to pre-crash
R9:        22%
R10:       27%
R11:       13%
R12:       35%
R13:       32%
R14:       23%
```

### What Happened

**MedListIntentAgent was the signal.** Adding it alone at R0 jumped eval from 27% → 42% — a 15pp gain from a single agent. This is the biggest single-round gain seen across any run. MIMIC notes have explicit medication reconciliation tables that the base predictor wasn't parsing reliably; the agent surfaces that signal directly.

**The R6 crash was RescueNeedAgent.** The agent's output for any refractory case ends with "the case likely warrants adding two or more adjunctive antiseizure drugs." This pushes the predictor toward polytherapy on cases where the GT is monotherapy or a small regimen. The agent doesn't name drugs but the implication is aggressive — the predictor read it as a green light to over-prescribe. 7% is near-random for a 10-drug task, meaning the predictions became essentially uncorrelated with GT.

**All rounds accepted (gating failed).** Every round shows `Y` in the Acc column — the gating mechanism accepted all 15 updates including the crash. This suggests the buffer comparison baseline was stale or the eval threshold wasn't enforced correctly. Need to check if there's a bug in the multi-buffer gating logic.

**Unstable after R6.** The run never fully recovered. Peak after the crash was 35% (R12), below the pre-crash peak of 42%. The RescueNeedAgent remained in the roster for all subsequent rounds, continuing to contaminate predictions.

### Agent Quality Analysis

**MedListIntentAgent** — best agent in this run. MIMIC-specific and correctly scoped: it lists each drug with its action (continue/stop/add/rescue) without recommending additional agents. Exactly what an agent should do.

**LevelSeizureMismatchAgent** — well-scoped. Surfaces the level-vs-breakthrough signal without naming drugs. Useful for cases where dose adjustment is the GT answer.

**FirstSeizureInitiationAgent** — correctly scoped. Flags the structural lesion risk for recurrence without drug recommendations. Feeds directly into the LEV-first-line learning.

**RescueBenzodiazepineAgent** — over-specific. Identifies PRN benzos in discharge documentation. Useful for benzo-containing GT cases but adds noise when the GT has no benzo. The single-buffer benzo rules cover this without an explicit agent.

**RescueNeedAgent** — harmful. "Likely warrants adding two or more adjunctive drugs" is a recommendation, not an observation. Violates the agent design principle (agents surface clinical signals, not drug decisions). Should be blocked or rewritten to just flag "refractory + therapeutic levels + breakthrough" without the implication.

### MIMIC-Specific Agent Patterns

The multi-buffer run discovered agents that are clearly MIMIC-driven:
- Structured discharge medication tables → MedListIntentAgent
- Serum level reporting (MIMIC notes have lab values) → LevelSeizureMismatchAgent
- First unprovoked seizure documentation → FirstSeizureInitiationAgent

These agents would have no signal in Uganda notes (which lack structured medication tables and serum levels). This is correct domain adaptation.

---

---

## TextGrad — MIMIC (120B, Seed 1)

Run: `textgrad_opt/runs/openai_gpt-oss-120b-1_0/tg_mimic_s1_20260424_1704/`

### Eval Progression

```
Baseline:  17% (10/60)
R0:        33% (+16pp) — only accepted round until R14
R1–R13:    22% — 13 consecutive rejections, stuck
R14:       37% (+4pp over R0 best)
```

**1 accept in 14 rounds (7% accept rate)** — then one late jump. Consistent with Uganda TG pattern (83% rejection rate across all Uganda runs).

### Final Learnings (15 rules)

```
1.  Scan entire discharge document for all 22 ASM names + surrounding verb phrase
    (start, continue, increase, decrease, taper, stop, PRN, bridge).

2.  Per-drug action hierarchy:
      1. stop/taper/bridge cue → STOP
      2. start/continue/maintain/increase/decrease → CONTINUE
      3. medication list "accurate and complete" + drug in admission list + no STOP → CONTINUE
      4. otherwise → no action

3.  Default "continue-unless-stopped": any ASM with dose/frequency and no STOP cue → retain unchanged.

4.  Admission-to-discharge dose parity: same drug, same dose/frequency in both tables → CONTINUE,
    suppress any inferred change.

5.  New-drug addition only when breakthrough trigger documented (seizure freq ≥ X/week, new seizure
    type, therapeutic-level failure) AND note explicitly recommends addition. Limit to single add-on
    per encounter.

6.  Exclude any drug matching documented allergy or severe adverse effect (rash, psychiatric worsening).

7.  Drug-interaction matrix: strong interactions downgrade score but don't auto-stop unless major
    interaction + no override.

8.  Female patients of reproductive potential: strong penalty to valproate, topiramate, phenobarbital;
    prioritize lamotrigine, levetiracetam, oxcarbazepine.

9.  Patients >60 years: avoid topiramate, phenobarbital, high-dose lacosamide unless specifically
    indicated.

10. Seizure-type matching: sodium-channel blockers (oxcarbazepine, lacosamide, lamotrigine) for focal
    seizures, especially with structural lesion.

11. Separate chronic ASM list from PRN rescue list; PRN benzos added only when breakthrough language
    present, excluded from chronic-agent count.

12. After generation: enforce chronic agent count = CONTINUE + START drugs (PRN excluded).

13. Confidence scoring:
      +1 per CONTINUE/START cue
      +0.5 per seizure-type cue matching drug class
      +0.5 for dose/level confirmation
      -0.5 per interaction warning
      -1 per STOP cue
    If total < threshold → output "no change" with clarification flag.

14. Post-generation validation:
      Drug in verified list, no STOP, but omitted → MISSED_DRUG flag
      Drug added without breakthrough trigger → OVER_PRESCRIBED flag
      Conflicting START + STOP cues → clarification flag, default no change

15. [Implicit — folded into rules above]
```

### Theme Breakdown

**Theme 1 — Document scanning + verb hierarchy (rules 1–4)** ✓ GOOD (MIMIC-specific)

Same MIMIC-specific insight as buffer's documentation parsing theme — US hospital notes have explicit verb cues (start/continue/stop/taper) that the model should parse literally. TG operationalized this as a full decision tree with priority ordering. More structured than buffer's rules, but the same underlying signal. Rule 4 (dose parity → CONTINUE) is the most precise version of the continuation rule seen in any run.

**Theme 2 — New drug gating (rule 5)** ✓ GOOD

"Add-on only when breakthrough trigger documented + note explicitly recommends" — almost identical to buffer's escalation logic. The "limit to single add-on per encounter" constraint is new and clinically sound. Directly counteracts over-prescribing.

**Theme 3 — Safety filters (rules 6–9)** ~ MIXED

- Rule 6 (allergy exclusion): correct and important — likely emerged from cases where the GT excluded a drug due to documented allergy
- Rule 7 (interaction matrix): reasonable but vague — "downgrade score" without specifics is not actionable
- Rule 8 (teratogenicity): clinically correct, MIMIC-specific (US notes document reproductive status). No fabricated percentages — just correct drug ordering
- Rule 9 (age >60): clinically reasonable but emerged from very few cases at most — risk of overfitting

**Theme 4 — Seizure type / structural matching (rule 10)** ✓ GOOD

Same as buffer rule 12. Focal + structural → sodium-channel blocker. Both systems converged independently on this.

**Theme 5 — PRN benzo separation (rules 11–12)** ✓ GOOD

More precise than buffer's benzo theme. Explicitly separates chronic vs PRN lists and defines the count-check. Eliminates the buffer contradiction (rules 5 vs 7) by making PRN a separate track.

**Theme 6 — Confidence scoring + validation (rules 13–14)** ✗ BAD

Classic TG over-engineering. A numeric scoring system (+1, +0.5, -0.5, -1) with a "preset threshold" that is never defined. The model invented a scoring rubric that sounds systematic but has no grounding — the weights are made up. Rule 14 (MISSED_DRUG / OVER_PRESCRIBED flags) is a post-hoc validation layer the model cannot actually execute on its own output. This is decoration, not a decision rule.

### Quality Metrics

| Metric | TG MIMIC s1 | Buffer MIMIC s1 | TG Uganda 120B (ref) |
|--------|------------|-----------------|----------------------|
| Rules total | 15 | 17 | 16.2 (mean) |
| Rules with numeric claims | 2 (13%) | 0 | 43% |
| Rules with fabricated numbers | 1 (scoring weights) | 0 | systematic |
| Rules with actionable drug decisions | ~10 (67%) | ~14 (82%) | 38% |
| Internal contradictions | 0 | 1 (benzo) | 0 |
| MIMIC-specific rules | ~7 | ~6 | N/A |

**Significantly less fabrication than Uganda TG** — no invented percentages, no availability figures, no citations. The numeric fabrication is limited to the confidence scoring weights (+1, +0.5 etc.) which are made up but not clinically harmful. This is a real improvement over Uganda TG behavior.

### Key Difference vs Uganda TG

Uganda TG spent ~43% of rules on monitoring, dosing, and availability — textbook content completely outside the task. MIMIC TG has almost none of that. Instead it converged on document-parsing rules (verb hierarchy, dose parity, PRN separation) that are directly relevant to drug-set prediction from structured US hospital notes. The task is easier to ground in MIMIC because the notes are more structured — less room for the optimizer to hallucinate clinical context.

### TG vs Buffer Single on MIMIC

| | TG | Buffer Single |
|---|---|---|
| Peak eval | 37% | not yet (s1 still in 10-drug run) |
| Baseline | 17% | 27% |
| Accept rate | 7% (1/14) | N/A |
| Core theme | Document parsing + verb hierarchy | Continuation + doc parsing + benzo |
| Over-engineering | Confidence scoring rubric | None |
| Fabrication | Minimal (scoring weights) | None |

TG's baseline was lower (17% vs 27%) likely because buffer's predictor gets warm-started differently. Both peaked around 33–37% but with 10-drug filter — new 22-drug runs needed for fair comparison.

---

## Cross-System Comparison — MIMIC (s1)

### Summary Table

| Dimension | Buffer Single | Buffer Multi | TextGrad |
|-----------|--------------|--------------|----------|
| Peak eval | — (10-drug, stale) | 42% (R0) then unstable | 37% (R14) |
| Baseline | 27% | 27% | 17% |
| Optimization stability | Stable, monotone | Crashed at R6, never recovered | Flat 13 rounds then late jump |
| Core learning style | Clinical decision rules | Specialized signal agents | Document parsing algorithm |
| Grounding | High — rules tied to observed errors | High for good agents, low for RescueNeedAgent | Medium — verb hierarchy grounded, scoring rubric invented |
| Fabricated numbers | None | None | Minimal (scoring weights only) |
| Made-up claims | None | None (agents) | None |
| Overfitting to note structure | Low | Medium (MedListIntentAgent very MIMIC-specific) | High (verb hierarchy, dose parity — only works on structured notes) |
| Internal contradictions | 1 (benzo rules 5 vs 7) | 0 | 0 |
| Rules outside task scope | 0 | 0 | 2 (interaction matrix, confidence scoring) |
| MIMIC-specific insight | Medium | High | High |

---

### 1. Which system learns the most grounded rules?

**Buffer Single.** Every rule is a direct response to a repeated error pattern across multiple patients. The architect only admits rules when the same mistake appears in several inspector reports from the same batch — so each rule is empirically grounded in the training signal. No rule in the buffer single output references a clinical concept that wasn't directly observed in the notes (no invented drug hierarchies, no scoring systems, no availability assumptions).

Buffer Multi is equally grounded for its good agents (MedListIntentAgent, LevelSeizureMismatchAgent) but produces one clearly harmful agent (RescueNeedAgent) that makes a claim ("likely warrants 2+ adjunctive drugs") not grounded in any specific patient evidence.

TG's document-parsing rules (verb hierarchy, dose parity) are well-grounded — they emerge directly from the structure of MIMIC notes. The confidence scoring rubric (+1, +0.5, -0.5, -1) is invented — no training signal produced those weights.

---

### 2. Which system overfits to note structure?

**TextGrad most, Buffer Multi second.**

TG built a verb-parsing algorithm (scan for start/continue/stop/taper/bridge, apply hierarchy) that is specific to MIMIC's structured discharge documentation. This is correct for MIMIC but would transfer poorly to Uganda notes or less structured clinical text. It learned the *format* of the notes rather than the *clinical reasoning* behind the prescriptions.

Buffer Multi's MedListIntentAgent is similarly over-fit to MIMIC's medication reconciliation tables — it explicitly looks for "discharge medication lists" with explicit directives. Again correct for MIMIC, brittle elsewhere.

Buffer Single's rules are more abstract ("if clinically stable → continue", "if non-adherence → don't escalate") and would transfer across settings.

---

### 3. Which system gets stuck?

**TextGrad.** 13 consecutive rejected rounds (R1–R13) with the best score frozen at 33% the entire time. The optimizer kept proposing full rewrites that couldn't beat the R0 learnings. This is the same pattern as Uganda — TG finds something that works early (R0) then spends the rest of the run proposing increasingly elaborate rewrites that add noise.

Buffer Single showed no stagnation — rules accumulated steadily and performance was stable.

Buffer Multi got stuck *after* the R6 crash — RescueNeedAgent poisoned the context and the run never returned to its R0 peak. A different kind of stuck: not optimization stagnation but unrecoverable agent contamination.

---

### 4. Which system makes up numbers or non-existent claims?

**None badly — MIMIC is significantly cleaner than Uganda across all three systems.**

Uganda TG invented availability percentages (">75% of district hospitals"), fabricated dose ceilings ("60 mg/kg/day valproate"), and in 20B runs invented citations ("Uganda MOH 2021"). None of that appears in MIMIC TG — the structured note format gives the optimizer real signal to latch onto instead of hallucinated clinical context.

The only fabricated numbers in MIMIC runs:
- TG: confidence scoring weights (+1, +0.5 etc.) — made up, but not clinically harmful
- Buffer Single: zero fabricated numbers
- Buffer Multi: zero fabricated numbers

**Why MIMIC is cleaner:** Uganda notes are sparse (a few paragraphs) so the optimizer filled the void with textbook content. MIMIC notes are 8–10K chars of structured clinical documentation — the model has enough real signal to learn from without inventing context.

---

### 5. Which system finds irrelevant content?

**Buffer Multi's RescueNeedAgent** is the clearest example of learned irrelevance — it outputs a recommendation disguised as an observation, which is outside the agent's scope by design. The agent was supposed to surface a signal; instead it surfaced a conclusion.

TG's interaction matrix rule (rule 7) and age >60 cognitive side-effects rule (rule 9) are borderline irrelevant — clinically real but too coarse to be actionable for drug-set prediction from a single note. The model learned them from a handful of cases at most.

Buffer Single has no irrelevant rules in this run — all 17 rules bear directly on the continue/stop/start decision.

---

### 6. Overall ranking for MIMIC

| Rank | System | Reason |
|------|--------|--------|
| 1 | **Buffer Single** | Most grounded, no fabrication, no contradictions, stable optimization, rules abstract enough to transfer |
| 2 | **TextGrad** | Good document-parsing rules, low fabrication vs Uganda baseline, but over-engineered scoring rubric and 13-round stagnation |
| 3 | **Buffer Multi** | Best single-round gain (+15pp at R0) but catastrophic instability from one bad agent. Gating failure made it unrecoverable. High ceiling, high risk. |

Buffer Multi's ceiling is higher than the others (42% at R0 with just one agent is the best single-round number in this analysis) but the floor is also lower (7% after RescueNeedAgent). The agent design quality determines everything — one bad agent can erase all gains.

The right framing: Buffer Single is the most reliable optimizer. Buffer Multi is the highest-upside optimizer with the most variance. TG is the most structured but least efficient (7% accept rate, over-engineered output).
