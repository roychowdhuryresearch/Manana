"""Pure-Python reimplementation of the EpiPick algorithm.

Reverse-engineered from the client-side bundle.js at https://epipick.org
(retrieved April 2026). No network calls are made — this is entirely local.

The EpiPick algorithm ranks antiseizure medications (ASMs) into up to 4
groups (Group 1 = best, Group 4 = least desirable if above unavailable)
based on:
  - Seizure type
  - Patient age
  - Gender + menopausal status
  - Clinical modifiers (comorbidities, comedications)

Reference:
  Asadi-Pooya et al. (2020). A pragmatic algorithm to select appropriate
  antiseizure medications in patients with epilepsy. Epilepsia.
  https://doi.org/10.1111/epi.16610
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Seizure type constants (from bundle.js: to(no,"SEIZURE_*", N))
# ---------------------------------------------------------------------------
SEIZURE_UNCERTAIN = 0
SEIZURE_FOCAL = 1
SEIZURE_ABSENCE = 2
SEIZURE_MYOCLONIC = 3
SEIZURE_MYOCLONIC_ABSENCE = 4
SEIZURE_GTCS = 5
SEIZURE_GTCS_MYOCLONIC = 6
SEIZURE_GTCS_ABSENCE = 7
SEIZURE_GTCS_MYOCLONIC_ABSENCE = 8

SEIZURE_NAMES = {
    SEIZURE_UNCERTAIN: "Uncertain",
    SEIZURE_FOCAL: "Focal",
    SEIZURE_ABSENCE: "Absence",
    SEIZURE_MYOCLONIC: "Myoclonic",
    SEIZURE_MYOCLONIC_ABSENCE: "Myoclonic + Absence",
    SEIZURE_GTCS: "Primary GTCS",
    SEIZURE_GTCS_MYOCLONIC: "GTCS + Myoclonic",
    SEIZURE_GTCS_ABSENCE: "GTCS + Absence",
    SEIZURE_GTCS_MYOCLONIC_ABSENCE: "GTCS + Myoclonic + Absence",
}

# ---------------------------------------------------------------------------
# AED abbreviation → full name map
# ---------------------------------------------------------------------------
AED_FULL_NAMES = {
    "VPA": "valproate",
    "ETS": "ethosuximide",
    "LTG": "lamotrigine",
    "LEV": "levetiracetam",
    "TPM": "topiramate",
    "ZNS": "zonisamide",
    "ACT": "acetazolamide",
    "CLB": "clobazam",
    "CLN": "clonazepam",
    "PB": "phenobarbital",
    "NTR": "nitrazepam",
    "LCM": "lacosamide",
    "OXC": "oxcarbazepine",
    "PER": "perampanel",
    "CBZ": "carbamazepine",
    "PHT": "phenytoin",
    "ESL": "eslicarbazepine acetate",
    "GBP": "gabapentin",
    "BRV": "brivaracetam",
    "PGB": "pregabalin",
    "CEN": "cenobamate",
}

# Ordered AED list — index must match classesOrig columns exactly
AEDS = [
    "VPA", "ETS", "LTG", "LEV", "TPM", "ZNS", "ACT", "CLB", "CLN", "PB",
    "NTR", "LCM", "OXC", "PER", "CBZ", "PHT", "ESL", "GBP", "BRV", "PGB", "CEN",
]

NAN = float("nan")

# ---------------------------------------------------------------------------
# Base class rankings per seizure type (from bundle.js classesOrig array)
# Rows correspond to: ABSENCE, MYOCLONIC, GTCS, GTCS_MYOCLONIC, GTCS_ABSENCE,
#   GTCS_MYOCLONIC_ABSENCE, MYOCLONIC_ABSENCE, FOCAL, UNCERTAIN≥21, UNCERTAIN<21
# Columns are indexed by AEDS list above
# NaN = not recommended for this seizure type
# ---------------------------------------------------------------------------
_CLASSES_ORIG = [
    # ABSENCE (classesOrig[0])
    [1, 1, 2, 3, NAN, 3, 3, 3, 3, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN],
    # MYOCLONIC (classesOrig[1])
    [1, NAN, NAN, 1, 3, 3, NAN, 2, 1, 3, 3, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN],
    # GTCS (classesOrig[2])
    [1, NAN, 2, 2, 3, 3, NAN, 3, NAN, 3, NAN, 2, 3, 2, 3, 3, NAN, NAN, 3, NAN, NAN],
    # GTCS_MYOCLONIC (classesOrig[3])
    [1, NAN, 3, 2, 3, 3, NAN, 3, 3, 3, NAN, 3, NAN, 3, NAN, 3, NAN, NAN, 3, NAN, NAN],
    # GTCS_ABSENCE (classesOrig[4])
    [1, NAN, 2, 2, 3, 3, NAN, 3, NAN, 3, NAN, 3, NAN, 3, NAN, NAN, NAN, NAN, NAN, NAN, NAN],
    # GTCS_MYOCLONIC_ABSENCE (classesOrig[5])
    [1, NAN, 2, 2, 3, 3, NAN, 3, 3, 3, NAN, 3, NAN, 3, NAN, NAN, NAN, NAN, NAN, NAN, NAN],
    # MYOCLONIC_ABSENCE (classesOrig[6])
    [1, 1, 2, 2, 3, 3, NAN, 3, 3, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN],
    # FOCAL (classesOrig[7])
    [2, NAN, 1, 1, 2, 2, NAN, 3, NAN, 3, NAN, 1, 1, 2, 1, 2, 1, 3, 2, 3, 2],
    # UNCERTAIN age>=21 (classesOrig[8])
    [2, NAN, 1, 1, 2, 2, NAN, 2, NAN, 3, NAN, 1, 1, 2, 1, 2, 1, 3, 2, 3, 2],
    # UNCERTAIN age<21 (classesOrig[9])
    [1, NAN, 1, 1, 3, 3, NAN, 2, NAN, 3, NAN, 2, 2, 2, 2, NAN, 2, NAN, NAN, NAN, 2],
]

# Map seizure type → classesOrig index
_SEIZURE_TO_ORIG_IDX = {
    SEIZURE_ABSENCE: 0,
    SEIZURE_MYOCLONIC: 1,
    SEIZURE_GTCS: 2,
    SEIZURE_GTCS_MYOCLONIC: 3,
    SEIZURE_GTCS_ABSENCE: 4,
    SEIZURE_GTCS_MYOCLONIC_ABSENCE: 5,
    SEIZURE_MYOCLONIC_ABSENCE: 6,
    SEIZURE_FOCAL: 7,
    # UNCERTAIN handled by age in get_classes()
}


@dataclass
class Modifiers:
    daily_medication: bool = False   # other daily meds (not OCP or ASM)
    contraceptive: bool = False      # OCP or hormonal contraceptive (female)
    tumor: bool = False              # brain tumor requiring chemo/radiation
    hepatic_failure: bool = False    # hepatic failure
    obesity: bool = False            # BMI >= 30
    diabetes: bool = False           # diabetes mellitus
    bleeding: bool = False           # significant thrombocytopenia or coagulopathy
    neutropenia: bool = False        # neutrophil count < 1500/µL
    renal_stone: bool = False        # renal stone
    allergy: bool = False            # drug allergy
    depression: bool = False         # depression
    aggressive: bool = False         # irritability / aggressive behaviour
    migraine: bool = False           # migraine (≥4 headaches/month)
    renal_failure: bool = False      # renal insufficiency


def _aed_index(aed: str) -> int:
    return AEDS.index(aed)


def _get_classes(seizure_type: int, age: float) -> list[float]:
    """Return mutable copy of base class array for given seizure type."""
    if seizure_type == SEIZURE_UNCERTAIN:
        orig = _CLASSES_ORIG[8] if age >= 21 else _CLASSES_ORIG[9]
    else:
        orig_idx = _SEIZURE_TO_ORIG_IDX.get(seizure_type)
        if orig_idx is None:
            return [NAN] * len(AEDS)
        orig = _CLASSES_ORIG[orig_idx]
    return list(orig)  # mutable copy


def run_epipick(
    seizure_type: int,
    age: float,
    gender: str,          # "male" or "female"
    menopausal: str,      # "pre" or "post" (only relevant if female)
    modifiers: Modifiers,
) -> dict:
    """Run EpiPick algorithm and return normalized AED groups.

    Returns:
        {
          "group1": [list of AED full names],
          "group2": [...],
          "group3": [...],
          "group4": [...],   # only present if needed
        }
    """
    classes = _get_classes(seizure_type, age)
    can_upgrade = [True] * len(AEDS)

    def block_upgrade(aed: str):
        can_upgrade[_aed_index(aed)] = False

    def remove_class(aed: str):
        classes[_aed_index(aed)] = NAN

    def change_class(aed: str, cls: int):
        idx = _aed_index(aed)
        if can_upgrade[idx] and not math.isnan(classes[idx]):
            classes[idx] = cls

    def improve_class(aed: str, n: int):
        idx = _aed_index(aed)
        if can_upgrade[idx] and not math.isnan(classes[idx]):
            classes[idx] -= abs(n)

    def worsen_class(aed: str, n: int):
        idx = _aed_index(aed)
        if not math.isnan(classes[idx]):
            classes[idx] += abs(n)

    def improve_several(aeds: list[str], n: int):
        for a in aeds:
            improve_class(a, n)

    def worsen_several(aeds: list[str], n: int):
        for a in aeds:
            worsen_class(a, n)

    # PHT blocked from upgrade for GTCS/GTCS+myoclonic
    if seizure_type in (SEIZURE_GTCS, SEIZURE_GTCS_MYOCLONIC):
        block_upgrade("PHT")

    # Gender/menopausal modifiers
    if gender == "female" and menopausal == "pre":
        worsen_class("PB", 1)
        if seizure_type not in (SEIZURE_GTCS, SEIZURE_FOCAL):
            change_class("VPA", 3); block_upgrade("VPA")
            change_class("ZNS", 3); block_upgrade("ZNS")
            change_class("TPM", 3); block_upgrade("TPM")
        elif seizure_type == SEIZURE_GTCS:
            change_class("VPA", 2); block_upgrade("VPA")
            change_class("LTG", 1); block_upgrade("LTG")
            change_class("LEV", 1); block_upgrade("LEV")
        elif seizure_type == SEIZURE_FOCAL:
            remove_class("VPA")
            remove_class("ZNS")
            remove_class("TPM")

    # Age > 65
    if age > 65:
        improve_several(["LTG", "LEV", "LCM", "GBP"], 1)

    # Daily medication (drug interactions)
    if modifiers.daily_medication:
        if seizure_type not in (SEIZURE_FOCAL, SEIZURE_UNCERTAIN):
            improve_several(["ETS", "LEV", "LCM", "LTG", "ZNS", "PER"], 1)
            worsen_several(["CBZ", "PHT", "PB"], 1)
        else:
            improve_several(["LEV", "LCM", "GBP", "LTG", "BRV", "ZNS", "PER"], 1)
            worsen_several(["CBZ", "PHT", "PB"], 1)

    # Contraceptive (female only)
    if modifiers.contraceptive and gender == "female":
        worsen_several(["TPM", "PER"], 1)
        worsen_several(["CBZ", "PB", "PHT", "OXC", "ESL"], 2)

    # Brain tumor
    if modifiers.tumor:
        worsen_several(["CBZ", "OXC", "ESL", "PHT", "PB"], 2)

    # Hepatic failure
    if modifiers.hepatic_failure:
        improve_several(["LEV", "LCM", "GBP"], 1)
        worsen_class("VPA", 2)

    # Obesity
    if modifiers.obesity:
        worsen_several(["PGB", "GBP"], 1)
        if seizure_type in (SEIZURE_FOCAL, SEIZURE_UNCERTAIN):
            worsen_class("VPA", 2)
        else:
            worsen_class("VPA", 1)

    # Diabetes
    if modifiers.diabetes:
        worsen_several(["VPA", "PHT", "CBZ", "PER"], 1)

    # Bleeding / coagulopathy
    if modifiers.bleeding:
        if seizure_type in (SEIZURE_FOCAL, SEIZURE_UNCERTAIN):
            worsen_class("VPA", 2)
        else:
            worsen_class("VPA", 1)

    # Neutropenia
    if modifiers.neutropenia:
        worsen_several(["CBZ", "PHT"], 1)

    # Renal stone
    if modifiers.renal_stone:
        worsen_several(["TPM", "ZNS", "ACT"], 1)

    # Drug allergy
    if modifiers.allergy:
        worsen_several(["LTG", "PHT", "CBZ", "OXC", "ESL", "PB", "ZNS", "CEN"], 1)

    # Depression
    if modifiers.depression:
        improve_several(["LTG"], 1)
        worsen_several(["LEV", "PB", "CLB", "CLN", "NTR"], 1)

    # Aggressive / irritability
    if modifiers.aggressive:
        worsen_several(["TPM", "PB", "LEV", "PER"], 1)

    # Migraine
    if modifiers.migraine:
        improve_several(["TPM", "VPA"], 1)

    # Renal failure
    if modifiers.renal_failure:
        improve_several(["CLB", "ETS", "LTG", "CBZ", "PHT"], 1)
        worsen_several(
            ["VPA", "LEV", "TPM", "ZNS", "ACT", "CLN", "PB", "NTR",
             "LCM", "OXC", "PER", "ESL", "GBP", "BRV", "PGB"], 1
        )

    # ---------------------------------------------------------------------------
    # Build normalized groups (calcNormalizedAEDs)
    # ---------------------------------------------------------------------------
    # Find min and max class values
    valid = [c for c in classes if not math.isnan(c)]
    if not valid:
        return {"group1": [], "group2": [], "group3": [], "group4": []}

    min_cls = min(valid)
    max_cls = max(valid)

    # Build raw groups by actual class value
    raw_groups: dict[int, list[str]] = {}
    for i, aed in enumerate(AEDS):
        if not math.isnan(classes[i]):
            cls = int(classes[i])
            raw_groups.setdefault(cls, []).append(aed)

    # Normalize: group indices start at 0 relative to min_cls
    # Then collapse everything at position >=3 into group4 (index 3)
    normalized: list[list[str]] = [[] for _ in range(4)]
    for cls_val in sorted(raw_groups.keys()):
        rel = cls_val - min_cls
        target = min(rel, 3)
        normalized[target].extend(raw_groups[cls_val])

    # ---------------------------------------------------------------------------
    # Post-processing (modifyNormalizedAEDs)
    # ---------------------------------------------------------------------------
    # GTCS+myoclonic / GTCS+myoclonic+absence: move CLN from g0/g1 → g2
    if seizure_type in (SEIZURE_GTCS_MYOCLONIC, SEIZURE_GTCS_MYOCLONIC_ABSENCE):
        for src in (0, 1):
            if "CLN" in normalized[src]:
                normalized[src].remove("CLN")
                normalized[2].append("CLN")

    # Female premenopausal: move VPA from g0/g1 → g2
    if gender == "female" and menopausal == "pre":
        for src in (0, 1):
            if "VPA" in normalized[src]:
                normalized[src].remove("VPA")
                normalized[2].append("VPA")

    # Focal: move CLB from g0 or g1 → g2
    if seizure_type == SEIZURE_FOCAL:
        moved = False
        if "CLB" in normalized[0]:
            normalized[0].remove("CLB")
            normalized[2].append("CLB")
            moved = True
        if not moved and "CLB" in normalized[1]:
            normalized[1].remove("CLB")
            normalized[2].append("CLB")

    # Myoclonic / uncertain: move CLB from g0 → g1
    if seizure_type in (SEIZURE_MYOCLONIC, SEIZURE_UNCERTAIN):
        if "CLB" in normalized[0]:
            normalized[0].remove("CLB")
            normalized[1].append("CLB")

    # GTCS / GTCS+myoclonic: move PHT to g2 if not already there
    if seizure_type in (SEIZURE_GTCS, SEIZURE_GTCS_MYOCLONIC):
        for src in (0, 1, 3):
            if "PHT" in normalized[src]:
                normalized[src].remove("PHT")
                normalized[2].append("PHT")

    # Map to output with full names
    def to_full(aeds_list: list[str]) -> list[str]:
        return [AED_FULL_NAMES[a] for a in aeds_list]

    result = {
        "group1": to_full(normalized[0]),
        "group2": to_full(normalized[1]),
        "group3": to_full(normalized[2]),
        "group4": to_full(normalized[3]),
    }
    return result
