"""Generate calibration plots for the BMA ensemble paper:
1. Coverage–Precision curve (headline)
2. Reliability diagram (calibration check)
3. Confidence histogram overlay (correct vs wrong)
4. Deferral-rate vs precision

All plots use BMA Beta-Binomial confidence (the proposed primary scheme).
Outputs PDFs into figs/ next to this script.

Usage:
    uv run python scripts/plot_calibration.py
"""

import json
import os

import matplotlib.pyplot as plt
import numpy as np

# Confidence and match prefixes per file
SINGLE_BMA = ("bma_match", "bma_confidence")
MULTI_BMA = ("bb_match", "bb_confidence")

PATHS = {
    "Single-agent A": (
        "self_learning/outputs/test_comparison/test_csv_20260501_161048/results.json",
        SINGLE_BMA,
    ),
    "Single-agent B": (
        "self_learning/outputs/test_comparison/test_pdf_20260501_161049/results.json",
        SINGLE_BMA,
    ),
    "Multi-agent A": (
        "self_learning/outputs/test_comparison/test_multi_csv_20260428_214555/results.json",
        MULTI_BMA,
    ),
    "Multi-agent B": (
        "self_learning/outputs/test_comparison/test_multi_pdf_20260428_214627/results.json",
        MULTI_BMA,
    ),
}

OUT_DIR = "figs"
os.makedirs(OUT_DIR, exist_ok=True)


def add_legend(ax, **kwargs):
    return ax.legend(**kwargs)


def load(path, match_key, conf_key):
    with open(path) as f:
        data = json.load(f)
    confs = np.array([r[conf_key] for r in data])
    correct = np.array([1 if r[match_key] else 0 for r in data], dtype=int)
    return confs, correct


def coverage_precision(confs, correct):
    order = np.argsort(-confs)  # descending confidence
    correct_sorted = correct[order]
    cumulative_correct = np.cumsum(correct_sorted)
    n_kept = np.arange(1, len(correct) + 1)
    coverage = n_kept / len(correct)
    precision = cumulative_correct / n_kept
    return coverage, precision


def deferral_precision(path, match_key, conf_key):
    confs, correct = load(path, match_key, conf_key)
    order = np.argsort(-confs)
    correct_sorted = correct[order]
    cumulative_correct = np.cumsum(correct_sorted)
    n_total = len(correct)

    # Display 5% operating points. Precision is measured on the non-deferred
    # subset, matching Table 3; the 100% endpoint is all-clinician review.
    deferral = np.arange(0, 101, 5)
    precision = []
    for rate in deferral:
        if rate == 100:
            precision.append(100.0)
            continue
        n_auto = max(1, int(round(n_total * (1 - rate / 100))))
        precision.append(cumulative_correct[n_auto - 1] / n_auto * 100)

    return deferral, np.array(precision)


def reliability_bins(path, match_key, conf_key, min_bin_n=5):
    confs, correct = load(path, match_key, conf_key)
    bin_edges = np.linspace(0, 1, 11)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    bin_idx = np.digitize(confs, bin_edges) - 1
    bin_idx = np.clip(bin_idx, 0, 9)
    bin_acc = []
    bin_n = []
    for b in range(10):
        mask = bin_idx == b
        bin_acc.append(np.nan if mask.sum() == 0 else correct[mask].mean())
        bin_n.append(mask.sum())
    bin_acc = np.array(bin_acc)
    bin_n = np.array(bin_n)
    valid = bin_n >= min_bin_n
    return bin_centers[valid], bin_acc[valid], bin_n[valid]


def save_plot(stem, legacy_stems=()):
    out = os.path.join(OUT_DIR, f"{stem}.pdf")
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.savefig(out.replace(".pdf", ".png"), dpi=300, bbox_inches="tight")
    print(f"Saved: {out}")
    for legacy_stem in legacy_stems:
        legacy_out = os.path.join(OUT_DIR, f"{legacy_stem}.pdf")
        plt.savefig(legacy_out, dpi=300, bbox_inches="tight")
        plt.savefig(legacy_out.replace(".pdf", ".png"), dpi=300, bbox_inches="tight")
        print(f"Saved: {legacy_out}")


