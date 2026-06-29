"""Pure Bayesian Prompt Averaging math — round selection and ballot voting.

No I/O and no Bedrock calls live here so the BPA logic can be unit-tested
directly. `run.py` supplies the per-round predicted options (produced via the
existing `manana.evaluate` inference) and consumes the aggregated result.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

# Empirical candidate-position prior P(correct regimen is at rank r), estimated
# once from a small training subset (paper: pi = (0.85, 0.11, 0.04)).
RANK_PRIOR: dict[int, float] = {1: 0.85, 2: 0.11, 3: 0.04}

WEIGHTINGS = ("uniform", "linear", "softmax")
DEFAULT_TAU = 5.0


@dataclass(frozen=True)
class RoundSelection:
    """One selected ensemble member: a round, its validation score and weight."""

    round_id: int
    top3_rate: float
    weight: float


def select_rounds(
    progression: list[dict[str, Any]],
    num: int,
    weighting: str = "softmax",
    tau: float = DEFAULT_TAU,
) -> list[RoundSelection]:
    """Pick the top-``num`` numbered rounds by validation top-3 rate and weight them.

    `progression` is the parsed `eval_progression.json`: a list of per-round dicts
    with an integer ``round`` and a ``top3_rate``. The string ``baseline`` entry
    (and any non-numbered rows) are ignored. Ties break by ascending round id so
    selection is deterministic.
    """
    if num <= 0:
        raise ValueError(f"--num must be positive, got {num}")
    if weighting not in WEIGHTINGS:
        raise ValueError(f"Unknown weighting {weighting!r}; choose from {WEIGHTINGS}")

    rounds = [
        (int(row["round"]), float(row.get("top3_rate") or 0.0))
        for row in progression
        if isinstance(row.get("round"), int)
    ]
    if not rounds:
        raise ValueError("No numbered rounds found in progression")

    # Highest validation score first; deterministic tie-break by round id.
    rounds.sort(key=lambda rr: (-rr[1], rr[0]))
    chosen = rounds[: min(num, len(rounds))]

    weights = _weights([rate for _, rate in chosen], weighting, tau)
    return [
        RoundSelection(round_id=rid, top3_rate=rate, weight=w)
        for (rid, rate), w in zip(chosen, weights)
    ]


def _weights(rates: list[float], weighting: str, tau: float) -> list[float]:
    k = len(rates)
    if weighting == "uniform":
        return [1.0 / k] * k
    if weighting == "linear":
        total = sum(rates)
        if total <= 0:  # all-zero scores: fall back to uniform
            return [1.0 / k] * k
        return [r / total for r in rates]
    # softmax
    exps = [math.exp(r * tau) for r in rates]
    total = sum(exps)
    return [e / total for e in exps]


def _drugset(option: dict[str, Any]) -> frozenset[str]:
    """The complete prescribed regimen for an option as a lowercased set."""
    drugs = option.get("drugs") or []
    return frozenset(str(d).strip().lower() for d in drugs if str(d).strip())


@dataclass
class _Tally:
    mass: float = 0.0
    best_ballot_weight: float = -1.0
    label: str = ""
    rationale: str = ""
    actions: dict[str, str] = field(default_factory=dict)


def aggregate(
    per_round_options: list[tuple[float, list[dict[str, Any]]]],
    rank_prior: dict[int, float] = RANK_PRIOR,
) -> dict[str, Any]:
    """Weighted vote over complete regimens → ranked regimens + confidence.

    `per_round_options` is ``[(round_weight, options), ...]`` where ``options`` is
    a grader-style list of ``{"rank", "drugs", "label", "rationale", "actions"}``
    (exactly what `manana.evaluate.run_multi_case` returns). Each option becomes a
    ballot for its complete drug regimen with weight ``round_weight *
    rank_prior[rank]``; empty regimens are skipped. Returns the top-3 regimens by
    posterior mass plus a confidence equal to the winner's normalized mass.
    """
    tallies: dict[frozenset[str], _Tally] = defaultdict(_Tally)

    for round_weight, options in per_round_options:
        for option in options:
            regimen = _drugset(option)
            if not regimen:  # skip unparseable / empty options
                continue
            rank = int(option.get("rank") or 0)
            ballot_weight = round_weight * float(rank_prior.get(rank, 0.0))
            if ballot_weight <= 0:
                continue
            tally = tallies[regimen]
            tally.mass += ballot_weight
            # Keep presentation fields from the single most-confident ballot.
            if ballot_weight > tally.best_ballot_weight:
                tally.best_ballot_weight = ballot_weight
                tally.label = str(option.get("label") or "")
                tally.rationale = str(option.get("rationale") or "")
                tally.actions = dict(option.get("actions") or {})

    total_mass = sum(t.mass for t in tallies.values())
    ranked = sorted(tallies.items(), key=lambda kv: kv[1].mass, reverse=True)

    options_out: list[dict[str, Any]] = []
    for i, (regimen, tally) in enumerate(ranked[:3], start=1):
        prob = tally.mass / total_mass if total_mass else 0.0
        options_out.append(
            {
                "rank": i,
                "drugs": sorted(regimen),
                "prob": round(prob, 4),
                "mass": round(tally.mass, 6),
                "label": tally.label,
                "rationale": tally.rationale,
                "actions": tally.actions,
            }
        )

    confidence = options_out[0]["prob"] if options_out else 0.0
    vote_distribution = [
        {"drugs": sorted(regimen), "prob": round(t.mass / total_mass, 4) if total_mass else 0.0}
        for regimen, t in ranked
    ]

    return {
        "options": options_out,
        "confidence": confidence,
        "n_unique_regimens": len(tallies),
        "total_mass": round(total_mass, 6),
        "vote_distribution": vote_distribution,
    }


def coverage_precision(
    cases: list[dict[str, Any]],
    confidence_key: str = "confidence",
    correct_key: str = "top1_match",
) -> list[dict[str, float]]:
    """Selective-prediction curve: sort by confidence desc, report running precision.

    Each case dict needs a confidence and a boolean correctness flag. Returns one
    row per coverage level: ``{"coverage", "precision", "confidence"}``.
    """
    total = len(cases)
    if total == 0:
        return []
    ordered = sorted(cases, key=lambda c: c.get(confidence_key, 0.0), reverse=True)
    curve = []
    correct = 0
    for i, case in enumerate(ordered, start=1):
        if case.get(correct_key):
            correct += 1
        curve.append(
            {
                "coverage": round(i / total, 4),
                "precision": round(correct / i, 4),
                "confidence": round(float(case.get(confidence_key, 0.0)), 4),
            }
        )
    return curve
