# Consilium — Reviewer-Proofing Guide

Everything needed to make the paper airtight before submission. Organized into three
buckets based on what kind of work is required. Bucket 1 is the most important — these
are NOT pending experiments, they are framing and presentation choices that must be
deliberately made in the writing. If the paper is written carelessly, reviewers will
flag these; if written deliberately, they become strengths.

Each item cites which reviewer in which paper raised the concern and what the authors
had to do in rebuttal. Better to address in the paper than in rebuttal.

---

## BUCKET 1 — Framing & Presentation (No New Experiments Needed)

These are the hardest to fix in rebuttal because they require restructuring the paper,
not just adding a table. Every item here should be treated as a writing task.

---

### B1.1 — Novelty: What Is Actually New Here?

**Why this gets flagged:**
MedAgentBoard Reviewer taNB (rated borderline 4/5): *"The novelty of this paper is
unclear. The datasets and experiments are obtained from existing papers. Similar
observations that multi-agent system will not work in all scenarios is also not news.
I am wondering if the authors can summarize the key novelty design in the work, making
it different from repeating experiments mechanically."*

MedAgentBoard had to write an entire table in rebuttal listing contradictory prior
findings (pro-collaboration: MedAgents ACL 2024, ReConcile ACL 2024; anti: Cemri et
al. 2025, Zhang et al. 2025) to justify why a systematic benchmark was needed. This
only worked because reviewers raised it to 5 during rebuttal — but it almost didn't.

MDAgents Reviewer g9qW: *"The paper makes a good case in comparing the main idea to
relevant related works, emphasizing how the combination of used concepts and their
grounding in the respective agent roles is new."* — they got credit for articulating
this clearly up front.

**What reviewers assume we are:**

- MDAgents but for prescribing (MDAgents already did adaptive multi-agent medical reasoning)
- FLAME but with debate (FLAME already did LLM medication recommendation)
- MedAgentBoard already showed multi-agent isn't always better

**Why we are genuinely different — must be stated in intro, crisp, in 3-4 sentences:**

1. **Task**: We are not doing medical QA. We are not predicting drug codes from ICD
  codes. We are predicting the *specific regimen* that a *specific doctor at a
   specific clinic in Uganda* will prescribe to a *specific patient with 3+ years of
   longitudinal history*, using *free-text clinical notes*. No existing paper does
   this task.
2. **OOD setting is the contribution, not the method**: MDAgents tests multi-agent on
  benchmarks where the model's training distribution matches the task. We test it on
   a patient population (Ugandan, pediatric-dominant, LMIC-formulary-constrained) that
   is essentially absent from every known LLM training corpus. The finding that
   multi-agent helps *specifically on OOD data where the single agent's prior is wrong*
   is a direct, precise response to MedAgentBoard's finding that it doesn't
   consistently help — and we have ablation evidence for it.
3. **Reasoning traces ARE the deliverable**: FLAME achieves Jaccard 0.484 on MIMIC and
  produces zero reasoning. DrugRec produces zero reasoning. Our claim is not "we get
   higher accuracy" — it is "we get *attributable, interpretable clinical reasoning*
   that a nurse practitioner or general physician in Uganda can act on, question, and
   reject." This is a fundamentally different contribution than score maximization.
4. **First LMIC longitudinal free-text drug prediction benchmark**: Nature Medicine 2025
  explicitly notes the "striking lack of real-world evidence" for LLM use in African
   clinical settings. We are filling that gap. No existing benchmark covers this.

**How to frame it in the intro:**
Lead with the gap, not the method. Don't say "we propose a multi-agent system." Say
"LLMs fail in specific, predictable ways on LMIC patient populations, and the existing
multi-agent literature doesn't address why or when structured collaboration helps in
genuinely out-of-distribution clinical settings. We study this question."

---

### B1.2 — Is Role-Prompting Actually Expertise? Or Just Theatrical?

**Why this gets flagged:**
MDAgents Reviewer mJeV: *"Is assigning an agent a role enough to let the LLM act like
an expert in that specific discipline, which requires a lot of domain knowledge? How
about equipping different agents with different knowledge for RAG?"*

