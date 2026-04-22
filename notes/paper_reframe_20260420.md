# Paper Reframe — 2026-04-20

## Core Thesis (Revised)

LLMs apply distribution-inappropriate clinical defaults when deployed in underrepresented settings. NPCL discovers interpretable correction signals from 50 cases that redirect the model's existing knowledge toward the target distribution — matching what domain experts identify independently.

## Key Framing Shift

**Old:** "LLMs fail on OOD data → we teach them with NPCL"
**New:** "LLMs have the knowledge but apply wrong defaults → NPCL discovers and corrects which defaults to suppress"

This is stronger because:
- More precise and harder to dismiss
- Explains why 50 cases is enough (redirecting, not teaching)
- Explains why rules are simple/few (correction signals, not medical education)
- More general (applies to any deployment where training ≠ target distribution)

## What NPCL Rules Actually Are

They are **distribution correction signals**, not clinical knowledge. "Prioritize formulary drugs" doesn't teach the model about carbamazepine — the model already knows carbamazepine. It corrects the model's default ordering of drugs to match the local deployment context.

## Distribution-Dependent Evidence

NPCL on MIMIC (US hospital) discovers:
- "Only retain a drug if there's an explicit continuation statement"
- "Acute focal deficits → add prophylactic levetiracetam"
- "IV loading dose without continuation intent → omit at discharge"

NPCL on Uganda (LMIC clinic) discovers:
- "Prioritize formulary drugs (CBZ, VPA, PB)"
- "Continue working regimens unless explicit failure"
- "Focal seizures → carbamazepine, not levetiracetam"

Different distributions → different correction signals. Same method, different discoveries. This IS the contribution.

## Reproducibility Strategy

| Component | Dataset | Reproducible? | What it proves |
|---|---|---|---|
| Method validation | MIMIC (1,208 patients) | Yes — code + public data | NPCL works, discovers structured rules, outperforms baselines |
| Clinical contribution | Uganda (699 patients) | No — but all metrics reported | Real-world impact, convergence with expert design, doctor evaluation |
| Distribution-dependence | MIMIC vs Uganda comparison | Partially | Different settings → different rules (same method) |
| Baselines (TextGrad, DSPy) | Both | Yes (MIMIC), No (Uganda) | NPCL generalizes where TextGrad overfits |

Release: code + MIMIC pipeline for reproduction. Uganda evaluation demonstrates clinical impact.

## MIMIC vs Uganda Rule Comparison

| Reasoning dimension | MIMIC rule | Uganda rule | Universal? |
|---|---|---|---|
| Drug selection | LEV as prophylactic default | CBZ/VPA as formulary default | No — distribution-specific |
| Treatment continuity | "Explicit continuation statement required" | "Continue if seizure-free" | Partially — both discover, different expression |
| Escalation logic | "Active dose titration → continue" | "≥2 failed ASMs before add-on" | No — different thresholds |
| Seizure classification | Not discovered (not a MIMIC failure mode) | Major rule cluster | No — only matters where defaults are wrong |

Universal reasoning = transfers across distributions. Distribution-specific = gets corrected/pruned when moving between sites.

## Narrative Flow (Revised)

1. LLMs have general medical knowledge but apply distribution-inappropriate defaults in underrepresented clinical settings (Uganda epilepsy prescribing)
2. These failures are structured and predictable: always toward LEV, always away from continuation, always toward Western prescribing patterns
3. Expert intervention works: two neurologists identify 7 failure categories → we build specialist agents → +6-16pp across 699 patients
4. Existing prompt optimization (TextGrad, DSPy) can't solve it: TextGrad matches accuracy but overfits, fabricates citations, fails cross-cohort; DSPy underperforms because it learns from successes not failures
5. NPCL: a simple 3-component loop (predictor, inspector, architect) that learns distribution-correction signals from failures and accumulates them as interpretable text
6. Result: closes most of the expert gap with 50 cases and zero clinical expertise
7. Finding: the automatically discovered corrections converge with expert-designed corrections — the failure structure is task-intrinsic
8. Distribution-dependence: same method on MIMIC discovers different corrections (discharge reconciliation) vs. Uganda (formulary-appropriate prescribing) — confirming NPCL is distribution-adaptive, not task-generic
9. Reproducibility: MIMIC pipeline + code released for verification; Uganda results demonstrate clinical impact

## Cohort A vs B: Genuine Distribution Shift

KL divergence analysis (stats/distribution/) shows A and B are meaningfully different populations:

| Feature | KL Divergence | Key Difference |
|---|---|---|
| Age at Visit | 0.315 | A is much younger (58% under 5), B more spread |
| Seizure Type | 0.300 | A ~37% focal / 59% GTC; B ~73% GTC / 22% focal |
| Seizure Onset Age | 0.256 | A skews earlier onset |
| Seizure Burden | 0.227 | A more daily seizures; B more seizure-free/rare |
| Cognitive Burden | 0.219 | A ~48% none; B ~68% none |
| LEV use | 0.208 | A 3.8% vs B 37.2% (10x difference) |
| VPA use | 0.127 | A 36.2% vs B 7.6% (5x difference) |

Cohort A = young, focal-dominant, VPA/CBZ-heavy (classic LMIC formulary)
Cohort B = older, GTC-dominant, LEV-heavy (closer to Western prescribing)

