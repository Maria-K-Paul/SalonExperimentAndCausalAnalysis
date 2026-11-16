"""Sample size, test duration and A/A checks for the Smart Reminders test.

The test randomises *clients* but the primary metric is a *booking-level* rate
(no-shows / bookings), so the plan works in three steps:

1. bookings needed per arm for a two-proportion test at the chosen MDE,
2. inflated by a design effect measured on history (clients with several
   bookings make bookings correlated),
3. converted to clients and then to enrolment days using the historical
   rate at which new eligible clients appear.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize


def eligible_bookings(appts: pd.DataFrame, clients: pd.DataFrame) -> pd.DataFrame:
    """Bookings that could receive a WhatsApp reminder: booked (not walk-in), known client, opted in."""
    opt = clients.set_index("client_id")["whatsapp_opt_in"]
    b = appts[~appts["is_walk_in"] & appts["client_known"]].copy()
    b["opt_in"] = b["client_id"].map(opt).fillna(False).astype(bool)
    return b[b["opt_in"]]


def planning_cohort(elig: pd.DataFrame, start: str, days: int = 28, window: int = 28) -> pd.DataFrame:
    """Replay the experiment's enrolment rule on history.

    A client 'enrols' at their first eligible booking scheduled in [start, start+days),
    then we count their bookings and no-shows in the next `window` days - exactly
    the per-client metric the real test uses.
    """
    s = pd.Timestamp(start)
    e = s + pd.Timedelta(days=days)
    first = elig[(elig["date"] >= s) & (elig["date"] < e)].groupby("client_id")["date"].min().rename("enrol")
    b = elig.merge(first, left_on="client_id", right_index=True)
    b = b[(b["date"] >= b["enrol"]) & (b["date"] < b["enrol"] + pd.Timedelta(days=window))]
    out = b.groupby("client_id").agg(enrol=("enrol", "first"), bookings=("appointment_id", "size"),
                                     no_shows=("is_no_show", "sum"))
    return out.reset_index()


def ratio_delta_var(y: np.ndarray, x: np.ndarray) -> float:
    """Delta-method variance of sum(y)/sum(x) with clients as independent units."""
    n = len(y)
    mx, my = x.mean(), y.mean()
    r = my / mx
    vy, vx = y.var(ddof=1), x.var(ddof=1)
    cxy = np.cov(y, x, ddof=1)[0, 1]
    return (vy - 2 * r * cxy + r * r * vx) / (n * mx * mx)


def design_effect(cohort: pd.DataFrame) -> dict:
    """Variance of the clustered ratio vs. the naive binomial variance (same data)."""
    y = cohort["no_shows"].to_numpy(float)
    x = cohort["bookings"].to_numpy(float)
    p = y.sum() / x.sum()
    v_delta = ratio_delta_var(y, x)
    v_binom = p * (1 - p) / x.sum()
    return {"baseline_rate": p, "bookings_per_client": x.mean(), "design_effect": v_delta / v_binom,
            "clients": len(y), "bookings": int(x.sum())}


def bookings_per_arm(p0: float, mde_abs: float, alpha: float = 0.05, power: float = 0.80) -> float:
    """Two-sided two-proportion test (Cohen's h, normal approximation)."""
    h = abs(proportion_effectsize(p0, p0 - mde_abs))
    return NormalIndPower().solve_power(effect_size=h, alpha=alpha, power=power, ratio=1.0, alternative="two-sided")


def mde_for_bookings(p0: float, n_per_arm_eff: float, alpha: float = 0.05, power: float = 0.80) -> float:
    """Smallest absolute drop in the rate detectable with n effective bookings per arm."""
    h = NormalIndPower().solve_power(nobs1=n_per_arm_eff, alpha=alpha, power=power, ratio=1.0, alternative="two-sided")
    # invert Cohen's h: h = 2 asin(sqrt(p0)) - 2 asin(sqrt(p1))
    p1 = math.sin(math.asin(math.sqrt(p0)) - h / 2) ** 2
    return p0 - p1


def mde_proportion(p0: float, n_per_arm: float, alpha: float = 0.05, power: float = 0.80) -> float:
    """Approximate MDE (absolute) for a client-level binary metric such as 45-day return."""
    z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    return z * math.sqrt(2 * p0 * (1 - p0) / n_per_arm)


def plan(p0: float, mde_abs: float, deff: float, bookings_per_client: float, enrol_per_day: float,
         alpha: float = 0.05, power: float = 0.80) -> dict:
    n_book = bookings_per_arm(p0, mde_abs, alpha, power)
    n_book_eff = n_book * deff
    n_clients = n_book_eff / bookings_per_client
    days = 2 * n_clients / enrol_per_day
    return {"bookings_per_arm_naive": n_book, "bookings_per_arm": n_book_eff, "clients_per_arm": n_clients,
            "clients_total": 2 * n_clients, "days_needed": days, "weeks_rounded_up": math.ceil(days / 7)}


def sensitivity_table(p0: float, deff: float, bpc: float, enrol_per_day: float,
                      mdes=(0.015, 0.02, 0.025, 0.03, 0.035)) -> pd.DataFrame:
    rows = []
    for m in mdes:
        r = plan(p0, m, deff, bpc, enrol_per_day)
        rows.append({"MDE (pp)": m * 100, "relative MDE": m / p0, "clients per arm": r["clients_per_arm"],
                     "enrolment days": r["days_needed"], "weeks (rounded up)": r["weeks_rounded_up"]})
    return pd.DataFrame(rows)


def aa_simulation(cohort: pd.DataFrame, n_sims: int = 2000, alpha: float = 0.05, seed: int = 7) -> dict:
    """Randomly split a historical cohort into two fake arms many times.

    With no real treatment, a correctly calibrated test should flag ~5% of splits.
    Also checks that the delta-method SE matches the spread of the fake 'effects'.
    """
    rng = np.random.default_rng(seed)
    y = cohort["no_shows"].to_numpy(float)
    x = cohort["bookings"].to_numpy(float)
    n = len(y)
    diffs, ses = np.empty(n_sims), np.empty(n_sims)
    for s in range(n_sims):
        t = rng.random(n) < 0.5
        rt, rc = y[t].sum() / x[t].sum(), y[~t].sum() / x[~t].sum()
        diffs[s] = rt - rc
        ses[s] = math.sqrt(ratio_delta_var(y[t], x[t]) + ratio_delta_var(y[~t], x[~t]))
    z = diffs / ses
    return {"sims": n_sims, "false_positive_rate": float((np.abs(z) > stats.norm.ppf(1 - alpha / 2)).mean()),
            "empirical_sd": float(diffs.std(ddof=1)), "mean_delta_se": float(ses.mean()),
            "diffs": diffs}
