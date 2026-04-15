# DSPy Baseline Results — 2026-04-14

## Setup

- **Method:** DSPy BootstrapFewShot (4 demos)
- **Model:** openai.gpt-oss-120b-1:0 via Bedrock
- **Starting knowledge:** Same as NPCL — "clinic in Uganda", 10 drug names, output format. No clinical reasoning, no formulary info, no seizure type guidance.
- **Training data:** 20 neurologist-reviewed feedback patients (63 cases, 61 valid examples) — same patients that motivated the Consilium agent design
- **Eval data:** Same stratified held-out 60 cases as NPCL (seed=42)
- **Optimizer:** BootstrapFewShot with max_bootstrapped_demos=4, max_labeled_demos=4

## Results

| Method | Top-3 Exact | Mean Score |
|--------|------------|------------|
| DSPy unoptimized (CoT, no demos) | 31/60 (52%) | 0.716 |
| DSPy optimized (4 bootstrapped demos) | 38/60 (63%) | 0.758 |

### Comparison on same eval set

| Method | Top-3 | How it learns |
|--------|-------|---------------|
| Zero-knowledge predictor | ~39/60 (65%) | Nothing |
| DSPy optimized | 38/60 (63%) | Few-shot example selection |
| NPCL text learnings (peak) | ~48/60 (80%) | Inspector → Architect → text rules |
| NPCL agent spawning (peak) | ~48/60 (80%) | Inspector → Architect → agent prompts |
| Consilium (expert-designed) | ~77-90% | Neurologist review |

**DSPy underperforms both the zero-knowledge predictor and NPCL by a wide margin.**

## What DSPy Actually Learned

DSPy's "optimization" = selecting 4 training cases where the unoptimized model happened to get the right answer, then using those as few-shot demonstrations. The full optimized prompt consists of:

1. System message with field definitions and task description
2. Four complete patient case examples (notes → reasoning → 3 options)
3. The actual query

The 4 selected demos were:
- Demo 1: Infant with focal epilepsy on carbamazepine → continue CBZ
- Demo 2: 12yo with focal epilepsy on CBZ + LEV → continue both
- Demo 3: Child with epilepsy on valproate → continue VPA
- Demo 4: 8yo with first focal seizure → start CBZ

### How the demo reasoning is generated

The reasoning in each demo is **model-generated, not expert-written**. DSPy's bootstrap process:
1. Runs the unoptimized model on a training case
2. Checks if the output matches ground truth
3. If yes, saves the model's own reasoning as the demo
4. Repeats until it has 4 successful traces

"Bootstrapped 4 full traces after 4 examples" — the first 4 training cases all happened to produce correct answers, so DSPy used those. The quality of the demo reasoning depends entirely on whether the model happened to reason well on those specific cases.

## Why DSPy Underperforms NPCL

### What DSPy can convey through demos
- Output format (by example)
- That carbamazepine and valproate are common drugs
- That continuation of current drugs is common
- Implicit patterns in the 4 specific cases shown

### What DSPy cannot convey
- **"This is an LMIC setting where drug availability is constrained"** — no demo captures this as an abstract principle
- **"Don't recommend levetiracetam as first-line"** — the demos happen not to use LEV first-line, but the model won't generalize this implicit pattern to a rule
- **"Classify seizure type before selecting drugs"** — the demo reasonings do this, but as behavior to imitate, not a rule to follow
- **"If the patient is seizure-free, continue everything"** — only visible if a demo happens to show this exact case

### The interpretability gap

NPCL's text rules are **explicit and general**:
> "Prioritize formulary drugs. Continue working regimens. Classify focal vs generalized."

DSPy's demos are **implicit and case-specific**:
> "Here are 4 cases where the model got the right answer. Do something similar."

A doctor reading NPCL's 15 rules can identify which rule is wrong and delete it. A doctor reading 4 example cases cannot easily identify which implicit pattern is causing a bad prediction downstream.

### The knowledge source gap

DSPy's demos are bootstrapped from model successes — cases where the model already got it right. This means DSPy can only teach what the model already knows. It cannot surface knowledge the model fails to apply.

