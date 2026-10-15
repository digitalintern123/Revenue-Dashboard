# Project Context — Encalm Revenue Analytics

> Start here as a developer (or AI assistant). Read [AI_RULES.md](AI_RULES.md)
> before changing code.

---

## 1. What this is

A Streamlit web app for Encalm Group's airport businesses.

- **Entry point:** `streamlit run Home.py`
- **Stack:** Python 3.11+ (server runs 3.14), Streamlit ≥ 1.40 (server runs
  1.60), pandas, SQLAlchemy 2, Plotly, openpyxl / pdfplumber
- **Database:** SQLite by default (`data/revenue_analytics.db`), PostgreSQL
  when `DATABASE_URL` is set
- **Tests:** 273 (`python -m pytest tests -q`)
- **Live:** Windows VPS behind IIS — see [SERVER_RUNBOOK.md](SERVER_RUNBOOK.md)

## 2. Business context

| Location | Notes |
|---|---|
| Delhi (IGI) | T1, T2, T3 (domestic, international, arrivals); most outlets |
| Hyderabad (RGIA) | one terminal, domestic + international |
| Goa | one terminal, domestic + international |
| Bhogapuram (Visakhapatnam) | data from Aug 2026 |

```
EHPL — Encalm Hospitality Pvt Ltd        (segment "EHPL"; business units Lounges / Atithya / Others)
   Lounges, Spa, Nap & Shower, Atithya (Meet & Greet), Porter, Buggy, Enwrap
   (baggage wrapping), Business Centre, RDC, bars
Sky Plates     — in-flight catering (IFK)  (segment "Sky Plates")
Encalm Eats    — F&B outlets               (segment "Encalm Eats")
```

Data sources: the daily/historical **revenue workbook** (long "Data" sheet:
Date, Location, Business, Sub-Business, PAX, Revenue, AOP), the **AOP master**
(monthly targets, lakhs), **airport traffic** workbooks and the **Encalm Eats
Master DSR** (one sheet per day, outlet level).

## 3. Architecture

```
Browser ─▶ (IIS) ─▶ Streamlit
                     Home.py   set_page_config, CSS, logo, menu (st.navigation)
                       │        sign-in screen hides the sidebar
                       ├── views/Uploads.py           Upload Data (default page)
                       ├── views/Previous_Uploads.py
                       ├── views/EHPL.py              → business_dashboard.render_ehpl_page
                       ├── views/Encalm_Eats.py       (own page code + DSR upload tab)
                       └── views/Sky_Plates.py        → business_dashboard.render_subsidiary_page
                     every page: require_login() → bootstrap_session() → content
                       │
   parsers ────────────┤  data_processor → excel_parser / pdf_parser / universal_parser
                       │  aop_parser, eats_skyplates_aop_parser, traffic_parser,
                       │  encalm_eats_dsr_parser
   reads (cached) ─────┤  cached_db (st.cache_data, 10 min, cleared after writes)
                       ▼
                     database.py  (only module that talks SQL) ─▶ SQLite / PostgreSQL
```

Pages are registered in `Home.py` with the page addresses used before
(`/Uploads`, `/Previous_Uploads`, `/EHPL`, `/Encalm_Eats`, `/Sky_Plates`).
They live in `views/`, **not** `pages/` — a `pages/` folder would also be
served by Streamlit's file-based routing, unstyled.

## 4. Module map