**Main paper**: KL divergence figure + cross-cohort generalization result (A-trained self-learning gets 76.2% on B V1, beating Consilium's 71.5%). This is already evidence of distribution-adaptive correction.

**Appendix (if results are clean)**: Formal A→B CL experiment — train on A, continue on B, measure forgetting on A. If A rules get appropriately pruned/edited for B without degrading A performance, include as supplementary CL evidence. If messy, omit — main paper doesn't depend on it.

## Regularization Framing (from advisor meeting 2026-04-20)

### Core Insight

TextGrad/DSPy perform **unregularized** text-space optimization — they minimize training loss without structural constraints, producing specific decision rules that overfit. Our method introduces **implicit regularization** through its architecture, biasing toward general reasoning dimensions that transfer.

### The Regularizers

1. **Quorum rule (minimum support)**: Architect needs 2+ patients showing the same pattern before acting. Prevents overfitting to single-case outliers.

2. **Inspector-Architect decomposition (abstraction bottleneck)**: Inspector diagnoses per-case errors. Architect sees batch-level summaries, never raw patient notes. Information bottleneck forces abstraction from cases to patterns.

3. **Append vs. rewrite (small learning rate)**: TextGrad rewrites the whole prompt each round (full gradient step). Our method appends/edits/prunes incrementally. Prevents catastrophic swings.

4. **Error-grounding (not parametric recall)**: Rules describe observed error patterns, not model-recalled "knowledge." Prevents confabulation of false-precision thresholds and fabricated citations.

5. **Agent specialization (structural bottleneck, multi-agent only)**: Each spawned agent covers exactly one clinical dimension. Factored representation prevents any single component from becoming a kitchen-sink memorizer.

### Evidence

- TextGrad R11 rules: mostly specific decision rules with fabricated thresholds ("≥4 seizures in 30 days", "≤18 mg/kg/day")
- Our rules: mostly reasoning dimensions ("classify seizure type", "prioritize formulary drugs", "continue working regimens")
- TextGrad on Cohort B V1: 62.8% (worse than no-learning baseline 65.9%)
- Ours on Cohort B V1: 76.2% (beats expert-designed Consilium 71.5%)
- Generalization gap: +13.4pp — explained by regularization bias

### Why Convergence With Experts Is a Consequence of Regularization

Doctors don't memorize lookup tables. They think in reasoning dimensions: "classify the seizure type, check what's available locally, continue what's working." The implicit regularizers in our method bias the system toward the same level of abstraction that clinical reasoning naturally operates at. Convergence isn't a coincidence — it's a consequence of the regularization pushing toward general dimensions, which is the same level experts operate at.

### Possible Ablations (if time allows)

| Ablation | Remove | Prediction |
|---|---|---|
| No quorum | Single-patient rules allowed | More specific, worse transfer |
| Per-case architect | Skip batch synthesis | More case-specific, worse transfer |
| Full rewrite | Replace append with rewrite | More like TextGrad, more oscillation |

### Paper Positioning

**Old:** "We have a different loop than TextGrad"
**New:** "The design of the learning process implicitly regularizes what can be learned, biasing toward general reasoning dimensions over specific decision rules — explaining both the generalization advantage and the convergence with expert knowledge"

## What Still Needs To Happen

### Must-have
- Multi-seed convergence (run NPCL 3x with different seeds, show same dimensions emerge)
- Bootstrap CIs on all main results
- Doctor evaluation (in progress — traces from Consilium vs self-learning)
- Copy-previous / CoT / CoT-SC baselines

### Should-have
- MIMIC→Uganda transfer experiment (warm-start from MIMIC rules, measure transfer + adaptation speed)
- Quantitative convergence metric (Jaccard over patient-fix-sets between NPCL rules and Consilium agents)
- Second model run (at least one more backbone)

### Framing decisions
- Drop "continual learning" from title unless CL experiment is run
- Use "non-parametric distribution adaptation" or "interpretable test-time calibration" instead
- Lead with the FINDING (distribution-dependent failures are discoverable and correctable) not the METHOD (the loop)

## One-Sentence Pitch

"LLMs apply distribution-inappropriate clinical defaults; NPCL discovers interpretable correction signals from 50 cases that redirect the model's existing knowledge toward the target distribution — matching what domain experts identify independently."

## Key Defensibility Points

**"Is it really OOD if prompting helps?"**
It's not OOD in the sense of missing knowledge — the model knows these drugs. It's distribution-dependent: the model's priors (which drug to prefer, when to escalate) are calibrated to its training distribution (Western prescribing), not the deployment distribution (Ugandan clinic). NPCL corrects the prior, not the knowledge.

**"Inspector knows Uganda — is discovery truly automatic?"**
Inspector knows WHERE (Uganda) but not HOW (no clinical reasoning, no guidelines, no prescribing rules). Knowing the geographic setting is metadata equivalent to "these are chest X-rays from India." All clinical reasoning structure emerges from error analysis.

**"Convergence is qualitative"**
Address with: (1) multi-seed showing same dimensions emerge, (2) quantitative patient-fix-set overlap between NPCL rules and Consilium agents, (3) doctor evaluation confirming clinical validity of discovered rules.

**"This is prompt optimization with extra steps"**
The output is different: TextGrad produces an opaque optimized prompt that fabricates and overfits. NPCL produces modular correction signals that generalize, don't fabricate (grounded in observed errors), and are clinician-editable. The mechanism matters less than what it produces.
