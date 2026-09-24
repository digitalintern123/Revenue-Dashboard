# Encalm Analytics — Changelog

All fixes made to the Encalm Analytics application from the initial codebase through the final build.

---

## Build: Final (Aug 2026)

### Summary
This build contains **16 distinct fixes** across 7 files, resolving critical data integrity issues, comparison logic bugs, segment classification errors, AOP/Traffic display failures, and UI correctness problems.

---

## Fixes by File

---

### `modules/database.py`

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

### `modules/revenue_analysis.py`

#### FIX-06 — compare_periods: Merge on (outlet, location), Not Segment
**Problem:** `GROUP_COLS = ["segment", "outlet", "location"]` was the merge key. DB3 uses "Lounges"/"Atithya"/"Others", July file uses "EHPL". Outer merge on segment caused every outlet to appear twice — one row per segment value — with Rs0 on the other side.
**Fix:** Merge always uses `join_cols = ["outlet", "location"]`. Segment is resolved from raw DataFrames directly and attached after the merge. Non-outlet comparisons (location/segment summaries) continue using their own `group_cols`.
**Affected function:** `compare_periods()`

#### FIX-07 — Segment Normalisation in compare_periods
**Problem:** DB3 rows carried old segment values ("Lounges", "Atithya") into comparison results. Page only styled/coloured "EHPL" — old values showed blank.
**Fix:** Added `_norm_seg()` inside `compare_periods()`. Maps legacy values to "EHPL". "Sky Plates" and "Encalm Eats" are explicitly NOT in the legacy set — they pass through unchanged.
**Legacy to EHPL set:** `{"lounges", "atithya", "others", "subsidiary", "lounge"}`

---

### `modules/aop_parser.py`

#### FIX-08 — Multi-FY AOP Parsing (FY26-27 was silently dropped)
**Problem:** `_extract_month_columns()` had `if result: break` which stopped at the first non-datetime column (e.g. "FY 25-26" summary column at index 17). Only Apr 2025 - Mar 2026 was parsed. Apr 2026 - Mar 2027 was silently ignored → July 2026 AOP = Rs0.
**Fix:** Removed the break. Non-datetime non-null columns are skipped. All month columns across multiple fiscal years are captured.
**Affected function:** `_extract_month_columns()`

#### FIX-09 — Amex Hyd Outlet Mapping Added
**Problem:** `("Hyderabad", "Amex Hyd")` had no entry in `_AOP_OUTLET_MAP`. The AOP row was silently skipped.
**Fix:** Added mapping `("Hyderabad", "Amex Hyd"): "International Lounge (New)"`.

---

### `modules/data_processor.py`

#### FIX-10 — NA Handling in Segment Column Processing
**Problem:** `_validate_and_clean()` called `.astype(str).str.strip().apply(_title_case_preserving_acronyms)` on the segment column. With pandas Arrow-backed string arrays (Python 3.12), `pd.NA` arrived as a non-string object causing `AttributeError: 'float' object has no attribute 'strip'`.
**Fix:** `_title_case_preserving_acronyms()` now handles `None`, `pd.NA`, `float NaN`, and the string `"<NA>"` — all treated as empty string.
**Affected function:** `_title_case_preserving_acronyms()`

---

### `modules/session.py`

#### FIX-11 — Auth Keys Preserved on Clear Session
**Problem:** `clear_session()` wiped all Streamlit session state including authentication keys, logging users out when they clicked "Clear Session Data".
**Fix:** Auth key constants are imported and preserved during `clear_session()`. Only non-auth keys are cleared.
**Affected function:** `clear_session()`

---

### `modules/outlet_groups.py`

#### FIX-12 — Spa Display Names and Reserved Lounge Delhi
**Problem:** "SPA Domestic"/"Dom Spa" displayed as "Encalm Spa (T1 Dom)" instead of "Encalm Spa (T3 Dom)". "Reserved Lounge" was incorrectly included in the T3 Arrivals LA22 group.
**Fix:** Updated display name mappings. Removed "Reserved Lounge" from T3 Arrivals LA22 group.

#### FIX-13 — Total T1 and Total T2 Subtotals in Delhi MIS
**Problem:** Delhi Business Performance table had no subtotals between T1 and T2 outlet groups.
**Fix:** Added "Total T1" and "Total T2" subtotal rows to `DELHI_ROW_ORDER`.

---

### `pages/3_Revenue_Comparison.py`

#### FIX-14 — Multi-Period Snapshot: Merge on (outlet, location)
**Problem:** The snapshot section merged all periods using `ra.GROUP_COLS = ["segment", "outlet", "location"]`. DB3 old segments vs July "EHPL" caused: segment column blank, PAX (2025) showing 0, AOP showing "--".
**Fix:** Snapshot merges now use `_SNAP_JOIN = ["outlet", "location"]`. Segment is resolved from a lookup after all merges. `_snap_agg()` aggregates on outlet+location only.
**Affected section:** Multi-Period Snapshot block

#### FIX-15 — Better Empty-Period Error Message
**Problem:** "Try a different date/period" was too vague when one comparison period had no data.
**Fix:** Error message now names the specific empty period and explains the most likely cause (upload missing for that period).

---

### `pages/7_Service_Categories.py`

#### FIX-16 — Penetration % / SPP Function Mismatch
**Problem:** `penetration_and_spp_table()` was called for location-level data but requires outlet-level data. Caused crashes and wrong Penetration % calculations.
**Fix:** Replaced with `location_level_summary_with_traffic()`. AOP section wrapped in its own `safe_run`.

---

## Data Files Corrected

### Revenue_Jul26_Corrected.xlsx
- Source: PAX & Rev. sheet from Revenue_Dashboardv_2_-_Jul-26.xlsx (Data sheet has corrupted dates 3601-6857)
- Rows: 1,305
- Date range: 1 Jul 2026 to 31 Jul 2026
- Total revenue: Rs99,78,21,860
- Segments: EHPL / Encalm Eats / Sky Plates (correctly assigned per outlet)
- By segment: EHPL=Rs83.57Cr, Sky Plates=Rs15.27Cr, Encalm Eats=Rs94.4L

### AOP_Clean_FY25-27.xlsx
- Source: db_aop.xlsx parsed and verified
- Rows: 1,080 (45 outlets x 24 months)
- Coverage: Apr 2025 to Mar 2027 (FY25-26 + FY26-27)
- Total AOP: Rs2,483.5 Cr
- Diff vs original: 0.0000%
- Format: parser-compatible layout

---

## Upload Order

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

## Deployment

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

## Segment Reference

| Source Segment | Outlet | Stored As |
|---|---|---|
| Lounges / Atithya / Others | Any | EHPL |
| Subsidiary | Encalm Eats | Encalm Eats |
| Subsidiary | Encalm Sky Plates | Sky Plates |
| EHPL | Encalm Eats | Encalm Eats |
| EHPL | Encalm Sky Plates | Sky Plates |
| EHPL | Any other outlet | EHPL |
