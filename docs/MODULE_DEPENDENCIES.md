# MODULE_DEPENDENCIES.md
# Encalm Revenue Analytics — Module Dependencies

---

## Dependency Graph

```
                    ┌─────────────────┐
                    │    Home.py      │
                    └────────┬────────┘
                             │ imports
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
    modules/auth.py    modules/database.py  modules/data_processor.py
          │                  │                  │
          │          ┌───────┴───────┐           ├── pdf_parser.py
          │          ▼               ▼           ├── excel_parser.py
          │    date_utils.py  terminal_mapping.py ├── traffic_parser.py
          │                                       ├── aop_parser.py
          │                                       └── universal_parser.py
          │                                            └── ingestion/*
          │
    ┌─────▼────────────────────────────────────────────────────────┐
    │              pages/1–8 (all analytics pages)                  │
    │                                                               │
    │  requires_login()    ← auth.py (FIRST)                       │
    │  bootstrap_session() ← session.py                            │
    │  render_user_badge() ← auth.py                               │
    │                                                               │
    │  database.*          ← database.py (data loading)            │
    │  revenue_analysis.*  ← revenue_analysis.py (KPIs)            │
    │  comparison_widget.* ← comparison_widget.py (date UI)        │
    │  formatting.*        ← formatting.py (display)               │
    │  table_style.*       ← table_style.py (Styler)               │
    │  app_logger.*        ← app_logger.py (error handling)        │
    │  outlet_groups.*     ← outlet_groups.py (Page 8 only)        │
    └───────────────────────────────────────────────────────────────┘
```

---

## Module-by-Module Reference

### `modules/database.py` (2,732 lines)
**Imports from project:** `date_utils`, `terminal_mapping`
**Imported by:** ALL pages, `data_processor`, `table_style`, `cached_db`, `insights`
**External deps:** `sqlalchemy`, `pandas`
**Key exports:**
- `init_db()`, `reset_db()`, `get_db_stats()`
- `save_dataframe()`, `save_dataframe_batched()`, `save_dataframe_batched_v2()`
- `load_for_date_range()`, `load_for_date()`, `load_all()`
- `save_traffic_dataframe()`, `get_traffic_total_for_range()`
- `join_revenue_with_traffic()`, `join_revenue_with_traffic_by_outlet()`
- `save_aop_targets()`, `save_aop_targets_daily()`
- `load_aop_targets_for_range()`, `join_revenue_with_aop()`
- `get_available_dates()`, `get_available_year_months()`
- `canonicalize_outlet_name()`, `canonicalize_segment_and_business_unit()`
- `register_session()`, `invalidate_session()`, `is_session_valid()`, `touch_session()`
- `record_failed_login()`, `clear_failed_logins()`, `get_lockout_status()`
- `check_upload_rate_limit()`, `_record_upload_history()`

---

### `modules/revenue_analysis.py` (970 lines)
**Imports from project:** `date_utils`
**Imported by:** ALL pages, `table_style`, `insights`
**External deps:** `pandas`, `numpy`
**No DB calls** — pure functions only
**Key exports:**
- `pct_change()`, `safe_div()`, `classify_trend()`, `classify_trend_with_new()`
- `compare_periods()`, `compare_segments()`, `compare_locations()`
- `summarize_period()`, `aop_variance()`, `volume_vs_spend_table()`
- `penetration_pct()`, `spp()`, `penetration_and_spp_table()`
- `penetration_spp_variance()`, `explain_revenue_driver()`
- `resolve_comparison_ranges()`, `week_range()`, `month_bounds()`, `year_bounds()`
- `GROWTH_THRESHOLD`, `DECLINE_THRESHOLD`, `NEW_ENTRANT_TREND`, `GROUP_COLS`

---

### `modules/auth.py` (306 lines)
**Imports from project:** `database` (for session/lockout DB calls)
**Imported by:** ALL pages
**External deps:** `streamlit`, `hashlib`, `hmac`, `secrets`
**Key exports:**
- `require_login()` — MUST be called first on every page
- `is_logged_in()`, `current_user()`, `logout()`
- `render_user_badge()` — sidebar username + logout button
- Constants: `_MAX_ATTEMPTS=5`, `_LOCKOUT_SECONDS=300`, `_SESSION_TIMEOUT_HOURS=8`

---

### `modules/outlet_groups.py` (457 lines)
**Imports from project:** None (standalone)
**Imported by:** `pages/8_Business_Performance.py` only
**Key exports:**
- `DELHI_GROUPS`, `DELHI_SUBTOTALS`, `DELHI_ROW_ORDER`
- `HYD_GROUPS`, `HYD_SUBTOTALS`, `HYD_ROW_ORDER`
- `GOA_GROUPS`, `GOA_SUBTOTALS`, `GOA_ROW_ORDER`
- `OUTLET_DISPLAY_NAMES` (124 entries)
- `LOCATION_DISPLAY_OVERRIDES`
- `get_display_name(outlet, location)` — page 8 display name lookup
- `get_outlet_group(outlet, groups)` — find which group an outlet belongs to

---

### `modules/terminal_mapping.py` (511 lines)
**Imports from project:** None (standalone)
**Imported by:** `database.py`, `pages/4_Traffic_and_Terminal.py`
**Key exports:**
- `get_terminal_for_outlet(outlet, location)` → terminal label or sentinel
- `add_terminal_column(df)` → adds "terminal" column to revenue DataFrame
- `get_unmapped_outlets(df)` → rows where terminal == "Unmapped"
- `get_known_terminals_for_location(location)` → list of terminals
- Private dicts: `_DELHI_OUTLET_TO_TERMINAL` (152 entries), `_HYDERABAD_OUTLET_TO_TERMINAL` (57), `_GOA_OUTLET_TO_TERMINAL` (31)

