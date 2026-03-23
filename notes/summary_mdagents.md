# MDAgents: An Adaptive Collaboration of LLMs for Medical Decision-Making

**Authors:** Yubin Kim, Chanwoo Park, Hyewon Jeong, et al. (MIT, Google Research, Seoul National University Hospital)
**Venue:** NeurIPS 2024
**Paper:** https://arxiv.org/abs/2404.15155
**Code:** https://github.com/mitmedialab/MDAgents

## Summary

MDAgents is a multi-agent LLM framework for medical decision-making that **adaptively assigns collaboration structure** based on task complexity. A moderator LLM triages each medical query into low/moderate/high complexity, then recruits the appropriate team:

- **Low complexity** — Single Primary Care Physician (PCP) agent with few-shot prompting
- **Moderate complexity** — Multi-Disciplinary Team (MDT) of specialist agents who discuss and reach consensus
- **High complexity** — Integrated Care Team (ICT) with sequential specialist teams producing reports, culminating in a final review team

The key insight is that not every medical question needs a full specialist team — simple cases do better with a single focused agent, while complex cases benefit from multi-agent collaboration.

## Architecture

1. **Medical Complexity Check** — Moderator LLM classifies query as low/moderate/high
2. **Expert Recruitment** — Recruiter LLM assembles the team (PCP, MDT, or ICT)
3. **Analysis & Synthesis** — Agents work solo (low), discuss to consensus (moderate), or produce sequential reports (high)
4. **Decision-Making** — Final answer synthesized from agent outputs

## Key Results

- Best performance on **7 out of 10** medical benchmarks vs solo and group baselines
- Up to **4.2% improvement** over previous best methods (p < 0.05)
- Moderator + MedRAG combination gave **11.8% average improvement**
- The LLM classifier selects the optimal complexity level ~80% of the time
- Solo methods outperform group on 4 simpler benchmarks; group outperforms solo on 6 complex ones — validating the need for adaptive complexity routing

## Benchmarks

10 datasets spanning:
- Medical QA: MedQA, PubMedQA, JAMA, MedBullets
- Diagnostic reasoning: DDXPlus, SymCat
- Medical vision: Path-VQA, PMC-VQA, MedVidQA, MIMIC-CXR

## Important Findings

- Static multi-agent (always using teams) sometimes **hurts** performance on simple tasks
- The complexity classifier is critical — wrong complexity assignment leads to suboptimal results
- Moderator review (feedback loop) is more impactful (+8.1%) than RAG alone (+4.7%)
- The adaptive approach achieves better cost-efficiency by not wasting API calls on simple cases
