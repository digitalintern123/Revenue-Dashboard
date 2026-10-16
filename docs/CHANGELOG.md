# Changelog — Encalm Revenue Analytics

Newest first. Earlier entries describe the app as it was at the time (page
names and file paths in them may no longer exist).

---

## Version 2.7.0 (October 2026) — every line item, Windows server operations

### Terminal-wise Performance
- Traffic, PEN % and SPP were blank for every location (traffic was looked up
  with text dates and old terminal names, and the error was hidden). The
  table now uses the same traffic as the outlet table, the compare period
  uses its own traffic, and TOTAL / *Airport-wide services* / *No terminal
  traffic* rows make it add up to TOTAL EHPL.
- Traffic totals no longer add a monthly figure on top of daily figures for
  the same days (SQLite text dates were compared with real dates).

### Comparisons
- **Year-wise uses the financial year** (1 April – 31 March). *To-Date*
  compares 1 April to the report date with the same span of the chosen FY;
  the year dropdown lists financial years (FY 2025-26 …).

### Imports
- **Historical Import tab removed** from Upload Data. Full revenue workbooks
  are uploaded in the *Daily Revenue* tab (same parser, batched saving above
  5,000 rows).
- **Rows not imported report.** Revenue uploads list every line left out (or
  imported without revenue/PAX) with its Excel row and reason, plus a CSV
  download (`modules/import_report.py`).
