"""Bayesian Prompt Averaging (BPA) over a Manana round trajectory.

BPA treats the learned per-round prompt states as an ensemble of estimators.
At inference, the top-``num`` rounds (by validation top-3 rate) each propose a
ranked regimen; their options are combined into a weighted vote over complete
drug regimens, yielding ranked regimens plus a confidence (deferral) signal.

`aggregate` is pure (no I/O, no Bedrock) and unit-tested; `run` wires it to the
existing `manana.evaluate` per-round inference and `lib.grader`-compatible output.
"""
