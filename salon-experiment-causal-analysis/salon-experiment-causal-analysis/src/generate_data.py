#!/usr/bin/env python3
"""Synthetic data generator for the Bloom & Blade case study.

Bloom & Blade Salon & Spa is a FICTIONAL 22-outlet chain in Coimbatore. Every
row is simulated, and the generator is seeded, so the data is reproducible:

    python src/generate_data.py

What the simulation builds in (so the analysis has something real to find)
-------------------------------------------------------------------------
* Coimbatore seasonality: Pongal and the Thai wedding season (Jan-Feb), the
  Aadi lull (mid-Jul to mid-Aug), Aavani weddings + Onam (late Aug-Sep), Diwali,
  and the Tuesday dip common to Tamil Nadu salons.
* "Glow Combos": a bundled service menu launched on 1 Jul 2026 in the 8 North-zone
  outlets only (last quarter's change, evaluated with difference-in-differences).
* "Smart Reminders": a WhatsApp reminder A/B test. Clients were enrolled at their
  first eligible booking scheduled 31 Aug - 27 Sep 2026 and randomised 50/50 by a
  hash of their client ID.
* The data-quality problems named in the brief - no-shows logged as cancellations,
  service names that differ by outlet, walk-ins without client IDs - plus duplicate
  rows, two date formats, amounts stored as text and messy categorical labels.

Outputs (data/raw/)
-------------------
outlets.csv, stylists.csv, clients.csv, appointments.csv.gz, service_lines.csv.gz,
product_sales.csv.gz, experiment_smart_reminders.csv
"""
from __future__ import annotations

import argparse
import hashlib
import json
from bisect import bisect_right
from datetime import date, datetime, timedelta
from itertools import accumulate
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 404
ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------------------
SIM_START = date(2024, 1, 1)      # one-year burn-in so returning clients exist on day one
DATA_START = date(2025, 1, 1)     # first scheduled date kept in the extract
DATA_END = date(2026, 11, 15)     # extract date
COMBO_LAUNCH = date(2026, 7, 1)   # Glow Combos go live in the North zone
EXP_START, EXP_END = date(2026, 8, 31), date(2026, 9, 27)  # enrolment window (scheduled date)
EXP_ACTIVE_END = date(2026, 10, 24)                         # reminders switched off
SRM_OUTLET, SRM_BUG_END = "BB16", date(2026, 9, 11)         # integration went live late here
POS_MIGRATION = {"BB12": date(2026, 3, 1)}                  # LegacyPOS -> SalonCloud
DIWALI = [date(2024, 10, 31), date(2025, 10, 20), date(2026, 11, 8)]

N_DAYS = (DATA_END - SIM_START).days + 1


def d2i(d: date) -> int:
    return (d - SIM_START).days


# --------------------------------------------------------------------------------------
# Outlets (localities are real Coimbatore areas; the chain itself is fictional)
# --------------------------------------------------------------------------------------
OUTLETS = [
    # id,   locality,          zone,      format,        opened, chairs, POS today
    ("BB01", "Saravanampatti", "North", "Salon & Spa", 2016, 10, "LegacyPOS"),
    ("BB02", "Ganapathy", "North", "Salon", 2017, 7, "LegacyPOS"),
    ("BB03", "Thudiyalur", "North", "Salon", 2018, 6, "LegacyPOS"),
    ("BB04", "Kavundampalayam", "North", "Salon & Spa", 2017, 9, "SalonCloud"),
    ("BB05", "Kalapatti", "North", "Salon", 2019, 7, "LegacyPOS"),
    ("BB06", "Vilankurichi", "North", "Salon", 2020, 6, "LegacyPOS"),
    ("BB07", "Saibaba Colony", "North", "Salon & Spa", 2015, 10, "LegacyPOS"),
    ("BB08", "Vadavalli", "North", "Salon", 2019, 7, "SalonCloud"),
    ("BB09", "Podanur", "South", "Salon", 2018, 6, "LegacyPOS"),
    ("BB10", "Kuniyamuthur", "South", "Salon & Spa", 2017, 9, "LegacyPOS"),
    ("BB11", "Sundarapuram", "South", "Salon", 2019, 7, "LegacyPOS"),
    ("BB12", "Ukkadam", "South", "Salon", 2016, 7, "SalonCloud"),
    ("BB13", "Selvapuram", "South", "Salon & Spa", 2018, 9, "LegacyPOS"),
    ("BB14", "Kovaipudur", "South", "Salon", 2020, 6, "LegacyPOS"),
    ("BB15", "Ramanathapuram", "South", "Salon & Spa", 2016, 10, "LegacyPOS"),
    ("BB16", "RS Puram", "Central", "Salon & Spa", 2014, 12, "LegacyPOS"),
    ("BB17", "Race Course", "Central", "Salon & Spa", 2015, 11, "SalonCloud"),
    ("BB18", "Gandhipuram", "Central", "Salon", 2014, 9, "LegacyPOS"),
    ("BB19", "Peelamedu", "Central", "Salon & Spa", 2016, 10, "LegacyPOS"),
    ("BB20", "Avinashi Road", "Central", "Salon & Spa", 2017, 10, "SalonCloud"),
    ("BB21", "Singanallur", "Central", "Salon", 2018, 8, "LegacyPOS"),
    ("BB22", "Town Hall", "Central", "Salon", 2015, 7, "LegacyPOS"),
]
# Service-name style used by each outlet's till (SalonCloud = style D).
LEGACY_STYLE = {"BB01": "A", "BB02": "B", "BB03": "C", "BB05": "A", "BB06": "B", "BB07": "C",
                "BB09": "B", "BB10": "A", "BB11": "C", "BB12": "A", "BB13": "B", "BB14": "C",
                "BB15": "A", "BB16": "B", "BB18": "C", "BB19": "A", "BB21": "B", "BB22": "C"}
DDMMYYYY_OUTLETS = {"BB07", "BB16"}   # export dates as dd-mm-yyyy
TEXT_AMOUNT_OUTLETS = {"BB09"}        # export amounts as "1,234.00"

