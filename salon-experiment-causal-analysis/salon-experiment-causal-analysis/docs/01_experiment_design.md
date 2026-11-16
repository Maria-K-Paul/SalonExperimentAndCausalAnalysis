# Experiment design: Smart Reminders A/B test

**Bloom & Blade Salon & Spa** (fictional, 22 outlets, Coimbatore) · Design frozen 24 Aug 2026, before launch ·
Prepared by Maria K Paul

## 1. Problem

Once hidden no-shows are recovered from the till data, **12.4% of bookings
end as no-shows or last-minute cancellations**. The tills record only 2.3%,
because 17 outlets log no-shows as "Cancelled". Every no-show is an idle stylist hour that could have been sold.

## 2. Initiative and hypothesis

**Smart Reminders:** a WhatsApp message 24 hours before each booking (2 hours for same-day bookings) with
one-tap **Confirm** and **Reschedule** buttons.

* **H0:** reminders do not change the no-show rate.
* **H1:** reminders change the no-show rate. The test is two-sided because a reminder could also annoy
  people. We expect a reduction.
* **Mechanism:** clients who would forget are prompted, and clients who can't make it reschedule early
  enough for the slot to be resold.

## 3. Design at a glance

| Item | Choice | Why |
|---|---|---|
| Unit of randomisation | Client | A client must not see reminders on some bookings and not others |
| Allocation | 50 / 50, salted MD5 hash of client ID | Stable, auditable, no assignment table to corrupt |
| Eligible | Booked appointments (not walk-ins) by known clients who opted in to WhatsApp | Reminders need a phone number and consent (WhatsApp Business policy, India's DPDP Act 2023) |
| Enrolment | First eligible booking scheduled 31 Aug - 27 Sep 2026 | Four full weeks |
| Exposure | Every booking of a treatment client until 24 Oct | Covers each client's whole outcome window |
| Outcome window | 28 days from enrolment (primary); 45 days (retention) | Same window for every client |
| Control experience | Existing SMS booking confirmation only | Business as usual |

## 4. Metrics

| Role | Metric | Definition | Threshold / expectation |
|---|---|---|---|
| **Primary** | **No-show rate** | (no-shows + cancellations <2h before start) ÷ bookings, in 28 days | Detect a **2.5 pp** drop |
| Secondary | No-shows per client | no-shows ÷ enrolled clients | Robust to extra rescheduled bookings |
| Secondary | 45-day return rate | completed visit within 45 days after enrolment | Retention signal |
| Guardrail | Revenue per completed visit | service + retail revenue ÷ completed visits | Breach if significantly worse **and** below -3% |
| Guardrail | Completed visits per client | completed bookings ÷ clients | Breach if significantly worse **and** below -3% |
| Guardrail | WhatsApp opt-out rate | opt-outs ÷ treatment clients | ≤ 3% overall, ≤ 5% in any age band |
| Monitor | Advance-cancellation rate | cancellations ≥2h before start ÷ bookings | Expected to **rise** (reschedules) |

**Why no-show rate is primary.** Reminders act on no-shows directly, and the effect shows up within weeks.
Revenue per visit is a guardrail, because reminders do not change what a client buys. Retention (45-day
return) is the long-run goal, but at this sample size it can only detect a 3.7 pp change, so
it would need about 3.5 times the clients and a 45-day wait for everyone. It is tracked as a secondary metric and,
after rollout, through a holdout group.

## 5. Power analysis and duration

Inputs come from history: a planning cohort that replays the enrolment rule on the four weeks starting
2026-06-29, with 28-day follow-up.

| Input | Value |
|---|---|
| Baseline no-show rate (eligible bookings) | 12.12% |
| Bookings per client in 28 days | 1.27 |
| Design effect (clustered vs. naive variance, measured) | 1.10 |
| New eligible clients per day | 197 |
| MDE | 2.5 pp (21% relative) |
| α / power | 0.05 two-sided / 80% |

| Step | Result |
|---|---|
| Bookings per arm (two-proportion test, Cohen's h) | 2,426 |
| × design effect | 2,670 |
| ÷ bookings per client = clients per arm | **2,095** |
| Enrolment days needed | **21.3** |
| **Planned run** | **4 full weeks (28 days)** |

The run is rounded up to whole weeks to cover the weekly cycle (Tuesday dip, weekend peak), a month-start
payday and any novelty effect.

**Sensitivity:**

| MDE (pp) | Relative | Clients per arm | Enrolment days | Weeks |
|---|---|---|---|---|
| 1.5 | 12% | 6,066 | 61.7 | 9 |
| 2.0 | 16% | 3,344 | 34.0 | 5 |
| 2.5 | 21% | 2,095 | 21.3 | 4 |
| 3.0 | 25% | 1,423 | 14.5 | 3 |
| 3.5 | 29% | 1,022 | 10.4 | 2 |

**What the guardrails can and cannot detect.** At the planned size, revenue per visit can only detect
changes of about ±9%. Guardrails are harm detectors: they catch large damage, but they
are not powered to prove "no change". Their confidence intervals are reported so readers can judge for
themselves.

**A/A check.** Splitting the historical cohort at random 2,000 times flagged 5.0% of
splits at p < 0.05, against an expected 5%. The spread of fake effects (0.82 pp) matches the
delta-method standard error (0.82 pp), so the planned test is calibrated.

## 6. Data-integrity checks (before reading any result)

1. **Sample ratio mismatch (SRM):** a χ² test of the 50/50 split, chain-wide **and by outlet and week**
   (Bonferroni across outlets). If p < 0.001, the cause is fixed before any analysis.
2. **Covariate balance:** standardised mean differences on pre-period behaviour must be < 0.1, plus a joint
   test that covariates cannot predict assignment.
3. **Crossovers:** any client found in both arms is excluded from both arms.
4. **Outcome audit:** experiment counts are reconciled against the cleaned appointment table.

## 7. Analysis plan

* **Primary estimate:** difference in booking-weighted no-show rates. The 95% CI uses the delta method with
  clients as independent units. A client-level bootstrap (10,000 resamples) and a Welch t-test on per-client
  rates serve as cross-checks.
* **Relative effect:** CI from the delta method on the log ratio.
* **Non-compliance:** reminders that could not be delivered are analysed as assigned (intention-to-treat).
  The effect on clients who actually got the message (CACE) is reported as a secondary number.
* **Variance reduction:** CUPED, plus regression adjustment on pre-period behaviour and the enrolling
  booking's own features (lead time, slot, channel, age).
* **Pre-specified segments:** age band, booking channel, lead time, no-show history, gender, zone.
  Holm-corrected p-values plus a heterogeneity (Q) test per dimension. Segment results are hypotheses
  unless the heterogeneity test is significant.

## 8. Decision rules (fixed in advance)

| Outcome | Rule |
|---|---|
| **GO** | Primary 95% CI entirely below 0 **and** no chain-level guardrail breached. A segment-level breach means a targeted fix, not a stop. |
| **NO-GO** | Primary CI entirely above 0, **or** any chain-level guardrail breached |
| **EXTEND** | Primary CI includes 0. Keep running up to the sample needed for the observed effect, or stop if even the CI's best case is below the MDE. |

The horizon is fixed: no interim peeking at the primary metric. Daily dashboards show only SRM and
guardrails, for safety.

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Integration or logging failure at an outlet | SRM checked by outlet and by week |
| Interference (freed slots go to control clients; shared family phones) | Client-level randomisation; effect may be slightly understated |
| Novelty effect | Four-week run, then a 10% holdout kept after rollout |
| Annoyance and opt-outs | Opt-out guardrail, overall and by age band |
| Concurrent Glow Combos in North | Randomisation within outlets, so both arms are exposed equally |
| No-shows mislabelled in legacy tills | Outcome rebuilt from timestamps and remarks, and audited against the platform log |
