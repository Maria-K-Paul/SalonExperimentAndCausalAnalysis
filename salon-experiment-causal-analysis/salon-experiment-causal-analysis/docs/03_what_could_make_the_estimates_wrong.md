# What could make the causal estimates wrong?

This note covers each threat to the two causal claims: what it would do to the estimate, how it was checked,
and what remains open.

## A. Smart Reminders (randomised A/B test)

| # | Threat | What it would do | How it was checked / handled | Residual risk |
|---|---|---|---|---|
| 1 | **Broken randomisation or logging** | Arms not comparable; any bias | SRM by outlet and week found BB16 (261 control vs 132 treatment, p < 0.0001). Excluded from both arms; the chain-wide test alone (p = 0.35) would have missed it. With BB16: -2.5 pp | An undetected bug elsewhere; next-worst outlet p (Bonferroni) = 0.35 |
| 2 | **Chance imbalance** | Bias from a covariate | Max SMD = 0.075 (< 0.1); joint test p = 0.13; regression-adjusted estimate -2.62 pp vs -2.52 pp unadjusted | Low |
| 3 | **Interference / spillover** | Freed slots refilled by control clients; shared family phones → effect understated | Client-level randomisation | Effect is probably a slight *under*estimate |
| 4 | **Non-compliance** | 8.1% of treatment reminders not delivered → effect diluted | ITT reported; CACE -2.74 pp (CI -4.31 pp to -1.15 pp) | None for the decision |
| 5 | **Novelty effect** | Effect fades after the first weeks | Four-week run | 10% holdout for 90 days after rollout |
| 6 | **Outcome measurement** | No-shows mislabelled as cancellations | Rebuilt with timestamps and remarks; 99.9% agreement with the platform log | Small: ~0.1% of cancellations ambiguous |
| 7 | **Ratio-metric denominator** | Reminders create extra (rescheduled) bookings, which deflates the rate | No-shows *per client* (no denominator) also fell 19% | Low |
| 8 | **Mechanical retention lift** | Reschedules count as "returns" | Retention kept secondary; holdout to measure it properly | Medium for the retention claim |
| 9 | **Multiple comparisons** | False "winning" segments | 20 segment estimates with Holm correction and Q tests; only the opt-out harm signal is acted on | Segment stories are hypotheses |
| 10 | **Concurrent Glow Combos (North)** | Confounding | Randomised within outlets; effect in North -2.3 pp vs elsewhere -2.6 pp | Low |
| 11 | **External validity** | Different effect in other months or for walk-ins | Only opted-in, booked clients in Sep-Oct (festive) | Re-check after rollout |

## B. Glow Combos (difference-in-differences)

| # | Threat | What it would do | How it was checked / handled | Residual risk |
|---|---|---|---|---|
| 1 | **Parallel trends fail** | Bias of unknown sign | Pre-trend slope -0.3%/yr (p = 0.87); joint quarterly leads p = 0.75; flat event study; placebo launch in Jul 2025 (same season) -0.9 pp (p = 0.68) | Untestable *after* launch |
| 2 | **Wrong control group** | Biased estimate | Central fails (slope -5.3%/yr, p = 0.006); using it would give +2.2% instead of +9.5% | Low with South |
| 3 | **A North-only shock in Q3 2026** (IT hiring slump, road works, a new competitor) | Attributed to combos | Effect starts exactly in July and is stable Jul-Sep | Cannot be ruled out statistically; check with local managers |
| 4 | **Spillover:** men priced out in North move to South | Inflates South, overstating the visit loss | Not testable without client addresses | Visit loss may be overstated |
| 5 | **Composition** | Revenue per visit rises because low-ticket visits leave | Fixed-mix estimate +7.2% vs +9.5%; visits and total revenue reported alongside | Part of the RPV gain is mix |
| 6 | **Few clusters** (8 vs 7 outlets) | Over-confident standard errors | Wild cluster bootstrap (9,999 draws); randomisation inference, rank 1 of 6,435 | Low |
| 7 | **Anticipation** | Pre-period contaminated | No drift in the pre-launch months of the event study | Low |
| 8 | **Seasonality differs by zone** | Q3 bump misread as an effect | Placebo on Q3 2025 found nothing; log outcome makes seasonal swings proportional | Low |
| 9 | **Heavy-tailed bridal revenue** | Noisy, outlier-driven estimate | Excluding bridal: +9.1% | Low |
| 10 | **Concurrent reminder test (Sep)** | Confounding | Treatment share North 50.3% vs South 49.8%, so it differences out; reminders did not move revenue per visit | Low |