# --------------------------------------------------------------------------------------
# Service catalogue: canonical name -> (category, 2024 base price in INR, premium flag)
# --------------------------------------------------------------------------------------
CATALOG = {
    "Haircut - Women": ("Hair", 550, 0), "Blow Dry": ("Hair", 450, 0),
    "Hair Spa": ("Hair", 1100, 1), "Root Touch-up": ("Hair", 1400, 1),
    "Global Hair Colour": ("Hair", 3200, 1), "Highlights": ("Hair", 3800, 1),
    "Keratin Treatment": ("Hair", 6000, 1), "Hair Smoothening": ("Hair", 5000, 1),
    "Hair Wash & Conditioning": ("Hair", 300, 0), "Head Massage": ("Hair", 300, 0),
    "Haircut - Men": ("Grooming", 320, 0), "Beard Trim": ("Grooming", 140, 0),
    "Shave": ("Grooming", 120, 0), "Hair Colour - Men": ("Grooming", 750, 1),
    "Hair Spa - Men": ("Grooming", 750, 1),
    "Threading - Eyebrows": ("Skin", 50, 0), "Threading - Upper Lip": ("Skin", 40, 0),
    "Clean-up": ("Skin", 650, 0), "Classic Facial": ("Skin", 1100, 1),
    "Gold Facial": ("Skin", 2000, 1), "De-tan Pack": ("Skin", 550, 0),
    "Waxing - Full Arms": ("Skin", 400, 0), "Waxing - Full Legs": ("Skin", 600, 0),
    "Manicure": ("Skin", 550, 0), "Pedicure": ("Skin", 750, 0),
    "Swedish Massage": ("Spa", 2300, 1), "Aromatherapy Massage": ("Spa", 2600, 1),
    "Foot Reflexology": ("Spa", 1100, 0), "Body Polish": ("Spa", 3000, 1),
    "Party Makeup": ("Occasion", 3200, 1), "Saree Draping": ("Occasion", 700, 0),
    "Mehendi": ("Occasion", 1400, 0), "Bridal Makeup": ("Occasion", 16000, 1),
    "Pre-bridal Package": ("Occasion", 11000, 1),
    # Glow Combos (North zone, from 1 Jul 2026) - priced off their parts
    "Glow Combo - Cut + Spa": ("Hair", 0, 1),
    "Glow Combo - Facial + Clean-up + Threading": ("Skin", 0, 1),
    "Glow Combo - Mani + Pedi": ("Skin", 0, 0),
    "Groom Combo - Haircut + Beard": ("Grooming", 0, 0),
}
COMBO_PARTS = {
    "Glow Combo - Cut + Spa": (("Haircut - Women", "Hair Spa"), 0.88),
    "Glow Combo - Facial + Clean-up + Threading": (("Classic Facial", "Clean-up", "Threading - Eyebrows"), 0.88),
    "Glow Combo - Mani + Pedi": (("Manicure", "Pedicure"), 0.88),
    "Groom Combo - Haircut + Beard": (("Haircut - Men", "Beard Trim"), 0.92),
}
# How each till style spells the same service (A/B/C = legacy tills, D = SalonCloud)
ALIASES = {
    "Haircut - Women": ("Haircut - Women", "Ladies Hair Cut", "HAIRCUT (F)", "Women's Haircut"),
    "Blow Dry": ("Blow Dry", "Blowdry", "BLOW DRY/STYLING", "Blow-dry & Styling"),
    "Hair Spa": ("Hair Spa", "Hairspa", "HAIR SPA TREATMENT", "Spa - Hair"),
    "Root Touch-up": ("Root Touch-up", "Root Touchup", "ROOT TOUCH UP (AMMONIA FREE)", "Hair Colour - Roots"),
    "Global Hair Colour": ("Global Hair Colour", "Global Colour", "GLOBAL HAIR COLOR", "Hair Colour - Global"),
    "Highlights": ("Highlights", "Hair Highlights", "HIGHLIGHTS - FULL", "Hair Colour - Highlights"),
    "Keratin Treatment": ("Keratin Treatment", "Keratin", "KERATIN TREATMENT (SHOULDER LENGTH)", "Keratin Smoothing"),
    "Hair Smoothening": ("Hair Smoothening", "Smoothening", "HAIR SMOOTHENING", "Smoothening Treatment"),
    "Hair Wash & Conditioning": ("Hair Wash & Conditioning", "Hair Wash", "WASH + CONDITION", "Wash & Condition"),
    "Head Massage": ("Head Massage", "Head Massage (Oil)", "HEAD MASSAGE 20 MIN", "Champi / Head Massage"),
    "Haircut - Men": ("Haircut - Men", "Gents Hair Cut", "HAIRCUT (M)", "Men's Haircut"),
    "Beard Trim": ("Beard Trim", "Beard Shaping", "BEARD TRIM/SHAPE", "Beard Styling"),
    "Shave": ("Shave", "Clean Shave", "SHAVE", "Classic Shave"),
    "Hair Colour - Men": ("Hair Colour - Men", "Gents Hair Colour", "HAIR COLOR (M)", "Men's Hair Colour"),
    "Hair Spa - Men": ("Hair Spa - Men", "Gents Hair Spa", "HAIR SPA (M)", "Men's Hair Spa"),
    "Threading - Eyebrows": ("Threading - Eyebrows", "Eyebrow Threading", "THREADING EYEBROW", "Eyebrows (Threading)"),
    "Threading - Upper Lip": ("Threading - Upper Lip", "Upper Lip Threading", "THREADING UPPERLIP", "Upper Lip (Threading)"),
    "Clean-up": ("Clean-up", "Cleanup", "CLEAN UP (BASIC)", "Express Clean-up"),
    "Classic Facial": ("Classic Facial", "Fruit Facial", "FACIAL - CLASSIC", "Facial - Classic Glow"),
    "Gold Facial": ("Gold Facial", "Facial Gold", "GOLD FACIAL (60 MIN)", "Facial - Gold Radiance"),
    "De-tan Pack": ("De-tan Pack", "D-Tan", "DETAN (FACE & NECK)", "De-Tan Treatment"),
    "Waxing - Full Arms": ("Waxing - Full Arms", "Full Arms Wax", "WAX FULL ARMS (RICA)", "Arms Waxing (Full)"),
    "Waxing - Full Legs": ("Waxing - Full Legs", "Full Legs Wax", "WAX FULL LEGS (RICA)", "Legs Waxing (Full)"),
    "Manicure": ("Manicure", "Manicure Classic", "MANICURE", "Classic Manicure"),
    "Pedicure": ("Pedicure", "Pedicure Classic", "PEDICURE", "Classic Pedicure"),
    "Swedish Massage": ("Swedish Massage", "Body Massage - Swedish", "SWEDISH MASSAGE 60 MIN", "Massage - Swedish (60)"),
    "Aromatherapy Massage": ("Aromatherapy Massage", "Aroma Massage", "AROMATHERAPY 60 MIN", "Massage - Aromatherapy (60)"),
    "Foot Reflexology": ("Foot Reflexology", "Foot Massage", "REFLEXOLOGY (FOOT)", "Reflexology - Foot"),
    "Body Polish": ("Body Polish", "Body Polishing", "BODY POLISH", "Body Polish & Glow"),
    "Party Makeup": ("Party Makeup", "Party Make-up", "MAKEUP - PARTY", "Makeup - Party / Reception"),
    "Saree Draping": ("Saree Draping", "Saree Drape", "SAREE DRAPING", "Draping - Saree"),
    "Mehendi": ("Mehendi", "Mehandi", "MEHENDI (BOTH HANDS)", "Henna / Mehendi"),
    "Bridal Makeup": ("Bridal Makeup", "Bridal Make-up", "MAKEUP - BRIDAL (HD)", "Makeup - Bridal"),
    "Pre-bridal Package": ("Pre-bridal Package", "Pre Bridal Pack", "PRE-BRIDAL PACKAGE", "Bridal Prep Package"),
    "Glow Combo - Cut + Spa": ("Glow Combo - Cut + Spa", "Combo: Haircut + Hairspa", "GLOW COMBO (CUT+SPA)", "Combo - Haircut & Hair Spa"),
    "Glow Combo - Facial + Clean-up + Threading": ("Glow Combo - Facial + Clean-up + Threading", "Combo: Facial+Cleanup+Threading", "GLOW COMBO (FACIAL+CU+TH)", "Combo - Facial, Clean-up & Threading"),
    "Glow Combo - Mani + Pedi": ("Glow Combo - Mani + Pedi", "Combo: Mani+Pedi", "GLOW COMBO (MANI+PEDI)", "Combo - Manicure & Pedicure"),
    "Groom Combo - Haircut + Beard": ("Groom Combo - Haircut + Beard", "Combo: Gents Cut+Beard", "GROOM COMBO (CUT+BEARD)", "Combo - Men's Haircut & Beard"),
}
STYLE_IDX = {"A": 0, "B": 1, "C": 2, "D": 3}

