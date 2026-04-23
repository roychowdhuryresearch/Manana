# Multi-Seed Learnings Analysis — OSS-120B vs OSS-20B

Date: 2026-04-22

Pooled qualitative analysis across 5 seeds × 2 models for all 3 systems.
Goal: check consistency within each system, flag fabrications, characterize what gets learned.

---

## 1. TextGrad

### 120B (0622 batch, all seeds end at round_15)

**Core failure mode: fabricated specific numbers, replicated across seeds.**

All 5 seeds share the same correct drug-to-seizure-type mapping (valproate → generalized, CBZ → focal) but diverge in the numbers they attach:

| Fabrication type | Examples across seeds |
|------------------|-----------------------|
| Valproate dose ceiling | s1: "up to ≈60 mg/kg/day"; s5: "max 60 mg/kg/day" (standard: 30–40) |
| Availability %   | s2: ">75% of district hospitals"; s3: "≥95% of district pharmacies"; s4: ">90% of Ugandan public-sector pharmacies" — each seed invents its own number |
| Threshold rules  | s3: "≥1 seizure per day" to trigger add-on — no such universal rule exists |
| CBZ dosing       | s4: "15–25 mg/kg/day, <15 mg/kg/day is sub-therapeutic" — lower bound invented |

**Citations:** No explicit citation strings in the 0622 batch (improvement over 0211 which had NSTG/STP/EML). The hallucinations are now embedded in the prose as confident percentages and thresholds rather than bracketed references.

**Cross-seed consistency:** High on drug selection logic, low on numbers. Each seed has a distinct "flavour" (s1 is CBZ-focused, s2 is formulary/availability-focused, s3 adds breakthrough seizure rules, s4 adds semiology-to-drug mapping, s5 adds formulation details). The optimizer is finding different facets of the same correct clinical picture, but decorating each with invented specifics.

**Overall character (120B TG):** Clinically directional but numerically unreliable. Safe to use the drug-selection logic; unsafe to use any threshold or percentage.

---

### 20B (0255 batch, all seeds end at round_15)

**Much worse.** 20B fabricates at the same rate but with more specificity and invents full citation strings.

| Fabrication type | Examples |
|------------------|----------|
| Invented citations | s1: "Uganda MOH 2021"; s2: "Uganda National Seizure Management Guidelines 2023" with age-banded dosing tables |
| Cost figures | s1: "$0.35/day valproate, $0.70/day levetiracetam"; s3: detailed cost tiers with exact prices |
| Drug interaction numbers | s3: "valproate reduces carbamazepine serum by ~20%, adjust CBZ upward by 25%" — made up |
| Adherence statistics | s4: "once-daily + 1 visit/month ≈30% adherence" — invented |
| Trough thresholds | s5: "CBZ trough <20 µg/mL" (standard is 4–12 µg/mL) |
| Dose calculation examples | s4: entire weight-based calculation walkthrough with specific mg values — precision theatre |

**Cross-seed consistency:** The drug-selection direction is consistent (same as 120B) but the fabricated numbers differ wildly per seed. s2 and s3 have age-banded decision trees; s4 and s5 go into calculation mechanics. Each seed hallucinates a different Uganda-specific "guideline" structure.

**Overall character (20B TG):** More verbose, more confidently specific, more fabricated than 120B. The clinical direction is still mostly right but the apparatus around it is almost entirely invented. Unusable without fact-checking every claim.

---

## 2. Buffer Single

### 120B (1217 batch)

**Highly consistent across all 5 seeds. Clean rules, no fabricated numbers, no citations.**

Four themes appear in every seed:

1. **Continuation rule** — if seizure-free + tolerating drug + no adverse effects → continue unchanged, no modification. The single most universal rule. Every seed learned it independently.

2. **First-line mapping** — valproate for generalized, CBZ for focal. All seeds. Usually stated without specific dosing numbers.

3. **Dose adequacy before escalation** — optimize/titrate current drug to therapeutic dose before adding or switching. 4/5 seeds.

4. **Discontinuation inference** — if a drug is mentioned without explicit stop order, treat it as continued. 4/5 seeds.

Additional rules that appear in 2–3 seeds:
- West syndrome / infantile spasms → continue valproate if seizure-free
- LGS → clobazam as adjunct to valproate
- CBZ + LEV adjunct for focal breakthrough

**No seed invented thresholds** (no "≥3 months", no "≥1 seizure/day", no specific mg/kg). Rules stay at the clinical reasoning level without false precision.

**Cross-seed similarity:** Very high. If you stripped the names and mixed the rules together you could barely tell which seed they came from. The main variation is in how explicitly they state the discontinuation-inference rule and how many syndrome-specific rules each seed picked up.

**Overall character (120B single):** Clean, consistent, characterizable. Functionally a "when to leave things alone + first-line drug selection" rule set.

---

