# MedAgentBench: A Realistic Virtual EHR Environment to Benchmark Medical LLM Agents

**Authors:** Yixing Jiang, Kameron C. Black, Gloria Geng, Danny Park, James Zou, Andrew Y. Ng, Jonathan H. Chen
**Affiliation:** Stanford University
**Venue:** NeurIPS 2024 (Datasets & Benchmarks track)
**Paper:** https://arxiv.org/abs/2501.14654
**Code:** https://github.com/stanfordmlgroup/MedAgentBench

## Summary

MedAgentBench is a benchmark for evaluating LLMs as **agents** (not chatbots) in medical contexts. It provides 300 clinically-derived tasks across 10 categories, 100 realistic patient profiles with 700K+ data elements, and a FHIR-compliant interactive EHR environment. The key distinction from QA benchmarks: agents must autonomously interact with medical records systems via API calls, not just answer questions.

## Key Design

- **Tasks:** Written by licensed physicians (internal medicine). Categories: patient info retrieval, lab results, vital signs, data recording, test ordering, medication ordering, referral ordering, documentation, data aggregation.
- **Environment:** FHIR-compliant server (HAPI FHIR JPA) with real deidentified Stanford Hospital patient data. Agents interact via standard HTTP GET/POST requests — the same APIs used in real EHR systems.
- **Evaluation:** Pass@1 task success rate (not pass@k — reflecting healthcare's low error tolerance). Rule-based grading for action tasks, exact match for query tasks. Max 8 interaction rounds per task.

## Key Results

- Best model: Claude 3.5 Sonnet v2 at **69.67%** overall success rate
- Query tasks (GET only): up to 85.33% — models are better at retrieval
- Action tasks (POST): up to 71.33% — harder, requires modifying records
- Large gap between closed and open-weight models
- Common errors: invalid action formatting, answering in natural language instead of structured output

## What This Paper Is NOT

- NOT a multi-agent system — uses a single LLM agent with tool access
- NOT about clinical reasoning or diagnosis — about administrative/operational EHR tasks
- NOT about drug prediction or treatment decisions — about navigating medical records systems
