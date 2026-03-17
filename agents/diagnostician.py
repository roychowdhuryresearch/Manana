"""Seizure Diagnostician agent — seizure type and syndrome classification."""

from agents.base import BaseAgent


class DiagnosticianAgent(BaseAgent):
    name = "diagnostician"
    role = "Seizure Diagnostician"
    prompt_file = "diagnostician.txt"
    always_active = True
