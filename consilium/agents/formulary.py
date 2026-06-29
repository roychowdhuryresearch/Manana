"""Clinical Setting & Formulary Specialist — drug availability and cost."""

from consilium.agents.base import BaseAgent


class FormularyAgent(BaseAgent):
    name = "formulary"
    role = "Formulary Specialist"
    description = (
        "Assesses drug availability, cost, and health system constraints "
        "in the patient's clinical setting (Uganda). Identifies drugs "
        "that may not be accessible or affordable."
    )
    key_question = "Can the patient actually get these drugs?"
    phase = 1
    prompt_file = "formulary.txt"
    always_active = True
