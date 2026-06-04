"""V2 Pipeline: orchestrator -> phase 1 -> epi -> pharma -> [debate] -> done."""

from __future__ import annotations
import asyncio
import logging

from lib.patient import PatientCase
from lib.responses import AgentResponse
from lib.llm import LLMClient

from consilium.agents.registry import PHASE1_AGENTS, PHASE2_AGENTS, PHASE3_AGENTS
from consilium.agents.orchestrator import run_orchestrator
from consilium.debate import run_debate, has_concerns
from lib.regimen_parser import parse_regimen

logger = logging.getLogger(__name__)


class ConsiliumPipeline:
    """V2 multi-agent epilepsy drug prediction pipeline."""

    def __init__(
        self,
        llm_client: LLMClient,
        disabled_agents: set[str] | None = None,
        max_debate_rounds: int = 0,
    ):
        self.llm = llm_client
        self.disabled_agents = disabled_agents or set()
        self.max_debate_rounds = max_debate_rounds

        # Instantiate all Phase 1 agents (orchestrator decides which run)
        self.phase1_agents = {}
        for name, cls in PHASE1_AGENTS.items():
            if name not in self.disabled_agents:
                self.phase1_agents[name] = cls(llm_client)

        # Phase 2/3 agents (always run)
        epi_cls = list(PHASE2_AGENTS.values())[0]
        pharm_cls = list(PHASE3_AGENTS.values())[0]
        self.epileptologist = epi_cls(llm_client)
        self.pharmacologist = pharm_cls(llm_client)

    async def run(self, patient: PatientCase) -> dict:
        """Run the full V2 pipeline on a single patient.

        Returns a dict matching the output JSON schema:
        {
            "orchestrator": {"decisions": [...]},
            "phase1": {"diagnostician": "...", ...},
            "epileptologist": {"reasoning": "...", "regimen": {...}},
            "pharmacologist": "...",
            "debate": [...],
            "final_regimen": {...}
        }
        """
        result = {}

        # ── ORCHESTRATOR: Decide which Phase 1 agents to activate ──
        decisions = await run_orchestrator(patient, self.llm, available_agents={
            name: cls for name, cls in PHASE1_AGENTS.items()
            if name in self.phase1_agents
        })
        result["orchestrator"] = {
            "decisions": [
                {"agent": d.agent_name, "activated": d.activated, "reason": d.reason}
                for d in decisions
            ]
        }

        # Determine which agents to run
        phase1_tasks = {}
        for decision in decisions:
            if decision.activated and decision.agent_name in self.phase1_agents:
                phase1_tasks[decision.agent_name] = self.phase1_agents[decision.agent_name]

        # ── PHASE 1: Run activated agents in parallel ──
        async def _run_agent(name, agent):
            return name, await agent.run(patient)

        phase1_results = await asyncio.gather(
            *[_run_agent(name, agent) for name, agent in phase1_tasks.items()]
        )

        phase1_responses = {}
        result["phase1"] = {}
        for name, response in phase1_results:
            phase1_responses[name] = response
            result["phase1"][name] = response.raw_output

        # ── PHASE 2: Epileptologist ──
        epi_context = {"phase1_responses": phase1_responses}
        epi_response = await self.epileptologist.run(patient, epi_context)

        epi_regimen = parse_regimen(epi_response.raw_output)
        if not epi_regimen:
            logger.warning("Failed to parse REGIMEN block (initial epi response)")
        result["epileptologist"] = {
            "reasoning": epi_response.raw_output,
            "regimen": epi_regimen,
        }

        # ── PHASE 3: Pharmacologist critique ──
        pharm_context = {
            "phase1_responses": phase1_responses,
            "epileptologist_response": epi_response,
        }
        pharm_response = await self.pharmacologist.run(patient, pharm_context)
        result["pharmacologist"] = pharm_response.raw_output

        # ── DEBATE: epi revises after pharma critique, always ends on epi ──
        # max_rounds=0: epi->pharma->epi (1 revision)
        # max_rounds=1: epi->pharma->epi->pharma->epi (2 revisions)
        # Skipped entirely only if pharma has no concerns
        result["debate"] = []

        if has_concerns(pharm_response.raw_output):
            debate_rounds = await run_debate(
                patient=patient,
                epileptologist=self.epileptologist,
                pharmacologist=self.pharmacologist,
                epi_response=epi_response,
                pharm_response=pharm_response,
                phase1_responses=phase1_responses,
                max_rounds=self.max_debate_rounds,
            )
            result["debate"] = debate_rounds

        # ── FINAL REGIMEN: last epi output ──
        if result["debate"]:
            result["final_regimen"] = result["debate"][-1]["epileptologist_regimen"]
        else:
            result["final_regimen"] = epi_regimen

        return result
