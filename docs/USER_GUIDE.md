# User Guide — Encalm Revenue Analytics

For everyone who uploads files or reads the dashboards. No technical
knowledge needed.

---

## 1. Signing in

- Open **dashboard.encalmhospitality.com**. You see only the Encalm logo and
  the sign-in form — the menu appears after you sign in.
- Five wrong passwords in a row lock the account for 5 minutes.
- After **30 minutes without any activity** you are signed out automatically.
- **Log out** is at the bottom of the left sidebar.
- Logins are created by the administrator (see the server runbook).

Old bookmarks such as `/EHPL` or `/Encalm_Eats` still work.

---

## 2. Uploading data (Upload Data page)

The page has four tabs. Formats are detected automatically; if a workbook has
several sheets you can pick the sheet or leave it on auto-detect.

| Tab | What to upload | Notes |
|---|---|---|
| **Daily Revenue** | The daily revenue report (Excel, PDF, CSV and more), or the full revenue workbook (e.g. the "Revenue Dashboard" file with the long *Data* sheet) | Usual daily upload; also loads many months at once. By default lines already stored (same date, outlet, location) are kept and the file's copy is skipped. Tick **"Replace existing revenue for the dates and locations in this file"** to upload a **corrected** file: everything stored for each date + location in the file is replaced by the file's figures. |
| **AOP Targets** | The AOP master workbook | Leave **"Replace existing AOP for the months in this file"** ticked so a corrected file overwrites old targets. |
| **Traffic** | Airport traffic workbooks (.xlsx/.xls), e.g. one sheet per airport (Delhi, Hyd, Goa, Vizag) | Needed for PEN % and SPP. Leave **"Replace existing traffic for the dates and airports in this file"** ticked so a corrected file overwrites earlier figures. Any sheet that gives no rows is listed in a warning. |
| **Database** | — | Shows what is stored. |

The **Encalm Eats DSR** (Master DSR and Starbucks & McD files) is uploaded on
the **Encalm Eats** page → **Upload DSR** tab.

### Analyse, then Save

Every upload works in two steps. Nothing is saved until you press **Save**.

1. Choose the file(s) and press **🔍 Analyse**. A panel shows:
   - **Confidence** — how sure the app is that it read the file correctly
     (100 % for the revenue workbook when every figure is accounted for).
   - **What the app found in the file** — every sheet, the layout recognised
     (e.g. *Revenue workbook — long table*, *Hyderabad side-by-side, PAX only*),
     the rows and dates it gave, and whether it is imported, not used, empty or
     not recognised. No sheet is skipped without being listed.
   - **Checks before saving** (they never change the data — the file is
     always stored as it is):

     | Check | Upload | What it means |
     |---|---|---|
     | Every figure in the file is accounted for | Revenue | File total = imported + "rows not imported". A gap means do not save. |
     | Outlets never seen before | Revenue | New names, with a stored name they may be a misspelling of |
     | Stored lines with different figures | Revenue, Traffic | How many stored lines this file would change — tick **Replace** if it is the corrected file |
     | Dates with identical figures | Revenue, Traffic | A day copied by mistake in the file (e.g. 4 = 5 Apr 2026) |
     | PAX but no revenue | Revenue | An outlet with PAX and 0 revenue on several days |
     | Unusual revenue per PAX / unusual traffic days | Revenue, Traffic | Far from the usual value — a typo or a genuine one-off |
     | Month changed by more than 40 % | Traffic | Against the stored earlier month — e.g. a column read as the wrong terminal |
     | Months already stored | AOP | Replaced if **Replace** is ticked |
     | Records already stored, unknown outlets, grand total | DSR | |
2. Read the warnings, correct the file if needed, then press **💾 Save**
   (or **✖️ Cancel**).

### A file in a new layout: "Teach the app this layout"

If the app cannot read a revenue or traffic file with confidence, the panel
shows **🧩 Teach the app this layout**:

1. Pick the sheet and the row that holds the column headers.
2. Check the **Role** of every column — the app's guess and its confidence
   are filled in. Revenue: Date, Location, Business, Outlet, PAX, Revenue,
   AOP, or *Revenue/PAX (date in header)* for a sheet with one column per day.
   Traffic: Date, Location, Terminal, Traffic (columns with the same
   *Terminal* label are added, e.g. Domestic arrivals + departures).
3. Type a value for anything the file has no column for (e.g. Location: Goa).
4. Press **Read with this mapping** — the normal checks run on the result.
5. Keep **Remember this layout** ticked and give it a name, then **Save**.
   The next file with the same headers (at least 90 % of them) is read
   automatically and shown as *Saved layout: <name>*.

Saved layouts are listed under **Upload Data → Database**; admins can delete
one there.

### After a revenue upload: "rows not imported"

The result panel says how many rows were saved. If any line of the file was
left out, an expander **"rows not imported"** lists each one with its **Excel
row number** and the **reason**, and a CSV download. Common reasons:

| Reason | What to do |
|---|---|
| Date cell is empty or an Excel error such as #VALUE! | Fix the date in the file and upload again |
| Date is not a valid date / outside the accepted range (1 Jan 2015 to one year ahead) | Usually a typo (e.g. year 3601) — fix and re-upload |
| Location / Business / Outlet is blank | Fill in the missing cell |
| Revenue (or PAX) is not a number — *Imported without revenue* | The line was saved with PAX only; correct the cell if revenue is missing |
| No PAX and no revenue (empty line) | Nothing to do — empty template line |
| Exact duplicate of another row | The repeated line was ignored so it is not counted twice |

