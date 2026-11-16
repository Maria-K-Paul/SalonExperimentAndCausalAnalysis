"""Cleaning pipeline: raw till exports -> analysis-ready tables.

Every fix is logged in ``QualityLog`` so the notebook and report can show exactly
what was changed and how many rows it touched.

Main entry point: ``run_cleaning()`` (writes data/processed/*.parquet).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process
from rapidfuzz.distance import OSA

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
REF = ROOT / "data" / "reference"
PROCESSED = ROOT / "data" / "processed"

NO_SHOW_POLICY_HOURS = 2.0   # cancelling less than 2h before the start counts as a no-show
FUZZY_CUTOFF = 85            # rapidfuzz ratio needed to accept a typo'd service name

NS_NOTE = re.compile(r"(?:\bns\b|\bdnc\b|no[\s-]?show|did not come|didn'?t turn up|not reachable|no response)", re.I)
CX_NOTE = re.compile(r"(?:cancel|resched|will come|sick|rain|travel|office)", re.I)
CHANNEL_MAP = {"walk-in": "Walk-in", "walk in": "Walk-in", "walkin": "Walk-in", "phone": "Phone",
               "phone call": "Phone", "whatsapp": "WhatsApp", "app": "App", "mobile app": "App"}
STATUS_MAP = {"completed": "completed", "done": "completed", "cancelled": "cancelled", "canceled": "cancelled",
              "no show": "no_show", "noshow": "no_show", "no-show": "no_show"}
SEGMENT = {"Grooming": "Men's grooming", "Hair": "Hair (women)", "Skin": "Skin & beauty", "Spa": "Spa",
           "Occasion": "Occasion & bridal"}


@dataclass
class QualityLog:
    rows: list[dict] = field(default_factory=list)

    def add(self, table: str, issue: str, affected: int, total: int, fix: str):
        self.rows.append({"table": table, "issue": issue, "rows_affected": int(affected),
                          "share_of_table": round(affected / total, 4) if total else 0.0, "fix": fix})

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


# --------------------------------------------------------------------------------------
# Loading & small helpers
# --------------------------------------------------------------------------------------
def load_raw(raw_dir: Path = RAW) -> dict[str, pd.DataFrame]:
    return {
        "outlets": pd.read_csv(raw_dir / "outlets.csv", dtype=str),
        "stylists": pd.read_csv(raw_dir / "stylists.csv", dtype=str),
        "clients": pd.read_csv(raw_dir / "clients.csv", dtype=str),
        "appointments": pd.read_csv(raw_dir / "appointments.csv.gz", dtype=str),
        "service_lines": pd.read_csv(raw_dir / "service_lines.csv.gz", dtype=str),
        "product_sales": pd.read_csv(raw_dir / "product_sales.csv.gz", dtype=str),
        "experiment": pd.read_csv(raw_dir / "experiment_smart_reminders.csv", dtype=str),
    }


def parse_mixed_datetime(s: pd.Series) -> tuple[pd.Series, int]:
    """Parse a column that mixes 'YYYY-mm-dd HH:MM:SS' with 'dd-mm-YYYY HH:MM'.

    Returns the parsed series and how many values used the day-first format.
    Parsing each format explicitly avoids silently swapping day and month.
    """
    s = s.astype("string").str.strip()
    dmy = s.str.match(r"^\d{2}-\d{2}-\d{4}").fillna(False).astype(bool)
    iso = pd.to_datetime(s.where(~dmy), format="%Y-%m-%d %H:%M:%S", errors="coerce")
    dm = pd.to_datetime(s.where(dmy), format="%d-%m-%Y %H:%M", errors="coerce")
    return iso.fillna(dm), int(dmy.sum())


def to_amount(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype("string").str.replace(r"[₹,\s]", "", regex=True), errors="coerce")


def norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


# --------------------------------------------------------------------------------------
# Dimension tables
# --------------------------------------------------------------------------------------
def clean_outlets(raw: pd.DataFrame) -> pd.DataFrame:
    o = raw.copy()
    o["opened_year"] = o["opened_year"].astype(int)
    o["chairs"] = o["chairs"].astype(int)
    o["pos_migrated_on"] = pd.to_datetime(o["pos_migrated_on"].replace("", pd.NA), errors="coerce")
    return o


def clean_stylists(raw: pd.DataFrame) -> pd.DataFrame:
    s = raw.copy()
    s["stylist_id"] = s["stylist_id"].str.strip().str.upper()
    s["join_date"] = pd.to_datetime(s["join_date"])
    s["exit_date"] = pd.to_datetime(s["exit_date"], errors="coerce")
    return s


def clean_clients(raw: pd.DataFrame, log: QualityLog) -> pd.DataFrame:
    c = raw.copy()
    n = len(c)
    g = c["gender"].str.strip().str.lower().map({"f": "F", "female": "F", "m": "M", "male": "M"})
    log.add("clients", "Gender coded 6 different ways (F/Female/female/M/Male/male) or blank",
            int((~c["gender"].isin(["F", "M"])).sum()), n, "Mapped to F / M; blanks -> 'Unknown'")
    c["gender"] = g.fillna("Unknown")
    ab = c["age_band"].str.replace(" ", "", regex=False)
    log.add("clients", "Age band blank or written '55 +'", int((c["age_band"].isna() | (c["age_band"] == "55 +")).sum()),
            n, "Standardised to 18-24 ... 55+; blanks -> 'Unknown'")
    c["age_band"] = ab.fillna("Unknown")
    c["signup_date"] = pd.to_datetime(c["signup_date"])
    c["whatsapp_opt_in"] = c["whatsapp_opt_in"].eq("Y")
    return c


# --------------------------------------------------------------------------------------
# Appointments
# --------------------------------------------------------------------------------------
def clean_appointments(raw: pd.DataFrame, outlets: pd.DataFrame, stylists: pd.DataFrame,
                       log: QualityLog) -> pd.DataFrame:
    a = raw.copy()
    n0 = len(a)
    dup = a.duplicated()
    log.add("appointments", "Exact duplicate rows from till sync", int(dup.sum()), n0, "Dropped (kept first copy)")
    a = a[~dup].copy()
    assert a["appointment_id"].is_unique, "appointment_id should be unique after de-duplication"
    n = len(a)

    for col in ["booked_at", "scheduled_start", "cancelled_at"]:
        a[col], n_dmy = parse_mixed_datetime(a[col])
        if col == "scheduled_start":
            log.add("appointments", "Two outlets export dates as dd-mm-yyyy, the rest as ISO", n_dmy, n,
                    "Parsed each format explicitly (no day/month guessing)")
    a = a.merge(outlets[["outlet_id", "zone", "format", "pos_system", "pos_migrated_on"]], on="outlet_id", how="left")

    ch_raw = a["booking_channel"].str.strip().str.lower()
    a["channel"] = ch_raw.map(CHANNEL_MAP)
    log.add("appointments", "Booking channel spelt 9 ways (e.g. 'walk in', 'WALKIN', 'Mobile App')",
            int((~a["booking_channel"].isin(["Walk-in", "Phone", "WhatsApp", "App"])).sum()), n,
            "Mapped to Walk-in / Phone / WhatsApp / App")
    a["is_walk_in"] = a["channel"].eq("Walk-in")

    a["client_id"] = a["client_id"].str.strip()
    a["client_known"] = a["client_id"].notna()
    log.add("appointments", "Walk-ins recorded without a client ID", int((a["is_walk_in"] & ~a["client_known"]).sum()), n,
            "Kept for outlet-level revenue and visits; excluded from client-level retention and from the A/B test")

    st = a["stylist_id"].str.strip().str.upper()
    log.add("appointments", "Stylist ID in lower case or with stray spaces",
            int((a["stylist_id"].notna() & (a["stylist_id"] != st)).sum()), n, "Trimmed and upper-cased")
    a["stylist_id"] = st
    known = set(stylists["stylist_id"])
    a = a.merge(stylists[["stylist_id", "level"]].rename(columns={"level": "stylist_level"}), on="stylist_id", how="left")
    log.add("appointments", "Stylist ID missing", int(a["stylist_id"].isna().sum()), n,
            "Left blank; only used for stylist-level breakdowns")
    assert a.loc[a["stylist_id"].notna(), "stylist_id"].isin(known).all()

    # POS regime in force on the day (BB12 switched from LegacyPOS to SalonCloud)
    mig = a["pos_migrated_on"].notna() & (a["scheduled_start"] < a["pos_migrated_on"])
    a["pos_regime"] = np.where(mig, "LegacyPOS", a["pos_system"])

    a["status_raw"] = a["status"]
    a["status_norm"] = a["status"].str.strip().str.lower().map(STATUS_MAP)
    log.add("appointments", "Status spelt 7 ways (Completed/completed/Done/Cancelled/CANCELLED/Canceled/No Show)",
            int((~a["status"].isin(["Completed", "Cancelled", "No Show"])).sum()), n,
            "Mapped to completed / cancelled / no_show")
    a["outcome"], a["outcome_rule"] = reconstruct_outcome(a)
    hidden = a["status_norm"].eq("cancelled") & a["outcome"].isin(["no_show", "late_cancel"])
    log.add("appointments", "No-shows (and <2h late cancellations) logged as 'Cancelled'", int(hidden.sum()), n,
            "Re-classified with cancellation timestamp + remarks (see outcome_rule)")
    a["is_no_show"] = a["outcome"].isin(["no_show", "late_cancel"])
    a["is_completed"] = a["outcome"].eq("completed")

    a["date"] = a["scheduled_start"].dt.normalize()
    a["lead_days"] = np.where(a["is_walk_in"], 0, (a["date"] - a["booked_at"].dt.normalize()).dt.days)
    a["hour"] = a["scheduled_start"].dt.hour
    a = a.drop(columns=["status", "booking_channel", "pos_migrated_on"])
    return a


def reconstruct_outcome(a: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Rebuild the true outcome of each booking.

    Legacy tills have no 'No Show' status: front-desk staff mark no-shows as
    'Cancelled' at closing time (timestamp after the start) or leave the
    cancellation time blank. Rules, in order:
      1. Completed -> completed.  SalonCloud 'No Show' -> no_show.
      2. Cancelled >= 2h before start -> cancelled_advance.
      3. Cancelled 0-2h before start -> late_cancel (a no-show under house policy).
      4. 'Cancelled' after the start time -> no_show (end-of-day tidy-up).
      5. No timestamp: a cancellation note ('rescheduled', 'called to cancel' ...) -> cancelled_advance;
         otherwise -> no_show (legacy convention).
      6. An explicit no-show note ('NS', 'did not come' ...) always wins.
    """
    st = a["status_norm"]
    hrs = (a["scheduled_start"] - a["cancelled_at"]).dt.total_seconds() / 3600
    rem = a["remarks"].fillna("").astype(str)
    ns_note = rem.str.contains(NS_NOTE)
    cx_note = rem.str.contains(CX_NOTE) & ~ns_note
    out = pd.Series("completed", index=a.index, dtype=object)
    rule = pd.Series("1 status completed", index=a.index, dtype=object)
    c = st.eq("cancelled")
    blank = c & a["cancelled_at"].isna()

    def put(mask, o, r):
        out[mask] = o
        rule[mask] = r

    put(st.eq("no_show"), "no_show", "1 status no-show (SalonCloud)")
    put(c & hrs.ge(NO_SHOW_POLICY_HOURS), "cancelled_advance", "2 cancelled >=2h before start")
    put(c & hrs.ge(0) & hrs.lt(NO_SHOW_POLICY_HOURS), "late_cancel", "3 cancelled <2h before start")
    put(c & hrs.lt(0), "no_show", "4 'cancelled' after start time")
    put(blank & cx_note, "cancelled_advance", "5a no timestamp, cancellation note")
    put(blank & ~cx_note, "no_show", "5b no timestamp, no cancellation note")
    put(c & ns_note, "no_show", "6 explicit no-show note")
    return out, rule


