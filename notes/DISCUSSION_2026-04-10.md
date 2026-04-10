# Paper Discussion — 2026-04-10

## Disagreement-as-Uncertainty: Explored and Shelved

### What we tried

Investigated whether inter-agent disagreement could serve as a calibrated uncertainty signal — predicting which cases the system gets wrong.

### Approach 1: Post-hoc signal extraction

Measured disagreement from existing outputs:
- Option diversity (Jaccard distance between Option 1/2/3)
- Pharmacologist verdict (CONCERNS vs NO_CONCERNS)
- Debate rounds triggered
- Regimen changed after debate
- Phase 1 drug mention spread

**Result: AUROC ~0.51-0.68 across visits. Essentially random at V1, modest at V2/V3.**

Why it failed:
- Pharmacologist raises concerns 99.6% of the time — no discriminative power
- Debate triggers 100% of the time — same problem
- Options are designed to be alternatives, so they're always different
- Only 9.2% of regimens change after debate — too sparse
- The architecture resolves disagreement before we measure it

### Approach 2: LLM-based conflict detection (novel)

Used an LLM to read Phase 1 agent outputs and classify conflicts into severity tiers:

- **Tier 0 (Consensus):** Agents compatible, no trade-offs needed
- **Tier 1 (Non-Blocking Tension):** Different priorities, can co-exist
- **Tier 2 (Recommendation Conflict):** One agent's drug recommendation invalidated by another
- **Tier 3 (Foundation Gridlock):** Agents disagree on base clinical facts implying different drug choices

Ran on full Cohort A V1 (279 patients, 1 LLM call each).

**Results (V1, Cohort A, 271 matched patients):**

| Tier | Cases | EM@3 |
|------|-------|------|
| 0 (Consensus) | 125 | 80.0% |
| 1 (Non-Blocking) | 16 | 87.5% |
| 2 (Recommendation Conflict) | 113 | 74.3% |
| 3 (Foundation Gridlock) | 17 | 76.5% |

By conflict count:

| Conflicts | Cases | EM@3 |
|-----------|-------|------|
| 0 | 125 | 80.0% |
| 1 | 94 | 78.7% |
| 2 | 47 | 74.5% |
| 3 | 5 | 40.0% |

### Assessment

- Tier signal is **noisy** — Tier 1 has higher accuracy than Tier 0, Tier 3 isn't much worse
- Conflict count is somewhat more discriminative — 3-conflict cases drop to 40% — but only 5 cases
- V2/V3 would have even fewer errors (35 and 26 respectively), making the signal sparser
- Not strong enough to be a headline finding

### Why it's weak

- System accuracy is already high (78-90%), leaving few errors to predict
- Architecture is designed to converge — by the time we measure, disagreement is resolved
- Phase 1 agents are advisory, not prescriptive — their "disagreements" are about emphasis, not drug choices
- Would need agents to independently prescribe (not just advise) for genuine disagreement signal

### Decision

- **Not a core contribution.** Don't position as headline finding.
- Include as exploratory analysis in supplementary material — shows we investigated it honestly
- The conflict taxonomy itself (Tier 0-3) is interesting framing but needs a stronger empirical basis
- Confidence language (hedging vs firm) was discussed as additional signal but deferred to keep complexity low
- **Not running V2/V3** — higher accuracy means even fewer errors, not worth 500+ LLM calls

### What IS the paper's contribution

Pivoting focus back to execution priorities:
1. Missing baselines (copy-previous-regimen, CoT, CoT-SC) — will get asked for these
2. Bootstrap CIs on all results — non-negotiable
3. Doctor evaluation (in progress with neurologists)
4. Paper writing

The paper's strength is the task, setting, results, ablations, and doctor evaluation — not uncertainty quantification.

## Conflict Detection Prompt (final version used)

Refined tier definitions to focus on drug-choice-affecting conflicts:
- Added: "Focus on conflicts that affect which drugs should be prescribed"
- Added: "A disagreement about seizure classification is only significant if it implies different drug choices"
- Added `drugs_in_conflict` field to output schema
- Tier 2 renamed from "Asymmetric Veto" to "Recommendation Conflict" for clarity

## Files produced

- `scripts/disagreement.py` — Post-hoc disagreement analysis (weak signal)
- `scripts/conflict_detection.py` — LLM-based conflict tier detection
- `outputs/analysis/disagreement_v1_csv.json` — Post-hoc results
- `outputs/analysis/conflicts_v1_csv.json` — LLM conflict detection results (279 patients)
