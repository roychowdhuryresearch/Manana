"""Final output data structures."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class DrugActionType(Enum):
    CONTINUE = "continue"
    START = "start"
    STOP = "stop"


DRUG_COLUMNS = [
    # Uganda (10)
    "carbamazepine", "clobazam", "clonazepam", "ethosuximide",
    "lamotrigine", "levetiracetam", "phenobarbital", "phenytoin",
    "topiramate", "valproate",
    # MIMIC additions (5, ≥4% frequency)
    "gabapentin", "lacosamide", "lorazepam", "oxcarbazepine",
    "pregabalin", "zonisamide",
]

ALLOWED_ACTIONS = {"continue", "start", "stop"}


@dataclass
class DrugAction:
    """A single drug action in a recommendation."""
    drug: str
    action: str  # continue, start, stop
    rationale: str = ""
    provenance: str = ""  # Which agent(s) contributed to this decision


@dataclass
class DrugOption:
    """A complete regimen option."""
    rank: int  # 1, 2, or 3
    label: str  # e.g. "Monotherapy - valproate"
    drugs: list[DrugAction] = field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.0
    uncertainty_markers: list[str] = field(default_factory=list)

    def drug_names(self) -> set[str]:
        return {d.drug for d in self.drugs if d.action != "stop"}

    def to_comparable(self) -> dict:
        """Format for comparison with ground truth."""
        return {
            "drugs": [{"drug": d.drug, "action": d.action} for d in self.drugs],
            "label": self.label,
            "rationale": self.rationale,
        }


@dataclass
class FinalRecommendation:
    """Final recommendation with 3 ranked options and full provenance."""
    patient_id: str
    visit: str
    options: list[DrugOption] = field(default_factory=list)
    synthesis_notes: str = ""  # How the final decision was made
    safety_vetoes_applied: list[str] = field(default_factory=list)
    debate_modifications: list[str] = field(default_factory=list)
    availability_adjustments: list[str] = field(default_factory=list)

    def format_drugs_str(self, option_num: int) -> str:
        """Format drugs for a specific option as string."""
        if option_num < 1 or option_num > len(self.options):
            return ""
        opt = self.options[option_num - 1]
        return "; ".join(f"{d.drug}:{d.action}" for d in opt.drugs)