# --------------------------------------------------------------------------------------
# Services
# --------------------------------------------------------------------------------------
def build_service_map(names: pd.Series, aliases: pd.DataFrame | None = None) -> pd.DataFrame:
    """Map every raw service spelling to a canonical service.

    1. exact match on the normalised alias table (data/reference/service_aliases.csv)
    2. fuzzy match (rapidfuzz ratio >= FUZZY_CUTOFF) for typos
    """
    if aliases is None:
        aliases = pd.read_csv(REF / "service_aliases.csv")
    lookup = {norm_name(r.alias): (r.canonical_service, r.category, bool(r.is_combo))
              for r in aliases.itertuples(index=False)}
    keys = list(lookup)
    exact = set(aliases["alias"])
    rows = []
    for raw in pd.Series(names.dropna().unique()):
        n = norm_name(raw)
        if n in lookup:
            canon, cat, combo = lookup[n]
            rows.append((raw, n, canon, cat, combo, "exact alias" if raw in exact else "normalised alias", 100.0, n))
            continue
        hit = process.extractOne(n, keys, scorer=fuzz.ratio, score_cutoff=FUZZY_CUTOFF)
        if hit is None:
            # short words: allow one transposed/dropped letter (OSA distance 1), if unambiguous
            cands = process.extract(n, keys, scorer=OSA.distance, limit=3)
            best = [c for c in cands if c[1] <= 1]
            if best and len({lookup[c[0]][0] for c in best}) == 1:
                hit = (best[0][0], 100.0 * (1 - best[0][1] / max(len(n), 1)), None)
        if hit:
            canon, cat, combo = lookup[hit[0]]
            rows.append((raw, n, canon, cat, combo, "fuzzy (typo)", float(hit[1]), hit[0]))
        else:
            rows.append((raw, n, None, None, None, "unmapped", 0.0, None))
    return pd.DataFrame(rows, columns=["raw_name", "normalised", "canonical_service", "category", "is_combo",
                                       "method", "score", "matched_alias"])


