# Swarm-Governed Self-Learning Multi-Agent System for Clinical Decision Support

## What We Are Trying To Do

We have a working multi-agent system (Consilium) for predicting epilepsy prescriptions in Uganda. It works well — but every specialist agent was designed by hand with clinician input. The research question is:

**Can a system discover its own useful clinical decomposition — without any doctor-designed roles — using only minimal medical knowledge, biologically grounded swarm rules, and delayed outcome feedback?**

The system starts with a single dumb agent. It runs on patients, gets answers wrong, sees the truth, and iteratively restructures itself — spawning new specialist agents, accumulating domain knowledge, and pruning what doesn't help. The spawning and restructuring follow rules derived directly from animal swarm intelligence (ant colonies, honeybee nest selection, fish schools), not from a central planner inventing roles.

---

## The Starting Point

### The Predictor (Agent Zero)

The system begins with exactly one agent. Its system prompt contains:

- **Output format (FIXED, never edited):** Produce exactly 3 ranked prescription predictions in a specified JSON schema. This constraint is permanent — no matter how the system evolves, the final output always follows this format.
- **Minimal medical context (editable):** A small seed of domain knowledge — seizure types matter, prior medications matter, dose and weight can matter, age can matter, local drug availability can matter. No specialist knowledge, no Ugandan-specific treatment rules, no decision algorithms.
- **Task description (editable):** You are predicting what an epilepsy doctor in Uganda will prescribe given these clinical notes. You have access to a shared learnings stream (initially empty). Read it before reasoning.

The Predictor's medical reasoning section CAN be edited by the Architect in later rounds. The output format section CANNOT. This means the system can improve how the Predictor thinks but can never break the interface contract.

When agents are spawned later, the Predictor's role shifts: it becomes the final synthesis node that reads all upstream agent outputs from the per-patient working context and produces the top-3 predictions. Its output format remains identical.

---

## The Loop

The system operates in repeating cycles. Each cycle has four phases.

### Phase 1 — Inference (per patient)

All currently active agents process the patient. Each agent receives:
- Its own system prompt (role-specific, written by the Architect)
- The shared learnings stream (persistent across patients, read-only during inference)
- The patient's clinical notes
- Outputs from any upstream agents (per-patient working context)

Each agent produces a structured output with:
- Its clinical assessment or recommendation (role-specific)
- An **uncertainty flag**: one sentence describing what it was unsure about, if anything. This is mandatory. The agent does not evaluate itself — it simply reports confusion.

The Predictor runs last, reads all upstream outputs, and produces the final 3 predictions.

### Phase 2 — Ground Truth Reveal

The actual doctor's prescription is revealed. The system now knows whether it was right or wrong, and by how much (exact match, partial Jaccard overlap, complete miss).

### Phase 3 — Inspection (per patient, parallelizable)

The **Inspector** processes each patient independently. It sees:
- The full patient clinical notes
- Every agent's full raw reasoning trace
- Every agent's uncertainty flag
- The final predictions vs. the ground truth

The Inspector's job is purely diagnostic. It produces a compact report per patient:
- What was the error (if any)?
- Which agent(s) contributed to the error?
- What information was present in the notes but no agent used?
- Which uncertainty flags were accurate vs. irrelevant?
- What clinical dimension was missing from the current agent population?

The Inspector does NOT make any structural decisions. It is compression with clinical understanding — turning pages of raw traces into targeted diagnostics.

### Phase 4 — Architecture Evolution (once per batch)

The **Architect** runs once after a batch of patients (e.g., 10-15) has been processed through Phases 1-3. It sees:
- All Inspector reports from the batch
- All current agent system prompts **in full**
- The current shared learnings stream
- The last round's edit history (what the Architect did last time and whether it helped)
- The swarm grammar rules (its permanent instructions)

The Architect produces a single structured output containing a list of actions. Each action is one of:

**Spawn** — Create a new agent. Provide its complete system prompt. Justify why based on repeated patterns in Inspector reports (quorum rule: the same gap appeared across multiple patients).

**Prune** — Remove an agent that has not contributed to correct predictions over the evaluation window. Justify based on evidence.

**Edit** — Modify an existing agent's system prompt. Provide the exact edit and reasoning. This includes the Predictor's medical reasoning section.

**Write shared learning** — Add a domain insight to the shared learnings stream. This must be a general clinical fact useful to ANY agent, not role-specific guidance. Tag with confidence based on how many patients supported the pattern.

**Prune shared learning** — Remove or downweight a shared learning that correlated with errors.

Every action is tagged with a destination:
- `agent_prompt` — goes to one specific agent's system prompt
- `shared_stream` — goes to the shared learnings stream
- `both` — goes to both a specific agent AND the shared stream
- `neither` — finding noted but no action taken (one-off, insufficient evidence)

---

## The Swarm Grammar

The Architect's permanent instructions encode these rules, derived from documented animal swarm behavior. These govern HOW the Architect makes decisions — they are not suggestions, they are constraints.

### Finite-Neighborhood Sensing
Each spawned agent must have a restricted local view. It sees one clinical dimension, one time window, or one aspect of the patient. No agent (except the Predictor at synthesis) should see everything and reason about everything. If the Architect creates an agent with an overly broad role, it is violating locality.

### Parallel Scouting / Repeated Sampling
Multiple agents may inspect overlapping aspects of the same patient. Redundancy is acceptable and expected. The system should not have exactly one agent per clinical dimension — some dimensions benefit from multiple perspectives.

### Stigmergy (Environment as Memory)
Agents coordinate through the shared learnings stream and per-patient working context, not by talking to each other. No agent directly reads another agent's system prompt or modifies another agent's behavior. Coordination is indirect, through traces left in the shared environment.