### 20B (1125 batch)

**Same themes as 120B but with more time-specific thresholds — a modest step toward over-specificity.**

The four core themes are all present. Key differences from 120B:

- **Time thresholds start appearing:** "≥3 months seizure-free" (s2), "≥6 months" (s4, s5), "≥12 months" (s4, s5). No single threshold dominates — each seed invents its own, suggesting the optimizer is reaching for specificity it shouldn't claim.
- **s1** adds "phenobarbital first-line for West syndrome / infantile spasms" — debatable, not standard.
- **s3** is the most verbose (13 rules) and most syndrome-specific (Doose, West, LGS all explicit).
- **s4** is the leanest (6 rules) and closest to 120B character.
- No invented citations. No fabricated availability percentages.

**Cross-seed similarity:** Moderately high on themes, lower on exact rule wording. The time thresholds cause the most divergence — seeds disagree on whether "seizure-free" means 3, 6, or 12 months.

**Overall character (20B single):** Similar quality to 120B but slightly noisier. The time thresholds add false precision without grounding. Still no fabricated citations — the hallucination doesn't penetrate the buffer format the same way it does TG.

---

## 3. Buffer Multi

### 120B (1217 batch)

**Agent roles converge on the same 4–5 functional categories across all seeds, independently.**

| Functional role | Found in seeds |
|-----------------|----------------|
| Medication tracker / continuation detector | s1, s2, s3, s4, s5 — every seed |
| Seizure type / semiology classifier | s1, s3, s4, s5 (s2 has EfficacyHistory instead) |
| Dose adequacy assessor | s1, s3, s4 |
| Efficacy / seizure control extractor | s2, s5 |
| Discontinuation tracker | s3, s4 |
| EEG / syndrome extractor | s1, s5 |

Agent prompts share a consistent constraint: "do not suggest medication changes", "output 2–4 sentences", "concise observation only." This disciplined scoping was learned and replicated across all 5 seeds — the Architect figured out that unfocused agents hurt.

**s2 r3** only has 4 agents (early round pick) but already has the 4 core roles.

**Overall character (120B multi):** Tightly scoped extractors. Functionally identical across seeds despite very different agent names. The topology is stable and specialised — each agent has a single lane and stays in it.

---

### 20B (1125 batch)

**Same functional categories but more variation in agent design philosophy.**

| Functional role | Found in seeds |
|-----------------|----------------|
| Medication tracker / reconciler | s1, s2, s3, s4, s5 — every seed |
| Seizure type classifier | s1, s2, s3, s5 |
| Dose adequacy | s1, s2, s3, s4, s5 — every seed |
| Seizure frequency / control | s1, s2, s5 |
| Adherence / local context | s2 (LocalTherapyPreferenceMatcher, AdherenceImpactAgent) |
| Drug-specific agents | s4 (CARB_DoseTarget, ValproateDoseSeizureControlIntegrator) — only seed that went drug-specific |

Notable divergences:
- **s4** took a drug-specific approach — one agent per drug (CBZ agent, VPA agent) rather than one agent per functional role. Unique to this seed.
- **s2** added adherence and local prescribing pattern agents — more context-aware than other seeds.
- **s3** agent names are quoted strings with capital letters (e.g., `"Medication List Extractor"`) — formatting quirk from the 20B model generating slightly different JSON structure.
- Agent prompts in 20B are generally longer and more prescriptive than 120B — less "observe and report", more "evaluate and flag".

**Cross-seed similarity:** Moderate. Core roles are there but the agent design philosophy differs more than in 120B. 20B seems to generate more idiosyncratic agents per seed.

**Overall character (20B multi):** Similar functional coverage to 120B but less disciplined in scoping. Some agents blur the line between extraction and recommendation.

---

## Cross-System Summary

| Dimension | TG 120B | TG 20B | Single 120B | Single 20B | Multi 120B | Multi 20B |
|-----------|---------|--------|-------------|------------|------------|-----------|
| Cross-seed consistency | Medium | Low | High | Medium-High | High | Medium |
| Fabricated numbers | Yes (systematic) | Yes (worse) | No | Minor (time thresholds) | No | No |
| Fabricated citations | No (0622) | Yes | No | No | No | No |
| Clinical direction correct | Yes | Yes | Yes | Yes | Yes | Yes |
| Characterizable themes | Partially | Partially | Yes — 4 clear themes | Yes — same 4 themes | Yes — 4–5 roles | Yes — same roles |
| 20B vs 120B delta | — | More verbose, more fabrication | — | Slightly noisier | — | More varied agent design |

**Key takeaway:** The buffer format (single and multi) suppresses hallucination that TG actively encourages. The Architect writes rules in clinical-reasoning language without needing to invent specific numbers to justify them. TG's optimizer, by contrast, rewards specificity in the learnings string — and the model achieves "specificity" by fabricating it.