This is the single most dangerous philosophical attack on the paper. If reviewers
believe our agents are just "different prompts that all call the same model," they can
dismiss the entire architecture as a prompt engineering exercise, not a scientific
contribution.

MedAgentBoard went even further — their case study showed a "Cardiologist" agent
analyzing a brain MRI admitted it had no neurological expertise, but the framework
still gave weight to its answer in the final synthesis. Reviewers used this to argue
role-playing doesn't create genuine expertise.

**The attack on us specifically:**
"Your tropical_medicine agent is just GPT with a prompt saying 'you are a tropical
medicine specialist.' The model has no more knowledge about Ugandan drug availability
than the single agent. You've just added latency and cost."

**Our answer — must be backed by trace evidence:**

The claim is NOT that role-prompting creates expertise that doesn't exist in the model.
The claim is that role-prompting creates *scope and attention* — it directs the model
to surface knowledge it has but would otherwise deprioritize given its general training
distribution.

Concretely:

- The `tropical_medicine` agent consistently flags that levetiracetam has limited
availability in sub-Saharan formularies — knowledge that exists in the model but
gets overridden by Western training priors when reasoning as a generalist.
- The `formulary` agent consistently notes that phenobarbital is the cost-dominant
option in LMIC settings — this is in the model's training data but doesn't surface
without explicit scope.
- The `pediatrician` agent adjusts dosing reasoning for pediatric weight-based
calculations — the model knows this but deprioritizes it without role scope.

**What this requires in the paper:**
The `error_detection.py` / `trace_quality.py` analysis scripts must produce hard
numbers: "In X% of cases where the single agent recommended levetiracetam, the
tropical_medicine agent flagged availability constraints." Qualitative trace examples
are mandatory in the appendix. At least 2-3 concrete agent-specific examples that
show domain-specific reasoning actually happening, not just role-playing language.

If we can't show this, the architecture is indefensible. This is the primary empirical
job of the trace analysis scripts.

---

### B1.3 — Counterintuitive Results: Pharmacologist Hurts Accuracy

**Why this gets flagged:**
MDAgents had Figure 5 showing "Low" complexity questions having lower accuracy than
"Moderate" when forced into the Low-complexity solver path. Reviewer mREC: *"The
results shown in Figure 5 seem counterintuitive. For image + text and video + text,
the score for Low is higher than for moderate and high. This suggests that some
questions that can be correctly solved with a single agent result in incorrect answers
when multiple agents are involved. More analysis is needed."*

Authors had to explain this carefully in rebuttal. They couldn't just say "trust us."

**Our version of this problem:**

Our pre-pharma vs post-pharma results:


| Visit | Pre-Pharma | Post-Pharma | Delta      |
| ----- | ---------- | ----------- | ---------- |
| V1    | 79.0%      | 77.9%       | **-1.1pp** |
| V2    | 87.2%      | 87.2%       | 0.0pp      |
| V3    | 89.3%      | 90.4%       | +1.1pp     |


Reviewers will say: "Your pharmacologist hurts performance at V1 and does nothing at
V2. Why is it in the pipeline? You're adding cost and latency for a net-negative
contribution."

Additionally, ablation table:

- `no_pediatrician` outperforms full pipeline at V1 (80.5% vs 78.7%) and V2 (83.6%
vs 89.4% — wait, no, 83.6% is worse at V2). At V1 though it's +1.8pp.
- `no_treatment_analyst` hurts significantly at V2/V3, confirming it's valuable later.

**The answer that must be in the paper (cannot be left for rebuttal):**

On pharmacologist:
Exact-match accuracy is the wrong metric for measuring pharmacologist value. The
pharmacologist's contribution is *safety*, not accuracy. Its job is to flag unsafe
drug combinations and catch dosing errors — events that are rare in the dataset because
the GT prescriptions ARE safe (the doctor already checked). A pharmacologist that
correctly prevents a dangerous combination that the epileptologist missed will show
as a *wrong prediction* if the doctor's GT was also the dangerous combination.