### Positive Feedback Recruitment
If multiple Inspector reports flag the same unaddressed clinical dimension across a batch, the Architect should spawn a specialist for it. Repeated signal = recruitment trigger.

### Negative Feedback / Cross-Inhibition
If an agent's outputs consistently conflict with the ground truth or if following its recommendations correlates with errors, the Architect should prune or weaken it. Agents that produce noise get suppressed.

### Quorum-Triggered Commitment
Do not spawn after seeing one patient's error. Do not prune after one patient's failure. Structural changes require consistent evidence across the batch. The minimum quorum for spawning or pruning should be specified (e.g., same pattern in ≥ 3 patients in a batch of 10).

### Response-Threshold Division of Labor
Roles are not predefined. They emerge because certain failure patterns repeatedly trigger certain types of spawned agents. Over time, the population should specialize — not because anyone designed the specialization, but because the evidence demanded it.

### Signal Decay / Forgetting
Shared learnings that are old and have not been reinforced by recent evidence should be downweighted or pruned. Agent prompts that were useful in early rounds but have not contributed recently should be revisited. The system should not be permanently committed to early decisions.

---

## The Shared Learnings Stream

This is a persistent, ordered list of domain insights that grows across patient batches. It is prepended to every agent's context at inference time.

**Properties:**
- Hard cap of ~30 entries to prevent context overflow.
- Each entry has: the insight text, a confidence score, the batch it was added, the last batch it was reinforced.
- The Architect can ADD, EDIT, REINFORCE (bump confidence), DOWNWEIGHT, or REMOVE entries.
- When the cap is reached, the Architect must merge, compress, or prune before adding new entries.

**What belongs here:** Domain facts any agent benefits from. "Phenobarbital is second-line in this clinic, not first-line." "Weight is recorded inconsistently — if missing, check prior visit notes."

**What does NOT belong here:** Role-specific instructions (those go in agent prompts). Patient-specific observations (those die with the per-patient context).

---

## Edit History

The Architect maintains a one-batch-deep memory of its own actions:
- What it spawned/pruned/edited last round
- What shared learnings it added/removed last round
- Whether those changes correlated with improved or worsened performance in the current batch

This gives the Architect continuity without unbounded memory growth. It can reason about "I tried X last time and it didn't help, so I should try Y instead" without needing the full history of all rounds.

Optionally, a compressed running log can be maintained: one line per round summarizing what was done. "Round 1: spawned dose_checker. Round 2: kept dose_checker, spawned seizure_classifier, added 3 shared learnings. Round 3: pruned seizure_classifier (no improvement)." This stays tiny indefinitely.

---

## Evaluation Strategy

### Primary Metric
- **EM@3**: Does any of the 3 predicted regimens exactly match the doctor's prescription?

### Secondary Metrics
- **Jaccard similarity**: Partial drug overlap
- **Polytherapy EM@3**: Performance specifically on multi-drug patients (the hardest subgroup)
- **Longitudinal consistency**: Does performance improve from V1 → V2 → V3 for the same patient?

### Experimental Comparisons

1. **Single agent baseline** — The Predictor alone, no spawned agents, no shared learnings. This is the floor.

2. **EvoAgent baseline** — Same Predictor, but agents are spawned via blind evolutionary mutation/crossover instead of swarm grammar. Same number of agents, same evaluation schedule. This isolates the effect of need-driven vs. random spawning.

3. **Consilium (doctor-designed agents)** — The existing hand-crafted multi-agent system. This is the ceiling — can the swarm approach recover any of this performance without expert input?

4. **Swarm system (this design)** — The full self-learning architecture described in this document.

### What We Hope To Show

The swarm system should:
- Outperform the single agent baseline (proving that self-discovered decomposition helps)
- Outperform or match EvoAgent (proving that need-driven spawning is more sample-efficient than blind evolution)
- Partially recover Consilium's performance (proving that the decomposition can be discovered, not just hand-designed)
- Discover emergent roles that are functionally similar to the doctor-designed ones (proving the decomposition is real, not arbitrary)

---

## System Components Summary

| Component | What It Is | When It Runs | What It Sees | What It Produces |
|-----------|-----------|-------------|-------------|-----------------|
| **Predictor** | Final synthesis agent, fixed output format | Every patient (last in chain) | All upstream agent outputs + shared learnings + patient notes | Top-3 prescription predictions |
| **Spawned Agents** | Narrow specialists, system prompts written by Architect | Every patient (before Predictor) | Their own prompt + shared learnings + patient notes + relevant upstream outputs | Structured clinical assessment + uncertainty flag |
| **Inspector** | Clinical error diagnostician | Every patient (after ground truth) | Full patient notes + all raw agent traces + ground truth | Compact diagnostic report per patient |
| **Architect** | Swarm-governed system evolver | Once per batch | All Inspector reports + all agent prompts + shared stream + edit history | Spawn/prune/edit/write-learning actions |
| **Shared Learnings Stream** | Persistent cross-patient domain knowledge | Read at inference, written by Architect | N/A (it is a data store) | Domain insights, capped at ~30 entries |
| **Edit History** | One-batch memory of Architect's own actions | Read by Architect each batch | N/A (it is a data store) | Last round's actions + their measured impact |

---

## What Is NOT Decided Yet

- Exact batch size (10? 15? 20 patients?)
- Exact quorum thresholds for spawn/prune decisions
- Whether the Predictor's medical reasoning section should be editable or frozen after round 1
- Exact format of uncertainty flags (free text vs. structured categories)
- How to handle agent execution order when dependencies exist between spawned agents
- Which LLM to use for each component (could differ for Inspector vs. Architect vs. agents)
- Patient sampling strategy across batches (random? stratified by mono/poly? longitudinal ordering?)
- Maximum number of agents the system is allowed to spawn