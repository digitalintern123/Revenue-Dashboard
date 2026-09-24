# AI_RULES.md
# Rules for AI Assistants Working on This Project

> Read this before making ANY change to the codebase.
> These rules exist because specific bugs were introduced when they were not followed.

---

## RULE 1 — Always run tests after any change

```bash
python -m pytest tests/ -v
```
Expected: **158 passed, 0 failed**. If any test fails, the change broke something.

---

## RULE 2 — Never import at module-level if it creates circular dependencies

Streamlit pages import each other's modules via the `modules/` package.
Import only what is actually used. Avoid `from modules import *`.

---

## RULE 3 — `require_login()` is ALWAYS the first call on every page

```python
st.set_page_config(...)   # Must be first Streamlit call
require_login()            # Must be second (before any st.* display)
bootstrap_session()        # Third
render_user_badge()        # Fourth
```
Never add page content before `require_login()`.

---

## RULE 4 — Import `_co` and `_gdn` BEFORE using them in functions

In `_build_location_report()` (page 8), these are imported at the TOP of the function body:
```python
from modules.database import canonicalize_outlet_name as _co
from modules.outlet_groups import get_display_name as _gdn
```
If you add a new function that uses these, import them at the start of the function, not partway through. A `NameError` will occur otherwise.

---

## RULE 5 — Never hardcode `0.05` or `-0.05` for thresholds

Always use:
```python
from modules import revenue_analysis as ra
# ra.GROWTH_THRESHOLD  = 0.05
# ra.DECLINE_THRESHOLD = -0.05
```
References: `revenue_analysis.py:25-26`

---

## RULE 6 — Three places must be updated when adding a new outlet

1. `database.py` — add to `_OUTLET_NAME_CANONICAL`
2. `terminal_mapping.py` — add to the location's terminal dict
3. `outlet_groups.py` — add to `OUTLET_DISPLAY_NAMES` and the correct group

Missing any one of these causes:
- Missing `_OUTLET_NAME_CANONICAL` → outlet stored under wrong/raw name in DB
- Missing `terminal_mapping.py` → Traffic, PEN%, SPP show `—` for that outlet
- Missing `outlet_groups.py` → outlet shows as "Other" in Page 8 or with raw name

---

## RULE 7 — `outlet_groups.py` changes only affect Page 8

`OUTLET_DISPLAY_NAMES` and `get_display_name()` are imported ONLY by `pages/8_Business_Performance.py`.
Pages 1–7 do not use these — they use raw canonical names from `revenue_master`.

---

## RULE 8 — `revenue_analysis.py` must remain DB-free

All functions in `revenue_analysis.py` take DataFrames and return DataFrames/dicts.
**Never add a `database.*` call inside `revenue_analysis.py`.**
If you need DB data in a calculation, fetch it in the page and pass it in.

---

## RULE 9 — Page 8 loads AOP directly — do not change to `join_revenue_with_aop()`

Page 8 uses `load_aop_targets_for_range()` directly at `8_Business_Performance.py:72–101`.
`join_revenue_with_aop()` was NOT used here because it prioritises `aop_target_daily`
over per-outlet data, blocking the MIS table from showing per-outlet AOP.
Do not "simplify" this to `join_revenue_with_aop()`.

---

## RULE 10 — Do not use `join_revenue_with_traffic_by_outlet()` for service category PEN%/SPP

Page 7 (Service Categories) uses `join_revenue_with_traffic()` (location-level), NOT `join_revenue_with_traffic_by_outlet()`.
Reason: `penetration_and_spp_table()` calls `location_level_summary_with_traffic()` which
deduplicates by `(date, location)`. Passing outlet-specific traffic gives wrong totals.

Reference: `pages/7_Service_Categories.py`

---

## RULE 11 — `terminal = ""` not `NULL` in `airport_traffic`

When inserting rows without a terminal breakdown, use `terminal = ""` (empty string).
Do NOT use `NULL`. SQLite treats every NULL as unique in UNIQUE constraints, breaking deduplication.
Reference: `database.py:1453` (`_norm_terminal()` function)

---

## RULE 12 — Indian number formatting everywhere

```python
# Always:
from modules.formatting import format_money, format_pax, format_pct, format_spp
format_money(4935256)   # → "₹49,35,256"
format_pax(122385)      # → "1,22,385"

# Never:
f"₹{4935256:,}"         # → "₹4,935,256" ← WRONG (Western grouping)
```

---

## RULE 13 — Percentage values are fractions, not percentages