CORE = {
    "Hair": [("Haircut - Women", .55), ("Hair Spa", .16), ("Blow Dry", .08), ("Root Touch-up", .08),
             ("Global Hair Colour", .05), ("Highlights", .03), ("Keratin Treatment", .025), ("Hair Smoothening", .025)],
    "Skin": [("Threading - Eyebrows", .30), ("Clean-up", .18), ("Classic Facial", .14), ("Gold Facial", .07),
             ("Waxing - Full Arms", .10), ("Waxing - Full Legs", .06), ("Manicure", .07), ("Pedicure", .08)],
    "Grooming": [("Haircut - Men", .72), ("Beard Trim", .14), ("Shave", .05), ("Hair Colour - Men", .05),
                 ("Hair Spa - Men", .04)],
    "Spa": [("Swedish Massage", .40), ("Aromatherapy Massage", .25), ("Foot Reflexology", .20), ("Body Polish", .15)],
    "Occasion": [("Party Makeup", .55), ("Saree Draping", .15), ("Mehendi", .15), ("Bridal Makeup", .10),
                 ("Pre-bridal Package", .05)],
}
ADDONS = {
    "Hair": [("Head Massage", .12), ("Hair Wash & Conditioning", .08), ("Threading - Eyebrows", .22)],
    "Skin": [("Threading - Upper Lip", .30), ("De-tan Pack", .12), ("Pedicure", .06)],
    "Grooming": [("Beard Trim", .35), ("Head Massage", .12), ("De-tan Pack", .05)],
    "Spa": [("Head Massage", .20), ("Pedicure", .10)],
    "Occasion": [("Saree Draping", .25), ("Threading - Eyebrows", .30)],
}
PRODUCTS = [  # name, category, MRP
    ("Argan Oil Shampoo 250ml", "Hair care", 650), ("Keratin Conditioner 200ml", "Hair care", 720),
    ("Hair Serum 100ml", "Hair care", 550), ("Onion Hair Oil 200ml", "Hair care", 399),
    ("Hair Mask 200g", "Hair care", 890), ("Colour Protect Shampoo 250ml", "Hair care", 780),
    ("Vitamin C Serum 30ml", "Skin care", 899), ("Sunscreen SPF50 50g", "Skin care", 599),
    ("Face Wash 100ml", "Skin care", 349), ("De-tan Scrub 100g", "Skin care", 450),
    ("Night Cream 50g", "Skin care", 1250), ("Hair Wax 50g", "Styling", 350),
    ("Heat Protect Spray 150ml", "Styling", 650), ("Volumising Mousse 200ml", "Styling", 750),
    ("Beard Oil 30ml", "Men's grooming", 399), ("Beard Wash 100ml", "Men's grooming", 349),
    ("Aftershave Balm 100ml", "Men's grooming", 449),
]
PRODUCT_BY_VISIT = {"Hair": [0, 1, 2, 3, 4, 5, 11, 12, 13], "Skin": [6, 7, 8, 9, 10], "Grooming": [14, 15, 16, 11, 3],
                    "Spa": [6, 7, 10, 8], "Occasion": [6, 7, 12, 13]}

AGE_BANDS = ["18-24", "25-34", "35-44", "45-54", "55+"]
CHANNELS = ["Walk-in", "Phone", "WhatsApp", "App"]
WALK, PHONE, WHATSAPP, APP = 0, 1, 2, 3
# Outcomes
DONE, ADVCX, LATECX, NOSHOW = 0, 1, 2, 3

SEGMENT_CHANNEL_PROBS = {  # by age band: Walk-in, Phone, WhatsApp, App
    0: [.15, .17, .35, .33], 1: [.15, .22, .35, .28], 2: [.16, .32, .34, .18],
    3: [.18, .42, .30, .10], 4: [.22, .48, .25, .05],
}
LEAD_VALUES = list(range(0, 61))


def _lead_cum(occasion: bool) -> list[float]:
    p = np.zeros(61)
    if occasion:
        p[1:4] = .10 / 3; p[4:8] = .20 / 4; p[8:15] = .30 / 7; p[15:31] = .30 / 16; p[31:61] = .10 / 30
    else:
        p[0], p[1], p[2], p[3] = .20, .26, .14, .10
        p[4:8] = .20 / 4; p[8:15] = .08 / 7; p[15:22] = .02 / 7
    return list(accumulate(p / p.sum()))


LEAD_CUM = _lead_cum(False)
LEAD_CUM_OCC = _lead_cum(True)
HOURS = list(range(9, 21))
HOUR_CUM_WEEKDAY = list(accumulate(np.array([.5, .7, .8, .8, .7, .6, .7, .9, 1.2, 1.5, 1.4, 1.0]) / 10.8))
HOUR_CUM_WEEKEND = list(accumulate(np.array([.8, 1.1, 1.3, 1.3, 1.2, 1.1, 1.1, 1.1, 1.1, 1.0, .9, .7]) / 12.7))
DOW_WEIGHT = np.array([0.95, 0.65, 0.95, 1.0, 1.1, 1.35, 1.3])  # Mon..Sun (Tuesday dip)
DOW_WEIGHT = DOW_WEIGHT / DOW_WEIGHT.mean()

# Smart Reminders effect: share of would-be no-shows converted by a delivered reminder
Q_SHOW, Q_RESCHED = 0.15, 0.18
OPTOUT_BY_AGE = [0.010, 0.012, 0.015, 0.025, 0.065]
NO_SHOW_SCALE = 0.87


# --------------------------------------------------------------------------------------
# Calendar curves
# --------------------------------------------------------------------------------------
def _periodic(anchors: list[tuple[str, float]]) -> np.ndarray:
    xs, ys = [], []
    for y in range(SIM_START.year - 1, DATA_END.year + 2):
        for md, v in anchors:
            m, d = map(int, md.split("-"))
            xs.append((date(y, m, d) - SIM_START).days)
            ys.append(v)
    order = np.argsort(xs)
    return np.interp(np.arange(N_DAYS), np.array(xs)[order], np.array(ys)[order])


def _festival_bump(dates: list[date], before: int, height: float) -> np.ndarray:
    b = np.zeros(N_DAYS)
    for dd in dates:
        c = d2i(dd)
        for k in range(-before, 2):
            i = c + k
            if 0 <= i < N_DAYS:
                w = (1 - abs(k) / (before + 1)) if k <= 0 else 0.3
                b[i] = max(b[i], height * w)
    return b


def _in_ranges(ranges: list[tuple[str, str]]) -> np.ndarray:
    days = pd.date_range(SIM_START, DATA_END)
    md = days.month * 100 + days.day
    out = np.zeros(N_DAYS, dtype=bool)
    for s, e in ranges:
        s_ = int(s.replace("-", "")); e_ = int(e.replace("-", ""))
        out |= ((md >= s_) & (md <= e_)) if s_ <= e_ else ((md >= s_) | (md <= e_))
    return out


DEMAND = _periodic([("01-01", 1.05), ("01-12", 1.20), ("01-20", 1.10), ("02-10", 1.10), ("03-01", 1.00),
                    ("04-01", 0.98), ("04-14", 1.08), ("05-01", 1.00), ("05-25", 1.05), ("06-15", 0.92),
                    ("07-01", 0.90), ("07-25", 0.85), ("08-15", 0.92), ("08-28", 1.08), ("09-15", 1.10),
                    ("09-30", 1.00), ("10-15", 1.05), ("11-01", 1.08), ("11-30", 0.97), ("12-15", 1.00),
                    ("12-24", 1.15), ("12-31", 1.10)]) * (1 + _festival_bump(DIWALI, 10, 0.25))
PREMIUM = _periodic([("01-01", 1.05), ("01-15", 1.18), ("02-10", 1.15), ("03-01", 1.00), ("04-01", 0.90),
                     ("05-01", 0.90), ("05-25", 0.92), ("06-15", 0.84), ("07-01", 0.88), ("07-25", 0.96),
                     ("08-15", 1.08), ("08-28", 1.30), ("09-15", 1.35), ("09-30", 1.18), ("10-15", 1.10),
                     ("11-01", 1.15), ("11-30", 1.00), ("12-24", 1.12), ("12-31", 1.06)]) \
    * (1 + _festival_bump(DIWALI, 10, 0.12))
OCCASION_MULT = np.ones(N_DAYS)
OCCASION_MULT[_in_ranges([("03-15", "05-14"), ("10-18", "12-15")])] = 1.5
OCCASION_MULT[_in_ranges([("01-15", "02-13"), ("05-15", "06-14"), ("08-17", "09-16")])] = 3.5
OCCASION_MULT[_in_ranges([("07-17", "08-16"), ("12-16", "01-13")])] = 0.3   # Aadi, Margazhi
AADI = _in_ranges([("07-17", "08-16")])
_days = pd.date_range(SIM_START, DATA_END)
DOW = _days.dayofweek.values
PRICE_REV = np.where(_days >= pd.Timestamp("2026-04-01"), 1.05 ** 2,
                     np.where(_days >= pd.Timestamp("2025-04-01"), 1.05, 1.0))