def clean_service_lines(raw: pd.DataFrame, appts: pd.DataFrame, log: QualityLog) -> tuple[pd.DataFrame, pd.DataFrame]:
    s = raw.copy()
    n = len(s)
    txt = s["list_price"].astype("string").str.contains(",", regex=False).fillna(False) | \
        s["list_price"].astype("string").str.match(r"^\d+\.\d{2}$").fillna(False)
    s["list_price"] = to_amount(s["list_price"])
    s["net_amount"] = to_amount(s["net_amount"])
    s["discount_pct"] = pd.to_numeric(s["discount_pct"])
    s["line_no"] = pd.to_numeric(s["line_no"])
    log.add("service_lines", "Amounts stored as text with thousands separators (one outlet)", int(txt.sum()), n,
            "Stripped separators and converted to numbers")
    smap = build_service_map(s["service_name"])
    s = s.merge(smap[["raw_name", "canonical_service", "category", "is_combo", "method"]],
                left_on="service_name", right_on="raw_name", how="left").drop(columns="raw_name")
    log.add("service_lines", f"Service names differ by outlet: {smap.shape[0]:,} spellings of "
            f"{smap['canonical_service'].nunique()} services (incl. typos, case, spacing)",
            int((s["service_name"] != s["canonical_service"]).sum()), n,
            "Alias table + fuzzy matching (typos, transpositions); 100% of lines mapped")
    assert s["canonical_service"].notna().all(), "unmapped service names remain"
    # Sanity check: fuzzy matches must sit in the normal price range for their service at that outlet
    s = s.merge(appts[["appointment_id", "outlet_id"]], on="appointment_id", how="left")
    med = s[s["method"] != "fuzzy (typo)"].groupby(["outlet_id", "canonical_service"])["list_price"].median()
    ratio = s["list_price"] / s.set_index(["outlet_id", "canonical_service"]).index.map(med).to_numpy()
    s["price_check_ok"] = ratio.between(0.6, 1.7) | s["list_price"].isna()
    log.add("service_lines", "Price far from the outlet median for its mapped service (possible mis-mapping)",
            int((~s["price_check_ok"]).sum()), n, "Reviewed; none are fuzzy matches" if
            (~s["price_check_ok"] & (s["method"] == "fuzzy (typo)")).sum() == 0 else "Flagged for review")
    s["segment"] = s["category"].map(SEGMENT)
    return s.drop(columns=["outlet_id"]), smap


