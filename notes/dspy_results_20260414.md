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

## Output Files

- `self_learning/outputs/dspy/dspy_feedback_20260413_1504/results.json` — per-case results
- Full prompt captured in notes (not saved to file by DSPy's optimizer)
