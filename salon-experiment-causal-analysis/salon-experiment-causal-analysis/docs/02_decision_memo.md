# Decision memo: Smart Reminders and Glow Combos

**To:** Leadership team, Bloom & Blade Salon & Spa · **From:** Maria K Paul · **Date:** 16 Nov 2026

## Decisions

| Initiative | Decision | One-line reason |
|---|---|---|
| **Smart Reminders** (WhatsApp reminders) | **GO**, with two conditions | No-shows fell **20%** in a clean randomised test; no chain-level guardrail breached |
| **Glow Combos** (North zone, since 1 Jul) | **EXTEND**: fix pricing, then a staggered rollout | Revenue per visit really rose **+9.5%**, not the claimed +23.5%; visits fell 7.1%, so total revenue moved by about zero |

## 1. Smart Reminders: GO

* **Primary result:** no-show rate **12.4% → 9.8%**,
  -2.5 pp (95% CI -4.0 pp to -1.1 pp), p = 0.0006. That is about 2,300 fewer no-shows a year
  across the chain.
* **Guardrails held:**
  * Revenue per completed visit -0.1% (CI -6.0% to +6.1%).
  * Completed visits per client +1.5%.
  * Opt-outs 1.5%, against a 3% limit.
* **Validity:** one outlet (BB16) logged no treatment clients in week 1, a late integration. It was caught
  by the outlet-level SRM check and excluded. Including it gives the same answer (-2.5 pp).
* **Who lost:** clients aged **55+** saw no benefit and opted out at **5.1%**, above the 5%
  segment guardrail.

**Conditions:**
1. Exclude 55+ clients from WhatsApp by default and give them a call or SMS reminder instead.
2. Fix BB16's integration and keep a **10% holdout for 90 days** to measure retention (45-day return
   +1.3 pp, not yet significant).

Messaging costs about ₹0.59 lakh a year (assumed rate). That is small next to up to
₹35 lakh of chair time freed, which is only realised if the freed slots are resold.

## 2. Glow Combos: EXTEND, don't scale yet

* **The claim:** North's revenue per visit rose +23.5% from Q2 to Q3. But South, with no
  combos, rose +13.7% too: Aavani weddings, Onam and festive demand.
* **Difference-in-differences** against South (the comparable zone; Central failed the pre-trend test):
  * Revenue per visit **+9.5% (95% CI +6.1% to +13.2%)**, about
    ₹101 a visit.
  * Visits **-7.1%**, driven by men's grooming (-11%)
    after the 15% haircut price rise.
  * **Total revenue +1.8% (95% CI -3.4% to +7.4%)**, about
    ₹2.3 lakh in Q3, indistinguishable from zero.
* **Checks passed:** flat pre-launch event study, placebo launch dates (p = 0.68 and
  0.62), and randomisation inference (rank 1 of 6,435).

**Action:**
1. Undo the men's haircut increase, or price the Groom Combo at the old haircut price.
2. Roll combos out to South with **randomised timing** (half the outlets now, half in 8 weeks).
3. Judge success on **total revenue per outlet**, not revenue per visit.

## What could change these conclusions

* **Reminders:** a logging bug we did not detect; novelty wearing off (the holdout will show it); and the
  test covered booked, opted-in clients in a festive month only.
* **Combos:** a North-only shock in Q3 2026 (cannot be ruled out after the fact); men switching to South
  outlets (would overstate the visit loss); and only 15 outlets, which is why wild bootstrap and permutation
  tests were used.
