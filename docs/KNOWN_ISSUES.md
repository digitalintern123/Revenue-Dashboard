# Known Issues & Limitations

Open items only (checked against the code, Oct 2026). Fixed items are in
[CHANGELOG.md](CHANGELOG.md).

---

## Data and mapping

### ISSUE-009 — Bhogapuram has no terminal mapping
`terminal_mapping.get_terminal_for_outlet(..., "Bhogapuram")` returns
"Unmapped", so Bhogapuram Traffic, PEN % and SPP show "—".
**Fix:** add Bhogapuram terminals and an outlet → terminal map once its
traffic file format is known.

### ISSUE-003 — Delhi domestic spa uses the international traffic pool
*Domestic Spa - T3* (from "SPA Domestic") maps to **T3 Int Dep**; it should
probably be T3 Dom Dep. Affects PEN %/SPP of that one row only.

### ISSUE-005 — EHPL AOP proration across two months
`business_dashboard._load_aop` prorates by the days of the **first** month in
the range, so a week spanning two months is slightly off. Sky Plates / Encalm
Eats (`load_segment_aop`) prorate per month correctly — reuse that logic.

### ISSUE-001 / ISSUE-007 — alias names with odd terminals (cosmetic)
Raw aliases `T3 DL023 &4`, `T3 DL02/03/04` resolve to "Unmapped" and
`Regular Lounge` to T2 Dep in `terminal_mapping`. Stored data uses canonical
names, which map correctly, so figures are not affected.

### ISSUE-010 — Delhi Starbucks renamed mid-September 2026
The DSR used *StarBucks T2 Gate 23* until 11 Sep and *StarBucks T2 Gate 23
Departure* after, so September shows two rows. Its AOP line has a note and is
not imported. Merge the names in `encalm_eats_dsr_parser._CANONICAL` if wanted.

### ISSUE-011 — Encalm Eats AOP lines not yet matched to a DSR outlet
BAR SHA, Walkway, Carnatic Café, Chaayos (T3 Arrivals), Subway, KFC, Popeyes,
Fly High BAR, GMR, IROP keep their AOP names and appear as "Other planned
outlets". Add mappings in `_DSR_OUTLET_MAP` when the outlets open.

## Uploads

### ISSUE-012 — No "replace month" for DSR uploads
DSR saves skip rows that already exist (same date + outlet + location). A DSR
re-uploaded after an outlet or location correction (e.g. the Bhogapuram
section fix of Oct 2026) adds rows under the new names but leaves the old ones.
Workaround: delete that month's rows from `encalm_eats_dsr` before
re-uploading. Proper fix: a "replace month" option like the AOP tab's.

### ISSUE-013 — Comparison column "—" when mixing sources
Encalm Eats months with a DSR are outlet-level; earlier months only have the
revenue-upload *Encalm Eats* total, so outlet rows have no comparison figure.

## UI

### ISSUE-014 — Encalm Eats opens on the shared report date
The page opens on the active date (latest revenue date), not the latest DSR
date; choose the DSR month in the filter.

## Server

### ISSUE-015 — `backup_db.ps1` in git is a PostgreSQL script with a hard-coded password
The live server uses SQLite and its own local `backup_db.ps1`. Remove the
password from the git version (read it from an environment variable) and
change it wherever it was used.

---

## Limitations

1. **SQLite** handles one write at a time; simultaneous large uploads queue.
   Use PostgreSQL (`DATABASE_URL`) for heavy multi-user use.
2. **Scanned PDFs** need OCR, which has lower confidence than Excel/CSV.
3. **`aop_target_daily`** (daily-total AOP format) has no outlet breakdown, so
   outlet rows cannot show it.
4. **Unused modules** from the earlier multi-page version (`insights.py`,
   `segment_tree_view.py`, `lounge_capacity.py`) are kept but not used by any
   page.
