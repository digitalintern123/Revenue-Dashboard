# PROJECT_CONTEXT.md
# Encalm Revenue Analytics — Project Context

> **Purpose of this file:** Single source of truth for any AI assistant or new developer
> working on this project. Read this before touching any code.

---

## 1. What This Project Is

A **Streamlit multi-page web application** for Encalm Group's airport business revenue analytics.

- **Entry point:** `streamlit run Home.py`
- **Stack:** Python 3.11+ · Streamlit ≥1.36 · SQLAlchemy 2.x · SQLite (local) / PostgreSQL (prod) · Pandas · Plotly
- **Tests:** 158 unit + integration tests (`python -m pytest tests/ -v`)

---

## 2. Business Context

Encalm Group operates airport hospitality services across **three Indian airports**:

| Location | Code | Terminals |
|----------|------|-----------|
| Delhi (IGI) | Delhi | T1, T2, T3 (Dom + Int + Arr) |
| Hyderabad (RGIA) | Hyderabad | Single terminal (Dom + Int) |
| Goa (GOA) | Goa | Single terminal (Dom + Int) |

### Three Business Segments

```
EHPL (Encalm Hospitality Private Ltd)     ← 95%+ of revenue
  ├── Lounges      (T1D, T2, T3 Dom, T3 Int, Arrivals)
  ├── Atithya      (Meet & Greet, Porter, Buggy, Enwrap)
  └── Others       (Business Centre, RDC, Bars)

Sky Plates                                 ← In-flight catering
Encalm Eats                               ← F&B subsidiary
```

---

## 3. Application Architecture

```
Browser (HTTPS)
     │
     ▼
Streamlit Server  (Home.py + pages/1–8)
     │
     ├── modules/auth.py          ← Login gate (FIRST on every page)
     ├── modules/database.py      ← ONLY module that touches SQLAlchemy
     ├── modules/revenue_analysis.py  ← Pure KPI functions (no DB)
     ├── modules/outlet_groups.py ← MIS table structure config
     ├── modules/terminal_mapping.py  ← Outlet→traffic pool mapping
     └── modules/formatting.py    ← Indian number formatting
     │
     ▼
Database  (SQLite locally at data/revenue_analytics.db)
          (PostgreSQL in production via DATABASE_URL secret)
```

---

## 4. File Structure

```
project_root/
├── Home.py                          # Entry: upload, DB management
├── requirements.txt
├── packages.txt                     # libpq-dev (for psycopg2 on Linux)
├── pytest.ini
├── conftest.py
├── startup_checks.py                # Production readiness validation
├── create_secrets.py                # CLI: generate secrets.toml
│
├── .streamlit/
│   ├── config.toml                  # maxUploadSize=200, CORS=false
│   ├── secrets.toml                 # NEVER committed. Contains passwords + DATABASE_URL
│   └── secrets.toml.example         # Template
│
├── pages/                           # Auto-discovered by Streamlit
│   ├── 1_Previous_Uploads.py        # Upload history + date browser
│   ├── 2_Executive_Summary.py       # KPI cards, charts, AOP
│   ├── 3_Revenue_Comparison.py      # 5-tab comparison + Dom/Int split
│   ├── 4_Traffic_and_Terminal.py    # Traffic, Penetration, SPP
│   ├── 5_Outlet_Performance.py      # Top/Bottom outlets, Rev/PAX
│   ├── 6_Business_Insights.py       # Management narrative + drivers
│   ├── 7_Service_Categories.py      # Per-category analysis
│   └── 8_Business_Performance.py   # Hierarchical MIS (Excel mirror)
│
├── modules/
│   ├── auth.py                      # PBKDF2 login, lockout, sessions
│   ├── app_logger.py                # RotatingFileHandler, safe_run()
│   ├── cached_db.py                 # @st.cache_data(ttl=60) wrappers
│   ├── comparison_widget.py         # Shared comparison selector UI
│   ├── data_processor.py            # Upload orchestration
│   ├── database.py                  # ALL DB interaction (2,732 lines)
│   ├── date_picker.py               # Year/Month/Day dropdown widget
│   ├── date_utils.py                # safe_month_shift()
│   ├── excel_parser.py              # Excel revenue parser
│   ├── formatting.py                # Indian number format (₹49,35,256)
│   ├── generate_password_hash.py    # CLI: hash passwords
│   ├── insights.py                  # Rule-based management narrative
│   ├── outlet_groups.py             # MIS row definitions + display names
│   ├── pdf_parser.py                # PDF revenue parser
│   ├── revenue_analysis.py          # All KPI calculations (970 lines)
│   ├── segment_tree_view.py         # Segment tree chart
│   ├── session.py                   # st.session_state helpers
│   ├── table_style.py               # Pandas Styler helpers
│   ├── terminal_mapping.py          # Outlet→terminal pool mapping
│   ├── traffic_parser.py            # Airport traffic file parser
│   ├── universal_parser.py          # Auto-detect parser
│   └── upload_status.py             # Upload progress display
│
│   └── ingestion/                   # 10-stage universal ingestion pipeline
│       ├── parser_factory.py        # Orchestrator
│       ├── file_detector.py
│       ├── table_detector.py
│       ├── schema_detector.py
│       ├── column_mapper.py
│       ├── data_cleaner.py
│       ├── normalizer.py
│       ├── validator.py
│       ├── confidence_engine.py
│       └── ocr_engine.py
│
├── docs/                            # ← You are here
│   ├── PROJECT_CONTEXT.md
│   ├── BUSINESS_RULES.md
│   ├── DATABASE_SCHEMA.md
│   ├── DATA_MAPPINGS.md
│   ├── MODULE_DEPENDENCIES.md
│   ├── UI_SPECIFICATION.md
│   ├── AI_RULES.md
│   ├── CHANGELOG.md
│   ├── KNOWN_ISSUES.md
│   └── CODING_STANDARDS.md
│
└── tests/
    ├── unit/
    │   ├── test_revenue_analysis.py  # 142 unit tests
    │   └── test_data_processor.py   # 16 unit tests
    └── integration/
        └── test_database.py
```