NPCL's learning is bootstrapped from model failures — the Inspector diagnoses why the model got it wrong, and the Architect writes rules to prevent recurrence. NPCL surfaces latent knowledge the model has but wasn't applying. This is fundamentally different from selecting good examples.

## Additional Runs — 2026-04-14

### DSPy BootstrapFewShot (50 stratified patients)

| | Top-3 Exact | Mean Score |
|---|---|---|
| Unoptimized | 31/60 (52%) | 0.716 |
| Optimized | 32/60 (53%) | 0.728 |

Barely moved. Bootstrap found 4 easy cases quickly and stopped. 3 of 4 demos recommended levetiracetam — inheriting the Western bias.

### DSPy MIPROv2 (50 stratified patients)

| | Top-3 Exact | Mean Score |
|---|---|---|
| Unoptimized | 31/60 (52%) | 0.716 |
| Optimized | 38/60 (63%) | 0.760 |

MIPRO generated 3 candidate instructions. The winning instruction (82.65% on internal eval) was a **copy-previous-regimen heuristic**: "Identify the most recent prescription block... Extract every drug name... Assign the action `continue` to each extracted drug... Produce three identical prescription options." It discovered the shortcut that ~80% of cases are continuations, but failed on the hard cases (63% on held-out eval).

### DSPy GEPA (50 stratified patients)

| | Top-3 Exact | Mean Score |
|---|---|---|
| Unoptimized | 31/60 (52%) | 0.716 |
| Optimized | 31/60 (52%) | 0.716 |

920 rollouts over 30 iterations. Best internal validation score: 76%. Held-out eval: 52% — identical to baseline. Massively overfit to its validation subset despite reflection-based optimization.

### Full Comparison Table (same eval set, same 50-patient training split)

| Method | Approach | Top-3 Exact | Key finding |
|--------|----------|-------------|-------------|
| Unoptimized baseline | Zero-shot CoT | 31/60 (52%) | — |
| DSPy Bootstrap | Few-shot selection | 32/60 (53%) | Selects demos with Western bias |
| DSPy MIPROv2 | Instruction rewriting | 38/60 (63%) | Discovers "copy last prescription" shortcut |
| DSPy GEPA | Reflective evolution | 31/60 (52%) | 920 rollouts, overfit, no improvement |
| **NPCL text learnings** | **Error-driven rules** | **~48/60 (80%)** | **15 interpretable clinical rules** |
| **NPCL agent spawning** | **Error-driven agents** | **~48/60 (80%)** | **5 spawned specialist agents** |

### Why DSPy fails where NPCL succeeds

1. **DSPy optimizes for the metric. NPCL optimizes for understanding.** DSPy's strongest result (MIPRO) discovered a shortcut — "copy the last prescription." This scores well on average but fails on every case where drugs change. NPCL discovers clinical rules that handle both easy and hard cases.

2. **DSPy bootstraps from successes. NPCL bootstraps from failures.** DSPy selects examples where the model already got it right, inheriting whatever reasoning (and biases) led to those successes. NPCL's Inspector diagnoses why the model got cases wrong, and the Architect writes rules to prevent recurrence. NPCL surfaces latent knowledge the model has but wasn't applying.

3. **DSPy's learned knowledge is implicit. NPCL's is explicit.** DSPy produces few-shot examples or rewritten instructions that a doctor cannot easily audit. NPCL produces "1. Prioritize formulary drugs. 2. Continue working regimens. 3. Classify seizure type." A doctor can read, validate, and edit these.

4. **DSPy overfits. NPCL generalizes.** Both MIPRO (82.65% internal → 63% held-out) and GEPA (76% internal → 52% held-out) show significant overfitting. NPCL's 80% is measured on a truly held-out eval set that the learning loop never touches.

## Output Files

- `self_learning/outputs/dspy/dspy_feedback_20260413_1504/` — Bootstrap, 20 feedback patients
- `self_learning/outputs/dspy/dspy_bootstrap_20260414_1706/` — Bootstrap, 50 stratified patients
- `self_learning/outputs/dspy/dspy_mipro_20260414_1722/` — MIPROv2, 50 stratified patients
- `self_learning/outputs/dspy/dspy_gepa_20260414_1747/` — GEPA, 50 stratified patients
