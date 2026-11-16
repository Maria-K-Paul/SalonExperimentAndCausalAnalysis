"""Difference-in-differences for Glow Combos (North zone, launched 1 Jul 2026).

Design
------
* Treated: the 8 North-zone outlets.  Control: the 7 South-zone outlets (chosen
  because their pre-launch trend is parallel to North's; Central fails that test).
* Panel: outlet x week, 6 Jan 2025 - 27 Sep 2026. The launch week (29 Jun - 5 Jul)
  is dropped because it is part pre, part post.
* Model: log(y_ot) = outlet FE + week FE + beta * (North x post) + e.
  Week fixed effects absorb everything that hits all outlets in the same week -
  Aadi, Aavani weddings, Onam, price revisions - which is exactly the seasonality
  a before/after comparison mistakes for impact.
* Inference: only 15 clusters, so on top of cluster-robust SEs we report a wild
  cluster bootstrap (Rademacher, 9,999 draws) and randomisation inference over all
  6,435 ways of labelling 8 of the 15 outlets as 'treated'.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
from scipy import stats

LAUNCH = pd.Timestamp("2026-07-01")
PANEL_START = pd.Timestamp("2025-01-06")
LAST_WEEK = pd.Timestamp("2026-09-21")         # week of 21-27 Sep, last full week of Q3
TRANSITION_WEEK = pd.Timestamp("2026-06-29")
FIRST_POST_WEEK = pd.Timestamp("2026-07-06")


# --------------------------------------------------------------------------------------
# Panels
# --------------------------------------------------------------------------------------
def outlet_panel(visits: pd.DataFrame, zones=("North", "South"), freq: str = "week",
                 segment: str | None = None, start=PANEL_START, end=LAST_WEEK,
                 treated_zone: str = "North") -> pd.DataFrame:
    v = visits[visits["zone"].isin(zones)]
    if segment is not None:
        v = v[v["segment"] == segment]
    key = "week" if freq == "week" else "month"
    v = v[(v[key] >= (start if freq == "week" else start.to_period("M").to_timestamp())) & (v[key] <= end)]
    if freq == "week":
        v = v[v["week"] != TRANSITION_WEEK]
    p = v.groupby(["outlet_id", "zone", key]).agg(visits=("appointment_id", "size"), revenue=("revenue", "sum")) \
        .reset_index().rename(columns={key: "period"})
    # balance the panel (an outlet-period with no visits of a segment gets zeros)
    full = pd.MultiIndex.from_product([p["outlet_id"].unique(), sorted(p["period"].unique())],
                                      names=["outlet_id", "period"]).to_frame(index=False)
    full = full.merge(p.drop_duplicates("outlet_id")[["outlet_id", "zone"]], on="outlet_id")
    p = full.merge(p.drop(columns="zone"), on=["outlet_id", "period"], how="left").fillna({"visits": 0, "revenue": 0})
    p["rpv"] = p["revenue"] / p["visits"].replace(0, np.nan)
    p["log_rpv"] = np.log(p["rpv"])
    p["log_visits"] = np.log(p["visits"].clip(lower=0.5))
    p["log_revenue"] = np.log(p["revenue"].clip(lower=1))
    p["treated"] = (p["zone"] == treated_zone).astype(int)
    first_post = FIRST_POST_WEEK if freq == "week" else LAUNCH.to_period("M").to_timestamp()
    p["post"] = (p["period"] >= first_post).astype(int)
    p["D"] = p["treated"] * p["post"]
    return p.sort_values(["outlet_id", "period"]).reset_index(drop=True)


# --------------------------------------------------------------------------------------
# Two-way fixed effects + inference
# --------------------------------------------------------------------------------------
def _design(p: pd.DataFrame, terms: list[str]) -> tuple[np.ndarray, list[str]]:
    o = pd.get_dummies(p["outlet_id"], drop_first=True, dtype=float)
    t = pd.get_dummies(p["period"], drop_first=True, dtype=float)
    X = pd.concat([pd.Series(1.0, index=p.index, name="const"), p[terms].astype(float), o, t], axis=1)
    return X.to_numpy(), list(X.columns)


def _cluster_vcov(X, u, cl, XtX_inv) -> np.ndarray:
    G = len(np.unique(cl))
    n, k = X.shape
    meat = np.zeros((k, k))
    for g in np.unique(cl):
        s = X[cl == g].T @ u[cl == g]
        meat += np.outer(s, s)
    c = G / (G - 1) * (n - 1) / (n - k)
    return c * XtX_inv @ meat @ XtX_inv


def twfe(p: pd.DataFrame, y: str, terms: list[str] | None = None, drop_na: bool = True) -> dict:
    """OLS with outlet & period fixed effects; CR1 cluster-robust SEs by outlet, t(G-1) inference."""
    terms = terms or ["D"]
    d = p.dropna(subset=[y]) if drop_na else p
    X, names = _design(d, terms)
    yy = d[y].to_numpy(float)
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ yy
    u = yy - X @ beta
    cl = d["outlet_id"].to_numpy()
    V = _cluster_vcov(X, u, cl, XtX_inv)
    G = len(np.unique(cl))
    out = {"n_obs": len(d), "clusters": G, "_X": X, "_y": yy, "_cl": cl, "_names": names, "_beta": beta,
           "_V": V, "_XtX_inv": XtX_inv}
    for term in terms:
        j = names.index(term)
        se = math.sqrt(V[j, j])
        tq = stats.t.ppf(0.975, G - 1)
        out[term] = {"coef": float(beta[j]), "se": se, "ci_low": float(beta[j] - tq * se),
                     "ci_high": float(beta[j] + tq * se), "p_value": float(2 * stats.t.sf(abs(beta[j] / se), G - 1))}
    return out


def wild_cluster_bootstrap(fit: dict, term: str = "D", B: int = 9999, seed: int = 11, chunk: int = 2000) -> dict:
    """Wild cluster bootstrap with Rademacher weights.

    p-value: restricted (null-imposed) WCR bootstrap-t, the version recommended for few clusters.
    CI: unrestricted percentile-t.
    """
    X, y, cl, names = fit["_X"], fit["_y"], fit["_cl"], fit["_names"]
    j = names.index(term)
    XtX_inv = fit["_XtX_inv"]
    n, k = X.shape
    groups, g_idx = np.unique(cl, return_inverse=True)
    G = len(groups)
    c = G / (G - 1) * (n - 1) / (n - k)
    a = X @ XtX_inv[:, j]                              # beta_j = a' y
    M = np.eye(n) - X @ XtX_inv @ X.T                  # residual maker
    beta, u = fit["_beta"], y - X @ fit["_beta"]
    se_obs = math.sqrt(fit["_V"][j, j])
    t_obs = beta[j] / se_obs
    # restricted model: drop the tested column
    Xr = np.delete(X, j, axis=1)
    br = np.linalg.pinv(Xr.T @ Xr) @ Xr.T @ y
    yhat_r, ur = Xr @ br, y - Xr @ br
    rng = np.random.default_rng(seed)
    t_r, t_u = [], []
    for s in range(0, B, chunk):
        b = min(chunk, B - s)
        W = rng.choice([-1.0, 1.0], size=(G, b))[g_idx]           # n x b
        for kind, ystar in (("r", yhat_r[:, None] + ur[:, None] * W), ("u", (X @ beta)[:, None] + u[:, None] * W)):
            bj = a @ ystar
            ustar = M @ ystar
            scores = np.zeros((G, b))
            np.add.at(scores, g_idx, a[:, None] * ustar)
            se = np.sqrt(c * (scores ** 2).sum(0))
            if kind == "r":
                t_r.append(bj / se)
            else:
                t_u.append((bj - beta[j]) / se)
    t_r, t_u = np.concatenate(t_r), np.concatenate(t_u)
    q_lo, q_hi = np.percentile(t_u, [2.5, 97.5])
    return {"coef": float(beta[j]), "p_value": float((np.abs(t_r) >= abs(t_obs)).mean()),
            "ci_low": float(beta[j] - q_hi * se_obs), "ci_high": float(beta[j] - q_lo * se_obs), "B": B}


def wald_test(fit: dict, terms: list[str]) -> dict:
    """Joint test that several coefficients are zero (cluster-robust, F with G-1 denominator df)."""
    names = fit["_names"]
    idx = [names.index(t) for t in terms]
    b = fit["_beta"][idx]
    V = fit["_V"][np.ix_(idx, idx)]
    W = float(b @ np.linalg.pinv(V) @ b)
    q, G = len(idx), fit["clusters"]
    F = W / q * (G - q) / (G - 1)            # small-sample (Hotelling-type) correction
    return {"wald": W, "restrictions": q, "F": F, "df": (q, G - q), "p_value": float(stats.f.sf(F, q, G - q))}


# --------------------------------------------------------------------------------------
# Assumption checks
# --------------------------------------------------------------------------------------
def event_study(p_month: pd.DataFrame, y: str, ref: str = "2026-06-01") -> pd.DataFrame:
    """Treated x month interactions (reference = the month before launch)."""
    p = p_month.copy()
    months = sorted(p["period"].unique())
    terms = []
    for m in months:
        if m == pd.Timestamp(ref):
            continue
        nm = f"ev_{pd.Timestamp(m):%Y_%m}"
        p[nm] = ((p["period"] == m) & (p["treated"] == 1)).astype(int)
        terms.append(nm)
    f = twfe(p, y, terms)
    rows = [{"month": pd.Timestamp(t[3:].replace("_", "-") + "-01"), **{k: f[t][k] for k in ["coef", "se", "ci_low", "ci_high", "p_value"]}}
            for t in terms]
    rows.append({"month": pd.Timestamp(ref), "coef": 0.0, "se": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p_value": np.nan})
    out = pd.DataFrame(rows).sort_values("month").reset_index(drop=True)
    out["post"] = out["month"] >= LAUNCH.to_period("M").to_timestamp()
    return out


def quarterly_leads_test(p_week: pd.DataFrame, y: str) -> dict:
    """Joint test of 5 pre-launch quarterly 'effects' (Q1-2025 ... Q1-2026, ref = Q2-2026)."""
    p = p_week.copy()
    q = p["period"].dt.to_period("Q").astype(str)
    leads = ["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1"]
    terms = []
    for l in leads:
        nm = f"lead_{l}"
        p[nm] = ((q == l) & (p["treated"] == 1)).astype(int)
        terms.append(nm)
    f = twfe(p, y, terms + ["D"])
    res = wald_test(f, terms)
    res["leads"] = {t: f[t]["coef"] for t in terms}
    return res


def linear_pretrend(p_week: pd.DataFrame, y: str, B: int = 9999) -> dict:
    """Differential linear trend before launch (per year), with wild-bootstrap p-value."""
    p = p_week[p_week["post"] == 0].copy()
    p["trend"] = p["treated"] * (p["period"] - PANEL_START).dt.days / 365.25
    f = twfe(p, y, ["trend"])
    wb = wild_cluster_bootstrap(f, "trend", B=B)
    return {"slope_per_year": f["trend"]["coef"], "ci_low": wb["ci_low"], "ci_high": wb["ci_high"],
            "p_value": wb["p_value"], "p_cr1": f["trend"]["p_value"]}


def placebo_in_time(visits: pd.DataFrame, y: str, start: str, fake_first_post: str, end: str,
                    zones=("North", "South"), B: int = 9999) -> dict:
    """Pretend the launch happened earlier, using only data from before the real launch."""
    p = outlet_panel(visits, zones=zones, start=pd.Timestamp(start), end=pd.Timestamp(end))
    p = p[p["period"] < TRANSITION_WEEK]
    p["post"] = (p["period"] >= pd.Timestamp(fake_first_post)).astype(int)
    p["D"] = p["treated"] * p["post"]
    f = twfe(p, y)
    wb = wild_cluster_bootstrap(f, "D", B=B)
    return {"fake_launch": fake_first_post, "coef": f["D"]["coef"], "ci_low": wb["ci_low"],
            "ci_high": wb["ci_high"], "p_value": wb["p_value"]}


def randomization_inference(p_week: pd.DataFrame, y: str) -> dict:
    """Exact permutation test over every way to label 8 of the 15 outlets as treated.

    On a balanced panel the TWFE estimate equals the difference in mean pre-to-post
    change between treated and control outlets, so each permutation is cheap.
    """
    chg = p_week.groupby(["outlet_id", "post"])[y].mean().unstack()
    delta = (chg[1] - chg[0])
    treated = p_week.drop_duplicates("outlet_id").set_index("outlet_id")["treated"].reindex(delta.index)
    obs = delta[treated == 1].mean() - delta[treated == 0].mean()
    ids = list(delta.index)
    n_t = int(treated.sum())
    vals = delta.to_numpy()
    perms = []
    for combo in itertools.combinations(range(len(ids)), n_t):
        m = np.zeros(len(ids), dtype=bool)
        m[list(combo)] = True
        perms.append(vals[m].mean() - vals[~m].mean())
    perms = np.array(perms)
    return {"observed": float(obs), "permutations": len(perms),
            "p_value": float((np.abs(perms) >= abs(obs) - 1e-12).mean()),
            "rank": int((perms >= obs - 1e-12).sum()), "perms": perms}


# --------------------------------------------------------------------------------------
# Convenience
# --------------------------------------------------------------------------------------
def pct(fit_or_dict: dict) -> dict:
    """Convert a log-point effect and its CI into percentages."""
    d = fit_or_dict
    return {"pct": math.exp(d["coef"]) - 1, "ci_low": math.exp(d["ci_low"]) - 1, "ci_high": math.exp(d["ci_high"]) - 1}


def naive_comparison(visits: pd.DataFrame) -> pd.DataFrame:
    """What management looked at: Q3 vs Q2 2026 revenue per visit, by zone."""
    v = visits[(visits["date"] >= "2026-04-01") & (visits["date"] <= "2026-09-30")].copy()
    v["quarter"] = np.where(v["date"] >= "2026-07-01", "Q3 2026", "Q2 2026")
    t = v.groupby(["zone", "quarter"]).agg(visits=("appointment_id", "size"), revenue=("revenue", "sum"))
    t["rpv"] = t["revenue"] / t["visits"]
    w = t["rpv"].unstack()
    w["change"] = w["Q3 2026"] / w["Q2 2026"] - 1
    vis = t["visits"].unstack()
    w["visits_change"] = vis["Q3 2026"] / vis["Q2 2026"] - 1
    return w
