"""Treatment Response Analyst — longitudinal medication assessment."""

from consilium.agents.base import BaseAgent


class TreatmentAnalystAgent(BaseAgent):
    name = "treatment_analyst"
    role = "Treatment Response Analyst"
    description = (
        "Evaluates longitudinal medication response across visits. "
        "Assesses whether current drugs are working, doses are optimized, "
        "and whether changes from the prior visit are justified."
    )
    key_question = "Is the current regimen working?"
    phase = 1
    prompt_file = "treatment_analyst.txt"
    always_active = True
