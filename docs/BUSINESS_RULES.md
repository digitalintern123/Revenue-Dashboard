# Business Rules & KPI Calculations

Formulas and rules as implemented. Function names are given so they can be
found with a search (line numbers change too often to be useful).

---

## 1. KPI formulas

| KPI | Formula | Code |
|---|---|---|
| Revenue / PAX change % | (current − previous) ÷ previous; `None` when previous is 0 or missing | `revenue_analysis.pct_change` |
| Penetration % (PEN %) | PAX ÷ traffic × 100 | `revenue_analysis.penetration_pct` |
| Spend per pax (SPP) | revenue ÷ traffic | `revenue_analysis.spp` |
| Revenue per PAX | revenue ÷ PAX | `revenue_analysis.safe_div` |
| AOP variance % | (actual − AOP) ÷ AOP | `pct_change(actual, aop)` |

**PAX vs traffic:** PAX = Encalm customers served (`revenue_master.pax`);
traffic = everyone passing through the terminal (`airport_traffic.traffic`).
They are never interchangeable.

## 2. Thresholds and trends

`revenue_analysis.GROWTH_THRESHOLD = 0.05`, `DECLINE_THRESHOLD = -0.05` —
never hard-code 0.05 elsewhere.

- `classify_trend`: below −5 % → decline, above +5 % → increase, otherwise
  stable; `None` → "—".
- `classify_trend_with_new`: as above, plus previous = 0 and current > 0 →
  "🆕 New".

## 3. Comparison periods — `revenue_analysis.resolve_comparison_ranges`

| Compare by | Current | Compared with |
|---|---|---|
| Day-wise | the report date | the chosen compare date (default: the previous date with data) |
| Week-wise | Mon–Sun of the report week (*Full Period*) or Mon–report date (*To-Date*) | the chosen earlier week, same span |
| Month-wise | the report month (full or to-date) | the chosen month, same span |
| Year-wise | the report's **financial year** (1 Apr – 31 Mar): full FY, or *To-Date* = 1 Apr to the report date | the chosen FY over the same span (To-Date: 1 Apr to the same day and month) — **default: the previous FY**, else the nearest other FY with data (`comparison_widget`) |

Financial years are named by their start year — FY 2026-27 = 1 Apr 2026 to 31 Mar 2027
(`revenue_analysis.fy_start_year`, `fy_bounds`, `fy_label`). Example: report
date 15 Oct 2026, *To-Date* → 1 Apr–15 Oct 2026 vs 1 Apr–15 Oct 2025.

If both periods would get the same label, the comparison columns are
labelled "… (compare)" so the table still renders.

## 4. Traffic denominators — `terminal_mapping.get_terminal_for_outlet`

**Delhi**

| Outlets | Traffic pool |
|---|---|
| T1 lounges (T1D, Prive T1, Amex T1), T1 spa | T1 Dep |
| T2 lounge | T2 Dep |
| T3 domestic (DL02/3/4, D49, Rupay, Centurion, Air India) | T3 Dom Dep |
| T3 international (INL 5&6, Prive T3, Xenia, AI Intl, Intl spa) | T3 Int Dep |
| T3 domestic spa (*Domestic Spa - T3*) | T3 Int Dep today — see KNOWN_ISSUES |
| Arrivals (LA22, Nap LA01/LA12, Reserved Lounge) | T3 Arr (dom + int arrivals) |
| Enwrap | All departures |
| Atithya (Meet & Greet) | whole airport |
| Porter | Porter pool (T1+T2 dep/arr, T3 dom/int dep) |
| Buggy | all T3 pools |
| Business Centre, RDC, CIP Lounge, Special Events, MLCP | none (no PEN %/SPP) |

Composite pools are resolved at query time in
`database.join_revenue_with_traffic_by_outlet`, not stored.

**Hyderabad / Goa:** domestic lounge → Domestic; international lounge,
Reserved Lounge, GAT, Airport Lodge → International; Prive (Hyderabad),
Atithya → Main Terminal; Enwrap, Porter → All. Transit Hotel (Hyderabad) and
CIP Lounge (Goa) have no traffic pool.

**Bhogapuram:** same scheme as Hyderabad — Domestic Lounge → Domestic;
International Lounge, Reserved Lounge → International; Atithya, Porter,
Enwrap → All (Domestic + International); anything else → Main Terminal
(whole airport).

**Stored traffic for Hyderabad / Goa / Bhogapuram** is always split into
*Domestic* and *International* (departures + arrivals), for daily and monthly
files alike (`traffic_parser._segment_to_terminal`). Older uploads that hold
only an airport total (terminal "") fall back to a fixed share (Hyderabad
82.7 % / 17.3 %, Goa 96.4 % / 3.6 %) marked as estimated — re-upload those
files with *Replace* to use the real split.

**Re-importing revenue:** off by default — stored lines are kept and the
file's copy is skipped. With *Replace existing revenue for the dates and
locations in this file* ticked, every stored row for each (location, date) in
the file is deleted first and the file's rows saved, in one transaction per
batch of whole dates (`database._delete_revenue_rows`); a line the file no
longer has for such a date is removed too.

