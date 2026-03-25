# Consilium Results

Model: `openai.gpt-oss-120b-1:0` (via AWS Bedrock)
Phase 1 agents: 200-word response limit

---

## Cohort A: 279-patient CSV cohort (3 visits each)

## 1. Baseline vs Multi-Agent


| Visit | Baseline | Multi-Agent | Delta   |
| ----- | -------- | ----------- | ------- |
| V1    | 71.3%    | 77.9%       | +6.6pp  |
| V2    | 79.9%    | 87.2%       | +7.3pp  |
| V3    | 80.1%    | 90.4%       | +10.3pp |


## 2. Mono vs Poly Breakdown

### Monotherapy


| Visit | Baseline | Multi-Agent | Delta  |
| ----- | -------- | ----------- | ------ |
| V1    | 86.4%    | 92.0%       | +5.6pp |
| V2    | 93.3%    | 96.2%       | +2.9pp |
| V3    | 91.7%    | 97.4%       | +5.7pp |


### Polytherapy


| Visit | Baseline | Multi-Agent | Delta   |
| ----- | -------- | ----------- | ------- |
| V1    | 16.9%    | 27.1%       | +10.2pp |
| V2    | 37.9%    | 59.1%       | +21.2pp |
| V3    | 52.5%    | 73.8%       | +21.3pp |


## 3. Pre-Pharma vs Post-Pharma (Multi-Agent)

Compares epileptologist's initial regimen (before pharmacologist review) vs final regimen.


| Visit | Pre-Pharma (Epi) | Post-Pharma (Final) | Delta  |
| ----- | ---------------- | ------------------- | ------ |
| V1    | 79.0%            | 77.9%               | -1.1pp |
| V2    | 87.2%            | 87.2%               | 0.0pp  |
| V3    | 89.3%            | 90.4%               | +1.1pp |


### Mono/Poly Pre vs Post


| Visit | Pre Mono | Post Mono | Pre Poly | Post Poly |
| ----- | -------- | --------- | -------- | --------- |
| V1    | 92.5%    | 92.0%     | 30.5%    | 27.1%     |
| V2    | 96.2%    | 96.2%     | 59.1%    | 59.1%     |
| V3    | 96.9%    | 97.4%     | 71.2%    | 73.8%     |


## 4. Dataset: Visit Gaps


|        | V1 → V2      | V2 → V3      |
| ------ | ------------ | ------------ |
| Mean   | 7.4 months   | 8.2 months   |
| Median | 6.3 months   | 6.7 months   |
| Std    | 5.8 months   | 5.4 months   |
| Range  | 14–1834 days | 21–1589 days |


### Accuracy by Visit Gap

**V2 accuracy by V1→V2 gap:**


| Bin     | N   | Multi-Agent | Baseline |
| ------- | --- | ----------- | -------- |
| < 4 mo  | 28  | 67.9%       | 64.3%    |
| 4–9 mo  | 201 | 88.6%       | 81.1%    |
| 9–15 mo | 30  | 96.7%       | 90.0%    |
| > 15 mo | 15  | 86.7%       | 73.3%    |


**V3 accuracy by V2→V3 gap:**


| Bin     | N   | Multi-Agent | Baseline |
| ------- | --- | ----------- | -------- |
| < 4 mo  | 32  | 87.5%       | 84.4%    |
| 4–9 mo  | 166 | 91.0%       | 80.1%    |
| 9–15 mo | 60  | 93.3%       | 78.3%    |
| > 15 mo | 14  | 78.6%       | 78.6%    |


Short-gap patients (< 4 months) have the lowest accuracy — not long gaps. These are unstable patients returning early because their meds aren't working. Of 9 wrong short-gap V2 predictions, 7 had regimen changes between V1→V2 (vs only 1/19 correct). The model expects continuity but the doctor switches drugs at the early follow-up.

### Accuracy by Regimen Change

Patients split by whether the doctor changed the drug regimen from the previous visit.


|             | V2 Unchanged (N=217) | V2 Changed (N=57) | V3 Unchanged (N=217) | V3 Changed (N=55) |
| ----------- | -------------------- | ----------------- | -------------------- | ----------------- |
| Multi-Agent | 95.9%                | 54.4%             | 98.2%                | 60.0%             |
| Baseline    | 87.1%                | 47.6%             | 88.9%                | 45.5%             |

---

## Cohort B: 53-patient extraction cohort (3–6 visits, LLM-extracted from CSV)

Patients selected for having 4+ visits in the CSV; visits extracted via LLM.

### Baseline vs Multi-Agent

| Visit | Baseline | Multi-Agent | Delta   |
| ----- | -------- | ----------- | ------- |
| V1    | 40.9%    | 70.5%       | +29.6pp |
| V2    | 51.0%    | 64.7%       | +13.7pp |
| V3    | 61.5%    | 71.2%       | +9.7pp  |
| V4    | 71.8%    | 84.6%       | +12.8pp |

### Mono vs Poly

| Visit | BL Mono | MA Mono | BL Poly | MA Poly |
| ----- | ------- | ------- | ------- | ------- |
| V1    | 44.4%   | 80.6%   | 25.0%   | 25.0%   |
| V2    | 63.2%   | 81.6%   | 15.4%   | 15.4%   |
| V3    | 76.5%   | 85.3%   | 33.3%   | 44.4%   |
| V4    | 88.9%   | 96.3%   | 33.3%   | 58.3%   |

---

## Cohort C: 367-patient PDF cohort (variable visits, LLM-split from clinic PDFs)

1,509 visits total (up to 10 per patient). GT extracted from clean output_text via LLM.

### Baseline vs Multi-Agent

| Visit | Baseline | Multi-Agent | Delta   |
| ----- | -------- | ----------- | ------- |
| V1    | 66.5%    | 68.9%       | +2.4pp  |
| V2    | 70.2%    | 83.4%       | +13.2pp |
| V3    | 71.8%    | 86.8%       | +15.0pp |
| V4    | 71.7%    | 87.7%       | +16.0pp |
| V5    | 73.7%    | 88.4%       | +14.7pp |
| V6    | 65.8%    | 81.6%       | +15.8pp |

### Mono vs Poly

| Visit | BL Mono | MA Mono | BL Poly | MA Poly |
| ----- | ------- | ------- | ------- | ------- |
| V1    | 77.1%   | 78.8%   | 41.2%   | 45.4%   |
| V2    | 81.6%   | 94.4%   | 49.2%   | 63.3%   |
| V3    | 82.1%   | 95.7%   | 54.8%   | 72.2%   |
| V4    | 86.5%   | 95.2%   | 51.6%   | 77.4%   |
| V5    | 87.1%   | 95.2%   | 48.5%   | 75.8%   |
| V6    | 81.8%   | 100.0%  | 43.8%   | 56.2%   |

