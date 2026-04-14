# Self-Learning: Ideas & Literature

---

## Pipeline Improvements

### 1. Socratic Bootstrapping — Discovering the Latent Questionnaire

**Motivation:** Human doctors don't think in terms of "running a Pharmacologist agent." They think: *"What questions do I need answered before I prescribe?"*

**How it starts (Round 0):** The Predictor makes a guess. It fails.

**The bootstrapping mechanism:** The Inspector identifies why it failed. But instead of spawning an Agent to extract a feature, the Architect adds a Question to a global "Intake Questionnaire" (e.g., "Q1: Is the patient currently experiencing side effects?").

**The Architect's action:** In the next round, before the Predictor runs, a set of mini "Q&A Agents" are spawned on the fly. If there are 5 questions on the checklist, 5 tiny, ultra-cheap LLM calls are made — each answers exactly one question with "Yes / No / Unknown" and a supporting quote from the notes.

**The result:** From zero, the system iteratively discovers the ultimate Medical Checklist for this specific clinic. The "agents" aren't personas; they are just instances of a model answering a dynamically growing list of essential questions.

---

### 2. The "Phase Transition" — Rules Solidifying into Agents

**Motivation:** Looking at the actual data: Rules (single-agent) learn very fast but break on messy PDFs. Agents (multi-agent) are highly robust but consume a lot of prompt space. What if the system uses both, depending on how mature the concept is?

**How it starts (Round 0):** The Architect starts by only writing Rules (Shared Memory) — e.g., "Remember to check if CBZ is at max dose."

**The bootstrapping mechanism:** Over multiple rounds, a specific Rule keeps getting tweaked, expanded, or keeps failing on hard PDFs because the Predictor forgets to apply it. The rule has become a bottleneck.

**The Architect's action:** The Architect triggers a Phase Transition. It deletes the Rule from shared memory and "compiles" it into a standalone Agent. The instruction becomes: *"This concept is too hard for the Predictor to remember. Build an Agent to handle it beforehand."*

**The result:** The system uses cheap text rules as short-term memory to test hypotheses. Once a rule proves critical and complex, it "solidifies" into the system's architecture as a permanent Agent. Biological-like memory — temporary insights (rules) eventually crystallize into permanent brain structures (agents) when they prove important enough.

---

### 3. Agent Ledger — Statefulness

**The problem:** The Architect looks at the current batch to decide whether to PRUNE or EDIT an agent. If an agent does its job perfectly for 5 rounds, but in Round 6 a patient case is just fundamentally confusing, the Architect might prune a historically excellent agent based on one bad batch.

**The fix:** Pass an **Agent Ledger** to the Architect.

> *"You will receive: Inspector reports from the current batch, and an Agent Ledger: a summary of how many times each active agent was flagged as helpful vs. harmful in previous rounds. Do not blindly prune agents without knowing their historical win rate."*

---

### 4. The Domain Crossover Hack — Separating Extraction from Policy

**The problem:** The multi-agent loop had to "hack" the Ugandan formulary preference by forcing the SeizureSemiologyMapper (a diagnostician) to say things like "avoid defaulting to broad-spectrum agents" — formulary logic crammed into an extraction agent because there was no other place to store policy. Agents are being forced to act as both extractors AND rule-bearers, violating the principle that they just "surface signals."

**The fix:** A hybrid system. The Architect should have two distinct output types:

- `SPAWN_AGENT` — for structural/extraction tasks (e.g., "Find the current dose")
- `ADD_POLICY` — for hard clinical or geographical constraints (e.g., "In Uganda, prefer CBZ for focal seizures")

Pass policies directly to the Predictor. Let agents just do extraction.

---

### 5. Ideas to Steal from MOOSE-Chem2

Things we don't yet have that MOOSE-Chem2 demonstrates value for — worth adding to our loop:

- **Test-time compute**: continued scaling of inference-time compute improves output quality — important to demonstrate in our setup too.
- **Persistent memory**: the system currently has no long-term memory across runs; need somewhere to store accumulated knowledge.
- **Critique agent**: we don't have a dedicated critique step yet. MOOSE uses one to filter weak hypotheses.
- **Tournament-style debate**: debate the hypothesis across candidates, not just one round.
- **Hypothesis graph**: track which hypotheses are good/bad across iterations so we don't re-explore dead ends.
- **Mutations**: apply structured mutations to hypotheses (not just rewrites) to explore the space more efficiently.

---

## New Papers

*(Caveat: search is still ongoing — these are the best matches found so far, no perfect fit yet.)*

---

