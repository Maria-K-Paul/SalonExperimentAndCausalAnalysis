"""Analysis of the Smart Reminders A/B test.

Conventions
-----------
* Unit of randomisation = client, so every estimator treats clients as the
  independent units (booking-level ratios use the delta method or a client
  bootstrap, never a naive booking-level test).
* Effects are reported as treatment minus control.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.multitest import multipletests

from power_analysis import ratio_delta_var

Z975 = stats.norm.ppf(0.975)


# --------------------------------------------------------------------------------------
# Preparing the experiment table
# --------------------------------------------------------------------------------------
def prepare_experiment(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Normalise labels, parse types and drop clients who appear in both arms."""
    e = raw.copy()
    e["variant"] = e["variant"].str.strip().str.lower()
    labels_fixed = int((raw["variant"] != e["variant"]).sum())
    both = e.groupby("client_id")["variant"].nunique()
    crossover = set(both[both > 1].index)
    log = {"rows_in_file": len(e), "variant_labels_fixed": labels_fixed,
           "crossover_clients": len(crossover), "crossover_rows": int(e["client_id"].isin(crossover).sum())}
    e = e[~e["client_id"].isin(crossover)].drop_duplicates("client_id").copy()
    for c in ["reminder_delivered", "opted_out"]:
        e[c] = e[c].astype(str).str.lower().eq("true")
    for c in ["enrol_booking_lead_days", "bookings_28d", "no_shows_28d", "cancellations_28d",
              "completed_visits_28d", "returned_45d"]:
        e[c] = pd.to_numeric(e[c]).astype(int)
    e["revenue_28d"] = pd.to_numeric(e["revenue_28d"])
    e["enrolled_on"] = pd.to_datetime(e["enrolled_on"])
    e["treat"] = e["variant"].eq("treatment").astype(int)
    log["clients_analysed"] = len(e)
    return e, log


def add_pre_period(e: pd.DataFrame, appts: pd.DataFrame, visits: pd.DataFrame, clients: pd.DataFrame,
                   days: int = 180) -> pd.DataFrame:
    """Join client attributes and 180-day pre-enrolment behaviour from the cleaned history."""
    e = e.merge(clients[["client_id", "gender", "age_band", "signup_date"]], on="client_id", how="left")
    known = appts[appts["client_known"]][["client_id", "date", "is_walk_in", "is_no_show"]]
    m = known.merge(e[["client_id", "enrolled_on"]], on="client_id")
    m = m[(m["date"] < m["enrolled_on"]) & (m["date"] >= m["enrolled_on"] - pd.Timedelta(days=days))]
    bk = m[~m["is_walk_in"]].groupby("client_id").agg(pre_bookings=("date", "size"), pre_no_shows=("is_no_show", "sum"))
    v = visits[visits["client_known"]][["client_id", "date", "revenue"]].merge(e[["client_id", "enrolled_on"]],
                                                                              on="client_id")
    v = v[(v["date"] < v["enrolled_on"]) & (v["date"] >= v["enrolled_on"] - pd.Timedelta(days=days))]
    vs = v.groupby("client_id").agg(pre_visits=("date", "size"), pre_revenue=("revenue", "sum"),
                                    last_visit=("date", "max"))
    e = e.join(bk, on="client_id").join(vs, on="client_id")
    for c in ["pre_bookings", "pre_no_shows", "pre_visits", "pre_revenue"]:
        e[c] = e[c].fillna(0)
    e["days_since_last_visit"] = (e["enrolled_on"] - e["last_visit"]).dt.days.fillna(days).clip(upper=days)
    e["tenure_days"] = (e["enrolled_on"] - e["signup_date"]).dt.days.clip(lower=0)
    e["is_new"] = (e["pre_bookings"] + e["pre_visits"] == 0).astype(int)
    e["pre_no_show_rate"] = np.where(e["pre_bookings"] > 0, e["pre_no_shows"] / e["pre_bookings"].replace(0, 1), np.nan)
    e["no_show_rate"] = e["no_shows_28d"] / e["bookings_28d"]
    # segments (all fixed before treatment started)
    e["seg_lead"] = pd.cut(e["enrol_booking_lead_days"], [-1, 0, 1, 3, 1000],
                           labels=["Same day", "Next day", "2-3 days", "4+ days"]).astype(str)
    e["seg_history"] = np.where(e["pre_no_shows"] > 0, "No-show in last 180d",
                                np.where(e["is_new"] == 1, "New client", "Returning, no recent no-show"))
    e["seg_client"] = np.where(e["is_new"] == 1, "New", "Returning")
    return e.drop(columns=["last_visit"])


# --------------------------------------------------------------------------------------
# Validity checks
# --------------------------------------------------------------------------------------
def srm(n_control: int, n_treatment: int, expected_share: float = 0.5) -> dict:
    n = n_control + n_treatment
    chi2, p = stats.chisquare([n_control, n_treatment], f_exp=[n * (1 - expected_share), n * expected_share])
    return {"control": int(n_control), "treatment": int(n_treatment), "treatment_share": n_treatment / n,
            "chi2": float(chi2), "p_value": float(p)}


