"""Main multi-agent pipeline — orchestrates all 4 phases."""

from __future__ import annotations
import asyncio

from schemas.patient import PatientCase
from schemas.responses import AgentResponse
from schemas.trace import ReasoningTrace
from schemas.output import FinalRecommendation
from llm.client import LLMClient

from agents.diagnostician import DiagnosticianAgent
from agents.treatment_analyst import TreatmentAnalystAgent
from agents.pediatrician import PediatricianAgent
from agents.tropical_medicine import TropicalMedicineAgent
from agents.formulary import FormularyAgent
from agents.epileptologist import EpileptologistAgent
from agents.pharmacologist import PharmacologistAgent

from orchestrator.conflict import detect_conflicts, apply_safety_vetoes
from orchestrator.debate import run_debate
from orchestrator.synthesis import (
    build_final_recommendation,
    compute_agreement_score,
    format_trace_output,
)


# Agent registry for ablation support
PHASE1_AGENTS = {
    "diagnostician": DiagnosticianAgent,
    "treatment_analyst": TreatmentAnalystAgent,
    "pediatrician": PediatricianAgent,
    "tropical_medicine": TropicalMedicineAgent,
    "formulary": FormularyAgent,
}


class ConsiliumPipeline:
    """Multi-agent epilepsy drug prediction pipeline."""

    def __init__(
        self,
        llm_client: LLMClient,
        disabled_agents: set[str] | None = None,
        enable_debate: bool = True,
        format_output: bool = True,
    ):
        self.llm = llm_client
        self.disabled_agents = disabled_agents or set()
        self.enable_debate = enable_debate
        self.format_output = format_output

        # Instantiate agents
        self.phase1_agents = {}
        for name, cls in PHASE1_AGENTS.items():
            if name not in self.disabled_agents:
                self.phase1_agents[name] = cls(llm_client)

        self.epileptologist = EpileptologistAgent(llm_client)
        self.pharmacologist = PharmacologistAgent(llm_client)

    async def run(self, patient: PatientCase) -> tuple[FinalRecommendation, ReasoningTrace]:
        """Run the full multi-agent pipeline on a single patient.

        Returns:
            (FinalRecommendation, ReasoningTrace)
        """
        trace = ReasoningTrace(
            patient_id=patient.patient_id,
            visit=patient.current_visit,
        )

        # ── PHASE 1: Independent Parallel Assessment ──
        phase1_tasks = {}
        for name, agent in self.phase1_agents.items():
            should_run, reason = agent.should_activate(patient)
            if should_run:
                phase1_tasks[name] = agent
                trace.agents_activated.append(name)
                trace.activation_reasons[name] = reason

        # Run Phase 1 agents in parallel
        async def _run_agent(name, agent):
            return name, await agent.run(patient)

        phase1_results = await asyncio.gather(
            *[_run_agent(name, agent) for name, agent in phase1_tasks.items()]
        )

        for name, response in phase1_results:
            trace.phase1_responses[name] = response

        # ── PHASE 1.5: Programmatic Conflict Detection ──
        trace.detected_conflicts = detect_conflicts(trace.phase1_responses)
        safety_vetoes = apply_safety_vetoes(trace.phase1_responses, trace.detected_conflicts)

        # ── PHASE 2: Informed Prescription ──
        trace.agents_activated.append("epileptologist")
        trace.activation_reasons["epileptologist"] = "always active"

        epi_context = {
            "phase1_responses": trace.phase1_responses,
            "conflicts": trace.detected_conflicts,
        }
        trace.epileptologist_response = await self.epileptologist.run(patient, epi_context)

        # ── PHASE 3: Adversarial Review ──
        trace.agents_activated.append("pharmacologist")
        trace.activation_reasons["pharmacologist"] = "always active"

        pharm_context = {
            "phase1_responses": trace.phase1_responses,
            "epileptologist_response": trace.epileptologist_response,
        }
        trace.pharmacologist_response = await self.pharmacologist.run(patient, pharm_context)

        # ── PHASE 3.5: Structured Debate ──
        if (
            self.enable_debate
            and trace.pharmacologist_response.concerns
        ):
            trace.debate_triggered = True
            trace.debate_rounds = await run_debate(
                patient,
                trace.epileptologist_response,
                trace.pharmacologist_response,
                self.llm,
            )

        # ── PHASE 4: Rule-Based Synthesis ──
        recommendation = build_final_recommendation(patient, trace, safety_vetoes)

        # Compute agreement score
        trace.agreement_score = compute_agreement_score(trace.phase1_responses)
        trace.total_concerns_raised = sum(
            len(r.concerns) for r in trace.phase1_responses.values()
        )
        if trace.pharmacologist_response:
            trace.total_concerns_raised += len(trace.pharmacologist_response.concerns)
        trace.critical_concerns = sum(
            1 for r in list(trace.phase1_responses.values()) + [trace.pharmacologist_response]
            if r
            for c in r.concerns
            if c.severity.value == "critical"
        )

        trace.final_recommendation = {
            "patient_id": recommendation.patient_id,
            "visit": recommendation.visit,
            "options": [opt.to_comparable() for opt in recommendation.options],
            "synthesis_notes": recommendation.synthesis_notes,
        }

        # Optional: format output with LLM
        if self.format_output:
            formatted = await format_trace_output(trace, recommendation, self.llm)
            # Store formatted output in epileptologist's raw output for compatibility
            if trace.epileptologist_response:
                trace.epileptologist_response.raw_output = formatted

        return recommendation, trace
