# UI_SPECIFICATION.md
# Encalm Revenue Analytics — UI Specification

---

## Global UI Conventions

- **Layout:** `st.set_page_config(layout="wide")` on all pages
- **Sidebar:** Username badge + Logout button (via `render_user_badge()`)
- **Number format:** Indian grouping (₹49,35,256 not ₹4,935,256)
- **Percentage format:** `+8.70%` (always 2 decimal places, leading sign)
- **Empty/missing values:** `"—"` (em dash U+2014)
- **Trend indicators:** `📈` (growth) / `📉` (decline) / `➡️` (stable) / `🆕` (new entrant)
- **Colors:** Growth = `#0B7A57` (dark green) / Decline = `#B91C1C` (dark red) / Neutral = `#64748B`

- **Visual style (2026 refresh):**
  - Theme in `.streamlit/config.toml`: navy `#1E3A5F` primary, gold `#C9A227` accent, Deploy toolbar hidden (`toolbarMode = "minimal"`).
  - Shared helpers in `modules/ui.py`: `inject_css()` (called once from `Home.py`), `page_header()`, `section()`, `summary_line()`, `COLORS`.
  - Charts in `modules/charts.py` (Plotly): current period = navy, compare period = grey, legend + hover on every chart.
  - Logo: `assets/logo.svg` wordmark; drop `assets/encalm_logo.png` in to use the real logo instead.
  - Dashboards (EHPL / Encalm Eats / Sky Plates): compact filter bar → summary line → Overview KPI cards → 2 charts → location tables.
  - Sidebar navigation is grouped: **Data** (Upload Data, Previous Uploads) and **Dashboards** (EHPL, Encalm Eats, Sky Plates).

---

## Home.py — Upload & Database Management

### Sections
1. **Upload & Analyze** — `st.file_uploader()` (multiple files, all formats)
   - Per-file: sheet selector for Excel (`st.selectbox`)
   - Per-file result: rows inserted/skipped, total revenue, spinner during processing
   - Rate limit: 20 Revenue uploads/hour per user

2. **Historical Excel Import** — For bulk historical imports
   - Format auto-detection (long vs wide pivot)
   - Two-step: parse first → preview → save with progress bar

3. **AOP Target Import** — AOP workbooks
   - Lists candidate sheets per file
   - User picks format (outlet_monthly / daily_outlet_pivot / daily_pivot)

4. **Traffic Data Import** — Airport traffic files
   - Auto-parses all known formats

5. **Database Management**
   - KPI cards: Total rows, date range, distinct dates
   - **Clear Session** button
   - **Reset Database** button — admin only (username ends in `_admin` or in `[auth.admins]`)

---

## Page 1 — Previous Uploads

### Sections
1. **Upload History table** — `st.dataframe()` with columns: Type, File, Date, Rows, Total Value, PAX, Uploaded At
2. **Available Dates** — one row per date with Revenue, PAX, Outlet Count
3. **Set Active Date** — clicking a date sets it as active for all other pages

---

## Page 2 — Executive Summary

### Date Selector
- `render_date_dropdown()` — Year/Month/Day dropdowns
- `render_comparison_selector()` — Day/Week/Month/Year-wise with Full Period / To-Date mode

### Sections
1. **KPI Cards** (4 columns):
   - Total Revenue (current period)
   - Compare Revenue
   - PAX (current period)
   - Revenue Change % with delta arrow

2. **AOP Card** (when AOP data exists):
   - AOP Target
   - Variance %
   - Variance Amount

3. **Segment Breakdown** — Revenue + PAX per segment (EHPL / Sky Plates / Encalm Eats)

4. **Location Breakdown** — Revenue + PAX per location (Delhi / Hyderabad / Goa)

5. **Charts** — Revenue by segment (bar), Revenue by location (bar), PAX trend (line)

---

## Page 3 — Revenue Comparison

### Date Controls
- `render_comparison_selector()` — comparison type + mode

### Five Tabs

#### Tab 1 — Detailed Comparison
- Outlet-level table: `compare_periods()` output
- Columns: Performance, Rev (current), Rev (compare), Rev YOY%, AOP Target, AOP Var%, PAX (current), PAX (compare), PAX YOY%, Traffic, PEN%, SPP
- Color coding: green/red on % columns
- Caption: "Traffic is each outlet's own terminal traffic pool. PEN % = outlet PAX ÷ that outlet's terminal traffic."

#### Tab 2 — Segment Summary
- Revenue/PAX comparison by segment

#### Tab 3 — Location → Services
- Revenue/PAX by (location, segment)

#### Tab 4 — Penetration % / SPP
- Location-level Traffic/PEN%/SPP comparison table
- Uses `join_revenue_with_traffic()` (location-level, NOT outlet-specific)

#### Tab 5 — Domestic vs International
- Revenue split by Dom/Int/Ancillary classification
- Donut chart
- Classification via `_OUTLET_MAP` dict (lowercase outlet name → category)
- Caption: "Add new outlets to `_OUTLET_MAP` in this file to adjust classification."

### Multi-Period Snapshot
- Below all tabs
- Week/Month/Year comparisons side by side

---

## Page 4 — Traffic & Terminal Analysis

### Date Controls
- `render_comparison_selector()` + location selector

### Sections
1. **Penetration % / SPP by Location** — KPI table + metric cards
   - Uses `join_revenue_with_traffic()` (location-level)

