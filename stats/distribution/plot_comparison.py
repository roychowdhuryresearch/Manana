"""
Cohort A vs Cohort B comparison plots.
Outputs PDFs to stats/distribution/.
"""

import json
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from scipy.stats import gaussian_kde

plt.rcParams.update({
    'font.family': 'serif',
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.labelsize': 11,
    'axes.titlesize': 13,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
})

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
DATA_PATH = os.path.join(_ROOT, 'classical', 'outputs', 'features_v1.json')
OUT_DIR = _HERE

CA_COLOR = '#1565C0'   # deep blue  — Cohort A
CB_COLOR = '#E64A19'   # deep orange — Cohort B
CA_LIGHT = '#90CAF9'
CB_LIGHT = '#FFAB91'


# ── helpers ──────────────────────────────────────────────────────────────────

def load():
    data = json.load(open(DATA_PATH))
    a = [r for r in data if r['cohort'] == 'csv']
    b = [r for r in data if r['cohort'] == 'pdf']
    return a, b


def drug_rates_all_visits():
    """Pooled drug rates across all visits (more accurate than v1-only)."""
    feat_dir = os.path.join(_ROOT, 'classical', 'outputs')
    drug_keys = [
        'drug_valproate','drug_carbamazepine','drug_levetiracetam',
        'drug_phenobarbital','drug_lamotrigine','drug_clobazam',
        'drug_topiramate','drug_clonazepam','drug_phenytoin','drug_ethosuximide',
    ]
    sums = {'csv': {k: 0 for k in drug_keys}, 'pdf': {k: 0 for k in drug_keys}}
    counts = {'csv': 0, 'pdf': 0}
    for v in [1, 2, 3, 4]:
        path = os.path.join(feat_dir, f'features_v{v}.json')
        if not os.path.exists(path):
            continue
        for r in json.load(open(path)):
            c = r.get('cohort')
            f = r.get('features', {})
            if not f or c not in sums:
                continue
            counts[c] += 1
            for k in drug_keys:
                sums[c][k] += f.get(k, {}).get('value', 0)
    rates = {}
    for c in ('csv', 'pdf'):
        n = counts[c]
        rates[c] = {k: sums[c][k] / n if n else 0 for k in drug_keys}
    return rates


def get(cohort, feat, exclude=None):
    vals = []
    for r in cohort:
        f = r.get('features', {})
        if feat in f:
            v = f[feat].get('value')
            if v is not None and (exclude is None or v not in exclude):
                vals.append(v)
    return np.array(vals, dtype=float)


def pct(arr, val):
    """Percentage of elements equal to val."""
    return 100 * np.sum(arr == val) / len(arr) if len(arr) else 0


def grouped_bars(ax, labels, vals_a, vals_b, title, xlabel='% of patients',
                 legend=True, horizontal=False):
    x = np.arange(len(labels))
    w = 0.36
    if horizontal:
        ax.barh(x + w/2, vals_a, w, color=CA_COLOR, label='Cohort A')
        ax.barh(x - w/2, vals_b, w, color=CB_COLOR, label='Cohort B')
        ax.set_yticks(x)
        ax.set_yticklabels(labels)
        ax.set_xlabel(xlabel)
        ax.invert_yaxis()
    else:
        ax.bar(x - w/2, vals_a, w, color=CA_COLOR, label='Cohort A')
        ax.bar(x + w/2, vals_b, w, color=CB_COLOR, label='Cohort B')
        ax.set_xticks(x)
        ax.set_xticklabels(labels, ha='center')
        ax.set_ylabel(xlabel)
    ax.set_title(title, fontweight='bold', pad=8)
    if legend:
        ax.legend(frameon=False)
    return ax


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 1 — Clinical Overview (6-panel)
# ═══════════════════════════════════════════════════════════════════════════════