def srm_by(e: pd.DataFrame, col: str) -> pd.DataFrame:
    rows = []
    for k, g in e.groupby(col):
        r = srm(int((g["treat"] == 0).sum()), int((g["treat"] == 1).sum()))
        r[col] = k
        rows.append(r)
    t = pd.DataFrame(rows).set_index(col)
    t["p_bonferroni"] = (t["p_value"] * len(t)).clip(upper=1)
    return t


def smd(x_t: np.ndarray, x_c: np.ndarray) -> float:
    s = math.sqrt((np.var(x_t, ddof=1) + np.var(x_c, ddof=1)) / 2)
    return float((x_t.mean() - x_c.mean()) / s) if s > 0 else 0.0


def balance_table(e: pd.DataFrame, numeric: list[str], categorical: list[str]) -> pd.DataFrame:
    rows = []
    t, c = e[e["treat"] == 1], e[e["treat"] == 0]
    for v in numeric:
        xt, xc = t[v].astype(float).to_numpy(), c[v].astype(float).to_numpy()
        p = stats.ttest_ind(xt, xc, equal_var=False).pvalue
        rows.append({"covariate": v, "level": "", "control": xc.mean(), "treatment": xt.mean(),
                     "smd": smd(xt, xc), "p_value": p})
    for v in categorical:
        tab = pd.crosstab(e[v], e["treat"])
        p = stats.chi2_contingency(tab)[1]
        for lvl in tab.index:
            xt = (t[v] == lvl).astype(float).to_numpy()
            xc = (c[v] == lvl).astype(float).to_numpy()
            rows.append({"covariate": v, "level": str(lvl), "control": xc.mean(), "treatment": xt.mean(),
                         "smd": smd(xt, xc), "p_value": p})
    return pd.DataFrame(rows)


def omnibus_balance(e: pd.DataFrame, numeric: list[str], categorical: list[str]) -> dict:
    """Can the covariates predict assignment? (likelihood-ratio test of a logit vs. intercept-only)."""
    X = pd.get_dummies(e[numeric + categorical], columns=categorical, drop_first=True, dtype=float)
    X = sm.add_constant(X.astype(float))
    fit = sm.Logit(e["treat"].astype(float), X).fit(disp=0)
    return {"lr_stat": float(fit.llr), "df": int(fit.df_model), "p_value": float(fit.llr_pvalue)}


# --------------------------------------------------------------------------------------
# Effect estimators
# --------------------------------------------------------------------------------------
def ratio_effect(e: pd.DataFrame, num: str, den: str) -> dict:
    """Difference in sum(num)/sum(den) between arms; delta-method CI (clients = units)."""
    t, c = e[e["treat"] == 1], e[e["treat"] == 0]
    yt, xt = t[num].to_numpy(float), t[den].to_numpy(float)
    yc, xc = c[num].to_numpy(float), c[den].to_numpy(float)
    rt, rc = yt.sum() / xt.sum(), yc.sum() / xc.sum()
    vt, vc = ratio_delta_var(yt, xt), ratio_delta_var(yc, xc)
    d, se = rt - rc, math.sqrt(vt + vc)
    lse = math.sqrt(vt / rt ** 2 + vc / rc ** 2)
    return {"control": rc, "treatment": rt, "diff": d, "se": se, "ci_low": d - Z975 * se, "ci_high": d + Z975 * se,
            "p_value": float(2 * stats.norm.sf(abs(d / se))), "rel": rt / rc - 1,
            "rel_ci_low": math.exp(math.log(rt / rc) - Z975 * lse) - 1,
            "rel_ci_high": math.exp(math.log(rt / rc) + Z975 * lse) - 1,
            "n_control": len(c), "n_treatment": len(t), "method": "delta method"}


def mean_effect(e: pd.DataFrame, col: str) -> dict:
    """Welch two-sample t-test on a client-level metric (works for 0/1 metrics too)."""
    t, c = e.loc[e["treat"] == 1, col].to_numpy(float), e.loc[e["treat"] == 0, col].to_numpy(float)
    vt, vc = t.var(ddof=1) / len(t), c.var(ddof=1) / len(c)
    se = math.sqrt(vt + vc)
    df = (vt + vc) ** 2 / (vt ** 2 / (len(t) - 1) + vc ** 2 / (len(c) - 1))
    d = t.mean() - c.mean()
    q = stats.t.ppf(0.975, df)
    return {"control": c.mean(), "treatment": t.mean(), "diff": d, "se": se, "ci_low": d - q * se,
            "ci_high": d + q * se, "p_value": float(2 * stats.t.sf(abs(d / se), df)),
            "rel": t.mean() / c.mean() - 1 if c.mean() else np.nan,
            "n_control": len(c), "n_treatment": len(t), "method": "Welch t-test"}