---

## 5. The Golden Rules (Never Break These)

1. **`require_login()` is ALWAYS the first call on every page.** Before `st.title()`, before anything.
2. **Only `database.py` imports SQLAlchemy.** No other module touches the ORM.
3. **`revenue_analysis.py` is pure — no DB calls.** All functions take DataFrames and return DataFrames/dicts.
4. **All money uses `format_money()`, all PAX uses `format_pax()`.** Never raw Python comma formatting.
5. **Percentage values are fractions internally.** `pct_change()` returns `0.08` for +8%. `format_pct()` converts to display.
6. **Outlet names are canonicalized at save time.** `canonicalize_outlet_name()` is called in `save_dataframe()`. Pages always see canonical names from the DB.
7. **`st.session_state` holds only lightweight references.** Never store DataFrames in session state.
8. **`safe_run()` wraps every error-prone section.** Never let one section crash the whole page.
9. **Indian number formatting throughout.** 4935256 → `₹49,35,256` (not `₹4,935,256`).
10. **`get_display_name(outlet, location)` for MIS display names.** Never hardcode display names in page 8.

---

## 6. Page Load Order (Every Page)

```python
st.set_page_config(...)     # 1. MUST be first Streamlit call
require_login()              # 2. Auth gate — st.stop() if not authenticated
bootstrap_session()          # 3. Ensure DB schema exists (runs init_db() once)
render_user_badge()          # 4. Sidebar: username + logout
# ... page content ...
```

---

## 7. Data Flow Summary

```
Uploaded file (PDF/Excel/CSV)
    │
    ▼ data_processor.process_uploaded_file()
    │
    ├── pdf_parser.py / excel_parser.py / traffic_parser.py / aop_parser.py
    │   └── universal_parser.py (fallback)
    │
    ▼ Normalised DataFrame: [date, segment, outlet, location, pax, revenue]
    │
    ▼ database.canonicalize_outlet_name()  ← outlet name normalisation
    │
    ▼ database.save_dataframe()  ← INSERT OR IGNORE (dedup by UNIQUE constraint)
    │
    ▼ revenue_master table
    │
    ▼ Analytics pages: database.load_for_date_range()
    │
    ▼ revenue_analysis.*()  ← KPI calculations
    │
    ▼ Streamlit display (formatting.py + table_style.py)
```

---

## 8. Environment Setup

```bash
# Development
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
python modules/generate_password_hash.py  # creates password hashes
streamlit run Home.py

# Run tests
python -m pytest tests/ -v  # must show 158 passed, 0 failed
```

---

## 9. Key Versions & Constraints

| Component | Version | Constraint |
|---|---|---|
| Python | 3.11+ | Required for `tomllib` (stdlib) |
| Streamlit | ≥1.36.0 | Required for `st.navigation` + MPA v1 |
| SQLAlchemy | ≥2.0.0 | Required for `declarative_base()` in modern form |
| Pandas | ≥2.0.0 | Required for `pd.concat` behavior changes |
| PostgreSQL | Any | Neon (serverless) preferred for Streamlit Cloud |

---

## 10. What NOT to Do

| ❌ Don't | ✅ Do instead |
|---|---|
| Add a new outlet without updating `terminal_mapping.py` | Always add to ALL THREE: `database.py` canonical map + `terminal_mapping.py` + `outlet_groups.py` |
| Call `database.*` from `revenue_analysis.py` | Pass DataFrames as arguments |
| Use `df.append()` | Use `pd.concat([df, new_row])` |
| Store DataFrames in `st.session_state` | Call `database.load_for_date_range()` per page run |
| Use `float("inf")` in any display path | Use `safe_div()` which returns `np.nan`, then `format_pct()` which returns `"—"` |
| Modify `outlet_groups.py` without testing page 8 | Run `python -m pytest tests/` after any change |
| Hardcode display names in page 8 | Use `get_display_name(outlet, location)` |
