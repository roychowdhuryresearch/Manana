"""Pediatric Specialist agent — developmental context and weight-based dosing."""

from agents.base import BaseAgent
from schemas.patient import PatientCase


class PediatricianAgent(BaseAgent):
    name = "pediatrician"
    role = "Pediatric Specialist"
    prompt_file = "pediatrician.txt"
    always_active = True  # Most patients are children in this dataset