2. **Driver Narrative** — Plain-English attribution
   - "Revenue increased despite traffic decline due to higher SPP"

3. **Terminal-wise Breakdown** (location-specific)
   - Revenue/PAX/Traffic/PEN%/SPP per terminal
   - Composite terminals (Porter Pool, All Dep, All, T3 Total, T3 Arr) show revenue/PAX but Traffic = `—`
   - Caption explaining why composite terminals show `—`
   - Friendly labels for composite terminals: `"Porter Pool"` → `"Porter Pool (T1+T2+T3 Dep+Arr)"`

4. **Unmapped Outlets expander** — shows any outlets without a terminal mapping

5. **Domestic vs International Traffic split** — Dom/Int table + pie charts (Delhi only)

---

## Page 5 — Outlet Performance

### Date Controls
- `render_comparison_selector()`

### Sections
1. **Top 10 by Revenue** — Horizontal bar chart
   - Outlet labels include location: `"Outlet Name (Delhi)"`

2. **Bottom 10 by Revenue** — Same format

3. **Change by Outlet** — Diverging bar chart
   - Green = growth, red = decline

4. **Revenue per PAX table** — Outlet-level Rev/PAX for current period

---

## Page 6 — Business Insights

### Date Controls
- `render_comparison_selector()`

### Sections
1. **Management Summary** (button-triggered)
   - `insights.generate_summary()` — rule-based narrative
   - Cached in `st.session_state`; invalidated when dates change
   - Button label: "Generate Insights" / "Regenerate Insights"

2. **Volume vs Spend Driver Table**
   - Per-outlet: Revenue Δ%, PAX Δ%, Rev/PAX Δ%, Traffic, PEN%, SPP, AOP, classification
   - Classification: `classify_driver()` → "Volume-driven" / "Spend-driven" / "Mixed" / "Flat"
   - Caption: "Traffic is each outlet's own terminal traffic pool."

---

## Page 7 — Service Categories

### Date Controls
- `render_comparison_selector()`

### Seven Tabs
| Tab | Filter |
|-----|--------|
| Total Airport Services | All segments |
| EHPL — All | segment == "EHPL" |
| EHPL — Lounges | segment == "EHPL" AND business_unit == "Lounges" |
| EHPL — Atithya | segment == "EHPL" AND business_unit == "Atithya" |
| EHPL — Others | segment == "EHPL" AND business_unit == "Others" |
| Sky Plates | segment == "Sky Plates" |
| Encalm Eats | segment == "Encalm Eats" |

### Per Tab Content
- Revenue KPI card
- PAX KPI card
- Revenue Change vs compare period
- AOP Variance (when data exists)
- **Penetration %/SPP** — uses `join_revenue_with_traffic()` (location-level)
- Location bar chart

---

## Page 8 — Business Performance (MIS)

### Date Controls
- `render_date_dropdown()` — current period (Year/Month/Day)
- `render_comparison_selector()` — comparison type

### Structure
```
Three tabs: 🏙️ Delhi | 🏙️ Hyderabad | 🏖️ Goa
  Each tab:
    MIS Table (scrollable, full width)
    [Divider + location label]

Below all tabs:
    Grand Total — All Locations
```

### MIS Table Columns
| Column | Description |
|--------|-------------|
| Performance | Outlet display name (indented) or bold subtotal label |
| Rev (current label) | `format_money(cur_rev)` |
| Rev (compare label) | `format_money(cmp_rev)` |
| Rev YOY% | `format_pct(rev_yoy)` with color |
| AOP Target | `format_money(aop)` (when available) |
| AOP Var% | `format_pct(aop_var)` with color |
| PAX (current label) | `format_pax(cur_pax)` |
| PAX (compare label) | `format_pax(cmp_pax)` |
| PAX YOY% | `format_pct(pax_yoy)` with color |
| Traffic (current) | `format_pax(cur_traffic)` or `—` |
| Traffic (compare) | `format_pax(cmp_traffic)` or `—` |
| Traffic Δ% | `format_pct(traffic_chg)` with color |
| PEN % (current) | `f"{pen_cur:.2f}%"` or `—` |
| PEN % (compare) | `f"{pen_cmp:.2f}%"` or `—` |
| PEN Δ% | `format_pct(pen_chg)` with color |
| SPP (current) | `format_spp(spp_cur)` |
| SPP (compare) | `format_spp(spp_cmp)` |
| SPP Δ% | `format_pct(spp_chg)` with color |

### Table Styling
- **Subtotal rows** — bold font weight (CSS applied via `st.dataframe` style)
- **Grand total (TOTAL EHPL)** — bold + slight background differentiation
- **Indented outlet rows** — 2-space indent via `"  Outlet Name"` prefix in Performance column
- **AOP columns** — only shown when AOP data exists for the selected period

### Error Handling
Each location tab wrapped in `try/except` with:
- Friendly error: "The comparison table could not be built"
- Expandable traceback: "🔍 Technical detail (for support)"

---

## Navigation Structure

```
Sidebar (auto-generated by Streamlit MPA):
  📊 Home
  📋 Previous Uploads
  📈 Executive Summary
  🔄 Revenue Comparison
  🛫 Traffic and Terminal
  🏪 Outlet Performance
  💡 Business Insights
  🏷️ Service Categories
  📊 Business Performance
  ─────────────────────
  👤 Signed in as <username>
  🔴 Log out
```