---

### `modules/formatting.py` (120 lines)
**Imports from project:** None
**Imported by:** ALL pages, `table_style`, `insights`
**Key exports:**
- `format_money(value)` → `"₹49,35,256"` or `"—"`
- `format_pax(value)` → `"1,22,385"` or `"—"`
- `format_pct(value)` → `"+8.70%"` or `"—"`
- `format_spp(value)` → `"95.57"` or `"—"`

---

### `modules/app_logger.py` (289 lines)
**Imports from project:** None
**Imported by:** ALL pages, `database`, `data_processor`
**Key exports:**
- `safe_run(context, error_type, reraise)` — context manager wrapping error-prone sections
- `show_friendly_error(error_type)` — renders user-friendly Streamlit error
- `log_exception(exc, context)` — writes to rotating log file
- Error types: `"no_data"`, `"traffic_columns"`, `"comparison_error"`, `"db_error"`, `"corrupted_file"`, `"generic"`

---

### `modules/cached_db.py` (~90 lines)
**Imports from project:** `database`
**Imported by:** ALL pages (via session.py or direct)
**Key exports:** `@st.cache_data(ttl=60)` wrappers:
- `get_available_dates()`
- `load_for_date_range(start, end)`
- `load_for_date(date)`
- `load_aop_targets_for_range(start, end)`
- `load_traffic_for_date_range(start, end, location)`
- `get_available_traffic_dates()`
- `clear_data_cache()` — call after uploads to invalidate all caches

---

### `modules/session.py` (~100 lines)
**Imports from project:** `database`
**Imported by:** ALL pages
**Key exports:**
- `bootstrap_session()` — runs `init_db()` once per Streamlit session
- `get_active_date()`, `set_active_date(date)`
- `get_compare_date()`, `set_compare_date(date)`
- `default_active_date()` — most recent DB date or today

---

### `modules/date_utils.py` (~60 lines)
**Imports from project:** None
**Imported by:** `database`, `revenue_analysis`, `comparison_widget`
**Key exports:**
- `safe_month_shift(d: date, months: int) -> date` — shift a date by N months, clamping to last valid day of month

---

### `modules/comparison_widget.py` (~230 lines)
**Imports from project:** `revenue_analysis`, `date_picker`
**Imported by:** ALL analytics pages (1–8)
**Key exports:**
- `render_comparison_selector(anchor_date, key_prefix) -> dict` — renders comparison type UI, returns `ranges` dict

---

### `modules/date_picker.py` (~180 lines)
**Imports from project:** None
**Imported by:** `comparison_widget`, `pages/8_Business_Performance.py`
**Key exports:**
- `render_date_dropdown(available_dates, key_prefix, label, default_date) -> date`

---

### `modules/table_style.py` (633 lines)
**Imports from project:** `database`, `revenue_analysis`, `formatting`
**Imported by:** Pages 3, 4, 5, 6, 7
**Key exports:**
- `style_pct_columns(df, pct_cols)` — green/red coloring
- `add_location_traffic_pen_columns(df, ...)` — appends Traffic/PEN%/SPP columns
- `add_aop_columns(df, ...)` — appends AOP Target/Variance columns
- `render_penetration_spp_table(...)` — Tab 4 of Revenue Comparison
- `metric_delta_args(pct_value)` — for `st.metric(delta=...)`

---

### `modules/insights.py` (362 lines)
**Imports from project:** `revenue_analysis`, `formatting`, `table_style`
**Imported by:** `pages/6_Business_Insights.py`
**Key exports:**
- `generate_summary(current_df, yesterday_df, ...) -> list[str]` — rule-based management narrative
- Escapes all outlet/location names with `html.escape()` to prevent XSS

---

### `modules/data_processor.py` (1,120 lines)
**Imports from project:** `database`, `pdf_parser`, `excel_parser`, `traffic_parser`, `aop_parser`, `universal_parser`, `app_logger`
**Imported by:** `Home.py` only
**Key exports:**
- `process_uploaded_file(file_obj, file_name, save_to_db, excel_sheet_name)` — main upload handler
- `_validate_upload(file_bytes, file_name)` — magic bytes + null-byte density check

---

### `modules/ingestion/parser_factory.py`
**Imports from project:** all 9 other ingestion sub-modules
**Imported by:** `universal_parser.py`
**10-stage pipeline orchestrator:** file_detector → table_detector → ocr_engine → schema_detector → data_cleaner → column_mapper → normalizer → validator → confidence_engine → IngestionResult

---

## Page-Level Import Summary

| Page | auth | database | revenue_analysis | outlet_groups | terminal_mapping | table_style | insights |
|------|------|----------|------------------|---------------|------------------|-------------|---------- |
| Home.py | ✅ | ✅ | — | — | — | — | — |
| 1_Previous_Uploads | ✅ | ✅ | — | — | — | — | — |
| 2_Executive_Summary | ✅ | ✅ | ✅ | — | — | — | — |
| 3_Revenue_Comparison | ✅ | ✅ | ✅ | — | — | ✅ | — |
| 4_Traffic_and_Terminal | ✅ | ✅ | ✅ | — | ✅ | ✅ | — |
| 5_Outlet_Performance | ✅ | ✅ | ✅ | — | — | — | — |
| 6_Business_Insights | ✅ | ✅ | ✅ | — | — | ✅ | ✅ |
| 7_Service_Categories | ✅ | ✅ | ✅ | — | — | — | — |
| 8_Business_Performance | ✅ | ✅ | ✅ | ✅ | — | — | — |