The correct framing: pharmacologist value is in clinical safety, not GT matching. The
pre-pharma vs post-pharma comparison is included to show the system doesn't degrade
significantly, not to prove the pharmacologist improves accuracy. The marginal accuracy
cost is small (~1pp at V1) and justifiable given the safety function.

On no_pediatrician at V1:
Pediatrician value is visit-dependent. At V1 (first visit, limited history), the
pediatrician adds noise because there's insufficient longitudinal context to reason
about pediatric treatment trajectories. At V2/V3, the pediatrician contribution
becomes more meaningful as it has prior visit responses to reason about. This is
confirmed by the ablation pattern. Frame this as a finding: "early-visit vs
late-visit agent contribution differs predictably based on available longitudinal
context."

Both of these must be pre-emptively explained in the results section, not left as
surprises.

---

### B1.4 — Counterintuitive Results: Short-Gap Patients Are Harder

**Why this gets flagged:**
Any result where "more clinical context" → worse performance will be questioned. The
short-gap finding directly challenges the intuition that the system should help most
for complex/unstable patients.

**Our result:**
V2 accuracy by V1→V2 gap:

- < 4 months: 67.9% (worst)
- 4-9 months: 88.6% (best)
- > 15 months: 86.7%

Short-gap patients return EARLY because they're unstable. Of 9 wrong short-gap V2
predictions, 7 had regimen changes between V1→V2.

**The answer — must be in results:**
Short-gap patients are not "easier cases with more context." They are the clinically
most unstable patients — they return early *because* their current regimen is failing.
The model (and the single-agent baseline even more so) has learned to predict
continuity; short-gap cases violate the continuity assumption because the doctor is
likely to switch. This is a genuine limitation AND a finding: it motivates the
regimen-change detection metric and the instability forecasting analysis. The system
struggles precisely where clinical instability is highest — which argues for the
disagreement-as-uncertainty work as a solution, not just a supplementary analysis.

---

### B1.5 — Why Exact Match? Is the Doctor Always Right?

**Why this gets flagged:**
MedAgentBoard reviewer Hr7A: *"In workflow automation, 'task completeness' emphasizes
output generation over clinical validity."* MedAgentBoard had to add clinical expert
reviewers mid-rebuttal.

For us, the attack is: "You're measuring agreement with a single doctor's decision.
Doctors disagree. The 'ground truth' prescription may not be the optimal prescription.
You're measuring imitation, not quality."

**Our answer — must be explicit in the metrics section:**

We make two distinct claims, and the metric must match the claim:

Claim 1: **System alignment with real prescribing practice.** Exact match and Jaccard
vs GT prescriptions are the right metrics for this. We are not claiming to prescribe
*better* than doctors — we are claiming to predict what the doctor will prescribe given
the same information. This is a legitimate and measurable task.

Claim 2: **Clinical reasoning quality.** Exact match is NOT the right metric for this.
Doctor validation (Likert + preference) addresses this. The right question there is
"is this reasoning clinically defensible and appropriate for the Ugandan context?" not
"does it match what we decided."

These are different claims requiring different evidence. The paper must be clear that
we are making both claims and evaluating each appropriately. Conflating them is what
gets attacked.

Additionally: the GT is not "what the optimal doctor would prescribe globally" — it is
"what the expert epilepsy clinician at Mulago Hospital prescribed for this specific
patient in this specific context." For the LMIC decision support application, matching
the expert local clinician IS the right target.

---

### B1.6 — Cohort Heterogeneity: Why Three Cohorts, Why Not Pooled?

**Why this gets flagged:**
Reviewers will notice three cohorts with different characteristics and ask: "Why not
pool them? Are you selecting the cohort with the best results? Why does Cohort C V1
show only +2.4pp while Cohort A V1 shows +6.6pp?"

**Our answer:**

The three cohorts represent different data collection modalities (structured CSV,
LLM-extracted multi-visit CSV, PDF-parsed clinic records) and are NOT interchangeable.
They should not be pooled because:

