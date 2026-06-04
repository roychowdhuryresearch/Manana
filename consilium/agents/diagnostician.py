"""Seizure Diagnostician agent — seizure type and syndrome classification."""

from consilium.agents.base import BaseAgent


class DiagnosticianAgent(BaseAgent):
    name = "diagnostician"
    role = "Seizure Diagnostician"
    description = (
        "Classifies seizure type and epilepsy syndrome from clinical "
        "semiology and EEG findings. Determines whether seizures are "
        "focal, generalized, or unknown onset."
    )
    key_question = "What kind of epilepsy is this?"
    phase = 1
    prompt_file = "diagnostician.txt"
    always_active = True