# --------------------------------------------------------------------------------------
# Product sales
# --------------------------------------------------------------------------------------
def clean_product_sales(raw: pd.DataFrame, appts: pd.DataFrame, log: QualityLog) -> pd.DataFrame:
    p = raw.copy()
    n = len(p)
    p["sale_datetime"] = pd.to_datetime(p["sale_datetime"])
    p["amount"] = to_amount(p["amount"])
    p["qty"] = pd.to_numeric(p["qty"])
    p["date"] = p["sale_datetime"].dt.normalize()
    p["link_method"] = np.where(p["appointment_id"].notna(), "appointment_id", None)
    # fallback: same client, same outlet, same day, completed visit
    done = appts.loc[appts["is_completed"] & appts["client_known"], ["appointment_id", "client_id", "outlet_id", "date"]]
    done = done.drop_duplicates(["client_id", "outlet_id", "date"])
    need = p["appointment_id"].isna() & p["client_id"].notna()
    m = p.loc[need, ["client_id", "outlet_id", "date"]].reset_index().merge(
        done, on=["client_id", "outlet_id", "date"], how="left").set_index("index")
    p.loc[m.index, "appointment_id"] = m["appointment_id"]
    p.loc[m.index[m["appointment_id"].notna()], "link_method"] = "client + outlet + date"
    p["link_method"] = p["link_method"].fillna("unlinked (counter sale)")
    n_linked = int((p["link_method"] == "client + outlet + date").sum())
    log.add("product_sales", "Product sales without an appointment ID", int(raw["appointment_id"].isna().sum()), n,
            f"{n_linked:,} re-linked by client + outlet + date; the rest kept as counter (retail-only) sales")
    return p