**1. SwarmAgentic**
[arxiv.org/pdf/2506.15672](https://arxiv.org/pdf/2506.15672)

The closest direct prior work. Given a task description and an objective function, the system jointly optimizes agent functionality and inter-agent collaboration through a population-based evolutionary loop inspired by Particle Swarm Optimization (PSO). Agents are not predefined — roles emerge dynamically. Results: +261.8% relative improvement over ADAS on TravelPlanner. This is the cleanest citation for the claim that "the workflow and the agents should be searched, not hand-authored." Must address directly: our differentiation is the high-stakes clinical domain, Uganda-specific constraints, and interpretable intermediate reasoning traces — none of which SwarmAgentic handles.

---

**2. AutoManual (NeurIPS 2024)**
[arxiv.org/abs/2405.16247](https://arxiv.org/abs/2405.16247)

Mechanistically one of the most relevant papers for our loop. Agents interact with an environment, accumulate rules online, and compile them into a reusable manual — with only one demonstration needed. Four roles: Planner (acts using the rule base), Builder (writes/updates rules after each trajectory), Consolidator (prunes redundant rules), Formulator (compiles rules into a readable Markdown manual). Six structured rule types — Special Phenomenon, Special Mechanism, Useful Helper Method, Success Process, Corrected Error, Unsolved Error — map almost directly onto medical rule discovery. Results: 97.4% on ALFWorld (GPT-4-turbo). Our Architect plays the Builder + Consolidator role but goes further by spawning agents, not just writing rules.

---

**3. OneFlow (+ AgentArk)**
[arxiv.org/pdf/2601.12307](https://arxiv.org/pdf/2601.12307)

The reviewer attack paper — read before submission. Core argument: most multi-agent systems are homogeneous (same LLM, different prompts), and a single agent running multi-turn conversation can match their performance via KV cache reuse. Tested across seven benchmarks. Their single-agent simulation works by injecting each role's instruction sequentially into one growing shared context. AgentArk goes further and distills multi-agent behavior into a single model. Differentiation: our agents encode genuinely specialized clinical knowledge (Uganda formulary, seizure semiology, pharmacology) that cannot be collapsed into one prompt without loss — and the reasoning traces are the artifact that clinicians need to audit, not just the final prescription.

---

**4. MegaAgent (ACL 2025 Findings)**
[aclanthology.org/2025.findings-acl.259.pdf](https://aclanthology.org/2025.findings-acl.259.pdf)

Autonomous multi-agent system without predefined SOPs. A Boss Agent decomposes a high-level meta-prompt, recruits admin agents for major subtasks, those admins recursively recruit sub-agents, and the hierarchy runs in parallel with multi-level monitoring. Adjacent to our work but the analogy is loose — their hierarchy is task-decomposition driven, ours is domain-specialization driven. Useful adjacent citation, not a direct prior.

---

**5. Towards an AI Co-Scientist**
[arxiv.org/pdf/2502.18864](https://arxiv.org/pdf/2502.18864)

Best paper to track for the highest-level vision of multi-agent scientific discovery. Treats scientific generation as an iterative multi-agent loop with proposal, critique, ranking, and refinement — rather than one-shot prompting. Useful as motivation for why structured multi-agent compute may matter, even though their roles are still hand-designed and not discovered from data.

---

**6. Self-Discover: Large Language Models Self-Compose Reasoning Structures**
[arxiv.org/pdf/2402.03620](https://arxiv.org/pdf/2402.03620)

Probably the most conceptually relevant paper for our actual bottleneck. Shows that a model can compose a task-specific reasoning structure from primitives, instead of manually writing one giant monolithic reasoning prompt. Not multi-agent, but the closest paper to the idea of *discovering structure* rather than hardcoding it — a very important bridge for our contribution.

---

**7. G-Designer: Architecting Multi-Agent Communication Topologies via Graph Neural Networks**
[arxiv.org/pdf/2410.11782](https://arxiv.org/pdf/2410.11782)

Strongest paper we've seen on task-aware communication topology. Doesn't create agents, but once candidate modules/specialists exist, this is the right reference for the claim that *who talks to whom should be learned and query-dependent, not fixed*. Stage-2 relevance: not agent creation, but agent wiring.

---

**8. MOOSE-Chem2: Exploring LLM Limits in Fine-Grained Scientific Hypothesis Discovery via Hierarchical Search**
[arxiv.org/pdf/2505.19209](https://arxiv.org/pdf/2505.19209)

Good reference for hierarchical search over scientific hypothesis spaces. Not our solution — the hierarchy is manually designed, not discovered — but still relevant when discussing how large scientific search spaces often require coarse-to-fine decomposition rather than flat generation. More about search structure than agent discovery.

---

## Quote Snippets

*For use in the paper — spread across sections as supporting citations.*

---

> "One significant bottleneck in existing agents arises from their inability to leverage test-time computation for exploration and multi-step planning."

---

> "Recent agentic work suggests that complex decision tasks benefit from structured test-time computation, where systems explicitly explore, evaluate, and prune alternative trajectories instead of relying on a single greedy rollout."

---

> "Recent advancements in large language model (LLM)-powered agents have shown that collective intelligence can significantly outperform individual capabilities, largely attributed to the meticulously designed inter-agent communication topologies. Though impressive in performance, existing multi-agent pipelines inherently introduce substantial token overhead, as well as increased economic costs, which pose challenges for their large-scale deployments."

---

> "That means the gain is not just 'more information,' but how computation is organized."

---

> "Intermediate state is explicit. Agents externalize sub-decisions that the final predictor can condition on."

---

*Framing note — for the contribution claim:*

Reviewers may push back and call this "a multi-stage scaffolded pipeline rather than autonomous agents in the strongest sense." The safest wording is: **"a clinically grounded multi-agent prescribing framework with specialized expert agents and dynamic routing."**