# --- Plot 1: Coverage–Precision curve ---
fig, ax = plt.subplots(figsize=(7, 5))

styles = {
    "Single-agent A": {"color": "#0072B2", "ls": "--", "lw": 2},
    "Multi-agent A": {"color": "#0072B2", "ls": "-", "lw": 2.5},
    "Single-agent B": {"color": "#D55E00", "ls": "--", "lw": 2},
    "Multi-agent B": {"color": "#D55E00", "ls": "-", "lw": 2.5},
}

for label, (path, (mk, ck)) in PATHS.items():
    confs, correct = load(path, mk, ck)
    coverage, precision = coverage_precision(confs, correct)
    ax.plot(coverage * 100, precision * 100, label=label, **styles[label])

ax.set_xlabel("Coverage (% of cases the system commits to)", fontsize=11)
ax.set_ylabel("Precision (%)", fontsize=11)
ax.set_title("Coverage–Precision Curve\n(Single- and Multi-Agent BMA Beta-Binomial)", fontsize=12)
ax.set_xlim(0, 100)
ax.set_ylim(60, 102)
ax.set_xticks(range(0, 101, 25))
ax.grid(alpha=0.3)
add_legend(ax, loc="lower left", fontsize=10)

# Annotate the headline finding
ax.annotate(
    "Cohort B multi-agent: 99%\nat 25% coverage",
    xy=(25, 99),
    xytext=(42, 98),
    fontsize=9,
    arrowprops={"arrowstyle": "->", "color": "#D55E00", "lw": 1.2},
)

plt.tight_layout()
save_plot("coverage_precision")
plt.close()


# --- Plot 2: Reliability diagram ---
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)

bin_edges = np.linspace(0, 1, 11)  # 10 bins
bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

for ax_idx, cohort in enumerate(["A", "B"]):
    ax = axes[ax_idx]
    for label, (path, (mk, ck)) in PATHS.items():
        if cohort not in label:
            continue
        confs, correct = load(path, mk, ck)
        bin_idx = np.digitize(confs, bin_edges) - 1
        bin_idx = np.clip(bin_idx, 0, 9)
        bin_acc = []
        bin_n = []
        for b in range(10):
            mask = bin_idx == b
            if mask.sum() == 0:
                bin_acc.append(np.nan)
            else:
                bin_acc.append(correct[mask].mean())
            bin_n.append(mask.sum())
        bin_acc = np.array(bin_acc)
        bin_n = np.array(bin_n)
        # Plot bins with at least 5 cases
        valid = bin_n >= 5
        ax.plot(
            bin_centers[valid],
            bin_acc[valid] * 100,
            marker="o",
            label=label.replace(f" {cohort}", ""),
            **styles[label],
        )
    # Diagonal
    ax.plot([0, 1], [0, 100], "k--", alpha=0.4, label="Perfectly calibrated")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 105)
    ax.set_yticks(range(0, 101, 20))
    ax.set_xlabel("Predicted confidence (bin midpoint)", fontsize=10)
    ax.set_ylabel("Empirical precision (%)", fontsize=10)
    ax.set_title(f"Cohort {cohort}", fontsize=11)
    ax.grid(alpha=0.3)
    add_legend(ax, loc="upper left", fontsize=8)

fig.suptitle("Reliability Diagram (BMA Beta-Binomial)", fontsize=12, y=1.00)
plt.tight_layout(w_pad=1.6)
save_plot("reliability_diagram")
plt.close()


# --- Plot 3: Confidence histogram (correct vs wrong) ---
fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True, sharey=False)