# --------------------------------------------------------------------------------------
# Visit-level table
# --------------------------------------------------------------------------------------
def build_visits(appts: pd.DataFrame, lines: pd.DataFrame, sales: pd.DataFrame) -> pd.DataFrame:
    """One row per completed visit with service, product and total revenue."""
    v = appts[appts["is_completed"]].copy()
    agg = lines.groupby("appointment_id").agg(service_revenue=("net_amount", "sum"),
                                               n_services=("line_no", "size"),
                                               has_combo=("is_combo", "any"))
    top = lines.sort_values("list_price", ascending=False).drop_duplicates("appointment_id") \
        .set_index("appointment_id")[["category", "segment"]].rename(columns={"category": "primary_category"})
    prod = sales.dropna(subset=["appointment_id"]).groupby("appointment_id")["amount"].sum().rename("product_revenue")
    v = v.join(agg, on="appointment_id").join(top, on="appointment_id").join(prod, on="appointment_id")
    v["product_revenue"] = v["product_revenue"].fillna(0.0)
    v["service_revenue"] = v["service_revenue"].fillna(0.0)
    v["revenue"] = v["service_revenue"] + v["product_revenue"]
    v["has_combo"] = v["has_combo"].fillna(False).astype(bool)
    v["week"] = v["date"] - pd.to_timedelta(v["date"].dt.dayofweek, unit="D")
    v["month"] = v["date"].dt.to_period("M").dt.to_timestamp()
    return v