def fig_clinical_overview(a, b):
    fig = plt.figure(figsize=(17, 12))
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.48, wspace=0.38)

    # ── 1. Age at visit (KDE) ─────────────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    ages_a = get(a, 'Age_Years')
    ages_b = get(b, 'Age_Years')
    xmax = max(ages_a.max(), ages_b.max())
    xs = np.linspace(0, xmax + 2, 400)
    med_a = np.median(ages_a)
    med_b = np.median(ages_b)
    for arr, col, label in [(ages_a, CA_COLOR, 'Cohort A'), (ages_b, CB_COLOR, 'Cohort B')]:
        kde = gaussian_kde(arr, bw_method=0.25)
        ys = kde(xs)
        ax1.plot(xs, ys, color=col, lw=2, label=label)
        ax1.fill_between(xs, ys, alpha=0.18, color=col)
        ax1.axvline(np.median(arr), color=col, lw=1.2, ls='--', alpha=0.7)
    ax1.set_xlabel('Age at visit (years)')
    ax1.set_ylabel('Density')
    ax1.set_title('Age at First Visit', fontweight='bold', pad=8)
    legend_handles = [
        Line2D([0], [0], color=CA_COLOR, lw=2, label='Cohort A'),
        Line2D([0], [0], color=CB_COLOR, lw=2, label='Cohort B'),
        Line2D([0], [0], color=CA_COLOR, lw=1.2, ls='--', label=f'Median A: {med_a:.0f} y'),
        Line2D([0], [0], color=CB_COLOR, lw=1.2, ls='--', label=f'Median B: {med_b:.0f} y'),
    ]
    ax1.legend(handles=legend_handles, frameon=False, fontsize=8.5)

    # ── 2. Seizure onset age (KDE, exclude -1) ───────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    onset_a = get(a, 'OnsetAgeYears', exclude=[-1])
    onset_b = get(b, 'OnsetAgeYears', exclude=[-1])
    xmax2 = min(max(onset_a.max(), onset_b.max()), 60)
    xs2 = np.linspace(0, xmax2 + 1, 400)
    for arr, col, label in [(onset_a, CA_COLOR, 'Cohort A'), (onset_b, CB_COLOR, 'Cohort B')]:
        arr_clip = arr[arr <= xmax2]
        kde = gaussian_kde(arr_clip, bw_method=0.3)
        ys = kde(xs2)
        ax2.plot(xs2, ys, color=col, lw=2, label=label)
        ax2.fill_between(xs2, ys, alpha=0.18, color=col)
        ax2.axvline(np.median(arr_clip), color=col, lw=1.2, ls='--', alpha=0.7)
    pct_known_a = 100 * len(onset_a) / len(get(a, 'OnsetAgeYears'))
    pct_known_b = 100 * len(onset_b) / len(get(b, 'OnsetAgeYears'))
    ax2.set_xlabel('Onset age (years)')
    ax2.set_ylabel('Density')
    ax2.set_title('Age at Seizure Onset', fontweight='bold', pad=8)
    ax2.legend(frameon=False)

    # ── 3. Gender ─────────────────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[0, 2])
    gen_a = get(a, 'Gender')
    gen_b = get(b, 'Gender')
    labels_g = ['Male', 'Female']
    va = [pct(gen_a, 0), pct(gen_a, 1)]
    vb = [pct(gen_b, 0), pct(gen_b, 1)]
    grouped_bars(ax3, labels_g, va, vb, 'Sex Distribution', legend=True)
    for xi, (va_i, vb_i) in enumerate(zip(va, vb)):
        ax3.text(xi - 0.18, va_i + 0.8, f'{va_i:.0f}%', ha='center', fontsize=9, color=CA_COLOR, fontweight='bold')
        ax3.text(xi + 0.18, vb_i + 0.8, f'{vb_i:.0f}%', ha='center', fontsize=9, color=CB_COLOR, fontweight='bold')
    ax3.set_ylim(0, 85)
    ax3.set_ylabel('% of patients')

    # ── 4. Seizure type ───────────────────────────────────────────────────────
    ax4 = fig.add_subplot(gs[1, 0])
    st_a = get(a, 'SeizureType', exclude=[-1])
    st_b = get(b, 'SeizureType', exclude=[-1])
    labels_st = ['Focal', 'Non-convulsive\ngeneralised', 'Convulsive\n(Tonic-Clonic)']
    va = [pct(st_a, i) for i in range(3)]
    vb = [pct(st_b, i) for i in range(3)]
    grouped_bars(ax4, labels_st, va, vb, 'Seizure Type', legend=False)
    ax4.set_ylabel('% (of those with\ndocumented type)')
    pct_doc_a = 100 * len(st_a) / len(get(a, 'SeizureType'))
    pct_doc_b = 100 * len(st_b) / len(get(b, 'SeizureType'))

    # ── 5. Seizure frequency ──────────────────────────────────────────────────
    ax5 = fig.add_subplot(gs[1, 1])
    sf_a = get(a, 'SeizureFreq', exclude=[-1])
    sf_b = get(b, 'SeizureFreq', exclude=[-1])
    labels_sf = ['Seizure-\nfree', 'Rare\n(<1/mo)', 'Monthly', 'Weekly', 'Daily']
    va = [pct(sf_a, i) for i in range(5)]
    vb = [pct(sf_b, i) for i in range(5)]
    grouped_bars(ax5, labels_sf, va, vb, 'Seizure Burden', legend=False)
    ax5.set_ylabel('% (of those with\ndocumented frequency)')
    pct_doc_a = 100 * len(sf_a) / len(get(a, 'SeizureFreq'))
    pct_doc_b = 100 * len(sf_b) / len(get(b, 'SeizureFreq'))

    # ── 6. Cognitive / developmental burden ───────────────────────────────────
    ax6 = fig.add_subplot(gs[1, 2])
    cp_a = get(a, 'CognitivePriority')
    cp_b = get(b, 'CognitivePriority')
    labels_cp = ['No impairment', 'Mild–Moderate\nimpairment', 'Severe\nimpairment']
    va = [pct(cp_a, i) for i in range(3)]
    vb = [pct(cp_b, i) for i in range(3)]
    grouped_bars(ax6, labels_cp, va, vb, 'Cognitive & Developmental Burden', legend=False)
    ax6.set_ylabel('% of patients')
    for xi, (va_i, vb_i) in enumerate(zip(va, vb)):
        if va_i > 2:
            ax6.text(xi - 0.18, va_i + 0.6, f'{va_i:.0f}%', ha='center', fontsize=8.5,
                     color=CA_COLOR, fontweight='bold')
        if vb_i > 2:
            ax6.text(xi + 0.18, vb_i + 0.6, f'{vb_i:.0f}%', ha='center', fontsize=8.5,
                     color=CB_COLOR, fontweight='bold')

    # shared legend strip
    handles = [
        mpatches.Patch(color=CA_COLOR, label='Cohort A'),
        mpatches.Patch(color=CB_COLOR, label='Cohort B'),
    ]
    fig.legend(handles=handles, loc='lower center', ncol=2, frameon=False,
               fontsize=12, bbox_to_anchor=(0.5, -0.01))

    fig.suptitle('Clinical Profile — Cohort A vs Cohort B', fontsize=16,
                 fontweight='bold', y=1.01)

    out = os.path.join(OUT_DIR, 'clinical_overview.pdf')
    plt.savefig(out, bbox_inches='tight')
    print(f'Saved → {out}')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 2 — Drug Fingerprint at First Visit
# ═══════════════════════════════════════════════════════════════════════════════