1. Cohort C GT was LLM-extracted from PDF — introducing extraction noise that
  structurally caps maximum achievable exact match. The +2.4pp at V1 for Cohort C
   likely reflects GT noise more than system limitation.
2. Cohort B represents a specific clinical subpopulation (patients with 4+ visits,
  treatment-resistant profile), not a random sample — pooling would bias the dataset.
3. Separate cohort results are a robustness demonstration: the multi-agent advantage
  holds across all three independent data collection processes.

Frame the three cohorts as a strength: "We demonstrate consistent advantages across
three independently collected cohorts with different data quality characteristics,
suggesting the results are robust to data collection methodology."

Also pre-emptively address Cohort B size (53 patients): "Cohort B is smaller by
design — it consists of patients with 4+ clinic visits, a patient subpopulation
specifically selected to study long-trajectory management. Results should be
interpreted with this selection bias in mind."

---

### B1.7 — Why Does Multi-Agent Help Here When MedAgentBoard Says It Doesn't Always?

**Why this gets flagged:**
This is the most important single question the paper must answer, because MedAgentBoard
(NeurIPS 2025) is going to be in the reviewer's memory. Its conclusion: "multi-agent
collaboration does not consistently outperform advanced single LLMs."

**Our answer — this is the thesis of the paper:**

MedAgentBoard tests multi-agent on in-distribution tasks: MedQA, PubMedQA, PathVQA,
MIMIC-IV — all domains heavily represented in LLM training. Wu et al. (arXiv 2025)
also find no advantage on 4 clinical vignettes drawn from Western multimorbidity
guidelines. The finding that "multi-agent doesn't always help" is precisely the finding
that motivates the right question: *when* does it help?

Our answer, backed by empirical evidence: multi-agent structured collaboration helps
specifically when the single agent's prior is miscalibrated for the target distribution
— i.e., on genuinely OOD tasks where the model would otherwise default to training
distribution patterns that are wrong in context.

We show this concretely with the failure mode taxonomy: the single agent recommends
levetiracetam (common in Western guidelines, limited in Uganda), avoids carbamazepine
in generalized epilepsy (correct per Western guidelines, wrong for Uganda where CBZ+VPA
is the backbone), and defaults to monotherapy when polytherapy is standard. These are
not random errors — they are the model's training prior applied to the wrong context.
Multi-agent structured debate with a tropical medicine specialist and formulary agent
creates a mechanism to override that prior. The improvement is attributable and specific.

This reframes MedAgentBoard from a threat to a setup: "Prior work shows multi-agent
doesn't consistently help on in-distribution medical tasks [MedAgentBoard]. We identify
the condition under which it does: when the base model's training prior is systematically
wrong for the target population. We demonstrate this on a uniquely OOD clinical dataset."

---

### B1.8 — Why Is Our Baseline Strong Enough? (The Copy-Previous Problem)

**Why this gets flagged:**
Our single-agent baseline is 7-stage reasoning. Reviewers will notice that our
single-agent baseline (75.5% V3) is higher than most prior work's single-agent results,
which is good — but then they'll ask: "What about a zero-intelligence baseline?"

The danger: ~80% of patients don't change their regimen visit-to-visit. A simple
"copy previous prescription" heuristic will hit approximately 80% exact match on V2/V3.
If we don't show this number, a reviewer will calculate it from our changed/unchanged
split and do the math themselves. Our changed/unchanged results show:

- V2 unchanged (N=217): multi-agent 95.9%
- V2 changed (N=57): multi-agent 54.4%