# --------------------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------------------
def no_show_by_regime(appts: pd.DataFrame) -> pd.DataFrame:
    """Raw vs reconstructed no-show rate by till type - the two should agree after cleaning."""
    b = appts[~appts["is_walk_in"]]
    t = b.groupby("pos_regime").agg(bookings=("appointment_id", "size"),
                                    raw_no_show_rate=("status_norm", lambda s: s.eq("no_show").mean()),
                                    raw_cancelled_rate=("status_norm", lambda s: s.eq("cancelled").mean()),
                                    reconstructed_no_show_rate=("is_no_show", "mean"),
                                    advance_cancel_rate=("outcome", lambda s: s.eq("cancelled_advance").mean()))
    return t


def crosscheck_experiment(exp: pd.DataFrame, appts: pd.DataFrame) -> dict:
    """Compare the experiment file's outcome counts with counts rebuilt from cleaned appointments."""
    e = exp.drop_duplicates("client_id", keep=False)[["client_id", "enrolled_on", "bookings_28d", "no_shows_28d"]].copy()
    e["enrolled_on"] = pd.to_datetime(e["enrolled_on"])
    b = appts.loc[~appts["is_walk_in"] & appts["client_known"], ["client_id", "date", "is_no_show"]]
    m = e.merge(b, on="client_id", how="left")
    w = m[(m["date"] >= m["enrolled_on"]) & (m["date"] <= m["enrolled_on"] + pd.Timedelta(days=27))]
    rebuilt = w.groupby("client_id").agg(bookings=("date", "size"), no_shows=("is_no_show", "sum"))
    e = e.join(rebuilt, on="client_id")
    e[["bookings", "no_shows"]] = e[["bookings", "no_shows"]].fillna(0)
    eb = pd.to_numeric(e["bookings_28d"])
    en = pd.to_numeric(e["no_shows_28d"])
    return {"clients_checked": int(len(e)),
            "bookings_match_rate": float((eb == e["bookings"]).mean()),
            "no_show_match_rate": float((en == e["no_shows"]).mean()),
            "no_shows_in_file": int(en.sum()), "no_shows_rebuilt": int(e["no_shows"].sum())}


# --------------------------------------------------------------------------------------
def run_cleaning(raw_dir: Path = RAW, out_dir: Path = PROCESSED, save: bool = True) -> dict:
    log = QualityLog()
    raw = load_raw(raw_dir)
    outlets = clean_outlets(raw["outlets"])
    stylists = clean_stylists(raw["stylists"])
    clients = clean_clients(raw["clients"], log)
    appts = clean_appointments(raw["appointments"], outlets, stylists, log)
    lines, smap = clean_service_lines(raw["service_lines"], appts, log)
    sales = clean_product_sales(raw["product_sales"], appts, log)
    visits = build_visits(appts, lines, sales)
    out = {"outlets": outlets, "stylists": stylists, "clients": clients, "appointments": appts,
           "service_lines": lines, "service_map": smap, "product_sales": sales, "visits": visits,
           "quality_log": log.frame(), "experiment_raw": raw["experiment"]}
    if save:
        out_dir.mkdir(parents=True, exist_ok=True)
        for k in ["appointments", "visits", "clients", "outlets"]:
            out[k].to_parquet(out_dir / f"{k}.parquet", index=False)
        smap.to_csv(out_dir / "service_name_map.csv", index=False)
        log.frame().to_csv(out_dir / "data_quality_log.csv", index=False)
    return out


if __name__ == "__main__":
    res = run_cleaning()
    print(res["quality_log"].to_string(index=False))
    print(no_show_by_regime(res["appointments"]).round(4))
    print(crosscheck_experiment(res["experiment_raw"], res["appointments"]))
