# Data dictionary

All data is **synthetic**, produced by `src/generate_data.py` with seed 404 for a fictional chain. Run
`python src/generate_data.py` to rebuild it exactly. Raw files are in `data/raw/`. Cleaned tables are written to
`data/processed/` by `src/cleaning.py`, which the notebook calls.

## Raw files

| File | Rows | Grain |
|---|---|---|
| `appointments.csv.gz` | 304,810 | one booking or walk-in (includes 1,516 duplicate rows) |
| `service_lines.csv.gz` | 458,557 | one service on an appointment |
| `product_sales.csv.gz` | 39,061 | one retail sale |
| `clients.csv` | 72,259 | one registered client |
| `stylists.csv` | 286 | one stylist |
| `outlets.csv` | 22 | one outlet |
| `experiment_smart_reminders.csv` | 6,435 | one enrolled client in the A/B test |

### appointments.csv.gz
| Column | Meaning | Known issues |
|---|---|---|
| appointment_id | APT + 7 digits | 0.5% duplicated rows |
| outlet_id | BB01-BB22 | |
| client_id | C + 6 digits | **missing for most walk-ins** |
| stylist_id | ST + 3 digits | lower-case or padded in ~2%; missing for some walk-ins |
| booking_channel | Walk-in / Phone / WhatsApp / App | 9 spellings (e.g. 'walk in', 'Mobile App') |
| booked_at, scheduled_start, cancelled_at | timestamps | **BB07 and BB16 use dd-mm-yyyy**, the rest ISO |
| status | Completed / Cancelled / No Show | 7 spellings; **legacy tills record no-shows as 'Cancelled'** |
| remarks | free text from the front desk | e.g. 'NS', 'did not come', 'rescheduled' |

### service_lines.csv.gz
| Column | Meaning | Known issues |
|---|---|---|
| service_name | as typed in the till | **2,195 spellings of 38 services**: outlet-specific names, typos, case and spacing |
| list_price, net_amount | INR; net = 0 if not completed | **BB09 stores amounts as text with commas** |
| discount_pct | 0 / 10 / 15 / 20 | |

### product_sales.csv.gz
`sale_id, outlet_id, sale_datetime, appointment_id, client_id, product_name, product_category, qty, amount`.
About a third of sales have no appointment ID. They are linked by client + outlet + date where possible; the
rest are counter sales.

### experiment_smart_reminders.csv
| Column | Meaning |
|---|---|
| variant | control / treatment (some labels have different case or trailing spaces) |
| enrolled_on | date of the client's first eligible booking in the window |
| enrol_booking_lead_days, enrol_booking_channel | features of the enrolling booking (pre-treatment) |
| reminder_delivered | treatment only: did WhatsApp deliver? |
| opted_out | opted out of messages during the test |
| bookings_28d, no_shows_28d, cancellations_28d, completed_visits_28d, revenue_28d | outcomes in the 28 days from enrolment |
| returned_45d | 1 if the client completed a visit within 45 days after enrolment |

Known issues: 30 clients appear in both arms (a CRM duplicate-profile bug), and outlet BB16 under-logged
treatment clients in its first two weeks.

## What the simulation builds in

* **Seasonality:** Pongal and Thai weddings (Jan-Feb), the Aadi lull (mid-Jul to mid-Aug), Aavani weddings
  and Onam (late Aug-Sep), Diwali, a Tuesday dip, and annual price revisions every April.
* **Glow Combos:** bundled services from 1 Jul 2026 in the North zone, plus a 15% rise in the stand-alone
  men's haircut price.
* **Smart Reminders:** randomised by client hash, with effects that vary by booking lead time, channel and age.
* **Zone trends:** the Central zone premiumises over time, so it is a deliberately bad control.
