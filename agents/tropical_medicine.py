"""ID/Tropical Medicine Specialist — infectious etiology differential."""

import re
from agents.base import BaseAgent
from schemas.patient import PatientCase


INFECTION_KEYWORDS = [
    "malaria", "cerebral malaria", "fever", "hiv", "retroviral",
    "meningitis", "encephalitis", "ncc", "neurocysticercosis",
    "cysticercosis", "tuberculosis", "tb meningitis",
    "infection", "sepsis", "acutely ill",
]


class TropicalMedicineAgent(BaseAgent):
    name = "tropical_medicine"
    role = "ID/Tropical Medicine Specialist"
    prompt_file = "tropical_medicine.txt"
    always_active = False  # Conditional — only when infection cues present

    def should_activate(self, patient: PatientCase) -> tuple[bool, str]:
        """Activate if clinical notes contain infection-related keywords."""
        full_text = patient.build_input_text().lower()
        found = [kw for kw in INFECTION_KEYWORDS if kw in full_text]
        if found:
            return True, f"infection cues detected: {', '.join(found[:3])}"
        return False, "no infection cues in clinical notes"
