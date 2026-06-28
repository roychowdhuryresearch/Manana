"""Tests for manana.bpa.aggregate — round selection and ballot voting.

Run:  uv run pytest tests/test_bpa_aggregate.py -q
"""

from __future__ import annotations

import pytest

from manana.bpa.aggregate import (
    RANK_PRIOR,
    aggregate,
    coverage_precision,
    select_rounds,
)

PROGRESSION = [
    {"round": "baseline", "top3_rate": 0.99},  # must be ignored
    {"round": 0, "top3_rate": 0.70},
    {"round": 1, "top3_rate": 0.90},
    {"round": 2, "top3_rate": 0.80},
    {"round": 3, "top3_rate": 0.90},  # ties round 1 -> lower id wins ordering
    {"round": 4, "top3_rate": 0.60},
]


def _opts(*regimens):
    """Build a grader-style options list from (rank, [drugs]) pairs."""
    return [
        {"rank": rank, "drugs": drugs, "label": f"opt{rank}", "rationale": "r", "actions": {}}
        for rank, drugs in regimens
    ]


# --- select_rounds ---------------------------------------------------------

def test_select_skips_baseline_and_picks_top_num():
    sel = select_rounds(PROGRESSION, num=3, weighting="uniform")
    assert [s.round_id for s in sel] == [1, 3, 2]  # by rate desc, id tiebreak


def test_uniform_weights_sum_to_one_and_equal():
    sel = select_rounds(PROGRESSION, num=4, weighting="uniform")
    assert sum(s.weight for s in sel) == pytest.approx(1.0)
    assert all(s.weight == pytest.approx(0.25) for s in sel)


def test_linear_weights_proportional_to_rate():
    sel = select_rounds(PROGRESSION, num=2, weighting="linear")  # rounds 1 & 3, both 0.90
    assert sum(s.weight for s in sel) == pytest.approx(1.0)
    assert sel[0].weight == pytest.approx(0.5)


def test_softmax_orders_by_rate():
    sel = select_rounds(PROGRESSION, num=3, weighting="softmax", tau=5.0)
    assert sum(s.weight for s in sel) == pytest.approx(1.0)
    by_id = {s.round_id: s.weight for s in sel}
    assert by_id[2] < by_id[1]  # lower rate -> lower softmax weight


def test_num_larger_than_available_selects_all():
    sel = select_rounds(PROGRESSION, num=99, weighting="uniform")
    assert len(sel) == 5


@pytest.mark.parametrize("bad_num", [0, -1])
def test_non_positive_num_raises(bad_num):
    with pytest.raises(ValueError):
        select_rounds(PROGRESSION, num=bad_num)


def test_bad_weighting_raises():
    with pytest.raises(ValueError):
        select_rounds(PROGRESSION, num=2, weighting="bogus")


# --- aggregate -------------------------------------------------------------

def test_aggregate_winner_is_top_ranked_majority():
    per_round = [
        (0.5, _opts((1, ["carbamazepine"]), (2, ["valproate"]), (3, ["lamotrigine"]))),
        (0.5, _opts((1, ["carbamazepine"]), (2, ["levetiracetam"]), (3, ["topiramate"]))),
    ]
    out = aggregate(per_round)
    top = out["options"][0]
    assert top["drugs"] == ["carbamazepine"]
    assert out["confidence"] == top["prob"]
    assert out["confidence"] > 0.5  # winner holds majority mass


def test_aggregate_rank_prior_applied():
    out = aggregate([(1.0, _opts((2, ["valproate"])))])
    assert out["total_mass"] == pytest.approx(RANK_PRIOR[2])


def test_aggregate_skips_empty_regimens():
    out = aggregate([(1.0, _opts((1, []), (2, ["valproate"])))])
    drugsets = [o["drugs"] for o in out["options"]]
    assert ["valproate"] in drugsets
    assert [] not in drugsets
    assert out["n_unique_regimens"] == 1


def test_aggregate_merges_duplicate_regimens_across_ranks():
    per_round = [
        (1.0, _opts((1, ["carbamazepine", "valproate"]))),
        (1.0, _opts((2, ["valproate", "carbamazepine"]))),  # order-independent set
    ]
    out = aggregate(per_round)
    assert out["n_unique_regimens"] == 1
    assert out["total_mass"] == pytest.approx(RANK_PRIOR[1] + RANK_PRIOR[2])


# --- coverage_precision ----------------------------------------------------

def test_coverage_precision_curve():
    cases = [
        {"confidence": 0.9, "top1_match": True},
        {"confidence": 0.7, "top1_match": False},
        {"confidence": 0.5, "top1_match": True},
        {"confidence": 0.3, "top1_match": True},
    ]
    curve = coverage_precision(cases)
    assert [row["coverage"] for row in curve] == [0.25, 0.5, 0.75, 1.0]
    assert curve[0]["precision"] == pytest.approx(1.0)
    assert curve[1]["precision"] == pytest.approx(0.5)
    assert curve[-1]["precision"] == pytest.approx(0.75)


def test_coverage_precision_empty():
    assert coverage_precision([]) == []
