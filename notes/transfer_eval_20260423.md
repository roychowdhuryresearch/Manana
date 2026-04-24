# Cross-Model Transfer Eval — 120B Learnings on 20B Model

Date: 2026-04-23

Goal: Show buffer learnings are model-agnostic (transfer across model sizes), while TG learnings are model-coupled.

Test set: CSV holdout (excl. 70 SL train+eval pids) + full PDF (367 patients), visits 1-3.

---

## Results (5 seeds, s1-s5)

### Table 1: EM@3 (%) — Mean ± std over 5 seeds


| Cohort      | Method         | V1         | V2         | V3         |
| ----------- | -------------- | ---------- | ---------- | ---------- |
| **A (CSV)** | Buf 20B native | 66.1 ± 3.2 | 69.5 ± 4.8 | 69.9 ± 2.6 |
|             | TG 20B native  | 61.8 ± 3.3 | 64.5 ± 5.6 | 67.0 ± 4.7 |
|             | Buf 120B→20B   | 72.5 ± 4.2 | 71.8 ± 5.2 | 74.9 ± 5.0 |
|             | TG 120B→20B    | 68.3 ± 1.7 | 71.0 ± 3.2 | 73.0 ± 1.5 |
| **B (PDF)** | Buf 20B native | 67.8 ± 1.6 | 72.7 ± 2.7 | 70.6 ± 4.0 |
|             | TG 20B native  | 61.8 ± 5.1 | 68.2 ± 3.1 | 68.5 ± 2.4 |
|             | Buf 120B→20B   | 65.8 ± 3.0 | 75.0 ± 3.3 | 73.5 ± 5.6 |
|             | TG 120B→20B    | 59.9 ± 3.1 | 68.9 ± 2.9 | 69.8 ± 3.4 |


### Table 2: EM@1 (%) — Mean ± std over 5 seeds


| Cohort      | Method         | V1         | V2         | V3         |
| ----------- | -------------- | ---------- | ---------- | ---------- |
| **A (CSV)** | Buf 20B native | 54.4 ± 3.4 | 58.4 ± 2.7 | 61.4 ± 4.0 |
|             | TG 20B native  | 47.0 ± 5.2 | 56.8 ± 4.9 | 61.6 ± 4.2 |
|             | Buf 120B→20B   | 58.1 ± 3.2 | 63.1 ± 6.1 | 67.7 ± 5.8 |
|             | TG 120B→20B    | 58.1 ± 1.7 | 61.9 ± 3.2 | 65.6 ± 2.8 |
| **B (PDF)** | Buf 20B native | 43.2 ± 1.7 | 61.4 ± 3.2 | 61.9 ± 3.3 |
|             | TG 20B native  | 39.3 ± 3.1 | 59.0 ± 3.0 | 61.3 ± 2.5 |
|             | Buf 120B→20B   | 43.7 ± 2.8 | 63.8 ± 4.4 | 64.9 ± 5.3 |
|             | TG 120B→20B    | 39.8 ± 1.2 | 58.9 ± 2.7 | 62.1 ± 4.7 |

---

## Legend

- **Buf / TG**: Buffer (experience replay with natural-language rules) vs TextGrad (gradient-descent-style prompt optimization)
- **20B native**: Learnings trained on 20B, evaluated on 20B — same model throughout
- **120B→20B**: Learnings trained on 120B, evaluated on 20B — tests whether learned knowledge transfers to a smaller model
- **EM@3**: Exact match allowing 3 candidate option sets (top-3 accuracy) — measures breadth of learned clinical knowledge
- **EM@1**: Exact match on top prediction only — measures precision of best guess
- **Cohort A (CSV)**: Structured EHR patients, holdout set (excl. 70 SL train+eval pids)
- **Cohort B (PDF)**: Unstructured clinical notes, fully held-out (never seen during training)

**What this experiment shows**: If 120B→20B transfer matches or beats 20B native, the learnings are model-agnostic — they encode reusable clinical knowledge, not model-specific prompt tricks. This matters because it means you can train on an expensive model once and deploy cheaply.
