"""Clinical Setting & Formulary Specialist — drug availability and cost."""

from agents.base import BaseAgent


class FormularyAgent(BaseAgent):
    name = "formulary"
    role = "Formulary Specialist"
    prompt_file = "formulary.txt"
    always_active = True
