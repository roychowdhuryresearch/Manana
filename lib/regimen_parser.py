"""Parse epileptologist's REGIMEN block into structured options."""

from __future__ import annotations
import re

from lib.output import DRUG_COLUMNS, ALLOWED_ACTIONS

# Map common synonyms/brand names to canonical drug names
DRUG_ALIASES = {
    "valproic acid": "valproate", "valproic": "valproate",
    "sodium valproate": "valproate", "depakote": "valproate",
    "epilim": "valproate", "vpa": "valproate",
    "tegretol": "carbamazepine", "cbz": "carbamazepine",
    "keppra": "levetiracetam", "lev": "levetiracetam",
    "lamictal": "lamotrigine", "ltg": "lamotrigine",
    "topamax": "topiramate", "tpm": "topiramate",
    "dilantin": "phenytoin", "pht": "phenytoin",
    "phenobarbitone": "phenobarbital", "pb": "phenobarbital", "phb": "phenobarbital",
    "zarontin": "ethosuximide", "esm": "ethosuximide",
    "frisium": "clobazam", "clb": "clobazam",
    "rivotril": "clonazepam", "czp": "clonazepam",
    # MIMIC drugs
    "trileptal": "oxcarbazepine", "oxcarbazepine": "oxcarbazepine",
    "vimpat": "lacosamide",
    "zonegran": "zonisamide",
    "neurontin": "gabapentin",
    "lyrica": "pregabalin",
    "onfi": "clobazam",
    "fycompa": "perampanel",
    "briviact": "brivaracetam",
    "valium": "diazepam",
    "ativan": "lorazepam",
    "diamox": "acetazolamide",
    "mysoline": "primidone",
    "banzel": "rufinamide",
    "felbatol": "felbamate",
}


def _normalize_drug(name: str) -> str | None:
    """Normalize a drug name to canonical form."""
    lower = name.strip().lower()
    if lower in DRUG_COLUMNS:
        return lower
    return DRUG_ALIASES.get(lower)


# Map common action synonyms to canonical actions in ALLOWED_ACTIONS
ACTION_SYNONYMS = {
    # → start
    "add": "start", "adding": "start", "adds": "start", "added": "start",
    "new": "start", "initiate": "start", "initiated": "start",
    "begin": "start", "commence": "start", "introduce": "start", "adjunct": "start",
    "adjunctive": "start", "trial": "start",
    # → stop
    "discontinue": "stop", "discontinued": "stop", "withdraw": "stop",
    "withdrawn": "stop", "wean": "stop", "weaned": "stop",
    "taper": "stop", "tapered": "stop",
    # → continue (regimen unchanged; dose changes still keep the drug)
    "maintain": "continue", "maintains": "continue", "maintained": "continue",
    "keep": "continue", "kept": "continue", "unchanged": "continue",
    "ongoing": "continue", "current": "continue",
    "increase": "continue", "increased": "continue",
    "decrease": "continue", "decreased": "continue", "reduce": "continue",
    "reduced": "continue", "adjust": "continue", "adjusted": "continue",
    "optimize": "continue", "optimized": "continue", "optimise": "continue",
    "titrate": "continue", "titrated": "continue",
}


def _normalize_action(action: str) -> str | None:
    """Normalize an action verb to one of ALLOWED_ACTIONS, or None if unmappable."""
    lower = action.strip().lower()
    if lower in ALLOWED_ACTIONS:
        return lower
    return ACTION_SYNONYMS.get(lower)


def _strip_md(text: str) -> str:
    """Strip markdown bold/italic markers."""
    return text.replace("**", "").replace("*", "").strip()


def parse_regimen(raw_output: str) -> dict:
    """Parse the REGIMEN block from epileptologist output.

    Returns:
        {
            "option_1": {"label": "...", "drugs": {"valproate": "continue", ...}, "rationale": "..."},
            "option_2": {...},
            "option_3": {...}
        }
    """
    result = {}

    # Strip markdown bold from entire text for easier parsing
    clean = _strip_md(raw_output)

    # Find the REGIMEN section (with or without colon)
    regimen_match = re.search(r'REGIMEN\s*:?', clean, re.IGNORECASE)
    if regimen_match:
        regimen_text = clean[regimen_match.end():]
    else:
        regimen_text = clean

    # Split into option blocks (handles "Option 1:", "Option 1 –", "Option 1 -", etc.)
    option_pattern = re.compile(
        r'Option\s+(\d)\s*[:\-\u2013\u2014]\s*(.+?)(?=Option\s+\d\s*[:\-\u2013\u2014]|$)',
        re.DOTALL | re.IGNORECASE,
    )

    for m in option_pattern.finditer(regimen_text):
        num = int(m.group(1))
        block = m.group(2).strip()

        label_line = block.split('\n')[0].strip()
        drugs = {}
        rationale = ""

        for line in block.split('\n'):
            stripped = line.strip()

            # Parse drug lines: "- drug_name: action (optional extra text)"
            drug_match = re.match(r'-\s*(.+?)\s*:\s*(\w+)', stripped)
            if drug_match:
                raw_drug = drug_match.group(1).strip()
                raw_action = drug_match.group(2).strip().lower()
                canonical_drug = _normalize_drug(raw_drug)
                # Handle "drug: drug" pattern (e.g., "- LEV: levetiracetam") — model
                # repeated the drug name where action should be. Default to "start".
                if canonical_drug and _normalize_drug(raw_action) == canonical_drug:
                    drugs[canonical_drug] = "start"
                    continue
                canonical_action = _normalize_action(raw_action)
                if canonical_drug and canonical_action:
                    drugs[canonical_drug] = canonical_action

            # Parse rationale
            rat_match = re.match(r'Rationale\s*:\s*(.*)', stripped, re.IGNORECASE)
            if rat_match:
                rationale = rat_match.group(1).strip()

        result[f"option_{num}"] = {
            "label": label_line,
            "drugs": drugs,
            "rationale": rationale,
        }

    return result
