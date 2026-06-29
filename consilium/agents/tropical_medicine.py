"""ID/Tropical Medicine Specialist — infectious etiology differential."""

from consilium.agents.base import BaseAgent


class TropicalMedicineAgent(BaseAgent):
    name = "tropical_medicine"
    role = "ID/Tropical Medicine Specialist"
    description = (
        "Evaluates whether seizures have an infectious etiology — "
        "cerebral malaria, neurocysticercosis, HIV-related, meningitis, "
        "or other tropical infections. Flags ASM-antimicrobial interactions. "
        "Relevant when clinical notes mention infection-related cues such as "
        "malaria, fever, HIV, retroviral, meningitis, encephalitis, "
        "neurocysticercosis, NCC, tuberculosis, TB, infection, sepsis, "
        "or acutely ill."
    )
    key_question = "Are these seizures from an infection, not epilepsy?"
    phase = 1
    prompt_file = "tropical_medicine.txt"
    always_active = True
