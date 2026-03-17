"""Treatment Response Analyst — longitudinal medication assessment."""

from agents.base import BaseAgent


class TreatmentAnalystAgent(BaseAgent):
    name = "treatment_analyst"
    role = "Treatment Response Analyst"
    prompt_file = "treatment_analyst.txt"
    always_active = True