def bootstrap_effect(e: pd.DataFrame, num: str, den: str | None = None, B: int = 5000, seed: int = 2026,
                     chunk: int = 500) -> dict:
    """Client-level percentile bootstrap (resampling within arm) for a ratio or a mean."""
    rng = np.random.default_rng(seed)
    t, c = e[e["treat"] == 1], e[e["treat"] == 0]
    yt, yc = t[num].to_numpy(float), c[num].to_numpy(float)
    xt = t[den].to_numpy(float) if den else np.ones_like(yt)
    xc = c[den].to_numpy(float) if den else np.ones_like(yc)
    diffs, rels = [], []
    for start in range(0, B, chunk):
        b = min(chunk, B - start)
        it = rng.integers(0, len(yt), (b, len(yt)))
        ic = rng.integers(0, len(yc), (b, len(yc)))
        rt = yt[it].sum(1) / xt[it].sum(1)
        rc = yc[ic].sum(1) / xc[ic].sum(1)
        diffs.append(rt - rc)
        rels.append(rt / rc - 1)
    d, r = np.concatenate(diffs), np.concatenate(rels)
    point = yt.sum() / xt.sum() - yc.sum() / xc.sum()
    return {"diff": point, "ci_low": float(np.percentile(d, 2.5)), "ci_high": float(np.percentile(d, 97.5)),
            "rel_ci_low": float(np.percentile(r, 2.5)), "rel_ci_high": float(np.percentile(r, 97.5)),
            "p_value": float(min(1.0, 2 * min((d >= 0).mean(), (d <= 0).mean()))), "B": B,
            "method": "client bootstrap"}


def cace(e: pd.DataFrame, num: str, den: str, B: int = 3000, seed: int = 99) -> dict:
    """Effect among clients whose reminder was actually delivered (Wald / IV estimator).

    Control clients cannot receive a reminder, so CACE = ITT / delivery rate in treatment.
    """
    itt = ratio_effect(e, num, den)["diff"]
    comp = e.loc[e["treat"] == 1, "reminder_delivered"].mean()
    rng = np.random.default_rng(seed)
    t, c = e[e["treat"] == 1], e[e["treat"] == 0]
    yt, xt, dt = t[num].to_numpy(float), t[den].to_numpy(float), t["reminder_delivered"].to_numpy(float)
    yc, xc = c[num].to_numpy(float), c[den].to_numpy(float)
    est = []
    for _ in range(B // 500):
        it = rng.integers(0, len(yt), (500, len(yt)))
        ic = rng.integers(0, len(yc), (500, len(yc)))
        est.append((yt[it].sum(1) / xt[it].sum(1) - yc[ic].sum(1) / xc[ic].sum(1)) / dt[it].mean(1))
    est = np.concatenate(est)
    return {"itt": itt, "delivery_rate": comp, "cace": itt / comp, "ci_low": float(np.percentile(est, 2.5)),
            "ci_high": float(np.percentile(est, 97.5))}


# --------------------------------------------------------------------------------------
# Segments
# --------------------------------------------------------------------------------------
def segment_effects(e: pd.DataFrame, dims: dict[str, str], num: str = "no_shows_28d",
                    den: str = "bookings_28d") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-segment treatment effects + Holm-adjusted p-values + a heterogeneity test per dimension."""
    rows, het = [], []
    for col, label in dims.items():
        ds, ws = [], []
        for lvl, g in e.groupby(col):
            if g["treat"].nunique() < 2 or len(g) < 60:
                continue
            r = ratio_effect(g, num, den)
            rows.append({"dimension": label, "segment": str(lvl), "clients": len(g), "control": r["control"],
                         "treatment": r["treatment"], "diff": r["diff"], "ci_low": r["ci_low"],
                         "ci_high": r["ci_high"], "p_value": r["p_value"]})
            ds.append(r["diff"]); ws.append(1 / r["se"] ** 2)
        ds, ws = np.array(ds), np.array(ws)
        dbar = (ws * ds).sum() / ws.sum()
        q = float((ws * (ds - dbar) ** 2).sum())
        het.append({"dimension": label, "segments": len(ds), "Q": q, "df": len(ds) - 1,
                    "p_heterogeneity": float(stats.chi2.sf(q, len(ds) - 1))})
    t = pd.DataFrame(rows)
    t["p_holm"] = multipletests(t["p_value"], method="holm")[1]
    return t, pd.DataFrame(het)


def segment_rates(e: pd.DataFrame, col: str, metric: str) -> pd.DataFrame:
    """Simple rate of a 0/1 metric by segment and arm, with Wilson intervals."""
    from statsmodels.stats.proportion import proportion_confint
    rows = []
    for (lvl, tr), g in e.groupby([col, "treat"]):
        k, n = int(g[metric].sum()), len(g)
        lo, hi = proportion_confint(k, n, method="wilson")
        rows.append({"segment": lvl, "arm": "treatment" if tr else "control", "rate": k / n, "ci_low": lo,
                     "ci_high": hi, "n": n})
    return pd.DataFrame(rows)
