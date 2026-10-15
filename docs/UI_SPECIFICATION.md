# UI Specification

Current layout of every page and the conventions shared between them.
Staff-facing explanations are in [USER_GUIDE.md](USER_GUIDE.md).

---

## 1. Global

### Shell (`Home.py`)
- `st.set_page_config(layout="wide")`, favicon = Encalm mark.
- `ui.inject_css()` (brand CSS) and `st.logo(...)` run on every rerun.
- Menu: `st.navigation`, sections **Data** (Upload Data, Previous Uploads) and
  **Dashboards** (EHPL, Encalm Eats, Sky Plates), Lucide icons via
  `ui.sidebar_nav_icons({url_path: icon})`.
- **Signed out:** `ui.hide_sidebar()` and `position="hidden"` — only the
  sign-in form (logo, username, password) is shown.
- Signed in: sidebar footer "Signed in as …" and **Log out**
  (`auth.render_user_badge`).
- Every page starts with `require_login()`, `bootstrap_session()`,
  `render_user_badge()`, then `ui.page_header(title, subtitle, icon=…)`.

### Branding (`modules/ui.py`, `assets/`)

| Token | Value | Use |
|---|---|---|
| navy | `#142248` | sidebar, headings, primary buttons, TOTAL rows |
| gold | `#CBA578` | accents, underlines, bars (never body text) |
| gold_text | `#8C6A3F` | gold-coloured text on white |
| gold_tint | `#F3ECE1` | subtotal rows, highlights |
| growth / decline / neutral | `#0B7A57` / `#B91C1C` / `#5F6677` | % changes |
| surface / border | `#F6F3EE` / `#E7E1D7` | inputs, cards |

Headings use **Montserrat** (Google Fonts); body uses the system sans-serif.
Icons are [Lucide](https://lucide.dev) SVGs in `assets/icons/`, drawn as CSS
masks so they take the text colour: `ui.icon_html(name)`,
`ui.tab_icons(key, [names])`, `ui.sidebar_nav_icons`. Streamlit's own
`icon=` parameter is not used for these.

### Helpers
`ui.section(title)` (gold-barred section heading), `ui.summary_line(current,
compare, location)` ("Showing … vs … · location"), `ui.field_label`.

---

## 2. Upload Data (`views/Uploads.py`, `/Uploads`, default page)

Tabs (`key="upload_tabs"`): **Daily Revenue** · **Historical Import** ·
**AOP Targets** · **Traffic** · **Database**.

- File uploader → sheet selector per workbook (auto-detect option) → action
  button (rate-limited for revenue).
- Result panel (`upload_status.render_result_from_process_result`): success /
  failure, rows saved, warnings, and the **rows not imported** expander
  (summary by reason, table with Excel row, CSV download).
- AOP tab: **Replace existing AOP for the months in this file** (on by
  default); after import, expanders for the Sky Plates / Encalm Eats outlet
  mapping (with *Result*) and rows not imported as EHPL AOP.
- Traffic tab: **Replace existing traffic for the dates and airports in this
  file** (on by default; `save_traffic_dataframe(replace=True)`); after import,
  "Replaced: n earlier rows" and a warning per sheet that produced no rows
  (`traffic_parser._skipped_sheets`).
- Every successful write calls `clear_data_cache()` then `st.rerun()`.

## 3. Previous Uploads (`views/Previous_Uploads.py`)

Tabs: **Upload History** · **Available Dates** · **Preview Data** (Single Date
/ Date Range, location filter) · **Load Date** (sets the active date used by
all dashboards).

## 4. Dashboards — shared parts (`modules/business_dashboard.py`)

1. **Filter bar** (bordered container): Report Date (year / month / day
   dropdowns), Compare by (+ Full Period / To-Date and the compare date, week,
   month or year), Location (All Locations + locations with data).
2. **Summary line** — what is being compared.
3. **Overview** — KPI cards: Revenue, PAX, AOP Target (+ variance), Traffic,
   PEN %, SPP (EHPL); Revenue, PAX, AOP for Encalm Eats / Sky Plates.
4. **Charts** (`modules/charts.py`): revenue by location/outlet (current vs
   compare bars) and a 30-day trend line.
5. **Tables** — one per location (All Locations) or one for the chosen location.

### Table conventions
- First row **TOTAL** (navy, white text); section totals (TOTAL LOUNGES …)
  bold on a gold tint, followed by their outlets sorted by current revenue.
- Missing values show **—**; % changes green for growth, red for decline, grey for zero or "—" (`modules/table_style.py`).
- Columns: PAX (current, compare), PAX Chg %, Revenue (current, compare),
  Rev Chg %, AOP, Variance; EHPL adds Traffic, PEN %, SPP and their changes.
- If both periods have the same label the compare columns get "(compare)".

## 5. EHPL (`views/EHPL.py` → `render_ehpl_page`)

Per location: the outlet table (`ehpl_layout.render_ehpl_location`, sections
LOUNGES, SPA, NAP & SHOWER, ATITHYA SERVICES, ENWRAP, PORTER, BAR, OTHERS)
then **Terminal-wise Performance**. Row rules: [DATA_MAPPINGS.md](DATA_MAPPINGS.md) §2, §4.

## 6. Encalm Eats (`views/Encalm_Eats.py`)

Tabs (`key="eats_tabs"`): **Analytics** · **Upload DSR**.
- Analytics: filter bar over DSR dates ∪ revenue-upload dates; caption says
  whether the figures come from the DSR, the revenue upload, or both; outlet
  table per location with AOP, **Other planned outlets – no sales (n)** row
  and an expander listing those outlets.
- Upload DSR: uploader (.xlsx/.xls, sheets named DD-MM-YYYY) → **Parse &
  Import DSR** → metrics (sheets, records, covers, revenue), period /
  locations / outlets, warnings, preview, save result.

## 7. Sky Plates (`views/Sky_Plates.py` → `render_subsidiary_page`)

One table per location (one *Encalm Sky Plates* row) with AOP.