- **Impossible dates rejected:** only 1 Jan 2015 to one year ahead is accepted
  (a #VALUE! date read as year 3601 had been stored).
- Lines lost when saving in batches across date boundaries are fixed; the
  upload's report date is the latest date in the file.

### AOP and Encalm Eats
- Encalm Eats AOP lines mapped to the DSR outlet names (IndiSip 32-34, CDH,
  Indisip Bar PESC → J&B Pour House T2, Bhogapuram McDonald's, IndiSip Café /
  Bistro, Svara, Totally Desi). One AOP line can cover several outlets
  (Bhogapuram Starbucks = Departure + Arrival, split by revenue).
- AOP lines with a note in the AOP master are not imported (provisional);
  shown as *Not imported* in the upload's mapping table.
- **DSR parser:** the *Bhogapuram Store's* section total was stored as a Delhi
  outlet (double count) and Bhogapuram outlets were filed under Delhi — fixed;
  repeated spaces in outlet names collapsed.
- Encalm Eats page offers revenue-upload dates again after a DSR is uploaded;
  per location and day the DSR is used where present, else the revenue
  upload total.

### Dashboards
- **EHPL tables built from the data:** every stored outlet appears exactly
  once and TOTAL EHPL equals the database. Before: Hyderabad GAT / Airport
  Lodge and Goa CIP / Reserved Lounge were dropped, Delhi RDC and Reserved
  Lounge and Bhogapuram Domestic Lounge were counted twice, and Delhi's total
  left out RDC, Business Centre and Reserved Lounge (₹50.65 L in Aug 2026).
  Unknown outlets go under OTHERS; AOP-only lines (MLCP, Spa T3 Dom) show.
- **Outlet lists per location** always shown: Hyderabad (Enwrap, Atithya,
  Airport Lodge / Dormitory, Domestic Lounge, GAT, International Lounge,
  Encalm Prive, Reserved Lounge, Transit Hotel), Goa (Enwrap, Atithya, Porter,
  CIP Lounge, Domestic Lounge, International Lounge, Reserved Lounge),
  Bhogapuram (Enwrap, Atithya, Porter, Domestic Lounge, International Lounge,
  Reserved Lounge, Spa Domestic).
- EHPL AOP no longer includes Sky Plates / Encalm Eats targets.
- Year-wise compares with the previous year by default (was the same year,
  which broke the tables); identical period labels no longer break tables.
- Checked against the Aug-2026 workbook: all 68 line items visible with exact
  amounts in every period 2022–2026 (222 checks).

### Interface
- Pages moved from `pages/` to `views/` and use the old addresses again
  (`/EHPL`, `/Encalm_Eats`, …). Opening `/EHPL` used to load the page unstyled
  with a raw file list in the sidebar and a "Page not found" popup.
- The sign-in screen shows no sidebar or menu.

### Server (Windows VPS)
- `C:\encalm` is now a clone of this repository (was a hand-copied folder of
  another repository).
- **Watchdog fixed:** a long dash in `watchdog.ps1` made Windows PowerShell 5.1
  fail on every run since 10 Sep 2026; scripts are ASCII and the task runs
  with `-ExecutionPolicy Bypass`.
- **Plesk Git deploys:** `deploy_sync.ps1` (run by the watchdog) applies
  commits pulled by Plesk, installs new requirements and restarts the app.
- Port 8501 blocked from the internet (firewall rule).
- SQLite: `DATA_DIR`, WAL mode, daily online backups (`data/backups`, 7 kept),
  `scripts/migrate_to_sqlite.py`.

### Traffic
- Delhi day-grid sheets with the month as a date in A1 (Sep-2026 file) are
  read; before, the whole Delhi sheet was skipped.
- Vizag / VTZ / Bhogapuram sheets in the Hyderabad layout are read as
  **Bhogapuram**; Bhogapuram outlets are mapped to Domestic / International /
  whole-airport traffic, so its PEN % and SPP work.
- The Traffic tab warns about every sheet that produced no rows (the Sep file
  had shown "120 rows parsed" with Delhi and Vizag missing).
- Traffic KPI card: whole-airport traffic per location counted once (it was
  adding the whole-airport pool to the terminal pools — about double).
- **Hyderabad traffic columns:** in the May-2026 template ("Domestic |
  International" right above "Departure | Arrival") international departures
  were counted as domestic and international was arrivals only (May:
  Domestic 12,92,765 / International 2,02,439 instead of 21,45,938 /
  4,12,854). Fixed.
- **Hyderabad PAX vs Flights:** in the Apr-2026 template (PAX Arr/Dep then
  Flights Arr/Dep per side) the Flights columns were read as traffic (April:
  Domestic 13,399 / International 1,765 instead of 20,66,956 / 3,42,714).
  Columns under a Flights / ATMs heading are now ignored.
- **Goa two-month sheets:** when the prior-year block (left) has daily
  figures (Jul-2026 file), a generic reader added both blocks together and
  stored them as July 2025 (e.g. 1 Jul 2025 = 19,334 instead of 12,163).
  Airports read by the dedicated Goa / Hyderabad readers now ignore the
  generic reader, so only the current month (July 2026) is imported.
- **Monthly traffic for Hyderabad / Goa stored as Domestic + International**
  (was one airport total). Lounge PEN % / SPP for Apr-2024 – Mar-2026 used
  a fixed-share estimate (Goa international up to ~70 % too low) and the
  whole-airport outlets (Atithya, Prive) were measured against twice the
  airport traffic. Values are stored exactly as in the file (the file is the
  source of truth). Re-upload `Monthly_Traffic_All_Apr_24_to_Mar26.xlsx`
  with Replace.
- **Replace on traffic import** (on by default): a corrected file overwrites
  stored traffic for its airports and dates; before, re-uploads were skipped.

### Docs
- Documentation rewritten for the current app; new
  [USER_GUIDE.md](USER_GUIDE.md) and [SERVER_RUNBOOK.md](SERVER_RUNBOOK.md).
  Tests: 274.

## Version 2.6.0 (October 2026) — hosting, Encalm branding, speed

- **Render hosting**: `render.yaml` blueprint; login settings come from a Render
  Secret File (`secrets.toml`). `DATABASE_URL` accepts pasted variants (psql
  snippet, quotes, `postgres://`) and pins the psycopg2 driver; pooled Neon hosts
  skip the `statement_timeout` startup option. Errors name the bad source without
  showing the password.
- **Encalm branding**: official logo (sidebar, sign-in, favicon), navy `#142248` /
  gold `#CBA578`, Montserrat headings, Lucide icons on pages and tabs.
- **Dashboards**: compact filter bar with a period summary line, Overview KPI
  cards (now also on EHPL) and two charts (revenue by location/outlet, 30-day
  trend). Upload Data and Previous Uploads are split into tabs.
- **Speed**: render-path reads are cached for 10 minutes and cleared by every
  upload; schema check once per server; login re-validated at most once a
  minute. A click on EHPL went from ~20 database queries to none.
- Previous Uploads preview shows one AOP column (was `aop_x`/`aop_y`).
- Tests (`tests/`, `test_universal_parser.py`) are now tracked in git.

## Version 2.5.0 (October 2026) — no more dropped month-end lines

- **Repeated date + outlet lines are now added together** instead of keeping only
  the last one. Revenue workbooks carry month-end lines (fixed fees, rentals,
  card-billing true-ups) on a second row for the same date and outlet; the old
  importer kept one row and dropped the other (₹7.4 L lost on 31 Aug 2026,
  ₹2.04 Cr would have been lost on 30 Sep 2026). Exact repeated rows are still
  removed so a block pasted twice is not double counted.
- Raw outlet names that map to the same outlet (e.g. Hyderabad "Dom Prive" and
  "Prive") are combined at save time too, instead of whichever row came first
  winning.
- `.streamlit/config.toml` now runs Streamlit headless (no first-run email prompt).
- The release zip no longer contains `.streamlit/secrets.toml`, so deploying can't
  overwrite the server's login settings or database connection.

## Version 2.4.0 (September 2026) — AOP master: full coverage

- **Sky Plates & Encalm Eats AOP** now imported from the AOP master's IFK and F&B
  rows (`modules/eats_skyplates_aop_parser.py`). The reader finds rows by their
  labels, reads both FY25-26 and FY26-27 monthly blocks, stores outlet-level
  targets only (no subtotal rows), and reports any section whose total differs
  from its outlets. Events & ODCs ("All") is stored under Delhi.
- **LA22 AOP was stored at 3×** (three alias names collapsed onto one outlet and
  were summed). Now written once.
- **EHPL AOP now covers Bhogapuram** (card lounges, M&G, Porter, Baggage Wrap) and
  Delhi's MLCP Nap & Shower unit. Parsed EHPL AOP reconciles exactly to the
  sheet's EHPL total row for every month.
- **AOP import "Replace" option** (on by default) clears stored AOP for the months
  a file covers before importing, so corrected files overwrite old values.
- Sky Plates / Encalm Eats pages show AOP Target and Variance in the KPI cards and
  tables, prorated per month for partial ranges; AOP for planned outlets with no
  sales appears as one "Other planned outlets" line plus a detail expander.

## Version 2.0.0 (August 2026) — production readiness

This release fixes all audit issues identified in the Production Readiness Audit
and promotes the application to production-ready status.

---

### Security Fixes

#### S2 — Admin Check Now Requires Explicit secrets Configuration
**Previously:** Any user whose username ended in `_admin` had admin access.
**Now:** Admin access requires explicit listing in `[auth.admins]` in secrets.toml.
Users not listed in `[auth.admins]` have no admin access regardless of username.
**File:** `Home.py`

#### S3 — Log Files Moved to Dedicated Directory
**Previously:** `encalm_analytics.log` written to app root directory (`C:\encalm\`).
**Now:** All logs written to `C:\encalm\logs\` — separate from app code, not web-accessible.
**File:** `modules/app_logger.py`

---

### Deployment Fixes

#### I1/I2 — Crash Recovery Watchdog
**New file:** `watchdog.ps1`
Monitors port 8501 every 3 minutes and auto-restarts the app if it stops responding.
Register in Task Scheduler:
```powershell
schtasks /create /tn "EncalmWatchdog" /tr "powershell.exe -File C:\encalm\watchdog.ps1" /sc minute /mo 3 /ru SYSTEM /f
```

#### I3 — IIS/ARR Timeout Configuration
**New file:** `docs/IIS_ARR_SETUP.md`
Documents exact steps to increase ARR request timeout from 30s to 300s,
fixing 502 errors during large file uploads (DB3.xlsx, 53K rows).

#### I4 — table_style.py Fix Included
Traffic merge now uses `(outlet, location)` not `(segment, outlet, location)`.
This fixes Traffic and Penetration% showing `—` for July and August data.
**File:** `modules/table_style.py`

---

### Data Integrity Fixes

#### D8 — Daily Database Backup
**New file:** `backup_db.ps1`
Creates daily PostgreSQL dumps to `C:\encalm\backups\`, retains 30 days.
Register in Task Scheduler:
```powershell
schtasks /create /tn "EncalmBackup" /tr "powershell.exe -File C:\encalm\backup_db.ps1" /sc daily /st 02:00 /ru SYSTEM /f
```

---

### Performance Improvements

#### P3 — Increased PostgreSQL Connection Pool
Pool size: 3 → 5, max_overflow: 7 → 10.
Supports more concurrent users without connection timeout errors.
**File:** `modules/database.py`

#### P4 — PostgreSQL Statement Timeout
Added 60-second statement timeout to prevent runaway queries from blocking the pool.
**File:** `modules/database.py`

---

### Configuration Improvements

#### Streamlit Config
- Upload size limit: 200MB → 300MB
- `headersTimeout`: added 300s for large uploads
- `maxMessageSize`: added 300MB
- `fastReruns`: enabled for better UI responsiveness

#### secrets.toml.example
- Added `[auth.admins]` section documentation
- Added `DATABASE_URL` production example
- Clarified all configuration options

---

### All v1 Fixes Carried Forward

All 16 fixes from v1 are included:
- FIX-01: 40+ outlet canonical name mappings
- FIX-02: UNIQUE constraint (date, outlet, location)
- FIX-03: Segment migration covers EHPL+Eats/SkyPlates
- FIX-04: Segment canonicalization — EHPL+Encalm Eats/Sky Plates
- FIX-05: AOP priority — per-outlet monthly before daily
- FIX-06: compare_periods merges on (outlet, location)
- FIX-07: Segment normalisation in comparisons
- FIX-08: Multi-FY AOP parsing (FY26-27 was dropped)
- FIX-09: Amex Hyd outlet mapping
- FIX-10: NA handling in segment column
- FIX-11: Auth keys preserved on clear session
- FIX-12: Spa display names + RL Delhi
- FIX-13: Total T1 + Total T2 subtotals
- FIX-14: Snapshot merges on (outlet, location)
- FIX-15: Better empty-period error message
- FIX-16: Penetration %/SPP function fix

---

### Production Readiness Score

| Category | v1 | v2 |
|---|---|---|
| Security | 68/100 | 88/100 |
| Authentication | 90/100 | 92/100 |
| Data Integrity | 85/100 | 90/100 |
| Error Handling | 82/100 | 85/100 |
| Deployment | 45/100 | 78/100 |
| Performance | 70/100 | 82/100 |
| Testing | 95/100 | 95/100 |
| **Overall** | **76/100** | **87/100** |

**v2 Verdict: GO ✅**

---


---

## Version 1 — final build (August 2026)

All fixes made to the Encalm Analytics application from the initial codebase through the final build.

---

### Build: Final (Aug 2026)

#### Summary
This build contains **16 distinct fixes** across 7 files, resolving critical data integrity issues, comparison logic bugs, segment classification errors, AOP/Traffic display failures, and UI correctness problems.

---

### Fixes by File

---

#### `modules/database.py`

#### FIX-01 — Outlet Name Canonicalization (40+ mappings added)
**Problem:** Same physical outlet stored under different names across files (e.g. `Business Center` vs `Business Centre`, `Round D Clock -Motel` vs `Round D Clock (RDC)`, `Nap & Shower LA01` vs `NAP - Premium Lounge`). Cross-file comparisons showed Rs0 for one side.
**Fix:** Added 40+ entries to `_OUTLET_NAME_CANONICAL` covering all name variants from DB3.xlsx, Revenue_Jul26_Corrected.xlsx, and the July 2026 stacked-daily format.
**Affected function:** `_OUTLET_NAME_CANONICAL` dict, `canonicalize_outlet_name()`

#### FIX-02 — UNIQUE Constraint Excludes Segment
**Problem:** UNIQUE constraint was `(date, segment, outlet, location)`. Same outlet uploaded twice with different segment values ("Lounges" from DB3 and "EHPL" from July file) created duplicate rows. Every outlet appeared twice in comparison tables with Rs0 on the other side.
**Fix:** Changed UNIQUE constraint to `(date, outlet, location)`. Added PostgreSQL migration to drop and recreate the constraint on existing databases.
**Affected:** `UniqueConstraint(...)`, `ON CONFLICT (date, outlet, location) DO NOTHING`, `_migrate_schema()`

#### FIX-03 — Segment Migration Covers All Cases
**Problem:** `_migrate_legacy_segments()` only updated rows with old segment names. Rows already stored as `segment="EHPL"` with outlets `Encalm Eats` or `Encalm Sky Plates` were never corrected.
**Fix:** Migration query extended to also catch `WHERE segment = 'EHPL' AND outlet IN ('Encalm Eats', 'Encalm Sky Plates', 'Sky Plates')`.
**Affected function:** `_migrate_legacy_segments()`

#### FIX-04 — Segment Canonicalization — EHPL + Encalm Eats/Sky Plates
**Problem:** `canonicalize_segment_and_business_unit("EHPL", "Encalm Eats")` returned `("EHPL", "Lounges")` instead of `("Encalm Eats", "Encalm Eats")`. The July 2026 file sends `segment="EHPL"` for ALL outlets including Encalm Eats and Encalm Sky Plates. The outlet-based segment override only ran for `segment="Subsidiary"`.
**Fix:** Moved `_OUTLET_TO_NEW_SEGMENT` lookup to the top of the function, before any raw_segment branch. Now applies regardless of whether raw_segment is "EHPL", "Subsidiary", blank, or None.
**Affected function:** `canonicalize_segment_and_business_unit()`

Expected mappings:
- `(any, "Encalm Eats")` → `("Encalm Eats", "Encalm Eats")`
- `(any, "Encalm Sky Plates")` → `("Sky Plates", "Sky Plates")`
- `("Lounges"/"Atithya"/"Others", any)` → `("EHPL", <original>)`
- `("EHPL", other)` → `("EHPL", <bu from outlet>)`

#### FIX-05 — AOP Priority: Per-Outlet Monthly Before Daily Location Total
**Problem:** `join_revenue_with_aop()` checked `aop_target_daily` first. DB3.xlsx embedded AOP was stored there as location-level daily totals. The function returned `__location_total__` sentinel rows and never reached `aop_target` (per-outlet monthly from AOP_Clean_FY25-27.xlsx). Result: AOP showed "--" for all outlets.
**Fix:** Reversed priority — per-outlet monthly (`load_aop_targets_for_range`) checked first. Daily location-total only used as fallback when per-outlet monthly is absent.
**Affected function:** `join_revenue_with_aop()`

---

#### `modules/revenue_analysis.py`

#### FIX-06 — compare_periods: Merge on (outlet, location), Not Segment
**Problem:** `GROUP_COLS = ["segment", "outlet", "location"]` was the merge key. DB3 uses "Lounges"/"Atithya"/"Others", July file uses "EHPL". Outer merge on segment caused every outlet to appear twice — one row per segment value — with Rs0 on the other side.
**Fix:** Merge always uses `join_cols = ["outlet", "location"]`. Segment is resolved from raw DataFrames directly and attached after the merge. Non-outlet comparisons (location/segment summaries) continue using their own `group_cols`.
**Affected function:** `compare_periods()`

#### FIX-07 — Segment Normalisation in compare_periods
**Problem:** DB3 rows carried old segment values ("Lounges", "Atithya") into comparison results. Page only styled/coloured "EHPL" — old values showed blank.
**Fix:** Added `_norm_seg()` inside `compare_periods()`. Maps legacy values to "EHPL". "Sky Plates" and "Encalm Eats" are explicitly NOT in the legacy set — they pass through unchanged.
**Legacy to EHPL set:** `{"lounges", "atithya", "others", "subsidiary", "lounge"}`

---

#### `modules/aop_parser.py`

#### FIX-08 — Multi-FY AOP Parsing (FY26-27 was silently dropped)
**Problem:** `_extract_month_columns()` had `if result: break` which stopped at the first non-datetime column (e.g. "FY 25-26" summary column at index 17). Only Apr 2025 - Mar 2026 was parsed. Apr 2026 - Mar 2027 was silently ignored → July 2026 AOP = Rs0.
**Fix:** Removed the break. Non-datetime non-null columns are skipped. All month columns across multiple fiscal years are captured.
**Affected function:** `_extract_month_columns()`

#### FIX-09 — Amex Hyd Outlet Mapping Added
**Problem:** `("Hyderabad", "Amex Hyd")` had no entry in `_AOP_OUTLET_MAP`. The AOP row was silently skipped.
**Fix:** Added mapping `("Hyderabad", "Amex Hyd"): "International Lounge (New)"`.

---

#### `modules/data_processor.py`

#### FIX-10 — NA Handling in Segment Column Processing
**Problem:** `_validate_and_clean()` called `.astype(str).str.strip().apply(_title_case_preserving_acronyms)` on the segment column. With pandas Arrow-backed string arrays (Python 3.12), `pd.NA` arrived as a non-string object causing `AttributeError: 'float' object has no attribute 'strip'`.
**Fix:** `_title_case_preserving_acronyms()` now handles `None`, `pd.NA`, `float NaN`, and the string `"<NA>"` — all treated as empty string.
**Affected function:** `_title_case_preserving_acronyms()`

---

#### `modules/session.py`

#### FIX-11 — Auth Keys Preserved on Clear Session
**Problem:** `clear_session()` wiped all Streamlit session state including authentication keys, logging users out when they clicked "Clear Session Data".
**Fix:** Auth key constants are imported and preserved during `clear_session()`. Only non-auth keys are cleared.
**Affected function:** `clear_session()`

---

#### `modules/outlet_groups.py`

#### FIX-12 — Spa Display Names and Reserved Lounge Delhi
**Problem:** "SPA Domestic"/"Dom Spa" displayed as "Encalm Spa (T1 Dom)" instead of "Encalm Spa (T3 Dom)". "Reserved Lounge" was incorrectly included in the T3 Arrivals LA22 group.
**Fix:** Updated display name mappings. Removed "Reserved Lounge" from T3 Arrivals LA22 group.

#### FIX-13 — Total T1 and Total T2 Subtotals in Delhi MIS
**Problem:** Delhi Business Performance table had no subtotals between T1 and T2 outlet groups.
**Fix:** Added "Total T1" and "Total T2" subtotal rows to `DELHI_ROW_ORDER`.

---

#### `pages/3_Revenue_Comparison.py`

#### FIX-14 — Multi-Period Snapshot: Merge on (outlet, location)
**Problem:** The snapshot section merged all periods using `ra.GROUP_COLS = ["segment", "outlet", "location"]`. DB3 old segments vs July "EHPL" caused: segment column blank, PAX (2025) showing 0, AOP showing "--".
**Fix:** Snapshot merges now use `_SNAP_JOIN = ["outlet", "location"]`. Segment is resolved from a lookup after all merges. `_snap_agg()` aggregates on outlet+location only.
**Affected section:** Multi-Period Snapshot block

#### FIX-15 — Better Empty-Period Error Message
**Problem:** "Try a different date/period" was too vague when one comparison period had no data.
**Fix:** Error message now names the specific empty period and explains the most likely cause (upload missing for that period).

---

#### `pages/7_Service_Categories.py`

#### FIX-16 — Penetration % / SPP Function Mismatch
**Problem:** `penetration_and_spp_table()` was called for location-level data but requires outlet-level data. Caused crashes and wrong Penetration % calculations.
**Fix:** Replaced with `location_level_summary_with_traffic()`. AOP section wrapped in its own `safe_run`.

---

### Data Files Corrected

#### Revenue_Jul26_Corrected.xlsx
- Source: PAX & Rev. sheet from Revenue_Dashboardv_2_-_Jul-26.xlsx (Data sheet has corrupted dates 3601-6857)
- Rows: 1,305
- Date range: 1 Jul 2026 to 31 Jul 2026
- Total revenue: Rs99,78,21,860
- Segments: EHPL / Encalm Eats / Sky Plates (correctly assigned per outlet)
- By segment: EHPL=Rs83.57Cr, Sky Plates=Rs15.27Cr, Encalm Eats=Rs94.4L

#### AOP_Clean_FY25-27.xlsx
- Source: db_aop.xlsx parsed and verified
- Rows: 1,080 (45 outlets x 24 months)
- Coverage: Apr 2025 to Mar 2027 (FY25-26 + FY26-27)
- Total AOP: Rs2,483.5 Cr
- Diff vs original: 0.0000%
- Format: parser-compatible layout

---

### Upload Order

Upload files in this order via Home > Upload:

1. DB3.xlsx (Revenue - historical)
2. Revenue_Jul26_Corrected.xlsx (Revenue - July 2026)
3. Monthly_Traffic_All_Apr_24_to_Mar_26.xlsx (Traffic - monthly)
4. Traffic_Data_-_Apr_26.xlsx (Traffic - daily)
5. Traffic_Data_May_2026.xlsx (Traffic - daily)
6. Traffic_Data_-_June_2026.xlsx (Traffic - daily)
7. Traffic_Data_-_till_15_July.xlsx (Traffic - daily)
8. july_2026_traffic.xlsx (Traffic - daily)
9. AOP_Clean_FY25-27.xlsx (AOP)

---

### Deployment

```powershell
# Push to GitHub
git add .
git commit -m "Final build - all 16 fixes applied"
git push

# VPS restart
cd C:\encalm
git pull
schtasks /end /tn "EncalmAnalytics"
schtasks /run /tn "EncalmAnalytics"

# Local - delete old DB first
del data\revenue_analytics.db
python -m streamlit run Home.py
```

---

### Segment Reference

| Source Segment | Outlet | Stored As |
|---|---|---|
| Lounges / Atithya / Others | Any | EHPL |
| Subsidiary | Encalm Eats | Encalm Eats |
| Subsidiary | Encalm Sky Plates | Sky Plates |
| EHPL | Encalm Eats | Encalm Eats |
| EHPL | Encalm Sky Plates | Sky Plates |
| EHPL | Any other outlet | EHPL |
