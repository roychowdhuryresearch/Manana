# Paper Framing — 2026-04-13

## Title (working)

Non-Parametric Continual Learning for Clinical Decision Support: Discovering Specialist Reasoning Structure from Task Feedback

## Core insight

When an LLM fails on out-of-distribution clinical data, the failures have structure — and that structure is discoverable. Two independent paths (expert clinical review and automatic NPCL from task feedback) converge on the same decomposition, proving it's a property of the task, not an artifact of system design.

## The narrative

**Act 1: The problem.** LLMs fail on OOD clinical data. Not randomly — in structured, repeatable ways. We demonstrate this on Ugandan epilepsy prescribing: the model recommends Western-preferred drugs that aren't available, switches working regimens, misses polytherapy. These aren't edge cases — they're the training prior applied to the wrong distribution.

**Act 2: The expert solution.** Two neurologists review 120 cases, identify 7 failure categories, and we design specialist agents to address each one. This works — +6-16pp across 699 patients, +21pp on polytherapy. But it required 120 expert reviews and manual prompt engineering. It doesn't scale to every clinic in every country.

**Act 3: The question.** Can we get the same result without the experts? If the failure structure is real (not an artifact of our design), a system learning from task feedback alone should discover the same structure.

**Act 4: NPCL.** We propose non-parametric continual learning — a frozen LLM adapts through interpretable text artifacts accumulated in the context window, guided by an inspect-diagnose-update loop. No weight changes. All learned knowledge is natural language a clinician can read, edit, and override. Two variants: text rules (lighter, simpler) and spawned agents (richer, more modular). These are two instantiations of the same NPCL idea, not independent methods.

**Act 5: The convergence.** Two independent paths — expert-designed agents and NPCL from task feedback — discover the same 3-4 clinical reasoning dimensions: treatment continuity, seizure classification, formulary awareness, polytherapy gating. The decomposition is a property of the task, not the method.

**Act 6: Analysis.** The learned rules are clinically valid (doctor evaluation). The system adapts from 50 patients. The rules are interpretable and editable. Comparison with DSPy shows prompt optimization gets performance but not interpretability.

## Scientific contribution

A method — non-parametric continual learning via transductive context accumulation — for adapting frozen LLMs to OOD clinical settings. The key properties:

1. **Non-parametric:** No weight updates. Knowledge stored as natural language in the context window.
2. **Interpretable:** Every learned rule/agent is human-readable, clinician-editable, auditable.
3. **Sample-efficient:** 50 calibration cases from the target clinic is enough.
4. **Convergent with expert knowledge:** Independently discovers the same reasoning structure that domain experts identify.

The clinical epilepsy application is the proof of concept. The method generalizes to any setting where you have a frozen LLM, a small calibration set with ground truth, and need interpretable adaptation.

## What makes this NeurIPS

- **Novel method:** NPCL as a paradigm for context-window-only continual learning
- **Scientific finding:** OOD failures decompose into discoverable dimensions; convergence between expert and automatic discovery
- **Practical impact:** Interpretable clinical AI that doctors can inspect and edit — unlike any parametric approach
- **Strong empirics:** 699 patients, 2,549 cases, 3 cohorts, real LMIC data
- **Interpretability is the point, not a side effect:** The entire learned knowledge is human-readable. Try doing that with LoRA weights.

## Paper sections

1. **Introduction** — OOD failure is structured + expert solution is expensive + can we automate discovery?
2. **Related work** — MDAgents, FLAME, DSPy, GEPA, continual learning, clinical AI
3. **Task & data** — Ugandan epilepsy prescribing, 699 patients, 2,549 cases, why it's OOD
4. **Expert-designed system (Consilium)** — architecture, results, what the experts identified
5. **Non-parametric continual learning** — the method: Inspector, Architect, context accumulation. Two variants (text learnings, agent spawning)
6. **Experiments** — NPCL results, convergence analysis, baselines (CoT, CoT-SC, DSPy, copy-previous), doctor evaluation
7. **Analysis** — what was discovered, mapping to expert design, interpretability, limitations
8. **Discussion** — implications for clinical AI deployment, NPCL beyond epilepsy

## Abstract (draft)

LLMs fail on out-of-distribution clinical populations in structured, predictable ways. We study this on epilepsy drug prediction in Uganda — a setting essentially absent from LLM training corpora — where a single-agent LLM systematically recommends unavailable drugs, de-escalates working regimens, and defaults to Western prescribing guidelines inappropriate for the local context.

We show these failure modes decompose into a small number of specialist reasoning dimensions. Two independent paths discover the same decomposition: (1) expert clinical review, where two neurologists identify 7 failure categories that motivate a hand-designed multi-agent system achieving +6-16pp over single-agent baselines across 699 patients, and (2) non-parametric continual learning (NPCL), where a frozen LLM adapts to the target setting by accumulating interpretable text rules in its context window through an inspect-diagnose-update loop on 50 calibration cases.

NPCL requires no weight updates, no expert input, and no domain-specific architecture. All learned knowledge is expressed in natural language — readable, editable, and auditable by clinicians. The convergence of expert-designed and automatically-discovered reasoning structures suggests the decomposition is inherent to the clinical task, not an artifact of system design. We release evaluation code and report results across three independent patient cohorts.

## Key comparison table for the paper

| Property | Fine-tuning | DSPy | NPCL (ours) |
|----------|------------|------|-------------|
| Weight updates | Yes | No | No |
| Interpretable learned knowledge | No | Partially (few-shot examples) | Fully (natural language rules/agents) |
| Clinician can edit learned knowledge | No | No | Yes — read, modify, delete any rule |
| Convergence with expert design | Unknown | Unknown | Demonstrated |
| Sample efficiency | Needs thousands | Needs tens | 50 cases |
| Catastrophic forgetting | Yes | N/A | No — modular text, additions don't corrupt |
| Auditable per-prediction | No | No | Yes — trace which rules influenced each prediction |

## Positioning vs key related work

- **vs MDAgents (NeurIPS 2024):** They do adaptive multi-agent on QA benchmarks (in-distribution). We show multi-agent helps specifically on OOD, and NPCL can discover the agent structure automatically.
- **vs FLAME (NeurIPS 2025):** They fine-tune on MIMIC (large, structured, Western). We adapt a frozen model to LMIC free-text with 50 cases. Different paradigm.
- **vs DSPy:** Prompt optimization produces optimized but opaque pipelines. NPCL produces interpretable clinical knowledge. We compare directly.
- **vs MedAgentBoard (NeurIPS 2025):** They show multi-agent doesn't always help. We identify the condition: it helps on OOD where the prior is wrong. NPCL is the mechanism.

## What still needs to happen

### Must-have
- Bootstrap CIs on all main results
- Copy-previous-regimen baseline
- CoT / CoT-SC baselines
- DSPy comparison (running now)
- Doctor evaluation (Raj + JP, 40-60 cases)
- Re-run NPCL with eval leakage fix (labmate running)

### Should-have
- Second LLM backbone
- Ablation study (which Consilium agents contribute what)
- Cost/token accounting