MONTHS_SINCE_START = (_days.year - SIM_START.year) * 12 + (_days.month - 1)
CENTRAL_PRICE_DRIFT = 1 + 0.004 * MONTHS_SINCE_START   # Central zone premiumisation
CENTRAL_MIX_DRIFT = 1 + 0.006 * MONTHS_SINCE_START
LAM = np.cumsum(DEMAND / DEMAND.mean())                  # "operational time" for revisit gaps
COMBO_I, EXP_S_I, EXP_E_I = d2i(COMBO_LAUNCH), d2i(EXP_START), d2i(EXP_END)
EXP_ACTIVE_END_I, SRM_BUG_END_I = d2i(EXP_ACTIVE_END), d2i(SRM_BUG_END)
DATA_START_I, LAST_I = d2i(DATA_START), N_DAYS - 1


def assignment(client_id: str) -> str:
    """Stable 50/50 assignment from a salted hash of the client ID."""
    h = int(hashlib.md5(f"SR2026:{client_id}".encode()).hexdigest(), 16)
    return "treatment" if h % 2 else "control"


def round10(x: float) -> int:
    return int(round(x / 10.0)) * 10


# --------------------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------------------
class Sim:
    def __init__(self, seed: int = SEED):
        self.rng = np.random.default_rng(seed)
        self.r = self.rng.random
        self.o_ids = [o[0] for o in OUTLETS]
        self.o_zone = [o[2] for o in OUTLETS]
        self.o_spa = [o[3] == "Salon & Spa" for o in OUTLETS]
        self.o_chairs = [o[5] for o in OUTLETS]
        rng = self.rng
        self.o_price = [float(rng.uniform(*{"North": (1.00, 1.06), "South": (0.95, 1.01),
                                             "Central": (1.04, 1.10)}[z])) for z in self.o_zone]
        self._make_stylists()
        self.events: list[tuple] = []     # appointment events
        self.lines: list[tuple] = []      # (event_idx, canonical, list_price, discount)
        self.sales: list[tuple] = []      # (event_idx|None, outlet, day, minute_of_day, client|None, product_idx, qty)
        self.enrol: dict[int, dict] = {}

    # ---------------- stylists ----------------
    def _make_stylists(self):
        rng = self.rng
        rows, active = [], []
        sid = 0
        for o, (oid, _, _, _, opened, chairs, _) in enumerate(OUTLETS):
            per_day = [[] for _ in range(N_DAYS)]
            for _slot in range(chairs + int(rng.integers(0, 2))):
                start = d2i(date(max(opened, 2014), 1, 1)) + int(rng.integers(0, 365 * 4))
                start = min(start, d2i(date(2023, 12, 1)))
                while start <= LAST_I:
                    level = rng.choice(["Junior", "Senior", "Master"], p=[.35, .45, .20])
                    tenure = int(rng.exponential(1100))
                    end = start + tenure
                    sid += 1
                    st_id = f"ST{sid:03d}"
                    join = SIM_START + timedelta(days=start) if start >= 0 else SIM_START - timedelta(days=-start)
                    exit_ = SIM_START + timedelta(days=end) if end <= LAST_I else None
                    rows.append((st_id, oid, str(level), str(rng.choice(["F", "M"], p=[.62, .38])),
                                 join.isoformat(), exit_.isoformat() if exit_ else ""))
                    lv = {"Junior": 0, "Senior": 1, "Master": 2}[str(level)]
                    for i in range(max(start, 0), min(end, LAST_I) + 1):
                        per_day[i].append((st_id, lv))
                    start = end + int(rng.integers(7, 45))
            active.append(per_day)
        st = pd.DataFrame(rows, columns=["stylist_id", "outlet_id", "level", "gender", "join_date", "exit_date"])
        live = (st["join_date"] <= DATA_END.isoformat()) & ((st["exit_date"] == "") | (st["exit_date"] >= DATA_START.isoformat()))
        self.stylists = st[live].reset_index(drop=True)
        self.active = active

    def pick_stylist(self, o: int, i: int, premium: bool):
        pool = self.active[o][i]
        if not pool:
            return None, 1
        if premium:
            w = [(3.0, 2.0, 1.0)[2 - lv] for _, lv in pool]  # Master 3, Senior 2, Junior 1
        else:
            w = [(2.0, 2.0, 1.0)[lv] for _, lv in pool]       # Junior 2, Senior 2, Master 1
        cum = list(accumulate(w))
        k = bisect_right(cum, self.r() * cum[-1])
        return pool[min(k, len(pool) - 1)]

    # ---------------- prices & baskets ----------------
    def price(self, svc: str, o: int, i: int, lv: int) -> int:
        if svc in COMBO_PARTS:
            parts, f = COMBO_PARTS[svc]
            return round10(f * sum(self.price(p, o, i, lv) for p in parts))
        cat, base, _ = CATALOG[svc]
        x = base * PRICE_REV[i] * self.o_price[o]
        if self.o_zone[o] == "Central":
            x *= CENTRAL_PRICE_DRIFT[i]
        if svc == "Haircut - Men" and self.o_zone[o] == "North" and i >= COMBO_I:
            x *= 1.15                       # menu restructure that came with Glow Combos
        if cat in ("Hair", "Grooming"):
            x *= (0.95, 1.0, 1.15)[lv]
        return round10(x)

    def basket(self, cat: str, o: int, i: int, spend: float) -> tuple[list[str], bool]:
        r = self.r
        prem = PREMIUM[i] * spend * (CENTRAL_MIX_DRIFT[i] if self.o_zone[o] == "Central" else 1.0)
        opts = CORE[cat]
        w = [p * (prem ** 2.5 if CATALOG[s][2] else 1.0) for s, p in opts]
        cum = list(accumulate(w))
        core = opts[min(bisect_right(cum, r() * cum[-1]), len(opts) - 1)][0]
        svcs = [core]
        for s, p in ADDONS[cat]:
            if s not in svcs and r() < min(0.9, p * prem):
                svcs.append(s)
        combo = False
        if self.o_zone[o] == "North" and i >= COMBO_I:
            if cat == "Hair" and core in ("Haircut - Women", "Blow Dry", "Hair Spa") and r() < 0.10:
                svcs = ["Glow Combo - Cut + Spa"] + [s for s in svcs[1:] if s != "Hair Wash & Conditioning"]
                combo = True
            elif cat == "Skin" and core in ("Clean-up", "Threading - Eyebrows", "Classic Facial") and r() < 0.06:
                svcs = ["Glow Combo - Facial + Clean-up + Threading"] + [s for s in svcs[1:] if not s.startswith("Threading")]
                combo = True
            elif cat == "Skin" and core in ("Manicure", "Pedicure") and r() < 0.25:
                svcs = ["Glow Combo - Mani + Pedi"] + [s for s in svcs[1:] if s not in ("Manicure", "Pedicure")]
                combo = True
            elif cat == "Grooming" and core == "Haircut - Men" and "Beard Trim" in svcs and r() < 0.6:
                svcs = ["Groom Combo - Haircut + Beard"] + [s for s in svcs[1:] if s != "Beard Trim"]
                combo = True
        return svcs, combo

    def visit_discount(self, i: int, cat: str) -> float:
        if cat == "Occasion":
            return 0.0
        if AADI[i]:
            return 0.15 if self.r() < 0.20 else 0.0     # "Aadi offer"
        return 0.10 if self.r() < 0.08 else 0.0

    def dow_shift(self, target: int, lo: int) -> int:
        """Nudge a target day by up to +/-2 days towards busier weekdays."""
        cands, ws = [], []
        for off, base in zip((-2, -1, 0, 1, 2), (0.5, 0.8, 1.0, 0.8, 0.5)):
            d = target + off
            if lo <= d <= LAST_I:
                cands.append(d)
                ws.append(base * DOW_WEIGHT[DOW[d]])
        if not cands:
            return min(max(target, lo), LAST_I)
        cum = list(accumulate(ws))
        return cands[min(bisect_right(cum, self.r() * cum[-1]), len(cands) - 1)]

    def hour(self, i: int) -> int:
        cum = HOUR_CUM_WEEKEND if DOW[i] >= 5 else HOUR_CUM_WEEKDAY
        return HOURS[min(bisect_right(cum, self.r()), 11)]

    # ---------------- recording ----------------
    def record(self, client, o, cat, ch, created_i, created_min, day, start_min, outcome, cancel_min,
               spend, resched=False, treated=False):
        """Store one appointment + its service lines + any product sale."""
        r = self.r
        prem_flag = cat in ("Occasion", "Spa")
        st_id, lv = self.pick_stylist(o, day, prem_flag)
        svcs, combo = self.basket(cat, o, day, spend)
        disc = self.visit_discount(day, cat)
        ev = len(self.events)
        self.events.append((client, o, cat, ch, created_i, created_min, day, start_min, outcome, cancel_min,
                            st_id, combo, resched, treated))
        for s in svcs:
            self.lines.append((ev, s, self.price(s, o, day, lv), disc))
        if outcome == DONE:
            female = cat in ("Hair", "Skin", "Spa", "Occasion")
            p = (0.13 if female else 0.07) * PREMIUM[day] ** 0.5 * (1.25 if combo else 1.0)
            if r() < p:
                pool = PRODUCT_BY_VISIT[cat]
                n_items = 1 if r() < 0.85 else 2
                for _ in range(n_items):
                    pidx = pool[int(r() * len(pool))]
                    self.sales.append((ev, o, day, start_min + 60 + int(r() * 45), client, pidx,
                                       1 if r() < 0.9 else 2))
        return ev

    # ---------------- client lifecycles ----------------
    def run_clients(self):
        rng, r = self.rng, self.r
        n_o = len(OUTLETS)
        base_new = np.array([0.36 * c for c in self.o_chairs])
        growth = np.ones((n_o, N_DAYS))
        for o in range(n_o):
            if self.o_zone[o] == "Central":
                growth[o] = 1 + 0.004 * MONTHS_SINCE_START
            # slow-moving outlet shocks (stylist churn, road works, a new competitor ...)
            shocks = np.repeat(rng.normal(0, 0.03, N_DAYS // 30 + 2), 30)[:N_DAYS]
            growth[o] *= np.exp(shocks)
        lam = base_new[:, None] * DEMAND[None, :] * DOW_WEIGHT[DOW][None, :] * growth
        counts = rng.poisson(lam)
        c_o, c_day = np.nonzero(counts)
        reps = counts[c_o, c_day]
        c_o = np.repeat(c_o, reps); c_day = np.repeat(c_day, reps)
        n = len(c_o)
        zone = np.array(self.o_zone)[c_o]
        spa = np.array(self.o_spa)[c_o]
        fem_p = np.where(spa, 0.68, 0.52)
        female = rng.random(n) < fem_p
        age_p = {"North": [.22, .38, .22, .11, .07], "South": [.15, .30, .27, .17, .11],
                 "Central": [.17, .33, .26, .15, .09]}
        age = np.empty(n, dtype=int)
        for z, p in age_p.items():
            m = zone == z
            age[m] = rng.choice(5, size=m.sum(), p=p)
        cat = np.empty(n, dtype=object)
        u = rng.random(n)
        cat[female & spa] = np.where(u[female & spa] < .45, "Hair", np.where(u[female & spa] < .85, "Skin", "Spa"))
        cat[female & ~spa] = np.where(u[female & ~spa] < .52, "Hair", "Skin")
        cat[~female & spa] = np.where(u[~female & spa] < .88, "Grooming", np.where(u[~female & spa] < .94, "Skin", "Spa"))
        cat[~female & ~spa] = np.where(u[~female & ~spa] < .94, "Grooming", "Skin")
        interval = np.array([{"Grooming": 30, "Hair": 45, "Skin": 32, "Spa": 55}[c] for c in cat]) \
            * rng.lognormal(0, 0.3, n)
        churn = rng.beta(2.2, 13, n)
        churn_first = np.clip(0.22 + rng.beta(2, 8, n), 0, 0.9)
        ns_age = np.array([1.35, 1.1, 0.95, 0.8, 0.7])[age]
        ns_prop = np.clip(rng.beta(0.8, 5.5, n) * ns_age, 0, 0.85)
        cx_prop = rng.beta(1.5, 18, n)
        spend = rng.lognormal(0, 0.4, n)
        chan = np.empty(n, dtype=int)
        for a in range(5):
            m = age == a
            p = np.array(SEGMENT_CHANNEL_PROBS[a], dtype=float)
            chan[m & female] = rng.choice(4, size=(m & female).sum(), p=p)
            pm = p.copy(); pm[WALK] += 0.10; pm /= pm.sum()
            chan[m & ~female] = rng.choice(4, size=(m & ~female).sum(), p=pm)
        optin = rng.random(n) < np.where(age == 4, 0.78, 0.88)
        acq = rng.choice(["Walk-in", "Instagram", "Google", "Referral", "Justdial", "Corporate tie-up"],
                         size=n, p=[.34, .18, .17, .18, .08, .05])
        chan_cum = {a: list(accumulate(SEGMENT_CHANNEL_PROBS[a])) for a in range(5)}

        self.clients = pd.DataFrame({
            "client_idx": np.arange(n), "outlet": c_o, "signup_day": c_day, "female": female, "age": age,
            "cat": cat, "optin": optin, "acq": acq, "chan": chan, "ns_prop": ns_prop})

        for k in range(n):
            cid = f"C{k + 1:06d}"
            o, t = int(c_o[k]), int(c_day[k])
            zone_k, fem, a = self.o_zone[o], bool(female[k]), int(age[k])
            north_men = (zone_k == "North") and not fem
            nvis = 0
            enrolled = False
            variant = None
            lost = delivered = opted = reminded = False
            enrol_i = -1
            first = True
            while t <= LAST_I:
                ccat = cat[k]
                if fem and r() < 0.015 * OCCASION_MULT[t]:
                    ccat = "Occasion"
                if first:
                    ch = int(chan[k]) if r() < 0.7 else WALK      # first visits skew walk-in
                else:
                    ch = int(chan[k]) if r() < 0.75 else min(bisect_right(chan_cum[a], r()), 3)
                if ccat == "Occasion" and ch == WALK:
                    ch = PHONE
                created_min = 8 * 60 + int(r() * 14 * 60)
                if ch == WALK:
                    day = self.dow_shift(t, t)
                    lead = 0
                    created_i = day
                else:
                    cumL = LEAD_CUM_OCC if ccat == "Occasion" else LEAD_CUM
                    lead = LEAD_VALUES[min(bisect_right(cumL, r()), 60)]
                    created_i = t
                    day = t if lead == 0 else self.dow_shift(t + lead, t + 1)
                    lead = day - t
                if day > LAST_I:
                    break
                hr = self.hour(day)
                start_min = hr * 60 + (int(r() * 60) if ch == WALK else (30 if r() < 0.5 else 0))
                if ch == WALK:
                    created_min = max(start_min - int(r() * 20), 0)
                elif lead == 0 and created_min > start_min - 60:
                    created_min = max(start_min - 60 - int(r() * 120), 0)
                # ---------- outcome ----------
                outcome, cancel_min, resched, treated_now = DONE, None, False, False
                if ch != WALK:
                    lead_mult = 0.55 if lead == 0 else 0.85 if lead == 1 else 1.0 if lead <= 3 \
                        else 1.3 if lead <= 7 else 1.5 if lead <= 14 else 1.6
                    slot_mult = 1.2 if hr >= 18 else 1.1 if hr <= 10 else 1.0
                    p_ns = min(ns_prop[k] * lead_mult * slot_mult * NO_SHOW_SCALE, 0.7)
                    u = r()
                    if u < p_ns:
                        outcome = NOSHOW if r() < 0.86 else LATECX
                    elif u < p_ns + cx_prop[k]:
                        outcome = ADVCX
                    # ---- Smart Reminders experiment ----
                    if not enrolled and optin[k] and EXP_S_I <= day <= EXP_E_I:
                        enrolled, enrol_i = True, day
                        variant = assignment(cid)
                        lost = variant == "treatment" and self.o_ids[o] == SRM_OUTLET and day <= SRM_BUG_END_I
                        delivered = variant == "treatment" and not lost and r() < 0.92
                        self.enrol[k] = {"client_id": cid, "outlet": o, "enrol_i": day, "variant": variant,
                                         "lost": lost, "delivered": delivered, "lead": lead, "channel": ch,
                                         "opted_out": False}
                    if (enrolled and variant == "treatment" and delivered and not opted
                            and enrol_i <= day <= EXP_ACTIVE_END_I):
                        treated_now = True
                        if not reminded:
                            reminded = True
                            if r() < OPTOUT_BY_AGE[a]:
                                opted = True
                                self.enrol[k]["opted_out"] = True
                        eff = 1.0
                        if ch == APP:
                            eff *= 0.35            # app users already get push notifications
                        if a == 4:
                            eff *= 0.35            # 55+ respond less to WhatsApp nudges
                        if lead == 0:
                            eff *= 0.5             # same-day booking: only a 2-hour reminder
                        elif lead >= 4:
                            eff *= 1.2             # long lead time = more forgetting to fix
                        if outcome in (NOSHOW, LATECX):
                            v = r()
                            if v < Q_SHOW * eff:
                                outcome = DONE
                            elif v < (Q_SHOW + Q_RESCHED) * eff:
                                outcome, resched = ADVCX, True
                        elif outcome == DONE and r() < 0.012:
                            outcome, resched = ADVCX, True   # one-tap reschedule makes cancelling easy
                    lo = created_i * 1440 + created_min
                    hi = day * 1440 + start_min - 120          # the 2-hour policy line
                    if outcome == ADVCX and hi <= lo:
                        outcome, resched = LATECX, False        # booked <2h ahead: can only cancel late
                    if outcome == ADVCX:
                        if resched:   # tapped "reschedule" on the reminder (24h, or 2h for same-day)
                            cm = day * 1440 + start_min - (int(20 * 60 + r() * 240) if lead >= 1 else int(125 + r() * 55))
                            cancel_min = min(max(cm, lo + 1), hi)
                        else:
                            cancel_min = int(lo + r() * (hi - lo))
                    elif outcome == LATECX:
                        cancel_min = max(day * 1440 + start_min - int(10 + r() * 105), lo + 1)
                self.record(cid, o, ccat, ch, created_i, created_min, day, start_min,
                            outcome, cancel_min, spend[k], resched, treated_now)
                first = False
                # ---------- what happens next ----------
                gap_mult = 1.15 if (north_men and day >= COMBO_I) else 1.0
                if outcome == DONE:
                    nvis += 1
                    pc = churn_first[k] if nvis == 1 else churn[k]
                    if north_men and day >= COMBO_I:
                        pc += 0.05
                    if r() < pc:
                        break
                    g = rng.gamma(4.0, interval[k] / 4.0) * gap_mult
                    t = int(np.searchsorted(LAM, LAM[day] + g))
                elif outcome == ADVCX:
                    cday = cancel_min // 1440
                    if resched and r() < 0.85:
                        t = cday + 1 + int(r() * 8)
                    elif r() < 0.70:
                        t = cday + int(r() * 8)
                    elif r() < 0.67:
                        t = int(np.searchsorted(LAM, LAM[day] + rng.gamma(4.0, interval[k] / 4.0) * gap_mult))
                    else:
                        break
                    t = max(t, created_i + 1)
                else:  # no-show or late cancel
                    if r() < 0.50:
                        t = day + 2 + int(r() * 13)
                    elif r() < 0.60:
                        t = int(np.searchsorted(LAM, LAM[day] + rng.gamma(4.0, interval[k] / 4.0) * gap_mult))
                    else:
                        break
                t = max(t, day + 1) if outcome != ADVCX else t

    def run_anonymous_walkins(self):
        rng, r = self.rng, self.r
        n_o = len(OUTLETS)
        base = np.array([0.50 * c for c in self.o_chairs])
        lam = base[:, None] * DEMAND[None, :] * DOW_WEIGHT[DOW][None, :]
        north = np.array([z == "North" for z in self.o_zone])
        counts = rng.poisson(lam)
        for o in range(n_o):
            for i in np.nonzero(counts[o])[0]:
                for _ in range(counts[o, i]):
                    male = r() < 0.65
                    if male and north[o] and i >= COMBO_I and r() < 0.15:
                        continue  # some price-sensitive men stop walking in after the menu change
                    ccat = "Grooming" if male else ("Skin" if r() < 0.6 else "Hair")
                    hr = self.hour(int(i))
                    sm = hr * 60 + int(r() * 60)
                    self.record(None, o, ccat, WALK, int(i), max(sm - 10, 0), int(i), sm, DONE, None, 0.85)

    def counter_sales(self):
        rng = self.rng
        counts = rng.poisson(0.45, size=(len(OUTLETS), N_DAYS))
        for o, i in zip(*np.nonzero(counts)):
            for _ in range(counts[o, i]):
                self.sales.append((None, int(o), int(i), 10 * 60 + int(self.r() * 600), None,
                                   int(self.r() * len(PRODUCTS)), 1))


# --------------------------------------------------------------------------------------
# Raw-file writers (this is where the realistic mess gets added)
# --------------------------------------------------------------------------------------
def _fmt_dt(day_i: np.ndarray, minute: np.ndarray, ddmm: np.ndarray, with_seconds: bool = True) -> np.ndarray:
    base = pd.Timestamp(SIM_START)
    ts = base + pd.to_timedelta(day_i, unit="D") + pd.to_timedelta(minute, unit="m")
    iso = ts.strftime("%Y-%m-%d %H:%M:%S" if with_seconds else "%Y-%m-%d %H:%M")
    dm = ts.strftime("%d-%m-%Y %H:%M")
    return np.where(ddmm, dm, iso)


def _typo(s: str, rng: np.random.Generator) -> str:
    """Introduce one realistic typo outside any bracketed text."""
    cut = s.find("(")
    head, tail = (s, "") if cut < 0 else (s[:cut], s[cut:])
    idx = [i for i, ch in enumerate(head) if ch.isalpha()]
    if len(idx) < 5:
        return s
    i = idx[int(rng.integers(1, len(idx) - 1))]
    if rng.random() < 0.5:
        head = head[:i] + head[i + 1:]                         # dropped letter
    elif i + 1 < len(head) and head[i + 1].isalpha():
        head = head[:i] + head[i + 1] + head[i] + head[i + 2:]  # swapped letters
    return head + tail


def build_raw(sim: Sim, out_dir: Path, truth_dir: Path | None, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed + 1)
    ev = pd.DataFrame(sim.events, columns=["client", "o", "cat", "ch", "created_i", "created_min", "day",
                                           "start_min", "outcome", "cancel_min", "stylist_id", "combo",
                                           "resched", "treated"])
    ev["ev"] = np.arange(len(ev))
    keep = (ev["day"] >= DATA_START_I) & (ev["day"] <= LAST_I)
    ev = ev[keep].sort_values(["day", "start_min", "o"], kind="stable").reset_index(drop=True)
    ev["appointment_id"] = [f"APT{i + 1:07d}" for i in range(len(ev))]
    ev["outlet_id"] = np.array(sim.o_ids)[ev["o"].values]
    is_walk = ev["ch"].values == WALK
    # walk-ins: the till rarely captures who the customer was
    has_client = ev["client"].notna().values
    drop_id = is_walk & has_client & (rng.random(len(ev)) < 0.85)
    ev["client_id"] = np.where(has_client & ~drop_id, ev["client"].values, None)
    ev["true_client"] = ev["client"]
    ddmm = ev["outlet_id"].isin(DDMMYYYY_OUTLETS).values

    # ---- POS regime per row ----
    pos = np.array([o[6] for o in OUTLETS])[ev["o"].values]
    for oid, mig in POS_MIGRATION.items():
        m = (ev["outlet_id"].values == oid) & (ev["day"].values < d2i(mig))
        pos = np.where(m, "LegacyPOS", pos)
    legacy = pos == "LegacyPOS"

    n = len(ev)
    out = ev["outcome"].values
    status = np.empty(n, dtype=object)
    u = rng.random(n)
    status[out == DONE] = np.where(u[out == DONE] < .90, "Completed", np.where(u[out == DONE] < .97, "completed", "Done"))
    status[out == ADVCX] = np.where(u[out == ADVCX] < .85, "Cancelled", np.where(u[out == ADVCX] < .95, "CANCELLED", "Canceled"))
    status[out == LATECX] = "Cancelled"
    ns = out == NOSHOW
    status[ns & legacy] = np.where(u[ns & legacy] < .95, "Cancelled", "CANCELLED")   # the core problem
    status[ns & ~legacy] = "No Show"

    cancel_min = ev["cancel_min"].astype("float").values
    canc_abs = np.full(n, np.nan)
    m = (out == ADVCX) | (out == LATECX)
    canc_abs[m] = cancel_min[m]
    # legacy tills: staff "cancel" no-shows at closing time, or leave the timestamp blank
    eod = ev["day"].values * 1440 + 21 * 60 + (rng.random(n) * 90).astype(int)
    blank = rng.random(n) < 0.40
    canc_abs[ns & legacy & ~blank] = eod[ns & legacy & ~blank]
    # 3% of genuine advance cancellations are missing their timestamp too
    canc_abs[(out == ADVCX) & (rng.random(n) < 0.03)] = np.nan
    has_c = ~np.isnan(canc_abs)
    cancelled_at = np.full(n, None, dtype=object)
    cancelled_at[has_c] = _fmt_dt((canc_abs[has_c] // 1440).astype(int), (canc_abs[has_c] % 1440).astype(int),
                                  ddmm[has_c])

    remarks = np.full(n, None, dtype=object)
    ns_txt = ["NS", "no show", "No-show", "did not come", "DNC", "not reachable", "client didnt turn up",
              "no response on call"]
    cx_txt = ["customer cancelled", "rescheduled", "called to cancel", "cancelled by client - travel",
              "will come next week", "sick", "rain", "office work"]
    late_txt = ["called last minute", "late cancel", "cancelled 1 hr before"]
    rr = rng.random(n)
    pick = lambda arr, k: np.array(arr, dtype=object)[rng.integers(0, len(arr), k)]
    mm = ns & (rr < .45); remarks[mm] = pick(ns_txt, mm.sum())
    mm = (out == ADVCX) & (rr < .35); remarks[mm] = pick(cx_txt, mm.sum())
    mm = (out == LATECX) & (rr < .40); remarks[mm] = pick(late_txt, mm.sum())
    mm = ev["resched"].values & (rr < 0.6); remarks[mm] = "rescheduled via WhatsApp"

    ch_raw = np.array(CHANNELS, dtype=object)[ev["ch"].values]
    v = rng.random(n)
    ch_raw = np.where((ch_raw == "Walk-in") & (v < .08), "walk in", ch_raw)
    ch_raw = np.where((ch_raw == "Walk-in") & (v > .96), "WALKIN", ch_raw)
    ch_raw = np.where((ch_raw == "Phone") & (v < .10), "phone call", ch_raw)
    ch_raw = np.where((ch_raw == "WhatsApp") & (v < .15), "Whatsapp", ch_raw)
    ch_raw = np.where((ch_raw == "App") & (v < .20), "Mobile App", ch_raw)

    st = ev["stylist_id"].astype(object).values.copy()
    w = rng.random(n)
    st = np.where(is_walk & (w < 0.04), None, st)
    st = np.array([s.lower() if (s is not None and x < 0.012) else (f" {s}" if s is not None and x > 0.99 else s)
                   for s, x in zip(st, rng.random(n))], dtype=object)

    appts = pd.DataFrame({
        "appointment_id": ev["appointment_id"], "outlet_id": ev["outlet_id"], "client_id": ev["client_id"],
        "stylist_id": st, "booking_channel": ch_raw,
        "booked_at": _fmt_dt(ev["created_i"].values, ev["created_min"].values, ddmm),
        "scheduled_start": _fmt_dt(ev["day"].values, ev["start_min"].values, ddmm),
        "status": status, "cancelled_at": cancelled_at, "remarks": remarks,
    })
    # POS sync duplicates (~0.5%)
    dup = appts.sample(frac=0.005, random_state=7)
    appts = pd.concat([appts, dup]).sort_values("appointment_id", kind="stable").reset_index(drop=True)

    # ---- service lines ----
    ln = pd.DataFrame(sim.lines, columns=["ev", "svc", "list_price", "disc"])
    ev_map = ev[["ev", "appointment_id", "o", "outcome", "day"]]
    ln = ln.merge(ev_map, on="ev", how="inner")
    ln["line_no"] = ln.groupby("appointment_id").cumcount() + 1
    style = []
    for o, d in zip(ln["o"].values, ln["day"].values):
        oid = sim.o_ids[o]
        if oid in POS_MIGRATION and d >= d2i(POS_MIGRATION[oid]):
            style.append(3)
        elif OUTLETS[o][6] == "SalonCloud" and oid not in POS_MIGRATION:
            style.append(3)
        else:
            style.append(STYLE_IDX[LEGACY_STYLE[oid]])
    names = np.array([ALIASES[s][k] for s, k in zip(ln["svc"].values, style)], dtype=object)
    z = rng.random(len(ln))
    names = np.array([
        (nm.lower() if x < .02 else nm.upper() if x < .035 else f"{nm} " if x < .05 else nm.replace(" ", "  ", 1)
         if x < .06 else _typo(nm, rng) if x < .075 else nm) for nm, x in zip(names, z)], dtype=object)
    net = np.where(ln["outcome"].values == DONE, np.round(ln["list_price"].values * (1 - ln["disc"].values)), 0.0)
    lines = pd.DataFrame({"appointment_id": ln["appointment_id"], "line_no": ln["line_no"],
                          "service_name": names, "list_price": ln["list_price"].astype(float),
                          "discount_pct": (ln["disc"] * 100).round().astype(int), "net_amount": net})
    txt = ln["o"].map(lambda o: sim.o_ids[o] in TEXT_AMOUNT_OUTLETS).values
    lines["list_price"] = lines["list_price"].astype(object)
    lines["net_amount"] = lines["net_amount"].astype(object)
    lines.loc[txt, "list_price"] = [f"{x:,.2f}" for x in lines.loc[txt, "list_price"].astype(float)]
    lines.loc[txt, "net_amount"] = [f"{x:,.2f}" for x in lines.loc[txt, "net_amount"].astype(float)]
    lines = lines.sort_values(["appointment_id", "line_no"]).reset_index(drop=True)

    # ---- product sales ----
    sl = pd.DataFrame(sim.sales, columns=["ev", "o", "day", "minute", "client", "pidx", "qty"])
    sl["ev"] = pd.to_numeric(sl["ev"]).astype("float64")
    sl = sl[(sl["day"] >= DATA_START_I) & (sl["day"] <= LAST_I)].copy()
    sl = sl.merge(ev[["ev", "appointment_id"]].assign(ev=lambda d: d["ev"].astype("float64")), on="ev", how="left")
    sl = sl.sort_values(["day", "minute"], kind="stable").reset_index(drop=True)
    k = rng.random(len(sl))
    linked = sl["appointment_id"].notna().values
    keep_appt = linked & (k < 0.78)
    keep_client = linked & (k >= 0.78) & (k < 0.92) & sl["client"].notna().values
    sales = pd.DataFrame({
        "sale_id": [f"PS{i + 1:06d}" for i in range(len(sl))],
        "outlet_id": np.array(sim.o_ids)[sl["o"].values],
        "sale_datetime": _fmt_dt(sl["day"].values, sl["minute"].values, np.zeros(len(sl), dtype=bool)),
        "appointment_id": np.where(keep_appt, sl["appointment_id"], None),
        "client_id": np.where(keep_appt | keep_client, sl["client"], None),
        "product_name": [PRODUCTS[p][0] for p in sl["pidx"]],
        "product_category": [PRODUCTS[p][1] for p in sl["pidx"]],
        "qty": sl["qty"].values,
        "amount": [PRODUCTS[p][2] * q for p, q in zip(sl["pidx"], sl["qty"])],
    })

    # ---- clients ----
    cl = sim.clients
    ids = [f"C{k + 1:06d}" for k in cl["client_idx"]]
    g = np.where(cl["female"], "F", "M").astype(object)
    gv = rng.random(len(cl))
    g = np.where(gv < .10, np.where(cl["female"], "Female", "Male"), g)
    g = np.where((gv >= .10) & (gv < .14), np.where(cl["female"], "female", "male"), g)
    g = np.where(gv > .985, None, g)
    ab = np.array(AGE_BANDS, dtype=object)[cl["age"].values]
    av = rng.random(len(cl))
    ab = np.where((ab == "55+") & (av < .2), "55 +", ab)
    ab = np.where(av > .965, None, ab)
    clients = pd.DataFrame({
        "client_id": ids, "gender": g, "age_band": ab,
        "signup_date": (pd.Timestamp(SIM_START) + pd.to_timedelta(cl["signup_day"], unit="D")).dt.strftime("%Y-%m-%d"),
        "home_outlet_id": np.array(sim.o_ids)[cl["outlet"].values],
        "whatsapp_opt_in": np.where(cl["optin"], "Y", "N"),
        "acquisition_channel": cl["acq"].values,
    })

    # ---- outlets ----
    outlets = pd.DataFrame([
        {"outlet_id": o[0], "outlet_name": f"Bloom & Blade - {o[1]}", "locality": o[1], "zone": o[2],
         "format": o[3], "opened_year": o[4], "chairs": o[5], "pos_system": o[6],
         "pos_migrated_on": POS_MIGRATION.get(o[0], "")} for o in OUTLETS])
    outlets["pos_migrated_on"] = outlets["pos_migrated_on"].astype(str)

    # ---- experiment file (assignment log + outcome extract) ----
    exp = build_experiment(sim, ev, sales_truth=sl, rng=rng)

    out_dir.mkdir(parents=True, exist_ok=True)
    outlets.to_csv(out_dir / "outlets.csv", index=False)
    sim.stylists.to_csv(out_dir / "stylists.csv", index=False)
    clients.to_csv(out_dir / "clients.csv", index=False)
    appts.to_csv(out_dir / "appointments.csv.gz", index=False, compression="gzip")
    lines.to_csv(out_dir / "service_lines.csv.gz", index=False, compression="gzip")
    sales.to_csv(out_dir / "product_sales.csv.gz", index=False, compression="gzip")
    exp.to_csv(out_dir / "experiment_smart_reminders.csv", index=False)

    if truth_dir is not None:   # ground truth for the author's own checks; not shipped
        truth_dir.mkdir(parents=True, exist_ok=True)
        ev[["appointment_id", "outcome", "ch", "true_client", "combo", "resched", "treated", "cat"]] \
            .to_parquet(truth_dir / "appointments_truth.parquet")
        pd.DataFrame(list(sim.enrol.values())).to_parquet(truth_dir / "enrolment_truth.parquet")

    return {"appointments": len(appts), "service_lines": len(lines), "product_sales": len(sales),
            "clients": len(clients), "stylists": len(sim.stylists), "outlets": len(outlets),
            "experiment_rows": len(exp)}


def build_experiment(sim: Sim, ev: pd.DataFrame, sales_truth: pd.DataFrame, rng) -> pd.DataFrame:
    en = pd.DataFrame(list(sim.enrol.values()))
    en = en[~en["lost"]].copy()       # the BB14 bug: early treatment enrolments never reached the log
    # outcomes are computed from what the CRM can see: bookings and walk-ins captured with an ID
    recorded = ev[ev["client_id"].notna()][["client_id", "appointment_id", "ev", "ch", "day", "outcome"]]
    rev_lines = pd.DataFrame(sim.lines, columns=["ev", "svc", "list_price", "disc"])
    rev_lines["net"] = np.round(rev_lines["list_price"] * (1 - rev_lines["disc"]))
    svc_rev = rev_lines.groupby("ev")["net"].sum()
    prod = sales_truth.dropna(subset=["ev"]).copy()
    prod["amt"] = [PRODUCTS[p][2] * q for p, q in zip(prod["pidx"], prod["qty"])]
    prod["ev"] = prod["ev"].astype("int64")
    prod_rev = prod.groupby("ev")["amt"].sum()
    recorded = recorded.assign(revenue=lambda d: np.where(
        d["outcome"] == DONE, d["ev"].map(svc_rev).fillna(0) + d["ev"].map(prod_rev).fillna(0), 0.0))
    m = recorded.merge(en[["client_id", "enrol_i"]], on="client_id", how="inner")
    in28 = (m["day"] >= m["enrol_i"]) & (m["day"] <= m["enrol_i"] + 27) & (m["ch"] != WALK)
    w = m[in28]
    agg = w.groupby("client_id").agg(
        bookings_28d=("appointment_id", "size"),
        no_shows_28d=("outcome", lambda s: int(((s == NOSHOW) | (s == LATECX)).sum())),
        cancellations_28d=("outcome", lambda s: int((s == ADVCX).sum())),
        completed_visits_28d=("outcome", lambda s: int((s == DONE).sum())),
        revenue_28d=("revenue", "sum"))
    ret = m[(m["day"] > m["enrol_i"]) & (m["day"] <= m["enrol_i"] + 45) & (m["outcome"] == DONE)]
    returned = ret.groupby("client_id").size().rename("visits_45d")
    en = en.merge(agg, left_on="client_id", right_index=True, how="left").merge(
        returned, left_on="client_id", right_index=True, how="left")
    for c in ["bookings_28d", "no_shows_28d", "cancellations_28d", "completed_visits_28d"]:
        en[c] = en[c].fillna(0).astype(int)
    en["revenue_28d"] = en["revenue_28d"].fillna(0).round(0)
    en["returned_45d"] = (en["visits_45d"].fillna(0) > 0).astype(int)
    ctrl = en["variant"] == "control"
    en.loc[ctrl, "opted_out"] = rng.random(ctrl.sum()) < 0.004     # SMS "STOP" replies in control
    en["enrolled_on"] = (pd.Timestamp(SIM_START) + pd.to_timedelta(en["enrol_i"], unit="D")).dt.strftime("%Y-%m-%d")
    en["outlet_id"] = np.array(sim.o_ids)[en["outlet"].values]
    en["zone"] = np.array(sim.o_zone)[en["outlet"].values]
    en["enrol_booking_channel"] = np.array(CHANNELS)[en["channel"].values]
    en = en.sort_values(["enrol_i", "client_id"]).reset_index(drop=True)
    out = pd.DataFrame({
        "experiment_id": "SR-2026-09", "client_id": en["client_id"], "outlet_id": en["outlet_id"],
        "zone": en["zone"], "variant": en["variant"], "enrolled_on": en["enrolled_on"],
        "enrol_booking_lead_days": en["lead"], "enrol_booking_channel": en["enrol_booking_channel"],
        "reminder_delivered": np.where(en["variant"] == "treatment", en["delivered"], False),
        "opted_out": en["opted_out"].astype(bool),
        "bookings_28d": en["bookings_28d"], "no_shows_28d": en["no_shows_28d"],
        "cancellations_28d": en["cancellations_28d"], "completed_visits_28d": en["completed_visits_28d"],
        "revenue_28d": en["revenue_28d"], "returned_45d": en["returned_45d"],
    })
    # messy labels + a CRM duplicate-profile bug that put ~30 clients in both arms
    lab = rng.random(len(out))
    out.loc[lab < 0.02, "variant"] = out.loc[lab < 0.02, "variant"].str.capitalize()
    out.loc[(lab >= 0.02) & (lab < 0.025), "variant"] = out.loc[(lab >= 0.02) & (lab < 0.025), "variant"] + " "
    cross = out.sample(30, random_state=11).copy()
    cross["variant"] = np.where(cross["variant"].str.strip().str.lower() == "control", "treatment", "control")
    out = pd.concat([out, cross]).sort_values(["enrolled_on", "client_id"], kind="stable").reset_index(drop=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--truth", default=None, help="optional folder for ground-truth labels (author checks)")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    t0 = datetime.now()
    sim = Sim(args.seed)
    sim.run_clients()
    sim.run_anonymous_walkins()
    sim.counter_sales()
    stats = build_raw(sim, Path(args.out), Path(args.truth) if args.truth else None, args.seed)
    stats["seconds"] = round((datetime.now() - t0).total_seconds(), 1)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