def fig_drug_fingerprint(a, b, _pooled=None):
    drugs_raw = [
        ('drug_carbamazepine', 'Carbamazepine'),
        ('drug_valproate',     'Valproate'),
        ('drug_levetiracetam', 'Levetiracetam'),
        ('drug_phenobarbital', 'Phenobarbital'),
        ('drug_lamotrigine',   'Lamotrigine'),
        ('drug_clobazam',      'Clobazam'),
        ('drug_topiramate',    'Topiramate'),
        ('drug_clonazepam',    'Clonazepam'),
        ('drug_phenytoin',     'Phenytoin'),
        ('drug_ethosuximide',  'Ethosuximide'),
    ]
    # sort by avg rate descending
    rows = []
    pooled = drug_rates_all_visits()
    for key, label in drugs_raw:
        ra = 100 * pooled['csv'][key]
        rb = 100 * pooled['pdf'][key]
        rows.append((label, ra, rb))
    rows.sort(key=lambda x: -(x[1] + x[2]))

    labels = [r[0] for r in rows]
    vals_a = [r[1] for r in rows]
    vals_b = [r[2] for r in rows]

    fig, ax = plt.subplots(figsize=(10, 7))
    y = np.arange(len(labels))
    h = 0.34

    bars_a = ax.barh(y + h/2, vals_a, h, color=CA_COLOR, label='Cohort A', zorder=3)
    bars_b = ax.barh(y - h/2, vals_b, h, color=CB_COLOR, label='Cohort B', zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=11)
    ax.invert_yaxis()
    ax.set_xlabel('% of patients already on this drug at first visit', fontsize=11)
    ax.set_title('Prior Medication Profile at First Visit\nCohort A vs Cohort B',
                 fontweight='bold', fontsize=14, pad=12)
    ax.legend(frameon=False, fontsize=11)
    ax.axvline(0, color='#ccc', lw=0.8)
    ax.grid(axis='x', ls='--', alpha=0.4, zorder=0)

    xmax = max(max(vals_a), max(vals_b)) * 1.18
    ax.set_xlim(0, xmax)

    # value labels
    for bar, v in zip(bars_a, vals_a):
        if v > 0.5:
            ax.text(v + xmax * 0.01, bar.get_y() + bar.get_height()/2,
                    f'{v:.1f}%', va='center', fontsize=9, color=CA_COLOR)
    for bar, v in zip(bars_b, vals_b):
        if v > 0.5:
            ax.text(v + xmax * 0.01, bar.get_y() + bar.get_height()/2,
                    f'{v:.1f}%', va='center', fontsize=9, color=CB_COLOR)
    plt.tight_layout()
    out = os.path.join(OUT_DIR, 'drug_fingerprint.pdf')
    plt.savefig(out, bbox_inches='tight')
    print(f'Saved → {out}')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 3 — Stacked cohort profile (diverging / mirror)
# ═══════════════════════════════════════════════════════════════════════════════