| Module | Purpose | Used by |
|---|---|---|
| `auth.py` | PBKDF2 logins from `secrets.toml`, lockout, 30-min inactivity timeout, server-side session tokens | Home, every page |
| `session.py` | `bootstrap_session` (schema check once per process, daily SQLite backup), active/compare date | pages, business_dashboard |
| `database.py` | Models, connection (`DATABASE_URL` / SQLite), saves, loads, canonical outlet names, traffic joins, rate limit | most modules |
| `cached_db.py` | `st.cache_data` wrappers for every render-path read; `clear_data_cache()` | pages, business_dashboard |
| `data_processor.py` | Upload orchestration: detect format, parse, validate (`_validate_and_clean_with_report`), save | Uploads |
| `excel_parser.py` | Revenue workbooks (long Data sheet, pivots); records skipped rows | data_processor |
| `import_report.py` | "Rows not imported" report: Excel row, reason; accepted date window | data_processor, excel_parser, upload_status |
| `pdf_parser.py`, `universal_parser.py`, `ingestion/` | PDF and other formats; generic schema detection pipeline | data_processor |
| `aop_parser.py` | EHPL AOP from the AOP master (outlet × month) and daily-total formats | Uploads |
| `eats_skyplates_aop_parser.py` | Sky Plates (IFK) and Encalm Eats (F&B) AOP; AOP→DSR outlet map; `load_segment_aop`, `align_aop_to_outlets` | Uploads, Encalm Eats, business_dashboard |
| `encalm_eats_dsr_parser.py` | Master DSR (per-day sheets, Delhi/Bhogapuram sections) | Encalm Eats |
| `traffic_parser.py` | Airport traffic workbooks | Uploads |
| `business_dashboard.py` | Filter bar, KPI cards, charts, EHPL tables (`_build_location_report`), subsidiary tables | EHPL, Sky Plates, Encalm Eats |
| `ehpl_layout.py` | EHPL table sections per location and rendering; terminal table | business_dashboard |
| `outlet_groups.py` | EHPL groups, display names, per-location overrides, `ALWAYS_SHOW_ROWS` | business_dashboard |
| `terminal_mapping.py` | Outlet → terminal traffic pool | database, business_dashboard, ehpl_layout |
| `revenue_analysis.py` | Pure KPI/comparison functions (no DB) | dashboards |
| `comparison_widget.py`, `date_picker.py`, `date_utils.py` | Compare-by selector, date dropdowns, date helpers | dashboards |
| `charts.py`, `table_style.py`, `formatting.py`, `ui.py` | Plotly charts, table colours, Indian number format, branding/CSS/icons | dashboards, pages |
| `upload_status.py`, `app_logger.py` | Upload result panels; error logging / `safe_run` | Uploads, dashboards |
| `insights.py`, `segment_tree_view.py`, `lounge_capacity.py` | From the earlier multi-page version; not used by the current pages | — |

## 5. Data flow

1. **Revenue upload** → `data_processor.process_uploaded_file` → parser →
   validation (dates, blanks, duplicates, month-end lines added together,
   skipped rows reported) → `database.save_dataframe` / `save_dataframe_batched_v2`
   (canonical outlet names, segment mapping) → `revenue_master`.
2. **AOP upload** → `aop_parser.parse_aop_auto` (EHPL) +
   `eats_skyplates_aop_parser.parse_eats_and_skyplates_aop` (Sky Plates, Eats) →
   optional delete of the months covered → `aop_target`.
3. **Traffic upload** → `traffic_parser` → `airport_traffic`.
4. **DSR upload** → `encalm_eats_dsr_parser.parse_dsr` → `encalm_eats_dsr`.
5. Every write calls `cached_db.clear_data_cache()`.
6. **Dashboards** read through `cached_db`, filter by location/period,
   build tables (EHPL: [DATA_MAPPINGS.md](DATA_MAPPINGS.md) §2) and prorate AOP
   ([BUSINESS_RULES.md](BUSINESS_RULES.md)).

## 6. Configuration

| Setting | Where |
|---|---|
| Logins (`[auth.users]`, `[auth.admins]`) | `.streamlit/secrets.toml` (never in git; `create_secrets.py` writes it) |
| `DATABASE_URL` (optional) | environment variable or `secrets.toml` |
| `DATA_DIR` (optional) | environment variable — folder for the SQLite file |
| Theme, upload size (300 MB), port | `.streamlit/config.toml` |
| Render test hosting | `render.yaml` (optional) |

## 7. Tests

`tests/unit` (parsers, KPI maths, EHPL line items, rows-not-imported, auth),
`tests/integration` (database), `tests/smoke` (every module imports).
`conftest.py` mocks Streamlit where needed. All 273 must pass before pushing.