If the copy-previous baseline is ~80% overall and our multi-agent is 87.2%, the actual
meaningful gain is on the 57 changed cases (+6.8pp) and the 217 unchanged cases
(where we're even better). The paper needs to present this framing proactively.

**The answer — must be in paper:**
Copy-previous-regimen is a critical baseline that MUST be run and reported. If we beat
it overall (which we should — it gets V1 completely wrong by definition), we can frame
the result as: "Copy-previous is a strong heuristic for unchanged cases but fails
completely on changed cases (by design). Multi-agent maintains near-human performance
on unchanged cases AND achieves +X% on changed cases, which is where clinical value
lies." The real contribution is on the 20% of visits where the doctor makes a change —
that's the clinically interesting and hard subset, and that's where our +10-20pp gains
are.

Never let copy-previous appear as a surprise in the review process. Show it, explain
it, and frame the contribution around the changed-regimen subset.

---

### B1.9 — The Fine-Tuning Baseline: Why Not FLAME-Style Fine-Tuning?

**Why this gets flagged:**
FLAME (NeurIPS 2025) fine-tunes Llama-3.1-8B on MIMIC-III and achieves Jaccard 0.484.
Reviewers know about FLAME. They will ask: "Why not fine-tune a small model on your
training split? It would be cheaper, faster, and interpretable."

**Our answer — must be in methods or discussion:**

1. **Dataset size makes SFT unreliable.** We have 699 patients. If we hold out 30% for
  test, that's ~490 training examples. SFT on 490 examples with a 8B+ model will
   overfit severely, especially for polytherapy combinations (the hard cases). FLAME
   used 14,207 visits from 6,226 patients — 30x our training data.
2. **Cross-cohort generalization is the claim.** Our three cohorts are from different
  data collection processes. A model fine-tuned on Cohort A will not generalize to
   Cohort C PDF data without re-training. Our zero-shot LLM approach generalizes
   across cohorts without any training.
3. **FLAME requires ICD/ATC structured codes; we have free text.** FLAME's architecture
  depends on medical code vocabularies (diagnoses, procedures as ICD codes, drugs as
   ATC codes). Our GT is free-text prescriptions from a Ugandan clinic with no
   standardized coding. FLAME cannot be applied to our setting without full dataset
   re-engineering.
4. **Generalization to unseen patients/clinics is the target application.** In
  deployment, there is no training data for a new clinic in a new country. The value
   of our approach is that it works zero-shot — this is the deployment-relevant property.

---

### B1.10 — No-Leakage: Proactive Statement Required

**Why this gets flagged:**
This comes up for any paper that uses a "novel dataset" — reviewers want to know if
the LLM has seen the data in training. If the model has seen Ugandan epilepsy clinic
data in training, our results are inflated.

**Our answer — must be a dedicated paragraph in methods:**

Mulago Hospital, Uganda outpatient epilepsy clinic records. These records were:

- Not digitized in any public database
- Not in MIMIC, eICU, or any known medical AI dataset
- In a format and language (informal clinical notes, non-standard drug names) unlike
any publicly available clinical text dataset
- From a demographic and treatment context (sub-Saharan African pediatric epilepsy
outpatient) essentially absent from known LLM training corpora

The Ugandan CBZ+VPA polytherapy backbone *contradicts* Western guidelines in LLM
training. If the model had seen this data, it would NOT exhibit the Western-bias
failures we document — it would already know CBZ+VPA is standard Ugandan practice.
The fact that the single agent fails in precisely the ways predicted by training
distribution mismatch (recommends LEV, avoids CBZ in generalized) is evidence the
model has NOT seen this data.

---

### B1.11 — Generalization of Conclusions (Not Just This Framework)

**Why this gets flagged:**
MedAgentBoard Reviewer taNB: *"The paper's conclusions about multi-agent collaboration
are intrinsically tied to the performance of the specific, mostly general-purpose
frameworks evaluated. The finding that these systems are not always superior could be a
reflection of the limitations of these current frameworks rather than a fundamental
weakness in the concept."*

For us: "Your results are for gpt-oss-120b-1:0 only. These might not generalize."

**Our answer — must be in limitations + addressed by multi-model experiment:**

Two-part answer:

1. (Limitations) Results are demonstrated on gpt-oss-120b-1:0. We run additional
  experiments on [Model B] to show the multi-agent advantage is model-agnostic at
   the architecture level. Absolute numbers will differ across models; the relative
   advantage of structured multi-agent reasoning over single-agent on OOD data is
   expected to hold for any model with sufficient base capability to follow
   role-specific instructions.
2. (Paper framing) Our contribution is not "this specific framework beats these specific
  baselines." Our contribution is the empirical demonstration that structured
   multi-agent reasoning specifically addresses OOD failure modes in clinical
   prescribing, and the identification of *which* agents address *which* failure modes
   (attributability). This analytical contribution holds regardless of which model is
   the backbone.

---

### B1.12 — Longitudinal Framing: Make It Central, Not a Feature

**Why this gets flagged:**
Most medical AI papers are single-encounter. Reviewers from outside the clinical domain
may not appreciate why longitudinal modeling matters here. MICRON (IJCAI 2021) also
does medication change prediction. Reviewers may say "this is just MICRON with LLMs."

**Our answer:**

MICRON requires structured ICD codes and learns statistical co-occurrence patterns
across visits. It cannot process free-text notes, cannot reason about why the doctor
changed medications, and cannot explain its predictions. The longitudinal aspect in our
work is fundamentally different: the model must reason about *treatment trajectory* —
why a patient is being brought back early, what the doctor learned from the previous
response, what the next escalation step should be given the full treatment history.

The key finding that drives this: multi-agent advantage *grows with more visit history*
(+6.6pp at V1 → +10.3pp at V3 for Cohort A). The system gets better as it accumulates
longitudinal context. Single-agent doesn't capitalize on this — it has the same history
but doesn't synthesize it as well across specialist perspectives. This is evidence that
the architecture is specifically designed to leverage longitudinal context, not just
copy from structured codes.

---

## BUCKET 2 — Derived Tasks (Analysis of Existing Data, No New LLM Calls)

These require coding/analysis but use already-run predictions. Estimated effort: 1-3
days each.

### B2.1 — Bootstrap 95% Confidence Intervals on All Main Results

Resample patients 1000x. Paired bootstrap vs baselines. Cluster-bootstrap by patient
if pooling V1+V2+V3. Required on every number in the main table.
**Why:** MDAgents was asked to justify 50-sample experiments. MedAgentBoard CIs show
where differences are significant. Without CIs, reviewers will dismiss numerical
differences as noise.

### B2.2 — Cost / Latency / Token Accounting

Tokens per patient (input/output), $/patient, wall-clock time for each method.
Performance vs cost Pareto plot.
**Why:** Both MDAgents and MedAgentBoard were asked for cost analysis during rebuttal.
Authors had to produce cost tables mid-review. Put it in the paper.

### B2.3 — Copy-or-Reason Decomposition

For every V2/V3 prediction, classify as Copy / Adjust / Innovate based on overlap with
previous GT. Compute accuracy within each bucket. Compute Treatment Inertia Index
(Jaccard with previous visit's GT). Show multi-agent value-add is in the Adjust and
Innovate buckets.
**Why:** Directly addresses copy-previous baseline concern. Shows contribution without
running copy-previous (though copy-previous should still be run).

### B2.4 — Disagreement-as-Uncertainty (AUROC)

From traces: drug-level agreement across agent outputs, contradiction density,
debate trigger features. Show these predict whether final answer matches GT.
**Why:** This is the safety argument. "Multi-agent disagreement identifies uncertain
cases for specialist review." Clinically important finding, no new runs.

### B2.5 — Selective Abstention / Coverage-Accuracy Curves

Use disagreement score as threshold. Plot: at X% coverage, accuracy = Y%.
Compare to random abstention and single-agent confidence-based abstention.
**Why:** "At 70% coverage, system hits 95% accuracy, flagging hardest 30% for
specialist review." This one figure sells the paper to a clinical audience.

### B2.6 — Failure Mode Taxonomy (LMIC-Specific Error Categories)

Categorize every wrong prediction:

- Western-guideline bias (recommends LEV not available in Uganda)
- Availability blindness (recommends unavailable drugs)
- Pharmacologist conservatism (removes correct drug)
- Polytherapy undercount (defaults to mono when poly prescribed)
- Longitudinal memory failure (ignores prior visit history)
Show error distribution. Show multi-agent reduces each category vs single-agent.
**Why:** Makes the OOD narrative concrete and measurable. Reviewer-proof because every
claim has a specific, verifiable count.

### B2.7 — Trajectory-Aware Error Taxonomy

For each wrong prediction at visit t, classify as:

- Stale/inertial (copied old regimen when doctor changed)
- Anticipatory (predicted the regimen the doctor later chose)
- Over-switching (changed when doctor stayed)
- Off-trajectory (matches neither adjacent state)
Claim: "Single-agent errors are mostly inertial; multi-agent errors are more often
anticipatory." No new runs — analysis of existing predictions + GT.

### B2.8 — Contingency Plan Validity

Score Option 2/3 (alternatives) against GT at t+1 and t+2.
Did any of the 3 options become the doctor's actual regimen at the next visit?
**Why:** Novel contribution, no new runs, directly rebuts "you only give one answer"
criticism. "Multi-agent alternatives frequently anticipate future doctor decisions."

### B2.9 — Inter-Agent Disagreement Analysis (disagreement.py)

Where do agents disagree? Does disagreement predict errors? Per-agent contribution to
final recommendation (which agents' outputs correlate with correct final answers).
Builds the "each agent does something specific" narrative.

### B2.10 — Ground Truth Quality Verification

Manually verify 50 randomly sampled cases from Cohort C (PDF-extracted) for GT
accuracy. Report extraction error rate. If ~5%, note explicitly that this caps
maximum achievable exact match for Cohort C and explains the smaller gains at V1.
**Why:** MedAgentBoard reviewers asked about ground truth quality and accessibility.
Pre-empt this.

---

## BUCKET 3 — New Experiments Required (Real Pending Tasks)

These require new LLM inference runs. Estimated effort noted per item.

### B3.1 — Copy-Previous-Regimen Baseline [CRITICAL — P0]

Trivial heuristic: for V2/V3, predict the exact drug set from the previous visit.
For V1, there is no previous visit — use the most common regimen in the training
distribution or flag as N/A.
**Effort:** No LLM calls. Pure logic on existing data.
**Why critical:** Reviewer will calculate this themselves from changed/unchanged split
if we don't include it. Must show copy-previous, explain it, and frame why multi-agent
beats it on the hard cases.

### B3.2 — Zero-Shot, CoT, CoT-SC Baselines [P0]

Zero-shot: "What drugs should this patient get?" Single call, no pipeline.
CoT: "Think step by step, then prescribe."
CoT-SC: CoT 5x at temp=0.7, majority vote on drug set.
**Effort:** ~3 new inference runs on full dataset. Already have infrastructure.
**Why:** MDAgents had these. MedAgentBoard had these. Any paper that doesn't include
CoT-SC as a baseline in 2026 will be asked for it in review.

### B3.3 — Doctor Evaluation: 60 Cases [P0]

60 cases: 20 V1, 20 V2, 20 V3. Blind A/B format. Raj + JP + ideally a 3rd rater.
4 Likert questions per output. 1 preference question per case. Cohen's kappa between
raters.
**Effort:** Build eval form, sample cases, coordinate with doctors.
**Why:** Both MDAgents and MedAgentBoard were pressed on human evaluation. MedAgentBoard
had to expand from 3 CS PhD students to 6 domain experts mid-rebuttal. We have real
doctors — this is a strength. Must be executed and must report inter-rater reliability.

### B3.4 — Second LLM Backbone [P1]

Run full pipeline + single-agent baseline on one additional model (GPT-4o or Claude
3.5 Sonnet or similar). Don't need all ablations — just main comparison.
**Effort:** 2 inference runs on full dataset (pipeline + baseline).
**Why:** MDAgents used GPT-4(V) + Gemini. Single-model results get flagged as
potentially model-specific. Even partial second-model results deflect this.

### B3.5 — History Ablation: 2x2 Factorial [P1]

Four conditions (no_history / notes_only / rx_only / full):
What's the marginal contribution of prior clinical notes vs prior prescriptions?
Hypothesis: prescriptions dominate for unchanged cases, notes matter at change points.
**Effort:** 4 new inference runs per visit. Clean causal experiment.
**Why:** This is a methodologically rigorous experiment that directly addresses the
"does it actually use history or just copy?" question.

### B3.6 — Traditional ML Baselines [P1]

XGBoost / Random Forest on structured features extracted from notes (age, seizure type,
prior drugs, visit number, comorbidities).
**Effort:** Feature extraction + sklearn training.
**Why:** MedAgentBoard showed XGBoost beats multi-agent LLMs on EHR tasks. Reviewers
expect this comparison. We likely beat it (our data is free-text-heavy, not structured
code-heavy) but must show it.

### B3.7 — Extended Visits V4-V7 on Cohort C [P2]

Run pipeline + baselines on V4-V7 of Cohort C PDF cohort (121 patients at V4, 64 at
V5, 28 at V6).
Does multi-agent advantage keep growing? Does it plateau?
**Effort:** 2 inference runs (pipeline + baseline) on long-trajectory patients.

---

## NeurIPS 2026 Submission Checklist

### Mandatory (desk rejection if missing)

- NeurIPS 2026 LaTeX template (Word submissions rejected)
- Anonymous submission (all author names, institutions, identifying info removed)
- Self-citations anonymized in double-blind submission
- Code ZIP (max 100MB) with training/evaluation code
- 16-item paper checklist completed
- HuggingFace dataset publicly accessible without personal request
- Croissant metadata on HuggingFace dataset
- Limitations section in paper
- Broader impacts statement
- LLM usage declaration

### Contribution Type Selection

Select "**Use-Inspired**" (novel methods for real-world applications). This is the
right category and signals to reviewers what evaluation criteria apply. Do NOT select
"General" — Use-Inspired papers are evaluated on real-world relevance, not just
theoretical novelty.

### Track Decision

**Primary target: Main Conference, Use-Inspired.**
**Alternative: Evaluations & Datasets Track** if we frame around the benchmark
contribution (first LMIC epilepsy treatment prediction benchmark, evaluation protocols,
trace quality metrics). E&D now requires Croissant metadata (already on HF) and
explicitly welcomes evaluation methodology papers. Both tracks have same deadline.

### Deadlines

- Abstract: **May 4, 2026 AOE** (~33 days from today)
- Full paper + supplementary + code: **May 6, 2026 AOE**
- Author notification: September 24, 2026

---

## Key Papers to Know Cold Before Submission

These will be cited by reviewers. Know their exact claims and how we differ.


| Paper                            | Claim                                                         | Our response                                                                                                             |
| -------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| MDAgents (NeurIPS 2024 Oral)     | Adaptive multi-agent beats single on 7/10 medical benchmarks  | We do real drug prescriptions, not QA. OOD setting, not benchmarks.                                                      |
| MedAgentBoard (NeurIPS 2025 D&B) | Multi-agent doesn't consistently beat single LLM              | They test in-distribution. We test OOD. That's exactly when multi-agent helps.                                           |
| FLAME (NeurIPS 2025)             | Fine-tuned LLM achieves Jaccard 0.484 on MIMIC medication rec | MIMIC ICU structured codes vs Ugandan free-text outpatient notes. Different task, different setting, different modality. |
| Wu et al. (arXiv 2025)           | Multi-agent matches single agent on 4 clinical vignettes      | 4 cases, Western guidelines, in-distribution. Our OOD setting is different.                                              |
| DrugRec (NeurIPS 2022)           | Causal debiasing improves MIMIC medication rec                | Purely statistical, no reasoning, no LMIC, structured codes only.                                                        |
| RareAgents (AAAI 2025)           | 41-agent MDT for rare disease, memory helps most              | Western ICU data, rare diseases ≠ epilepsy, no LMIC, memory finding supports our longitudinal approach.                  |