Two lines with the **same date and outlet but different figures** (month-end
fixed fees, rentals, true-ups) are **added together**, not dropped.

### After an AOP upload: outlet mapping

Two expanders appear:

- **Sky Plates / Encalm Eats outlet mapping** — every IFK and F&B line of the
  AOP master, the outlet name it is shown under, whether it matches a DSR
  outlet, and its **Result**. Lines that carry a note in the AOP file (e.g.
  "Put in as other rev", "Change as per actual") are **Not imported** because
  their figures are provisional.
- **Rows not imported as EHPL AOP** — lines outside EHPL (hotels, IFK, F&B …)
  that the EHPL importer deliberately skips.

---

## 3. Reading the dashboards

All three dashboards (EHPL, Encalm Eats, Sky Plates) share the same filter bar:

- **Report Date** (year / month / day) — the anchor date.
- **Compare by** — **Day-wise**, **Week-wise**, **Month-wise** or **Year-wise**,
  with **Full Period** or **To-Date**. Year-wise works on **financial years**
  (1 April – 31 March) and compares with the previous FY by default; *To-Date*
  means 1 April to the report date, e.g. 1 Apr–15 Oct 2026 vs 1 Apr–15 Oct 2025.
- **Location** — one location or **All Locations** (one table per location).
- The line under the filters says exactly what is shown, e.g.
  *Showing Aug 2026 (full month) vs Jul 2026 (full month) · All Locations*.

Then: **Overview** cards (Revenue, PAX, AOP Target, Traffic, PEN %, SPP), two
charts, and the tables.

### Table conventions

- **TOTAL** is the first row; section totals (TOTAL LOUNGES, TOTAL SPA, …)
  come before their outlets; outlets are sorted by revenue.
- **—** means no figure for that period (no sales, no traffic, or no AOP).
- **AOP Var %** = (Revenue − AOP) ÷ AOP.
- **PEN %** = PAX ÷ terminal traffic × 100; **SPP** = revenue ÷ traffic.

### EHPL

One table per location, then a **Terminal-wise Performance** table (below).
Every outlet in the data is shown once and the location TOTAL always equals
the uploaded figures. These outlets **always have a row** (shown with "—" in
periods without sales):

| Hyderabad | Goa | Bhogapuram |
|---|---|---|
| Enwrap | Enwrap | Enwrap |
| Atithya | Atithya | Atithya |
| Airport Lodge / Dormitory | Porter | Porter |
| Domestic Lounge | CIP Lounge | Domestic Lounge |
| GAT | Domestic Lounge | International Lounge |
| International Lounge | International Lounge | Reserved Lounge |
| Encalm Prive | Reserved Lounge | Spa Domestic |
| Reserved Lounge | | |
| Transit Hotel | | |

Delhi follows the management-report layout: Lounges (T1, T2, T3 Domestic,
T3 International, Arrivals, Reserved), Spa, Nap & Shower, Atithya, Enwrap,
Bar and Others.
An outlet the layout does not know yet appears under **TOTAL OTHERS**
rather than disappearing.


**Terminal-wise Performance:** TOTAL, then one row per terminal (Delhi: T1, T2,
T3 Domestic, T3 International, T3 Arrivals; Hyderabad / Goa / Bhogapuram:
Domestic, International), plus *Airport-wide services* (Atithya, Porter,
Enwrap, Buggy — measured against whole-airport traffic) and *No terminal
traffic* (Business Centre, RDC, CIP Lounge …). The rows add up to the
location's TOTAL EHPL. Traffic, PEN % and SPP show "—" for a period with no
traffic uploaded.

### Encalm Eats

- Months with an uploaded **DSR** show **outlet-level** figures from the DSR.
- Days or locations **without** a DSR show the single **Encalm Eats** total
  from the revenue upload. Both are never counted together.
- AOP is shown per outlet. A Bhogapuram Starbucks target covers Departure and
  Arrival together and is split between them by their revenue.
- **Other planned outlets – no sales (n)** collects AOP for outlets with no
  sales in the period (not yet open, or not in the DSR under that name); the
  expander below lists them.

### Sky Plates

One row per location (Delhi, Hyderabad, Bhogapuram) with revenue, PAX and AOP.

---

## 4. Previous Uploads

| Tab | Use |
|---|---|
| Upload History | Every upload: file, date, rows, totals, who uploaded it |
| Available Dates | Which dates/months are in the database |
| Preview Data | Spot-check stored revenue, AOP and traffic for a date or range |
| Load Date | Make a past date the "active" date the dashboards open on |

---

## 5. FAQ

**A number looks wrong.** Check the "rows not imported" list for that upload,
then Previous Uploads → Preview Data for that date.

**Why is an outlet shown as "—"?** No sales (and no PAX) in the selected
period. For the comparison column it can also mean the other period has no
figure — e.g. comparing a DSR month (outlet-level) with an earlier month that
only had the revenue-upload total.

**Why are two names in one row?** Renamed outlets (e.g. *T1D Lounge* → *T1D
L4&5 Lounge*) and items the management report adds together are combined.
The full list is in [DATA_MAPPINGS.md](DATA_MAPPINGS.md) (section 4).

**I uploaded a corrected AOP file but the target didn't change.** Upload it
again with "Replace existing AOP for the months in this file" ticked.

**I uploaded the same DSR twice.** Rows already stored for the same date,
outlet and location are skipped, so nothing is doubled.

**The page shows no menu / looks unstyled.** Press Ctrl+F5. If it persists,
tell the administrator (runbook → Troubleshooting).
