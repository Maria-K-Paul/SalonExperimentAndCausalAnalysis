# Viva preparation: likely questions and short answers

**1. Why is the no-show rate the primary metric, and not retention or revenue per visit?**
Reminders act on no-shows directly, so the effect shows up within weeks. Revenue per visit isn't something a
reminder should change, so it is a guardrail. Retention is the ultimate goal, but at our sample size it could
only detect a 3.7 pp change. Detecting 2 pp would need about 3.5 times the clients and a
45-day wait for everyone.

**2. Why randomise clients and not bookings?**
If bookings were randomised, the same client would get reminders on some bookings and not others, and
behaviour would carry over between them. Randomising clients keeps each client's experience consistent.
The analysis therefore treats clients as the independent units.

**3. How did you get the sample size?**
- Two-proportion power calculation: baseline 12.1%, MDE 2.5 pp, α 0.05 two-sided, 80% power.
- Multiplied by a design effect of 1.10, measured on history, because one client can have
  several correlated bookings.
- Converted to clients (2,095 per arm) and then to days using the historical enrolment
  rate: 21.3 days.

**4. Why run 28 days when 21 were enough?**
To cover whole weeks (salons have a strong weekly cycle, with a Tuesday dip and a weekend peak), to include a
payday, and to dilute any novelty effect. The extra week also adds a safety margin.

**5. What is sample ratio mismatch, and what did you find?**
An SRM means the arms are not the 50/50 split we designed. That signals a bug, not an effect. The chain-wide
test passed (p = 0.35), but by outlet, BB16 had 261 control clients against 132
treatment clients (p < 0.0001). Its WhatsApp integration started late, so no treatment clients
were logged in week 1.

**6. Why drop BB16 from both arms, rather than just the missing treatment clients?**
Those clients are not missing at random. BB16's surviving treatment clients are only late enrollees, so
comparing them with BB16's full control group would be biased. Dropping the whole outlet keeps the comparison
like-for-like. Keeping it changes almost nothing (-2.46 pp).

**7. Why the delta method or bootstrap, instead of a simple z-test on bookings?**
The no-show rate is a ratio of sums, and bookings from the same client are correlated. A booking-level z-test
would treat about 8,000 correlated bookings as independent, giving standard errors that are too small. The
delta method and the client bootstrap both treat the client as the unit, and they agree.

**8. What does "95% CI -3.97 pp to -1.08 pp" mean?**
If we repeated this experiment many times, 95% of intervals built this way would contain the true effect. The
whole interval is below zero, so reminders reduce no-shows. Even the least favourable plausible value is about
a 1 pp reduction.

**9. Why did CUPED help so little?**
CUPED removes variance in proportion to ρ², the squared correlation between a client's past and future
outcome. Here ρ is only 0.14: no-shows are rare yes/no events and most clients book about once a
month, so the past predicts one booking poorly. Regression adjustment with booking features reached
5.9%, about one week less in whole-week terms. For revenue per client it reached
14.8%.

**10. What is the parallel-trends assumption, and how did you check it?**
Without Glow Combos, North and South would have changed by the same proportion. It can't be proven after
launch, but it was checked before launch in four ways:
- a near-zero differential pre-trend (p = 0.87);
- jointly zero quarterly leads (p = 0.75);
- a flat monthly event study;
- placebo launch dates that find nothing, including one in the same season a year earlier.

**11. Why South and not Central as the control?**
Central fails the pre-trend test. Its revenue per visit drifted up about 5%
a year faster than North's because of premiumisation. Using it would have given
+2.2%, a biased answer.

**12. Why log revenue per visit?**
Seasonal swings are proportional: a wedding month raises spend by a percentage, not by a fixed amount in
rupees. Parallel trends is more plausible in percentages. The rupee version gives the same story
(+₹101 a visit).

**13. Why use a wild cluster bootstrap?**
With only 15 outlets (clusters), ordinary cluster-robust standard errors are too optimistic. The wild cluster
bootstrap and an exact permutation test (randomisation inference over all 6,435 ways to pick 8 "treated"
outlets) give reliable p-values with few clusters.

**14. Revenue per visit rose 9.5%. Why not call Glow Combos a success?**
Because visits fell 7.1%, mainly men put off by the 15% haircut price rise. Net revenue
changed by +1.8%, with a CI of -3.4% to
+7.4%, so it can't be distinguished from zero. Revenue per visit can rise just because
low-ticket customers leave. The right target is total revenue per outlet.

**15. How did you find the hidden no-shows, and how do you know the rule works?**
Legacy tills mark no-shows as "Cancelled", either at closing time or with no timestamp. Timestamps came first,
then remarks. The SalonCloud outlets, which record no-shows properly, served as a benchmark: after cleaning,
both till types show about the same rate (12.3% vs
12.5%). The rebuilt counts also match the reminder platform's log for
99.9% of clients.

**16. Why treat segment results as hypotheses?**
With 20 segment estimates, a few will look different by chance. None of the heterogeneity tests are
significant. The exception is the 55+ opt-out rate, a pre-registered harm guardrail, which is acted on.

**17. What would you do next?**
- Keep the 10% reminder holdout for 90 days to measure retention.
- Run Glow Combos as a staggered, randomised rollout in South, judged on total revenue.
- Build a real-time SRM alert into the experimentation platform.