for ax_idx, (label, (path, (mk, ck))) in enumerate(PATHS.items()):
    ax = axes[ax_idx // 2][ax_idx % 2]
    confs, correct = load(path, mk, ck)
    correct_confs = confs[correct == 1]
    wrong_confs = confs[correct == 0]
    bins = np.linspace(0, 1, 21)
    ax.hist(correct_confs, bins=bins, alpha=0.55, label=f"Correct (n={len(correct_confs)})",
            color="#2ca02c", density=False)
    ax.hist(wrong_confs, bins=bins, alpha=0.55, label=f"Wrong (n={len(wrong_confs)})",
            color="#d62728", density=False)

    # Annotate means
    cm = correct_confs.mean(); wm = wrong_confs.mean()
    ax.axvline(cm, color="#2ca02c", linestyle=":", alpha=0.7)
    ax.axvline(wm, color="#d62728", linestyle=":", alpha=0.7)
    ax.text(0.02, 0.95, f"Correct mean: {cm:.3f}\nWrong mean:   {wm:.3f}\nGap:          {cm-wm:.3f}",
            transform=ax.transAxes, va="top", ha="left", fontsize=9,
            bbox={"boxstyle": "round", "facecolor": "white", "edgecolor": "gray", "alpha": 0.85})
    ax.set_title(label, fontsize=10)
    add_legend(ax, loc="upper right", fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Confidence")
    ax.set_ylabel("Number of cases")
    ax.grid(alpha=0.3)

fig.suptitle("Confidence distribution: correct vs wrong predictions (BMA Beta-Binomial)",
             fontsize=12, y=1.00)
plt.tight_layout()
save_plot("confidence_histograms")
plt.close()

# --- Plot 4: Deferral-rate vs precision (clinician's view) ---
fig, ax = plt.subplots(figsize=(7.2, 5.0), constrained_layout=True)
deferral_curves = {}

for label, (path, (mk, ck)) in PATHS.items():
    x, y = deferral_precision(path, mk, ck)
    deferral_curves[label] = (x, y)
    ax.plot(x, y, label=label, **styles[label])

headline_label = "Multi-agent B"
headline_x = 50.0
headline_y = np.interp(headline_x, *deferral_curves[headline_label])
headline_style = styles[headline_label]
ax.scatter(
    [headline_x],
    [headline_y],
    s=46,
    color=headline_style["color"],
    edgecolor="white",
    linewidth=1.1,
    zorder=5,
)
ax.annotate(
    f"50% deferral\n{headline_y:.0f}% precision",
    xy=(headline_x, headline_y),
    xytext=(16, 96.0),
    fontsize=8.5,
    color="#333333",
    arrowprops={
        "arrowstyle": "->",
        "color": headline_style["color"],
        "lw": 1.1,
    },
    bbox={
        "boxstyle": "round,pad=0.25",
        "facecolor": "white",
        "edgecolor": "#cccccc",
        "alpha": 0.92,
    },
)

ax.set_xlabel("Deferral rate (% sent to clinician)", fontsize=11)
ax.set_ylabel("Precision (%)", fontsize=11)
ax.set_title("Deferral Rate vs Precision\n(Single- and Multi-Agent BMA Beta-Binomial)", fontsize=12)
ax.set_xlim(0, 100)
ax.set_ylim(60, 102)
ax.set_xticks(range(0, 101, 25))
ax.grid(alpha=0.3)
add_legend(ax, loc="lower left", ncol=2, frameon=True, framealpha=0.92, fontsize=9)

save_plot("deferral_precision")
plt.close()


# --- Paper figure: reliability cohorts and deferral side by side ---
fig = plt.figure(figsize=(9.4, 5.35))
gs = fig.add_gridspec(1, 3, width_ratios=[1.0, 1.0, 1.22], wspace=0.25)
ax_rel_a = fig.add_subplot(gs[0, 0])
ax_rel_b = fig.add_subplot(gs[0, 1], sharey=ax_rel_a)
ax_deferral = fig.add_subplot(gs[0, 2])
summary_styles = {
    label: {**style, "lw": style["lw"] + 0.5}
    for label, style in styles.items()
}

# Reliability diagram, preserving the Cohort A/B split.
bin_edges = np.linspace(0, 1, 11)
bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
reliability_axes = [ax_rel_a, ax_rel_b]
for ax_idx, cohort in enumerate(["A", "B"]):
    ax = reliability_axes[ax_idx]
    for label, (path, (mk, ck)) in PATHS.items():
        if cohort not in label:
            continue
        confs, correct = load(path, mk, ck)
        bin_idx = np.digitize(confs, bin_edges) - 1
        bin_idx = np.clip(bin_idx, 0, 9)
        bin_acc = []
        bin_n = []
        for b in range(10):
            mask = bin_idx == b
            bin_acc.append(np.nan if mask.sum() == 0 else correct[mask].mean())
            bin_n.append(mask.sum())
        bin_acc = np.array(bin_acc)
        bin_n = np.array(bin_n)
        valid = bin_n >= 5
        ax.plot(
            bin_centers[valid],
            bin_acc[valid] * 100,
            marker="o",
            markersize=6.8,
            label=label.replace(f" {cohort}", ""),
            **summary_styles[label],
        )
    ax.plot([0, 1], [0, 100], "k--", lw=2.2, alpha=0.4, label="Perfectly calibrated")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 105)
    ax.set_yticks(range(0, 101, 20))
    ax.set_xlabel("Predicted confidence", fontsize=12)
    ax.set_ylabel("Empirical precision (%)", fontsize=12)
    ax.set_title(f"Cohort {cohort}", fontsize=13)
    ax.grid(alpha=0.3)
    ax.tick_params(labelsize=11)
    add_legend(ax, loc="upper left", fontsize=8.4, frameon=True, framealpha=0.92)

# Deferral-precision.
ax = ax_deferral
summary_deferral_curves = {}
for label, (path, (mk, ck)) in PATHS.items():
    x, y = deferral_precision(path, mk, ck)
    summary_deferral_curves[label] = (x, y)
    ax.plot(x, y, label=label, **summary_styles[label])
headline_y = np.interp(50.0, *summary_deferral_curves["Multi-agent B"])
ax.scatter([50.0], [headline_y], s=58, color=styles["Multi-agent B"]["color"],
           edgecolor="white", linewidth=1.0, zorder=5)
ax.annotate(
    f"50% deferral\n{headline_y:.0f}% precision",
    xy=(50.0, headline_y),
    xytext=(16, 96.0),
    fontsize=9.8,
    color="#333333",
    arrowprops={"arrowstyle": "->", "color": styles["Multi-agent B"]["color"], "lw": 1.0},
    bbox={"boxstyle": "round,pad=0.22", "facecolor": "white", "edgecolor": "#cccccc", "alpha": 0.92},
)
ax.set_title("Deferral Rate vs Precision", fontsize=13)
ax.set_xlabel("Deferral rate (%)", fontsize=12)
ax.set_ylabel("Precision (%)", fontsize=12)
ax.set_xlim(0, 100)
ax.set_ylim(60, 102)
ax.set_xticks(range(0, 101, 25))
ax.grid(alpha=0.3)
ax.tick_params(labelsize=11)
add_legend(ax, loc="lower left", fontsize=9.0, frameon=True, framealpha=0.92)

fig.subplots_adjust(left=0.075, right=0.993, bottom=0.205, top=0.87, wspace=0.25)
fig.canvas.draw()
rel_a_pos = ax_rel_a.get_position()
rel_b_pos = ax_rel_b.get_position()
rel_mid_x = (rel_a_pos.x0 + rel_b_pos.x1) / 2
fig.text(rel_mid_x, 0.945, "Reliability Diagram", ha="center", va="center", fontsize=13)

save_plot("calibration_summary")
plt.close()


print("\nAll plots saved to figs/")
