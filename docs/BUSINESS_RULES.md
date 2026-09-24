# BUSINESS_RULES.md
# Encalm Revenue Analytics — Business Rules & KPI Calculations

> All formulas verified against actual code. File/line references current as of July 2026.

---

## 1. Core KPI Formulas

| KPI | Formula | Function | File:Line |
|-----|---------|----------|-----------|
| Revenue Change % | `(current − previous) / previous` | `pct_change()` | `revenue_analysis.py:83` |
| PAX Change % | `(current − previous) / previous` | `pct_change()` | `revenue_analysis.py:83` |
| Penetration % (PEN%) | `PAX / Traffic × 100` | `penetration_pct()` | `revenue_analysis.py:411` |
| SPP | `Revenue / Traffic` | `spp()` | `revenue_analysis.py:417` |
| Revenue per PAX | `Revenue / PAX` | `safe_div(revenue, pax)` | `revenue_analysis.py:121` |
| AOP Variance % | `(Actual − Target) / Target` | `pct_change(actual, aop)` | `revenue_analysis.py:284` |
| AOP Variance Abs | `Actual − Target` | direct subtraction | `revenue_analysis.py:305` |
| AOP Proration | `Monthly_AOP × (days_selected / days_in_month)` | Page 8 inline | `8_Business_Performance.py:87` |

---

## 2. Threshold Constants

```python
# revenue_analysis.py:25-26
GROWTH_THRESHOLD  = 0.05   # +5%: "📈 Revenue Increase"
DECLINE_THRESHOLD = -0.05  # -5%: "📉 Revenue Decline"
# Between -5% and +5%: "➡️ Stable"
```

These constants are imported by all pages. **Never hardcode `0.05` or `-0.05` anywhere else.**
Reference: `revenue_analysis.GROWTH_THRESHOLD`, `revenue_analysis.DECLINE_THRESHOLD`.

---

## 3. Trend Classification

```python
# revenue_analysis.py:41-62
def classify_trend(pct_change, metric_label="Revenue") -> str:
    # None → "—" (no baseline or no data)
    # < -0.05 → "📉 Revenue Decline" (or "PAX Decline")
    # > +0.05 → "📈 Revenue Increase" (or "PAX Increase")
    # else   → "➡️ Stable"

# revenue_analysis.py:63-82
def classify_trend_with_new(pct_change, current, compare, metric_label) -> str:
    # Same as classify_trend PLUS:
    # compare == 0 AND current > 0 → "🆕 New"  (NEW_ENTRANT_TREND)
```

`classify_trend_with_new()` is used in `compare_periods()` for the trend column.
`classify_trend()` is used everywhere else.

---

## 4. Revenue Comparison Logic

```python
# revenue_analysis.py:134-197
def compare_periods(current_df, compare_df, group_cols=GROUP_COLS) -> pd.DataFrame:
```

**Output columns:**
- `segment`, `outlet`, `location`
- `current_revenue`, `compare_revenue`, `revenue_change`, `revenue_pct_change`, `revenue_trend`
- `current_pax`, `compare_pax`, `pax_change`, `pax_pct_change`, `pax_trend`

**Group columns** default: `["segment", "outlet", "location"]`

**Edge cases:**
- Outlet in current but not compare → `compare_revenue = 0`, `trend = "🆕 New"`
- Outlet in compare but not current → `current_revenue = 0`, `trend = "📉 Revenue Decline"`
- Both zero → `pct_change = None`, `trend = "—"`

---

## 5. PAX vs Traffic — Critical Distinction

| Metric | Source | Meaning |
|--------|--------|---------|
| **PAX** | `revenue_master.pax` | Encalm customers who used our service |
| **Traffic** | `airport_traffic.traffic` | Total airport/terminal visitors (everyone who passed through) |

- `PAX / Traffic × 100 = PEN%` (what fraction of airport visitors chose Encalm)
- `Revenue / Traffic = SPP` (revenue yield per airport visitor)
- PAX and Traffic are **never interchangeable**. Traffic is always > PAX.

---

## 6. Traffic Denominator per Outlet (Delhi)

| Outlet Group | Terminal Pool | Sentinel |
|---|---|---|
| T1D Lounges (T1D, Prive T1, Amex T1) | T1 Dep | `T1 Dep` |
| T2 Lounges | T2 Dep | `T2 Dep` |
| T3 Domestic (DL02/3/4, D49, Rupay, Centurion, Air India, Dom Spa) | T3 Dom Dep | `T3 Dom Dep` |
| T3 International (INL, Prive T3, Xenia, AI Intl, Intl Spa) | T3 Int Dep | `T3 Int Dep` |
| T3 Arrivals (LA22, LA01, LA12, RL Delhi/Reserved Lounge) | T3 Dom Arr + T3 Int Arr | `T3 Arr` (composite) |
| Enwrap / Baggage Wrapping | All Departures (T1+T2+T3D+T3I Dep) | `All Dep` (composite) |
| Atithya / Meet & Greet | All 8 pools — entire airport | `All` (composite) |
| Porter | T1+T2 Dep+Arr + T3 Dom+Int Dep | `Porter Pool` (composite) |
| Buggy | All 4 T3 pools | `T3 Total` (composite) |
| Business Centre, RDC | None | `None` (no traffic metric) |

Composite sentinels are NOT stored in `airport_traffic.terminal`.
They are resolved in `database.join_revenue_with_traffic_by_outlet()` at query time.

---

## 7. Traffic Denominator per Outlet (Hyderabad & Goa)

