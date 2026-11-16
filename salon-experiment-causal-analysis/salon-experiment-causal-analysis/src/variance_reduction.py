"""CUPED and regression adjustment for the Smart Reminders test.

CUPED (Deng et al., 2013) removes the part of each client's outcome that was
predictable from their own pre-experiment behaviour. Because assignment is random,
that part is unrelated to treatment, so the estimate stays unbiased while its
variance falls by roughly rho^2 (the squared pre/post correlation).

Sample size scales with variance, so a variance reduction of VR means the
same power is reached with (1 - VR) of the clients - i.e. a shorter test.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import statsmodels.api as sm


def cuped(e: pd.DataFrame, y: str, x: str, x_missing_flag: str | None = None) -> dict:
    """Classic single-covariate CUPED on a client-level metric.

    Missing covariate values (new clients have no history) are set to the pooled
    mean, which is the standard fix and keeps the estimator unbiased.
    """
    d = e[[y, x, "treat"]].copy()
    d[x] = d[x].fillna(d[x].mean())
    theta = d[[y, x]].cov().iloc[0, 1] / d[x].var()
    d["y_cv"] = d[y] - theta * (d[x] - d[x].mean())
    rho = d[[y, x]].corr().iloc[0, 1]
    out = {"theta": float(theta), "rho": float(rho)}
    for tag, col in [("unadjusted", y), ("cuped", "y_cv")]:
        t, c = d.loc[d["treat"] == 1, col], d.loc[d["treat"] == 0, col]
        se = math.sqrt(t.var(ddof=1) / len(t) + c.var(ddof=1) / len(c))
        out[tag] = {"diff": float(t.mean() - c.mean()), "se": se,
                    "ci_low": float(t.mean() - c.mean() - 1.96 * se), "ci_high": float(t.mean() - c.mean() + 1.96 * se)}
    out["variance_reduction"] = 1 - (out["cuped"]["se"] / out["unadjusted"]["se"]) ** 2
    return out


def regression_adjusted(e: pd.DataFrame, y: str, covariates: list[str], weights: str | None = None,
                        categorical: list[str] | None = None) -> dict:
    """OLS/WLS of the outcome on treatment +/- centred pre-period covariates, HC1 robust SEs.

    With weights = bookings and y = per-client no-show rate, the treatment coefficient
    equals the difference in booking-weighted no-show rates (the primary metric).
    """
    d = e.copy()
    X0 = sm.add_constant(d[["treat"]].astype(float))
    cov = d[covariates].astype(float)
    if categorical:
        cov = pd.concat([cov, pd.get_dummies(d[categorical], drop_first=True, dtype=float)], axis=1)
    cov = cov - cov.mean()
    X1 = pd.concat([X0, cov], axis=1)
    w = d[weights].astype(float) if weights else None
    fits = {}
    for tag, X in [("unadjusted", X0), ("adjusted", X1)]:
        model = sm.WLS(d[y].astype(float), X, weights=w) if weights else sm.OLS(d[y].astype(float), X)
        f = model.fit(cov_type="HC1")
        b, se = float(f.params["treat"]), float(f.bse["treat"])
        fits[tag] = {"diff": b, "se": se, "ci_low": b - 1.96 * se, "ci_high": b + 1.96 * se,
                     "p_value": float(f.pvalues["treat"]), "r2": float(f.rsquared)}
    fits["variance_reduction"] = 1 - (fits["adjusted"]["se"] / fits["unadjusted"]["se"]) ** 2
    fits["covariates"] = covariates + (categorical or [])
    return fits


def shorter_test(days_needed: float, variance_reduction: float, planned_days: int) -> dict:
    """Translate a variance reduction into enrolment days saved at the same power."""
    adj = days_needed * (1 - variance_reduction)
    return {"days_needed_unadjusted": days_needed, "days_needed_adjusted": adj,
            "weeks_unadjusted": math.ceil(days_needed / 7), "weeks_adjusted": math.ceil(adj / 7),
            "planned_days": planned_days, "days_saved_vs_plan": planned_days - 7 * math.ceil(adj / 7),
            "share_saved": variance_reduction}
