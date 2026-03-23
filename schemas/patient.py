"""Patient case data structures."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class VisitData:
    """Clinical data for a single visit."""
    visit_name: str  # "Visit_1", "Visit_2", "Visit_3"
    visit_label: str  # "Visit 1 (0 months)", etc.
    input_text: str  # Clinical observations
    prescription: str  # Clean prescription (empty for current visit)
    is_current: bool = False


@dataclass
class MedicationHistory:
    """Extracted medication history from prior visits."""
    prescribed: list[str] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)


@dataclass
class PatientCase:
    """Complete patient case for agent processing."""
    patient_id: str
    age: str = ""
    sex: str = ""
    diagnosis: str = ""
    seizure_onset: str = ""
    seizure_duration: str = ""
    visits: list[VisitData] = field(default_factory=list)
    current_visit: str = ""  # Which visit we're predicting
    medication_history: dict[str, MedicationHistory] = field(default_factory=dict)
    clinical_context: str = ""  # Full patient context string; if set, used directly by agents

    @property
    def is_pediatric(self) -> bool:
        """Check if patient is likely pediatric based on age field."""
        if not self.age:
            return False
        age_str = self.age.lower().strip()
        # Check for months
        if "month" in age_str:
            return True
        # Try to extract numeric age
        import re
        nums = re.findall(r'(\d+)', age_str)
        if nums:
            age_val = int(nums[0])
            if "year" in age_str or age_str.isdigit():
                return age_val < 18
        return False

    @property
    def prior_drugs(self) -> set[str]:
        """All drugs mentioned in prior visit prescriptions."""
        drugs = set()
        for visit_med in self.medication_history.values():
            drugs.update(visit_med.prescribed)
        return drugs

    def build_input_text(self) -> str:
        """Build the full input text string for this patient case."""
        if self.clinical_context:
            return self.clinical_context

        parts = ["For this patient, here is what you have:\n"]

        demo = " | ".join(x for x in [
            f"Age: {self.age}" if self.age else "",
            f"Sex: {self.sex}" if self.sex else "",
            f"Diagnosis: {self.diagnosis}" if self.diagnosis else "",
        ] if x)
        if demo:
            parts.append(demo)

        detail = " | ".join(x for x in [
            f"Seizure onset: {self.seizure_onset}" if self.seizure_onset else "",
            f"Seizure duration: {self.seizure_duration}" if self.seizure_duration else "",
        ] if x)
        if detail:
            parts.append(detail)

        parts.append("")

        for visit in self.visits:
            parts.append(f"[{visit.visit_label} - Clinical Notes]")
            parts.append(visit.input_text.strip() if visit.input_text.strip() else "(no clinical notes recorded)")

            if not visit.is_current and visit.prescription is not None:
                parts.append(f"\n[{visit.visit_label} - Prescription]")
                parts.append(visit.prescription.strip() if visit.prescription.strip() else "(no prescription recorded)")

            parts.append("")

        return "\n".join(parts).strip()