| Outlet Group | Terminal |
|---|---|
| Domestic Lounge | `Domestic` |
| International Lounge, Encalm Prive, GAT, Airport Lodge | `International` |
| Atithya (M&G), Porter, Buggy, Baggage Wrapping | `All` (whole airport) |

---

## 8. Subtotal Traffic Aggregation Rules (Page 8)

`_subtotal_traffic()` in `8_Business_Performance.py` — three cases:

1. **Same pool (e.g. all T3 Int outlets):** Unique values = 1 → return it (don't sum duplicates)
2. **All-airport group present** (Atithya M&G or HYD/GOA Atithya): → return MAX (= whole airport)
3. **Overlapping pool dominates (≥80% of sum):** → return MAX
4. **Distinct additive pools (T1 + T2 + T3D):** → SUM

```python
# 8_Business_Performance.py
_ALL_AIRPORT_GROUPS: frozenset[str] = frozenset({
    "Atithya (M&G)",   # Delhi
    "Atithya",         # HYD/GOA
})
```

---

## 9. AOP (Annual Operating Plan) Rules

### Source tables
- `aop_target` — per-outlet, per-month targets (from AOP workbooks)
- `aop_target_daily` — location-level daily totals (alternative source)

### Proration
When selected period is a partial month:
```
AOP_for_period = Monthly_AOP × (days_selected / days_in_month)
```
Uses `current_start.month` and `calendar.monthrange()`. Cross-month periods use the first month's days.

### Page 8 AOP loading (special rule)
Page 8 **bypasses** `join_revenue_with_aop()` and loads directly from `load_aop_targets_for_range()`.
**Reason:** `join_revenue_with_aop()` prioritises `aop_target_daily` (location-level) over per-outlet data.
When both tables have data, this blocks per-outlet AOP from appearing in the MIS table.
**File:** `8_Business_Performance.py:72–101`

### AOP Outlet Name Matching
AOP outlet names are canonicalized via `canonicalize_outlet_name()` at:
1. Save time: `save_aop_targets()` in `database.py:2049`
2. Load time (page 8): `_co_aop = canonicalize_outlet_name` applied inline
3. Join time: `join_revenue_with_aop()` applies it before merging

---

## 10. Segment & Business Unit Mapping

```
Raw segment from source file   →   Stored segment   Stored business_unit
──────────────────────────────────────────────────────────────────────────
"EHPL"                         →   "EHPL"           inferred from outlet
"Lounges"                      →   "EHPL"           "Lounges"
"Atithya"                      →   "EHPL"           "Atithya"
"Others"                       →   "EHPL"           "Others"
"Subsidiary" + Sky Plates outlet →  "Sky Plates"    "Sky Plates"
"Subsidiary" + Encalm Eats     →   "Encalm Eats"   "Encalm Eats"
```

**Function:** `canonicalize_segment_and_business_unit()` in `database.py:617`

---

## 11. Driver Classification (Volume vs Spend)

```python
# revenue_analysis.py:352-369
def classify_driver(pax_pct, rev_per_pax_pct) -> str:
    # Both up   → "Mixed" (Volume + Spend both contributed)
    # PAX up, Rev/PAX flat/down → "Volume-driven"
    # Rev/PAX up, PAX flat/down → "Spend-driven"
    # Both flat/down → "Flat" or follows dominant decline
```

Used on **Page 6 Business Insights** driver table.

---

## 12. Comparison Types and Date Range Resolution

`resolve_comparison_ranges()` in `revenue_analysis.py:759`

| Type | Current period | Compare period |
|---|---|---|
| Day-wise | `anchor_date` | Prior date with data (or `anchor_date - 1`) |
| Week-wise Full | Mon–Sun of anchor's week | Mon–Sun of selected prior week |
| Week-wise To-Date | Mon–anchor_date | Mon–same weekday of prior week |
| Month-wise Full | Jan 1–last day of anchor's month | Same for selected prior month |
| Month-wise To-Date | 1st–anchor_date | 1st–same day-of-month of prior month |
| Year-wise Full | Jan 1–Dec 31 of anchor's year | Same for selected prior year |
| Year-wise To-Date | Jan 1–anchor_date | Jan 1–same day-of-year of prior year |

---

## 13. New Entrant Rule

When an outlet has `compare_revenue == 0` (or no prior data) but `current_revenue > 0`:
- `pct_change()` returns `None` (not inf)
- `classify_trend_with_new()` returns `NEW_ENTRANT_TREND = "🆕 New"`
- This is shown in the trend column on Pages 3, 6, 8

---

## 14. Upload Rate Limiting

- **Limit:** 20 Revenue uploads per user per hour
- **Backend:** DB-backed (`upload_history` table), cross-session, cross-tab
- **Function:** `check_upload_rate_limit(username)` in `database.py`
- **Returns:** `(bool allowed, str message)`

---

## 15. Session Timeout

- **Duration:** 8 hours from login (`_SESSION_TIMEOUT_HOURS = 8` in `auth.py:52`)
- **Check:** On every page load in `require_login()`
- **Action:** Automatic logout + redirect to login form

---

## 16. Login Lockout

- **Trigger:** 5 consecutive wrong passwords (`_MAX_ATTEMPTS = 5` in `auth.py:50`)
- **Duration:** 5 minutes (`_LOCKOUT_SECONDS = 300` in `auth.py:51`)
- **Backend:** `login_attempts` table (persists across tabs/sessions/incognito)
- **Reset:** On successful login — `clear_failed_logins(username)` in `database.py`