**Re-importing traffic:** with *Replace* ticked (default), the stored rows for
every airport + date in the file (all terminals, same granularity) are
deleted first (`database._delete_traffic_rows`); otherwise existing rows are
kept and the file's rows for them are skipped.

**Location total (Traffic KPI card):** each location's stored terminal rows
added once (`database.join_revenue_with_traffic`) — Delhi's 8 pools,
Domestic + International elsewhere. Adding outlet pools would double-count,
because the whole-airport pool already contains the others.

**Terminal-wise Performance** (`ehpl_layout._get_terminal_rows`): outlets are
grouped by their traffic pool's terminal; a terminal's traffic = the sum of
the distinct pools its outlets use (T3 Arrivals = T3 Dom Arr + T3 Int Arr);
*Airport-wide services* (Atithya, Porter, Enwrap, Buggy) use the largest of
their pools (the whole airport); *No terminal traffic* rows have no PEN/SPP;
TOTAL traffic = the location total above. Each period uses its own traffic.

**Subtotals** (`business_dashboard._subtotal_traffic`): one shared pool →
that value; a group containing Atithya (whole airport) → the maximum;
one pool ≥ 80 % of the sum → the maximum; otherwise the sum.

## 5. AOP rules

- **Tables:** `aop_target` (outlet × month; EHPL, Sky Plates, Encalm Eats),
  `aop_target_daily` (location × day, alternative format).
- **Units:** the AOP master is in lakhs; stored in rupees (× 100,000).
- **Replace on import (default on):** stored targets for every month in the
  file are deleted first (`database.delete_aop_targets_for_months`), so a
  corrected file overwrites old values.
- **EHPL proration** (`business_dashboard._load_aop`): monthly AOP ×
  (days selected ÷ days in the *first* month of the range). Ranges spanning
  two months use the first month's day count (KNOWN_ISSUES).
- **Sky Plates / Encalm Eats proration**
  (`eats_skyplates_aop_parser.load_segment_aop`): per month — each month
  contributes its own share of the selected days.
- **EHPL AOP excludes** Sky Plates and Encalm Eats targets
  (`render_ehpl_page`).
- **Noted AOP lines** (Business Segment column has a note) are not imported
  for Sky Plates / Encalm Eats.
- **Outlet matching:** AOP outlet names are canonicalised at save and load;
  EHPL attaches each AOP line to exactly one table row
  ([DATA_MAPPINGS.md](DATA_MAPPINGS.md) §2).

## 6. Totals

- **EHPL TOTAL** = sum of every row of the location (no outlet is left out),
  so it equals the database total for the location and period.
- Section totals (TOTAL LOUNGES …) = sum of their rows.
- Encalm Eats / Sky Plates: TOTAL = outlets with sales + "Other planned
  outlets" AOP.

## 7. Encalm Eats data source

Per **location and day**: if a DSR exists for that day and location, its
outlet rows are used; otherwise the *Encalm Eats* row from the revenue
upload. Never both. Dates offered = DSR dates ∪ revenue-upload dates with
Encalm Eats rows.

## 8. Revenue import validation

`data_processor._validate_and_clean_with_report` and
`excel_parser.parse_revenue_dashboard`; every dropped or partly imported
line goes into the "rows not imported" report (`import_report`) with its
Excel row and reason.

| Rule | Result |
|---|---|
| Date empty, `#VALUE!` or not a date | not imported |
| Date before 1 Jan 2015 or more than 365 days ahead (`import_report.MIN_VALID_DATE`, `MAX_FUTURE_DAYS`) | not imported |
| Location, Business or Outlet blank | not imported |
| Revenue or PAX not a number | imported without that figure |
| No PAX and no revenue | not imported (empty line) |
| Exact duplicate row | not imported (counted once) |
| Same date + outlet + location, different figures (month-end lines) | **added together** (`database.combine_duplicate_revenue_rows`) |
| Fully blank padding rows | ignored silently |

The upload's report date is the latest date in the file.

## 9. Volume vs spend — `revenue_analysis.classify_driver`

PAX up and revenue/PAX flat or down → volume-driven; revenue/PAX up and PAX
flat or down → spend-driven; both up → mixed.

## 10. Access and limits

| Rule | Value | Code |
|---|---|---|
| Login lockout | 5 wrong passwords → 5 minutes (`login_attempts` table, survives new tabs) | `auth._MAX_ATTEMPTS`, `_LOCKOUT_SECONDS` |
| Inactivity sign-out | 30 minutes without any interaction | `auth._INACTIVITY_TIMEOUT_MINUTES` |
| Session check | token re-validated against `active_sessions` at most once a minute | `auth.require_login` |
| Upload rate limit | 20 revenue uploads per user per hour | `database._MAX_UPLOADS_PER_HOUR` |
| Admins | only users listed in `[auth.admins]` | `secrets.toml` |
| Upload size | 300 MB | `.streamlit/config.toml` |
