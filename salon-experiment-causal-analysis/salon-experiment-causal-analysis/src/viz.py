"""Shared chart style and the figures used in the notebook and report.

Colour roles are fixed across every chart so a colour always means the same thing:
treated / North = blue, control / South = orange, Central = aqua, reference marks = grey.
(Palette checked for colour-blind separation; aqua sits below 3:1 contrast, so every
chart that uses it also carries a legend and direct labels.)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
from matplotlib import font_manager

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
CRITICAL = "#d03b3b"
ZONE_COLOR = {"North": BLUE, "South": ORANGE, "Central": AQUA}
ARM_COLOR = {"treatment": BLUE, "control": ORANGE}
FIG_DIR = Path(__file__).resolve().parents[1] / "reports" / "figures"


def setup():
    fams = {f.name for f in font_manager.fontManager.ttflist}
    family = next((f for f in ["Inter", "Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"] if f in fams), "sans-serif")
    mpl.rcParams.update({
        "font.family": family, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "semibold",
        "axes.titlelocation": "left", "axes.titlepad": 12, "axes.labelsize": 10, "axes.labelcolor": INK2,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "grid.linestyle": "-",
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
        "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False, "legend.fontsize": 9,
        "text.color": INK, "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
        "lines.linewidth": 2.0, "lines.solid_capstyle": "round", "lines.solid_joinstyle": "round",
        "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
    })


def save(fig, name: str):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / f"{name}.png")


def _subtitle(ax, text):
    ax.text(0, 1.02, text, transform=ax.transAxes, fontsize=9, color=INK2, va="bottom")


def _title(fig, ax, title, subtitle=None):
    ax.set_title(title, pad=24 if subtitle else 12)
    if subtitle:
        _subtitle(ax, subtitle)


def pct_axis(ax, axis="y", decimals=0):
    fmt = mtick.PercentFormatter(1.0, decimals=decimals)
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


# --------------------------------------------------------------------------------------
# Data quality
# --------------------------------------------------------------------------------------
def no_show_reconstruction(regime: pd.DataFrame, bb12: pd.DataFrame):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1, 1.6]})
    x = np.arange(len(regime))
    w = 0.32
    a1.bar(x - w / 2 - 0.01, regime["raw_no_show_rate"], w, color=AXIS, label="As recorded ('No Show' status)")
    a1.bar(x + w / 2 + 0.01, regime["reconstructed_no_show_rate"], w, color=BLUE, label="After cleaning")
    for i, (r, c) in enumerate(zip(regime["raw_no_show_rate"], regime["reconstructed_no_show_rate"])):
        a1.text(i - w / 2 - 0.01, r + 0.003, f"{r:.1%}", ha="center", fontsize=9, color=INK2)
        a1.text(i + w / 2 + 0.01, c + 0.003, f"{c:.1%}", ha="center", fontsize=9, color=INK)
    a1.set_xticks(x, regime.index)
    pct_axis(a1)
    a1.set_ylim(0, 0.16)
    a1.legend(loc="upper left", bbox_to_anchor=(0, -0.1), ncol=1)
    a1.grid(axis="x", visible=False)
    _title(fig, a1, "No-show rate by till type", "Bookings, Jan 2025 - Nov 2026")
    a2.plot(bb12["month"], bb12["raw_no_show_rate"], color=AXIS, label="As recorded")
    a2.plot(bb12["month"], bb12["reconstructed_no_show_rate"], color=BLUE, label="After cleaning")
    a2.axvline(pd.Timestamp("2026-03-01"), color=MUTED, lw=1)
    a2.text(pd.Timestamp("2026-03-08"), 0.155, "Till upgraded\n1 Mar 2026", fontsize=8.5, color=INK2, va="top")
    pct_axis(a2)
    a2.set_ylim(0, 0.17)
    a2.legend(loc="upper left")
    _title(fig, a2, "Outlet BB12 (Ukkadam), monthly", "The recorded rate jumps when the new till starts logging no-shows; the cleaned rate does not")
    fig.tight_layout()
    return fig


def spellings_per_service(smap: pd.DataFrame, top: int = 12):
    t = smap.groupby("canonical_service").size().sort_values(ascending=True).tail(top)
    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.barh(t.index, t.values, color=BLUE, height=0.55)
    for i, v in enumerate(t.values):
        ax.text(v + 1, i, str(v), va="center", fontsize=9, color=INK2)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Distinct spellings in the till exports")
    _title(fig, ax, "Same service, many names", f"{len(smap):,} spellings map to {smap['canonical_service'].nunique()} services; top {top} shown")
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------------------
# Experiment design
# --------------------------------------------------------------------------------------
def power_curve(sens: pd.DataFrame, chosen_mde_pp: float, chosen_days: float, planned_days: int):
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(sens["MDE (pp)"], sens["enrolment days"], color=BLUE, marker="o", ms=6)
    ax.axhline(planned_days, color=MUTED, lw=1)
    ax.text(sens["MDE (pp)"].max(), planned_days + 1.5, f"Planned run: {planned_days} days", ha="right", fontsize=9, color=INK2)
    ax.scatter([chosen_mde_pp], [chosen_days], s=90, color=BLUE, zorder=5, edgecolor="white", linewidth=2)
    ax.annotate(f"MDE {chosen_mde_pp:.1f} pp -> {chosen_days:.1f} days", (chosen_mde_pp, chosen_days),
                xytext=(chosen_mde_pp + 0.25, chosen_days + 12), fontsize=9, color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    ax.set_xlabel("Minimum detectable effect (percentage-point drop in no-show rate)")
    ax.set_ylabel("Enrolment days needed")
    _title(fig, ax, "How long the test must run", "alpha = 0.05 two-sided, power = 80%, design effect and enrolment rate from history")
    fig.tight_layout()
    return fig


def aa_hist(diffs: np.ndarray, se: float, fpr: float):
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.hist(diffs * 100, bins=40, color=BLUE, alpha=0.85, edgecolor="white", linewidth=0.6, density=True)
    xs = np.linspace(diffs.min() * 100, diffs.max() * 100, 200)
    ax.plot(xs, np.exp(-0.5 * (xs / (se * 100)) ** 2) / (se * 100 * np.sqrt(2 * np.pi)), color=INK, lw=1.4)
    ax.set_xlabel("Fake 'effect' on no-show rate (pp) from random splits of historical clients")
    ax.set_yticks([])
    ax.grid(axis="y", visible=False)
    _title(fig, ax, "A/A check: the test does not cry wolf",
           f"{len(diffs):,} random splits; {fpr:.1%} flagged at p<0.05 (expect 5%). Black line = spread the delta-method SE predicts")
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------------------
# A/B results
# --------------------------------------------------------------------------------------
def srm_by_week(t: pd.DataFrame, outlet: str):
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(len(t))
    w = 0.34
    ax.bar(x - w / 2 - 0.01, t["control"], w, color=ORANGE, label="Control")
    ax.bar(x + w / 2 + 0.01, t["treatment"], w, color=BLUE, label="Treatment")
    for i, (c, tr) in enumerate(zip(t["control"], t["treatment"])):
        ax.text(i - w / 2 - 0.01, c + 1, str(int(c)), ha="center", fontsize=9, color=INK2)
        ax.text(i + w / 2 + 0.01, tr + 1, str(int(tr)), ha="center", fontsize=9, color=INK2)
    ax.set_xticks(x, t.index)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Clients enrolled")
    ax.set_ylim(0, max(t["control"].max(), t["treatment"].max()) * 1.25)
    ax.legend(loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.0))
    _title(fig, ax, f"Sample ratio mismatch at {outlet}: no treatment clients logged in week 1",
           "Weekly enrolments by arm; the WhatsApp integration went live late at this outlet")
    fig.tight_layout()
    return fig


NICE = {"pre_bookings": "Bookings, prior 180 days", "pre_no_shows": "No-shows, prior 180 days",
        "pre_visits": "Visits, prior 180 days", "pre_revenue": "Spend, prior 180 days",
        "days_since_last_visit": "Days since last visit", "tenure_days": "Days since sign-up", "is_new": "New client",
        "enrol_booking_lead_days": "Booking lead time (days)", "enrol_evening": "Evening slot", "enrol_weekend": "Weekend slot",
        "gender": "Gender", "age_band": "Age", "enrol_booking_channel": "Channel", "zone": "Zone"}


def love_plot(bt: pd.DataFrame):
    b = bt.copy()
    nm = b["covariate"].map(NICE).fillna(b["covariate"])
    b["label"] = np.where(b["level"] == "", nm, nm + ": " + b["level"])
    b = b.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 6.2))
    ax.axvspan(-0.1, 0.1, color=GRID, alpha=0.6, lw=0)
    ax.axvline(0, color=AXIS, lw=1)
    ax.scatter(b["smd"], b["label"], s=40, color=BLUE, zorder=3, edgecolor="white", linewidth=1.5)
    ax.set_xlim(-0.2, 0.2)
    ax.set_xlabel("Standardised mean difference (treatment - control)")
    ax.grid(axis="y", visible=False)
    _title(fig, ax, "Covariate balance", "Grey band = |SMD| < 0.1, the usual threshold for 'balanced'")
    fig.tight_layout()
    return fig


def effects_forest(rows: pd.DataFrame, title: str, subtitle: str):
    """rows: label, rel, rel_ci_low, rel_ci_high, kind ('primary'/'secondary'/'guardrail'/'monitor')."""
    r = rows.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8.5, 0.55 * len(r) + 1.6))
    ax.axvline(0, color=AXIS, lw=1)
    for i, row in r.iterrows():
        c = BLUE if row["kind"] in ("primary", "secondary") else MUTED
        ax.plot([row["rel_ci_low"], row["rel_ci_high"]], [i, i], color=c, lw=2)
        ax.scatter([row["rel"]], [i], s=55, color=c, zorder=3, edgecolor="white", linewidth=1.5)
        ax.text(max(row["rel_ci_high"], 0) + 0.02, i, f"{row['rel']:+.1%}", va="center", fontsize=9, color=INK)
    ax.set_yticks(range(len(r)), [f"{l}  ({k})" for l, k in zip(r["label"], r["kind"])])
    pct_axis(ax, "x")
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Relative change vs control (95% CI)")
    xmax = max(r["rel_ci_high"].max() + 0.15, 0.2)
    ax.set_xlim(min(r["rel_ci_low"].min() - 0.05, -0.1), xmax)
    _title(fig, ax, title, subtitle)
    fig.tight_layout()
    return fig


def segment_forest(seg: pd.DataFrame, overall: float, title: str, subtitle: str, unit: str = "pp"):
    items = []
    for dim, g in seg.groupby("dimension", sort=False):
        items.append(("h", dim, None))
        items.extend(("r", r["segment"], r) for _, r in g.iterrows())
    n = len(items)
    ys = np.arange(n)[::-1]
    fig, ax = plt.subplots(figsize=(8.5, 0.3 * n + 1.6))
    ax.axvline(0, color=AXIS, lw=1)
    ax.axvline(overall, color=BLUE, lw=1, alpha=0.45)
    ticks, labels = [], []
    for y, (kind, lab, row) in zip(ys, items):
        if kind == "h":
            ax.text(-0.012, y, lab, transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=9,
                    color=INK, fontweight="semibold")
            continue
        c = CRITICAL if row["ci_low"] > 0 else BLUE
        ax.plot([row["ci_low"], row["ci_high"]], [y, y], color=c, lw=2)
        ax.scatter([row["diff"]], [y], s=40, color=c, zorder=3, edgecolor="white", linewidth=1.5)
        ticks.append(y); labels.append(f"{lab}   ")
    ax.set_yticks(ticks, labels, fontsize=9, color=INK2)
    ax.set_ylim(-0.7, n - 0.3)
    if unit == "pp":
        ax.xaxis.set_major_locator(mtick.MultipleLocator(0.02))
        ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v * 100:+.0f} pp"))
    else:
        pct_axis(ax, "x")
    ax.grid(axis="y", visible=False)
    _title(fig, ax, title, subtitle)
    fig.tight_layout()
    return fig


def optout_by_age(t: pd.DataFrame, threshold: float):
    t = t[t["segment"] != "Unknown"]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(len(t))
    colors = [CRITICAL if r > threshold else BLUE for r in t["rate"]]
    ax.bar(x, t["rate"], 0.5, color=colors)
    ax.errorbar(x, t["rate"], yerr=[t["rate"] - t["ci_low"], t["ci_high"] - t["rate"]], fmt="none", ecolor=INK2,
                elinewidth=1, capsize=0)
    ax.axhline(threshold, color=INK2, lw=1)
    ax.text(-0.45, threshold + 0.002, f"Segment guardrail {threshold:.0%}", ha="left", va="bottom", fontsize=9, color=INK2)
    for i, (r, hi) in enumerate(zip(t["rate"], t["ci_high"])):
        ax.text(i, hi + 0.003, f"{r:.1%}", ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_ylim(0, t["ci_high"].max() + 0.015)
    ax.set_xticks(x, t["segment"])
    pct_axis(ax)
    ax.grid(axis="x", visible=False)
    ax.set_xlabel("Age band (treatment arm)")
    _title(fig, ax, "WhatsApp opt-outs by age: the 55+ group breaches the guardrail", "Share of treatment clients who opted out, with 95% Wilson intervals")
    fig.tight_layout()
    return fig


def cuped_chart(rows: pd.DataFrame, vr_rows: pd.DataFrame):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.9), gridspec_kw={"width_ratios": [1.3, 1]})
    r = rows.iloc[::-1].reset_index(drop=True)
    a1.axvline(0, color=AXIS, lw=1)
    for i, row in r.iterrows():
        a1.plot([row["ci_low"], row["ci_high"]], [i, i], color=BLUE, lw=2)
        a1.scatter([row["diff"]], [i], s=55, color=BLUE, zorder=3, edgecolor="white", linewidth=1.5)
        a1.text(row["ci_high"] + 0.001, i, f"width {(row['ci_high'] - row['ci_low']) * 100:.2f} pp", va="center",
                fontsize=9, color=INK2)
    a1.set_yticks(range(len(r)), r["label"])
    a1.axhline(1.5, color=GRID, lw=1)
    a1.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: "0 pp" if abs(v) < 1e-9 else f"{v * 100:+.1f} pp"))
    a1.set_xlim(r["ci_low"].min() - 0.004, 0.014)
    a1.grid(axis="y", visible=False)
    _title(fig, a1, "No-show effect: 95% CI with and without adjustment", "Each pair estimates the same quantity on the same clients")
    v = vr_rows.iloc[::-1].reset_index(drop=True)
    a2.barh(v["metric"], v["variance_reduction"], color=BLUE, height=0.5)
    for i, x in enumerate(v["variance_reduction"]):
        a2.text(x + 0.004, i, f"{x:.1%}", va="center", fontsize=9, color=INK)
    pct_axis(a2, "x")
    a2.set_xlim(0, max(0.2, v["variance_reduction"].max() + 0.05))
    a2.grid(axis="y", visible=False)
    _title(fig, a2, "Variance removed by regression adjustment", "= share fewer clients needed for the same power")
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------------------
# Difference-in-differences
# --------------------------------------------------------------------------------------
def zone_rpv_monthly(m: pd.DataFrame, launch: pd.Timestamp):
    fig, ax = plt.subplots(figsize=(10, 4.3))
    for z in ["North", "South", "Central"]:
        d = m[m["zone"] == z]
        ax.plot(d["month"], d["rpv"], color=ZONE_COLOR[z], label=z + (" (Glow Combos from Jul 2026)" if z == "North" else ""),
                alpha=1.0 if z != "Central" else 0.75)
        ax.text(d["month"].iloc[-1] + pd.Timedelta(days=8), d["rpv"].iloc[-1], z, va="center", fontsize=9, color=INK2)
    ax.axvline(launch, color=MUTED, lw=1)
    ax.text(launch - pd.Timedelta(days=6), ax.get_ylim()[1] * 0.995, "Launch", ha="right", va="top", fontsize=9, color=INK2)
    for s, e, lab in [("2025-07-17", "2025-08-16", "Aadi"), ("2026-07-17", "2026-08-16", "Aadi")]:
        ax.axvspan(pd.Timestamp(s), pd.Timestamp(e), color=GRID, alpha=0.5, lw=0)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"₹{v:,.0f}"))
    ax.set_ylabel("Revenue per visit")
    ax.legend(loc="upper left", ncol=3)
    _title(fig, ax, "Revenue per visit rises every Q3 in every zone", "Monthly revenue per completed visit (service + product); shaded = Aadi month")
    fig.tight_layout()
    return fig


def control_choice(gaps: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(10, 4.0))
    for z, c in [("South", ORANGE), ("Central", AQUA)]:
        d = gaps[gaps["control"] == z]
        ax.plot(d["month"], d["gap"], color=c, label=f"North minus {z}", marker="o", ms=4)
        k = np.polyfit(np.arange(len(d)), d["gap"], 1)
        ax.plot(d["month"], np.polyval(k, np.arange(len(d))), color=c, lw=1, alpha=0.7)
        ax.text(d["month"].iloc[-1] + pd.Timedelta(days=8), d["gap"].iloc[-1], f"vs {z}", va="center", fontsize=9, color=INK2)
    ax.axhline(0, color=AXIS, lw=1)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v * 100:+.0f}%"))
    ax.set_ylabel("Gap in log revenue per visit")
    ax.legend(loc="upper right")
    _title(fig, ax, "Choosing the control region: South tracks North, Central drifts away",
           "Pre-launch months only (Jan 2025 - Jun 2026); thin lines = linear trend")
    fig.tight_layout()
    return fig


def event_study_chart(es: pd.DataFrame, title: str, subtitle: str):
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.axhline(0, color=AXIS, lw=1)
    ax.axvline(pd.Timestamp("2026-06-16"), color=MUTED, lw=1)
    pre, post = es[~es["post"]], es[es["post"]]
    for d, c in [(pre, MUTED), (post, BLUE)]:
        ax.vlines(d["month"], d["ci_low"], d["ci_high"], color=c, lw=2)
        ax.scatter(d["month"], d["coef"], s=45, color=c, zorder=3, edgecolor="white", linewidth=1.5)
    pcts = np.array([-0.15, -0.10, -0.05, 0, 0.05, 0.10, 0.15, 0.20, 0.25])
    lo, hi = es["ci_low"].min(), es["ci_high"].max()
    keep = pcts[(np.log1p(pcts) >= lo - 0.03) & (np.log1p(pcts) <= hi + 0.03)]
    ax.set_yticks(np.log1p(keep), [f"{p * 100:+.0f}%" if p else "0%" for p in keep])
    ax.text(pd.Timestamp("2026-06-08"), hi, "Glow Combos launch", fontsize=9, color=INK2, va="top", ha="right")
    ax.set_ylabel("North vs South, relative to Jun 2026")
    _title(fig, ax, title, subtitle)
    fig.tight_layout()
    return fig


def claim_vs_causal(naive_n: float, naive_s: float, did_pct: float, lo: float, hi: float):
    fig, ax = plt.subplots(figsize=(8, 3.6))
    labels = ["What management saw\n(North, Q3 vs Q2)", "Same change in South\n(no Glow Combos)", "Causal effect\n(difference-in-differences)"]
    vals = [naive_n, naive_s, did_pct]
    cols = [AXIS, ORANGE, BLUE]
    ax.barh(range(3)[::-1], vals, color=cols, height=0.5)
    ax.errorbar([did_pct], [0], xerr=[[did_pct - lo], [hi - did_pct]], fmt="none", ecolor=INK, elinewidth=1.2, capsize=0)
    for i, v in zip(range(3)[::-1], vals):
        ax.text(v + 0.006 if i != 0 else hi + 0.006, i, f"+{v:.1%}", va="center", fontsize=10, color=INK)
    ax.set_yticks(range(3)[::-1], labels)
    pct_axis(ax, "x")
    ax.set_xlim(0, max(vals) * 1.25)
    ax.grid(axis="y", visible=False)
    _title(fig, ax, "Most of the claimed lift was seasonal", "Revenue per visit; causal effect with 95% wild-cluster-bootstrap CI")
    fig.tight_layout()
    return fig


def ri_hist(perms: np.ndarray, obs: float, p: float):
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.hist(perms * 100, bins=50, color=AXIS, edgecolor="white", linewidth=0.5)
    ax.axvline(obs * 100, color=BLUE, lw=2)
    ax.text(obs * 100, ax.get_ylim()[1] * 0.92, f"  Actual North vs South\n  {obs * 100:+.1f} log-pts", color=INK, fontsize=9, va="top")
    ax.set_xlabel("DiD estimate (log points x 100) for every way to pick 8 of the 15 outlets as 'treated'")
    ax.set_yticks([])
    ax.grid(axis="y", visible=False)
    _title(fig, ax, "Randomisation inference", f"{len(perms):,} placebo assignments; exact p = {p:.4f}")
    fig.tight_layout()
    return fig


def did_segments(t: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.9), sharey=True)
    for ax, (outcome, lab) in zip(axes, [("visits", "Visits"), ("rpv", "Revenue per visit")]):
        d = t[(t["outcome"] == outcome) & (t["segment"] != "Occasion & bridal")].iloc[::-1].reset_index(drop=True)
        ax.axvline(0, color=AXIS, lw=1)
        for i, row in d.iterrows():
            c = CRITICAL if row["ci_high"] < 0 else BLUE
            ax.plot([row["ci_low"], row["ci_high"]], [i, i], color=c, lw=2)
            ax.scatter([row["pct"]], [i], s=50, color=c, zorder=3, edgecolor="white", linewidth=1.5)
        ax.set_yticks(range(len(d)), d["segment"])
        pct_axis(ax, "x")
        ax.set_xlim(-0.3, 0.3)
        ax.grid(axis="y", visible=False)
        _title(fig, ax, lab, "Glow Combos effect, North vs South, 95% CI (bridal: too few visits, see table)")
    fig.tight_layout()
    return fig