```python
pct_change(110, 100)  # → 0.10  (not 10)
format_pct(0.10)      # → "+10.00%"
```

When comparing to thresholds:
```python
# Correct:
if pct > ra.GROWTH_THRESHOLD:   # 0.05

# Wrong:
if pct > 5:                      # would never trigger
```

---

## RULE 14 — `safe_run()` wraps all error-prone sections

```python
with safe_run("My Section", error_type="comparison_error"):
    # risky code here
```

On exception: logs to file + shows user-friendly message. Does NOT crash the whole page.

For Page 8 location tabs, use `try/except` with traceback expander:
```python
try:
    ...
except Exception as _err:
    import traceback as _tb
    log_exception(_err, context="Delhi Business Performance")
    show_friendly_error("comparison_error")
    with st.expander("🔍 Technical detail (for support)"):
        st.code(_tb.format_exc(), language="text")
```

---

## RULE 15 — Never store DataFrames in `st.session_state`

```python
# WRONG:
st.session_state["revenue_df"] = database.load_for_date_range(start, end)

# RIGHT:
revenue_df = database.load_for_date_range(start, end)
# (loaded fresh on every page run — cached by cached_db.py for 60 seconds)
```

---

## RULE 16 — Call `clear_data_cache()` after any DB write

After uploading data or resetting the DB, cached data is stale:
```python
from modules.cached_db import clear_data_cache
database.save_dataframe(df, source_file)
clear_data_cache()
st.rerun()
```

---

## RULE 17 — When modifying `8_Business_Performance.py`

The page starts with `#` comments (not a `"""` docstring). This is intentional.
A module-level docstring caused `IndentationError` with Streamlit's magic parser on Python 3.14.
**Do not change the first line to a triple-quote docstring.**

---

## RULE 18 — Subtotal labels in `DELHI_SUBTOTALS` must match `DELHI_ROW_ORDER` exactly

The `_build_location_report()` function looks up subtotal definitions by matching
`group_key in {s[0] for s in subtotals}`. If a label appears in `DELHI_ROW_ORDER`
but not in `DELHI_SUBTOTALS` (or vice versa), the row is silently skipped or
calculated with wrong source groups.

After any change to `DELHI_SUBTOTALS` or `DELHI_ROW_ORDER`, simulate with:
```python
python3 -c "
from modules.outlet_groups import DELHI_ROW_ORDER, DELHI_SUBTOTALS, get_display_name
sub = {s[0] for s in DELHI_SUBTOTALS}
for r in DELHI_ROW_ORDER:
    print('SUBTOTAL' if r in sub else get_display_name(r, 'Delhi'))
"
```

---

## RULE 19 — `_ALL_AIRPORT_GROUPS` must be updated when group keys change

```python
# 8_Business_Performance.py
_ALL_AIRPORT_GROUPS: frozenset[str] = frozenset({
    "Atithya (M&G)",   # Delhi: M&G group key
    "Atithya",         # HYD/GOA: Atithya group key
})
```

This frozenset determines which subtotals use `MAX` (whole-airport traffic) instead of `SUM`.
If you rename a group key that contains M&G data, update this set.

---

## RULE 20 — The `TOTAL EHPL` row appears IN the table (not as metric cards)

As of the current version, `TOTAL EHPL` is rendered as a bold grand-total row inside
`_render_table()`. The old `_render_ehpl_metric_cards()` function still exists but
is no longer called. Do not add back the `table_rows = [r for r in ... if r["Performance"] != "TOTAL EHPL"]` filter.

---

## Common Mistakes to Avoid

| Mistake | Consequence | Correct approach |
|---------|------------|-----------------|
| Adding outlet to `outlet_groups.py` but not `terminal_mapping.py` | Traffic shows `—` | Update both files |
| Using `join_revenue_with_aop()` on Page 8 | Per-outlet AOP blocked by daily AOP | Use `load_aop_targets_for_range()` directly |
| Using `join_revenue_with_traffic_by_outlet()` for page 7 PEN%/SPP | Wrong traffic totals | Use `join_revenue_with_traffic()` |
| String `"—"` (em dash) vs `"–"` (en dash) vs `"-"` (hyphen) | Display inconsistencies | Use `formatting.py` functions which return `"—"` |
| `float("inf")` in any display path | Crash or literal "inf%" | `safe_div()` returns `np.nan`, `format_pct()` returns `"—"` |
| Docstring at line 1 of page 8 | `IndentationError` on Python 3.14 | Start with `#` comment |
| Importing `_co` after its first use | `NameError` | Import at top of function |
