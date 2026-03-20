"""Pediatric Specialist agent — developmental context and weight-based dosing."""

from agents.base import BaseAgent
from schemas.patient import PatientCase


class PediatricianAgent(BaseAgent):
    name = "pediatrician"
    role = "Pediatric Specialist"
    description = (
        "Assesses developmental context, weight-based dosing, and "
        "age-specific drug safety. Flags drugs contraindicated in "
        "children or requiring dose adjustment by weight."
    )
    key_question = "Is this safe for this child's body?"
    phase = 1
    prompt_file = "pediatrician.txt"
    always_active = True