def fig_diverging_age(a, b):
    """Back-to-back population pyramid by age group."""
    age_bins = [0, 5, 10, 18, 30, 45, 60, 120]
    bin_labels = ['0–4', '5–9', '10–17', '18–29', '30–44', '45–59', '60+']

    ages_a = get(a, 'Age_Years')
    ages_b = get(b, 'Age_Years')

    counts_a = np.histogram(ages_a, bins=age_bins)[0]
    counts_b = np.histogram(ages_b, bins=age_bins)[0]

    pct_a = 100 * counts_a / counts_a.sum()
    pct_b = 100 * counts_b / counts_b.sum()

    fig, ax = plt.subplots(figsize=(10, 6))
    y = np.arange(len(bin_labels))
    h = 0.5

    ax.barh(y, -pct_a, h, color=CA_COLOR, label='Cohort A', zorder=3)
    ax.barh(y,  pct_b, h, color=CB_COLOR, label='Cohort B', zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(bin_labels, fontsize=11)
    ax.axvline(0, color='black', lw=1.0)
    ax.grid(axis='x', ls='--', alpha=0.35, zorder=0)

    # fix x tick labels to be positive
    xticks = ax.get_xticks()
    ax.set_xticklabels([f'{abs(x):.0f}%' for x in xticks])

    # value labels
    for i, (pa, pb) in enumerate(zip(pct_a, pct_b)):
        if pa > 1:
            ax.text(-pa - 0.4, i, f'{pa:.0f}%', ha='right', va='center', fontsize=9, color=CA_COLOR)
        if pb > 1:
            ax.text(pb + 0.4, i, f'{pb:.0f}%', ha='left', va='center', fontsize=9, color=CB_COLOR)

    ax.set_xlabel('← Cohort A                                         Cohort B →', fontsize=11)
    ax.set_title('Age Distribution — Population Pyramid\nCohort A vs Cohort B',
                 fontweight='bold', fontsize=14, pad=10)
    ax.legend(frameon=False, fontsize=11, loc='upper right')

    plt.tight_layout()
    out = os.path.join(OUT_DIR, 'age_pyramid.pdf')
    plt.savefig(out, bbox_inches='tight')
    print(f'Saved → {out}')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 4 — Radar / spider summary
# ═══════════════════════════════════════════════════════════════════════════════

def fig_radar(a, b):
    """Radar chart comparing normalised clinical indicators."""

    cp_a = get(a, 'CognitivePriority')
    cp_b = get(b, 'CognitivePriority')
    st_a = get(a, 'SeizureType', exclude=[-1])
    st_b = get(b, 'SeizureType', exclude=[-1])
    sf_a = get(a, 'SeizureFreq', exclude=[-1])
    sf_b = get(b, 'SeizureFreq', exclude=[-1])
    gen_a = get(a, 'Gender')
    gen_b = get(b, 'Gender')
    age_a = get(a, 'Age_Years')
    age_b = get(b, 'Age_Years')

    # Each spoke: value normalised 0–1 so both cohorts are comparable visually
    # Spokes:
    # 1. % with severe cognitive impairment (CognitivePriority == 2)
    # 2. % with convulsive seizures (SeizureType == 2)
    # 3. % with daily/weekly seizure burden (SeizureFreq >= 3)
    # 4. % female
    # 5. % paediatric (<18)
    # 6. % on valproate at first visit
    # 7. % on levetiracetam at first visit
    # 8. % with any cognitive concern (CognitivePriority >= 1)

    lev_a = get(a, 'drug_levetiracetam')
    lev_b = get(b, 'drug_levetiracetam')
    vpa_a = get(a, 'drug_valproate')
    vpa_b = get(b, 'drug_valproate')

    spokes = [
        'Severe\ncognitive\nimpairment',
        'Convulsive\nseizure type',
        'High-frequency\nseizures\n(weekly/daily)',
        'Female\npatients',
        'Paediatric\npatients\n(<18 y)',
        'On valproate\nat presentation',
        'On levetiracetam\nat presentation',
        'Any cognitive\nor developmental\nconcern',
    ]

    def v(arr, condition):
        return 100 * np.sum(condition(arr)) / len(arr) if len(arr) else 0

    vals_a = [
        v(cp_a, lambda x: x == 2),
        v(st_a, lambda x: x == 2),
        v(sf_a, lambda x: x >= 3),
        v(gen_a, lambda x: x == 1),
        v(age_a, lambda x: x < 18),
        v(vpa_a, lambda x: x == 1),
        v(lev_a, lambda x: x == 1),
        v(cp_a, lambda x: x >= 1),
    ]
    vals_b = [
        v(cp_b, lambda x: x == 2),
        v(st_b, lambda x: x == 2),
        v(sf_b, lambda x: x >= 3),
        v(gen_b, lambda x: x == 1),
        v(age_b, lambda x: x < 18),
        v(vpa_b, lambda x: x == 1),
        v(lev_b, lambda x: x == 1),
        v(cp_b, lambda x: x >= 1),
    ]

    N = len(spokes)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    va = vals_a + vals_a[:1]
    vb = vals_b + vals_b[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

    ax.plot(angles, va, color=CA_COLOR, lw=2.2, label='Cohort A')
    ax.fill(angles, va, color=CA_COLOR, alpha=0.18)
    ax.plot(angles, vb, color=CB_COLOR, lw=2.2, label='Cohort B')
    ax.fill(angles, vb, color=CB_COLOR, alpha=0.18)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(spokes, fontsize=9.5)
    ax.set_rlabel_position(30)
    ax.yaxis.set_tick_params(labelsize=8)
    ax.set_ylabel('')
    ax.set_title('Cohort Profile — Radar Summary\n(values are % of patients)',
                 fontweight='bold', fontsize=13, pad=22)
    ax.legend(loc='upper right', bbox_to_anchor=(1.28, 1.12), frameon=False, fontsize=11)

    # annotate a few key values
    for i, (angle, va_i, vb_i) in enumerate(zip(angles[:-1], vals_a, vals_b)):
        pass  # kept clean

    plt.tight_layout()
    out = os.path.join(OUT_DIR, 'radar_summary.pdf')
    plt.savefig(out, bbox_inches='tight')
    print(f'Saved → {out}')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 5 — All features as probability distributions (single unified figure)
# ═══════════════════════════════════════════════════════════════════════════════

def _pmf(arr, bins):
    """Normalised histogram (PMF) over given bin edges."""
    counts, _ = np.histogram(arr, bins=bins)
    total = counts.sum()
    return counts / total if total > 0 else counts.astype(float)


def fig_all_distributions(a, b, _pooled=None):
    fig = plt.figure(figsize=(18, 10))
    gs = gridspec.GridSpec(2, 4, figure=fig, hspace=0.52, wspace=0.38)

    alpha_fill = 0.22
    lw = 2.0

    # ── helper: draw a step-histogram as a smooth PMF bar ────────────────────
    def pmf_bars(ax, bin_labels, pmf_a, pmf_b, title, ylabel='Probability'):
        x = np.arange(len(bin_labels))
        w = 0.36
        ax.bar(x - w/2, pmf_a, w, color=CA_COLOR, alpha=0.85, label='Cohort A')
        ax.bar(x + w/2, pmf_b, w, color=CB_COLOR, alpha=0.85, label='Cohort B')
        ax.set_xticks(x)
        ax.set_xticklabels(bin_labels, ha='right', rotation=35, fontsize=8.5)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(title, fontweight='bold', pad=7, fontsize=12)
        ax.set_ylim(0, max(pmf_a.max(), pmf_b.max()) * 1.25)

    # ── 1. Age (continuous → binned PMF) ─────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    age_bins = [0, 5, 10, 18, 30, 45, 60, 200]
    age_labels = ['0–4', '5–9', '10–17', '18–29', '30–44', '45–59', '60+']
    ages_a = get(a, 'Age_Years')
    ages_b = get(b, 'Age_Years')
    pmf_bars(ax1, age_labels, _pmf(ages_a, age_bins), _pmf(ages_b, age_bins), 'Age at Visit')

    # ── 2. Seizure onset age ──────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    onset_bins = [0, 1, 5, 10, 18, 30, 60, 200]
    onset_labels = ['<1', '1–4', '5–9', '10–17', '18–29', '30–59', '60+']
    onset_a = get(a, 'OnsetAgeYears', exclude=[-1])
    onset_b = get(b, 'OnsetAgeYears', exclude=[-1])
    pmf_bars(ax2, onset_labels, _pmf(onset_a, onset_bins), _pmf(onset_b, onset_bins), 'Seizure Onset Age')

    # ── 3. Gender ─────────────────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[0, 2])
    gen_a = get(a, 'Gender')
    gen_b = get(b, 'Gender')
    pmf_bars(ax3, ['Male', 'Female'],
             _pmf(gen_a, [-0.5, 0.5, 1.5]), _pmf(gen_b, [-0.5, 0.5, 1.5]), 'Sex')

    # ── 4. Cognitive burden ───────────────────────────────────────────────────
    ax4 = fig.add_subplot(gs[0, 3])
    cp_a = get(a, 'CognitivePriority')
    cp_b = get(b, 'CognitivePriority')
    pmf_bars(ax4, ['None', 'Mild–\nModerate', 'Severe'],
             _pmf(cp_a, [-0.5, 0.5, 1.5, 2.5]), _pmf(cp_b, [-0.5, 0.5, 1.5, 2.5]),
             'Cognitive Burden')

    # ── 5. Seizure type ───────────────────────────────────────────────────────
    ax5 = fig.add_subplot(gs[1, 0])
    st_a = get(a, 'SeizureType', exclude=[-1])
    st_b = get(b, 'SeizureType', exclude=[-1])
    pmf_bars(ax5, ['Focal', 'Non-\nconvulsive', 'Convulsive\n(GTC)'],
             _pmf(st_a, [-0.5, 0.5, 1.5, 2.5]), _pmf(st_b, [-0.5, 0.5, 1.5, 2.5]),
             'Seizure Type')

    # ── 6. Seizure burden ─────────────────────────────────────────────────────
    ax6 = fig.add_subplot(gs[1, 1])
    sf_a = get(a, 'SeizureFreq', exclude=[-1])
    sf_b = get(b, 'SeizureFreq', exclude=[-1])
    pmf_bars(ax6, ['Seizure-\nfree', 'Rare\n<1/mo', 'Monthly', 'Weekly', 'Daily'],
             _pmf(sf_a, [-0.5, 0.5, 1.5, 2.5, 3.5, 4.5]),
             _pmf(sf_b, [-0.5, 0.5, 1.5, 2.5, 3.5, 4.5]),
             'Seizure Burden')

    # ── 7. Top drugs ──────────────────────────────────────────────────────────
    ax7 = fig.add_subplot(gs[1, 2])
    drug_keys = ['drug_valproate', 'drug_carbamazepine', 'drug_levetiracetam',
                 'drug_phenobarbital', 'drug_lamotrigine']
    drug_names = ['VPA', 'CBZ', 'LEV', 'PHB', 'LTG']
    pa = np.array([_pooled['csv'][k] for k in drug_keys])
    pb = np.array([_pooled['pdf'][k] for k in drug_keys])
    pmf_bars(ax7, drug_names, pa, pb, 'Current Medications\n(top 5)', ylabel='Proportion on drug')

    # ── 8. Remaining drugs ────────────────────────────────────────────────────
    ax8 = fig.add_subplot(gs[1, 3])
    drug_keys2 = ['drug_clobazam', 'drug_topiramate', 'drug_clonazepam',
                  'drug_phenytoin', 'drug_ethosuximide']
    drug_names2 = ['CLB', 'TPM', 'CZP', 'PHT', 'ESM']
    pa2 = np.array([_pooled['csv'][k] for k in drug_keys2])
    pb2 = np.array([_pooled['pdf'][k] for k in drug_keys2])
    pmf_bars(ax8, drug_names2, pa2, pb2, 'Current Medications\n(remaining)', ylabel='Proportion on drug')

    # shared legend
    handles = [
        mpatches.Patch(color=CA_COLOR, alpha=0.85, label='Cohort A'),
        mpatches.Patch(color=CB_COLOR, alpha=0.85, label='Cohort B'),
    ]
    fig.legend(handles=handles, loc='lower center', ncol=2, frameon=False,
               fontsize=12, bbox_to_anchor=(0.5, -0.02))

    fig.suptitle('Feature Distributions — Cohort A vs Cohort B',
                 fontsize=16, fontweight='bold', y=1.01)

    out = os.path.join(OUT_DIR, 'all_distributions.pdf')
    plt.savefig(out, bbox_inches='tight')
    print(f'Saved → {out}')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 6 — Flattened single-axis distribution
# ═══════════════════════════════════════════════════════════════════════════════

def fig_flattened(a, b, _pooled=None):
    """All feature PMFs concatenated onto one x-axis, no dividers."""

    age_bins   = [0, 5, 10, 18, 30, 45, 60, 200]
    onset_bins = [0, 1, 5, 10, 18, 30, 60, 200]

    groups = [
        ('Age at Visit',
         ['0–4','5–9','10–17','18–29','30–44','45–59','60+'],
         _pmf(get(a,'Age_Years'), age_bins),
         _pmf(get(b,'Age_Years'), age_bins)),
        ('Onset Age',
         ['<1','1–4','5–9','10–17','18–29','30–59','60+'],
         _pmf(get(a,'OnsetAgeYears',exclude=[-1]), onset_bins),
         _pmf(get(b,'OnsetAgeYears',exclude=[-1]), onset_bins)),
        ('Sex',
         ['Male','Female'],
         _pmf(get(a,'Gender'),[-0.5,0.5,1.5]),
         _pmf(get(b,'Gender'),[-0.5,0.5,1.5])),
        ('Cognitive Burden',
         ['None','Mild–Mod','Severe'],
         _pmf(get(a,'CognitivePriority'),[-0.5,0.5,1.5,2.5]),
         _pmf(get(b,'CognitivePriority'),[-0.5,0.5,1.5,2.5])),
        ('Seizure Type',
         ['Focal','Non-conv','Convulsive'],
         _pmf(get(a,'SeizureType',exclude=[-1]),[-0.5,0.5,1.5,2.5]),
         _pmf(get(b,'SeizureType',exclude=[-1]),[-0.5,0.5,1.5,2.5])),
        ('Seizure Burden',
         ['Sz-free','<1/mo','Monthly','Weekly','Daily'],
         _pmf(get(a,'SeizureFreq',exclude=[-1]),[-0.5,0.5,1.5,2.5,3.5,4.5]),
         _pmf(get(b,'SeizureFreq',exclude=[-1]),[-0.5,0.5,1.5,2.5,3.5,4.5])),
        ('Medications (top 5)',
         ['VPA','CBZ','LEV','PHB','LTG'],
         np.array([_pooled['csv'][k] for k in ['drug_valproate','drug_carbamazepine',
                   'drug_levetiracetam','drug_phenobarbital','drug_lamotrigine']]),
         np.array([_pooled['pdf'][k] for k in ['drug_valproate','drug_carbamazepine',
                   'drug_levetiracetam','drug_phenobarbital','drug_lamotrigine']])),
        ('Medications (rest)',
         ['CLB','TPM','CZP','PHT','ESM'],
         np.array([_pooled['csv'][k] for k in ['drug_clobazam','drug_topiramate',
                   'drug_clonazepam','drug_phenytoin','drug_ethosuximide']]),
         np.array([_pooled['pdf'][k] for k in ['drug_clobazam','drug_topiramate',
                   'drug_clonazepam','drug_phenytoin','drug_ethosuximide']])),
    ]

    # flatten: all bins in sequence, uniform bar width, no gaps
    BAR_W = 0.35
    all_pa, all_pb, all_labels, all_xs = [], [], [], []
    group_mid_xs, group_names = [], []
    x = 0
    for gname, blabels, pmf_a, pmf_b in groups:
        start_x = x
        for lbl, va, vb in zip(blabels, pmf_a, pmf_b):
            all_xs.append(x)
            all_pa.append(va)
            all_pb.append(vb)
            all_labels.append(lbl)
            x += 1
        group_mid_xs.append((start_x + x - 1) / 2)
        group_names.append(gname)

    fig, ax = plt.subplots(figsize=(20, 5))
    xs = np.array(all_xs, dtype=float)
    ax.bar(xs - BAR_W/2, all_pa, BAR_W, color=CA_COLOR, alpha=0.88, zorder=3)
    ax.bar(xs + BAR_W/2, all_pb, BAR_W, color=CB_COLOR, alpha=0.88, zorder=3)

    ax.set_xticks(xs)
    ax.set_xticklabels(all_labels, fontsize=7, rotation=45, ha='right')
    ax.set_ylabel('Normalised probability', fontsize=11)
    ax.set_xlim(xs[0] - 0.8, xs[-1] + 0.8)
    ax.set_ylim(0, None)
    ax.spines['bottom'].set_visible(False)
    ax.tick_params(axis='x', length=0, pad=1)
    ax.grid(axis='y', ls='--', alpha=0.3, zorder=0)

    # group name labels just above the x-axis ticks, at the midpoint of each group
    ymax = ax.get_ylim()[1]
    for mid, gname in zip(group_mid_xs, group_names):
        ax.text(mid, ymax * 1.02, gname, ha='center', va='bottom',
                fontsize=8, color='#444', fontstyle='italic')

    handles = [
        mpatches.Patch(color=CA_COLOR, alpha=0.88, label='Cohort A'),
        mpatches.Patch(color=CB_COLOR, alpha=0.88, label='Cohort B'),
    ]
    ax.legend(handles=handles, frameon=False, fontsize=11, loc='upper right')
    ax.set_title('All Feature Distributions — Cohort A vs Cohort B',
                 fontweight='bold', fontsize=14, pad=12)

    plt.tight_layout()
    out = os.path.join(OUT_DIR, 'flattened_distributions.pdf')
    plt.savefig(out, bbox_inches='tight')
    print(f'Saved → {out}')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 7 — KL Divergence summary
# ═══════════════════════════════════════════════════════════════════════════════

def _kl_sym(p, q, eps=1e-9):
    """Symmetric KL divergence: (KL(P||Q) + KL(Q||P)) / 2."""
    p = np.array(p, dtype=float) + eps
    q = np.array(q, dtype=float) + eps
    p /= p.sum()
    q /= q.sum()
    return 0.5 * (np.sum(p * np.log(p / q)) + np.sum(q * np.log(q / p)))


def fig_kl_divergence(a, b):
    age_bins   = [0, 5, 10, 18, 30, 45, 60, 200]
    onset_bins = [0, 1, 5, 10, 18, 30, 60, 200]

    features = [
        ('Age at Visit',          _pmf(get(a,'Age_Years'), age_bins),
                                  _pmf(get(b,'Age_Years'), age_bins)),
        ('Seizure Onset Age',     _pmf(get(a,'OnsetAgeYears',exclude=[-1]), onset_bins),
                                  _pmf(get(b,'OnsetAgeYears',exclude=[-1]), onset_bins)),
        ('Seizure Burden',        _pmf(get(a,'SeizureFreq',exclude=[-1]),[-0.5,0.5,1.5,2.5,3.5,4.5]),
                                  _pmf(get(b,'SeizureFreq',exclude=[-1]),[-0.5,0.5,1.5,2.5,3.5,4.5])),
        ('Seizure Type',          _pmf(get(a,'SeizureType',exclude=[-1]),[-0.5,0.5,1.5,2.5]),
                                  _pmf(get(b,'SeizureType',exclude=[-1]),[-0.5,0.5,1.5,2.5])),
        ('Cognitive Burden',      _pmf(get(a,'CognitivePriority'),[-0.5,0.5,1.5,2.5]),
                                  _pmf(get(b,'CognitivePriority'),[-0.5,0.5,1.5,2.5])),
        ('Sex',                   _pmf(get(a,'Gender'),[-0.5,0.5,1.5]),
                                  _pmf(get(b,'Gender'),[-0.5,0.5,1.5])),
        ('Valproate use',         np.array([1-get(a,'drug_valproate').mean(), get(a,'drug_valproate').mean()]),
                                  np.array([1-get(b,'drug_valproate').mean(), get(b,'drug_valproate').mean()])),
        ('Levetiracetam use',     np.array([1-get(a,'drug_levetiracetam').mean(), get(a,'drug_levetiracetam').mean()]),
                                  np.array([1-get(b,'drug_levetiracetam').mean(), get(b,'drug_levetiracetam').mean()])),
        ('Carbamazepine use',     np.array([1-get(a,'drug_carbamazepine').mean(), get(a,'drug_carbamazepine').mean()]),
                                  np.array([1-get(b,'drug_carbamazepine').mean(), get(b,'drug_carbamazepine').mean()])),
        ('Lamotrigine use',       np.array([1-get(a,'drug_lamotrigine').mean(), get(a,'drug_lamotrigine').mean()]),
                                  np.array([1-get(b,'drug_lamotrigine').mean(), get(b,'drug_lamotrigine').mean()])),
        ('Phenobarbital use',     np.array([1-get(a,'drug_phenobarbital').mean(), get(a,'drug_phenobarbital').mean()]),
                                  np.array([1-get(b,'drug_phenobarbital').mean(), get(b,'drug_phenobarbital').mean()])),
    ]

    kl_vals = [(_kl_sym(pa, pb), name) for name, pa, pb in features]
    kl_vals.sort(key=lambda x: x[0])

    names = [x[1] for x in kl_vals]
    kls   = [x[0] for x in kl_vals]

    # color by magnitude
    max_kl = max(kls)
    colors = [plt.cm.RdYlBu_r(v / max_kl * 0.85 + 0.05) for v in kls]

    fig, ax = plt.subplots(figsize=(10, 7))
    bars = ax.barh(names, kls, color=colors, edgecolor='white', linewidth=0.5, zorder=3)
    ax.set_xlabel('Symmetric KL Divergence  (higher → more different)', fontsize=11)
    ax.set_title(
        'How Different Are The Two Cohorts?\nKL Divergence Per Feature  —  Cohort A vs Cohort B',
        fontweight='bold', fontsize=14, pad=12
    )
    ax.grid(axis='x', ls='--', alpha=0.4, zorder=0)
    ax.axvline(0, color='#aaa', lw=0.8)

    for bar, v in zip(bars, kls):
        ax.text(v + max_kl * 0.01, bar.get_y() + bar.get_height()/2,
                f'{v:.3f}', va='center', fontsize=9.5)

    ax.text(0.98, 0.03,
            'KL divergence measures how much one\nprobability distribution differs from another.\n'
            'Values near 0 = near-identical distributions.',
            transform=ax.transAxes, ha='right', va='bottom',
            fontsize=8.5, color='#666',
            bbox=dict(boxstyle='round,pad=0.4', fc='#f8f8f8', ec='#ddd', lw=0.8))

    plt.tight_layout()
    out = os.path.join(OUT_DIR, 'kl_divergence.pdf')
    plt.savefig(out, bbox_inches='tight')
    print(f'Saved → {out}')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 8 — Co-prescription heatmap
# ═══════════════════════════════════════════════════════════════════════════════

DRUG_KEYS  = ['drug_valproate','drug_carbamazepine','drug_levetiracetam',
              'drug_phenobarbital','drug_lamotrigine','drug_clobazam',
              'drug_topiramate','drug_clonazepam','drug_phenytoin','drug_ethosuximide']
DRUG_SHORT = ['VPA','CBZ','LEV','PHB','LTG','CLB','TPM','CZP','PHT','ESM']

def _coprescription_matrix(cohort):
    n = len(DRUG_KEYS)
    mat = np.zeros((n, n))
    total = 0
    for r in cohort:
        f = r.get('features', {})
        if not f:
            continue
        vals = np.array([f.get(k, {}).get('value', 0) for k in DRUG_KEYS], dtype=float)
        mat += np.outer(vals, vals)
        total += 1
    return 100 * mat / total if total else mat

def fig_coprescription(a, b):
    mat_a = _coprescription_matrix(a)
    mat_b = _coprescription_matrix(b)
    vmax = max(mat_a.max(), mat_b.max())

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, mat, title in [(axes[0], mat_a, 'Cohort A'), (axes[1], mat_b, 'Cohort B')]:
        im = ax.imshow(mat, cmap='Blues', vmin=0, vmax=vmax, aspect='auto')
        ax.set_xticks(range(len(DRUG_SHORT)))
        ax.set_yticks(range(len(DRUG_SHORT)))
        ax.set_xticklabels(DRUG_SHORT, fontsize=9, rotation=45, ha='right')
        ax.set_yticklabels(DRUG_SHORT, fontsize=9)
        ax.set_title(title, fontweight='bold', fontsize=13, pad=8)
        for i in range(len(DRUG_SHORT)):
            for j in range(len(DRUG_SHORT)):
                v = mat[i, j]
                if v > 0.3:
                    ax.text(j, i, f'{v:.1f}', ha='center', va='center',
                            fontsize=7, color='white' if v > vmax * 0.55 else '#222')
        plt.colorbar(im, ax=ax, shrink=0.82, label='% of patients')

    fig.suptitle('Drug Co-prescription at First Visit — Cohort A vs Cohort B\n'
                 '(diagonal = single-drug rate, off-diagonal = both prescribed simultaneously)',
                 fontweight='bold', fontsize=13, y=1.01)
    plt.tight_layout()
    out = os.path.join(OUT_DIR, 'coprescription_heatmap.pdf')
    plt.savefig(out, bbox_inches='tight')
    print(f'Saved → {out}')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 9 — Age × Cognitive burden 2D heatmap
# ═══════════════════════════════════════════════════════════════════════════════

def fig_age_cognitive(a, b):
    age_bins   = [0, 5, 10, 18, 30, 45, 60, 200]
    age_labels = ['0–4','5–9','10–17','18–29','30–44','45–59','60+']
    cog_labels = ['No impairment','Mild–Moderate','Severe']

    def build_mat(cohort):
        mat = np.zeros((3, len(age_labels)))
        total = 0
        for r in cohort:
            f = r.get('features', {})
            if not f:
                continue
            age = f.get('Age_Years', {}).get('value')
            cog = f.get('CognitivePriority', {}).get('value')
            if age is None or cog is None:
                continue
            ab = np.digitize(age, age_bins) - 1
            ab = min(ab, len(age_labels) - 1)
            mat[int(cog), ab] += 1
            total += 1
        return 100 * mat / total if total else mat

    mat_a = build_mat(a)
    mat_b = build_mat(b)
    vmax = max(mat_a.max(), mat_b.max())

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, mat, title in [(axes[0], mat_a, 'Cohort A'), (axes[1], mat_b, 'Cohort B')]:
        im = ax.imshow(mat, cmap='YlOrRd', vmin=0, vmax=vmax, aspect='auto')
        ax.set_xticks(range(len(age_labels)))
        ax.set_yticks(range(3))
        ax.set_xticklabels(age_labels, fontsize=9, rotation=40, ha='right')
        ax.set_yticklabels(cog_labels, fontsize=9)
        ax.set_xlabel('Age at visit', fontsize=10)
        ax.set_title(title, fontweight='bold', fontsize=13, pad=8)
        for i in range(3):
            for j in range(len(age_labels)):
                v = mat[i, j]
                if v > 0.3:
                    ax.text(j, i, f'{v:.1f}%', ha='center', va='center',
                            fontsize=8, color='white' if v > vmax * 0.6 else '#222')
        plt.colorbar(im, ax=ax, shrink=0.82, label='% of all patients')

    fig.suptitle('Age × Cognitive Burden — Cohort A vs Cohort B\n'
                 '(cell = % of all patients in that age–impairment combination)',
                 fontweight='bold', fontsize=13, y=1.01)
    plt.tight_layout()
    out = os.path.join(OUT_DIR, 'age_cognitive_heatmap.pdf')
    plt.savefig(out, bbox_inches='tight')
    print(f'Saved → {out}')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 10 — Polytherapy rate by visit
# ═══════════════════════════════════════════════════════════════════════════════

def fig_polytherapy(a_raw, b_raw):
    """Load all visits from HF and show mono/dual/triple+ prescription rates."""
    import os as _os
    _root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    feat_dir = _os.path.join(_root, 'classical', 'outputs')

    visits = [1, 2, 3, 4]
    results = {'A': {}, 'B': {}}

    for v in visits:
        path = _os.path.join(feat_dir, f'features_v{v}.json')
        if not _os.path.exists(path):
            continue
        data = json.load(open(path))
        for cohort_key, cohort_id in [('A','csv'),('B','pdf')]:
            rows = [r for r in data if r['cohort'] == cohort_id]
            counts = []
            for r in rows:
                f = r.get('features', {})
                if not f:
                    continue
                n_drugs = sum(f.get(k, {}).get('value', 0) for k in DRUG_KEYS)
                counts.append(int(n_drugs))
            if counts:
                counts = np.array(counts)
                total = len(counts)
                results[cohort_key][v] = {
                    'none':   100 * np.sum(counts == 0) / total,
                    'mono':   100 * np.sum(counts == 1) / total,
                    'dual':   100 * np.sum(counts == 2) / total,
                    'triple': 100 * np.sum(counts >= 3) / total,
                }

    cats   = ['none','mono','dual','triple']
    clabels = ['None','Monotherapy','Dual','Triple+']
    cat_colors = ['#ccc','#42A5F5','#1565C0','#0D2F6E']

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, (cohort_key, title) in zip(axes, [('A','Cohort A'),('B','Cohort B')]):
        vs = sorted(results[cohort_key].keys())
        bottoms = np.zeros(len(vs))
        for cat, clabel, col in zip(cats, clabels, cat_colors):
            vals = np.array([results[cohort_key][v][cat] for v in vs])
            ax.bar(vs, vals, bottom=bottoms, color=col, label=clabel, width=0.5, zorder=3)
            for xi, (vi, va, bot) in enumerate(zip(vs, vals, bottoms)):
                if va > 3:
                    ax.text(vi, bot + va/2, f'{va:.0f}%', ha='center', va='center',
                            fontsize=8.5, color='white' if col != '#ccc' else '#555',
                            fontweight='bold')
            bottoms += vals
        ax.set_xticks(vs)
        ax.set_xticklabels([f'Visit {v}' for v in vs], fontsize=10)
        ax.set_title(title, fontweight='bold', fontsize=13, pad=8)
        ax.set_ylabel('% of patients', fontsize=10)
        ax.set_ylim(0, 105)
        ax.grid(axis='y', ls='--', alpha=0.3, zorder=0)
        ax.legend(frameon=False, fontsize=9, loc='upper left')

    fig.suptitle('Polytherapy Profile by Visit — Cohort A vs Cohort B\n'
                 '(drugs patient was already on at time of visit)',
                 fontweight='bold', fontsize=13, y=1.01)
    plt.tight_layout()
    out = _os.path.join(OUT_DIR, 'polytherapy_by_visit.pdf')
    plt.savefig(out, bbox_inches='tight')
    print(f'Saved → {out}')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 11 — Seizure type × drug usage
# ═══════════════════════════════════════════════════════════════════════════════

def fig_seizuretype_drug(a, b):
    sz_labels = ['Focal','Non-convulsive','Convulsive (GTC)']
    show_drugs = ['drug_valproate','drug_carbamazepine','drug_levetiracetam',
                  'drug_phenobarbital','drug_lamotrigine','drug_clobazam','drug_topiramate']
    show_names = ['VPA','CBZ','LEV','PHB','LTG','CLB','TPM']
    colors_d   = ['#1565C0','#E64A19','#2E7D32','#6A1B9A','#F9A825','#00838F','#AD1457']

    fig, axes = plt.subplots(1, 2, figsize=(15, 5), sharey=False)

    for ax, cohort, title in [(axes[0], a, 'Cohort A'), (axes[1], b, 'Cohort B')]:
        # group patients by seizure type (exclude -1)
        groups = {0: [], 1: [], 2: []}
        for r in cohort:
            f = r.get('features', {})
            if not f:
                continue
            st = f.get('SeizureType', {}).get('value')
            if st is None or st == -1:
                continue
            groups[int(st)].append(f)

        x = np.arange(len(sz_labels))
        w = 0.10
        for di, (dkey, dname, dcol) in enumerate(zip(show_drugs, show_names, colors_d)):
            vals = []
            for sz in range(3):
                fs = groups[sz]
                if fs:
                    rate = 100 * np.mean([f.get(dkey, {}).get('value', 0) for f in fs])
                else:
                    rate = 0.0
                vals.append(rate)
            offset = (di - len(show_drugs)/2 + 0.5) * w
            ax.bar(x + offset, vals, w, color=dcol, label=dname, alpha=0.88, zorder=3)

        ax.set_xticks(x)
        ax.set_xticklabels(sz_labels, fontsize=10)
        ax.set_ylabel('% of patients on drug', fontsize=10)
        ax.set_title(title, fontweight='bold', fontsize=13, pad=8)
        ax.legend(frameon=False, fontsize=8.5, ncol=2, loc='upper right')
        ax.grid(axis='y', ls='--', alpha=0.3, zorder=0)
        ax.set_ylim(0, None)

    fig.suptitle('Drug Usage by Seizure Type — Cohort A vs Cohort B\n'
                 '(% of patients with that seizure type already on each drug at visit)',
                 fontweight='bold', fontsize=13, y=1.01)
    plt.tight_layout()
    out = os.path.join(OUT_DIR, 'seizuretype_drug.pdf')
    plt.savefig(out, bbox_inches='tight')
    print(f'Saved → {out}')
    plt.close()


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    a, b = load()
    pooled = drug_rates_all_visits()
    print(f'Loaded: Cohort A n={len(a)}, Cohort B n={len(b)}')
    fig_clinical_overview(a, b)
    fig_drug_fingerprint(a, b, _pooled=pooled)
    fig_diverging_age(a, b)
    fig_radar(a, b)
    fig_all_distributions(a, b, _pooled=pooled)
    fig_flattened(a, b, _pooled=pooled)
    fig_kl_divergence(a, b)
    fig_coprescription(a, b)
    fig_age_cognitive(a, b)
    fig_polytherapy(a, b)
    fig_seizuretype_drug(a, b)
    print('\nAll done.')
