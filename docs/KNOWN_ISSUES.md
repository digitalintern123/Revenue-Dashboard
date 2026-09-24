# KNOWN_ISSUES.md
# Encalm Revenue Analytics — Known Issues & Limitations

---

## Active Issues

### ISSUE-001 — `T3 DL023 &4` and `T3 DL02/03/04` return "Unmapped" in terminal mapping

**Status:** Low priority (revenue still found correctly; only affects terminal breakdown display)
**Location:** `modules/terminal_mapping.py`, `_DELHI_OUTLET_TO_TERMINAL`
**Detail:**
- `T3 DL023 &4` canonicalizes to itself (not a known canonical)
- `T3 DL02/03/04` canonicalizes to itself (not a known canonical)
- Both exist in `T3 Domestic DL02/3/4` group in `outlet_groups.py`
- Revenue is found correctly via other variants in the same group (`Lounge DL 02,03,04`, `Domestic Lounge T3`)
- Terminal resolves to "Unmapped" for these specific raw names

**Fix:** Add to `_DELHI_OUTLET_TO_TERMINAL`:
```python
"T3 DL023 &4":   TERMINAL_3_DOM_DEP,
"T3 DL02/03/04": TERMINAL_3_DOM_DEP,
```

---

### ISSUE-002 — `Centurion Lounge` (without T1/T3 suffix) maps to wrong terminal

**Status:** Low priority (data rarely uses bare "Centurion Lounge")
**Location:** `outlet_groups.py`, `Lounge Amex Centurion` group
**Detail:** `canonicalize_outlet_name("Centurion Lounge")` → `"Centurion Lounge T1"` (T1 terminal)
But this raw name is in the `Lounge Amex Centurion` group (T3 Dom Dep).
If the DB stores `"Centurion Lounge T1"` from this group, it will get T1 traffic instead of T3 Dom.
**Fix:** Add `"Centurion Lounge"` → `"Centurion Lounge T3"` mapping in `database.py` for T3 context, or disambiguate in the group list.

---

### ISSUE-003 — `SPA Domestic` and `Dom Spa` in `Spa T3 Dom` group resolve to T1 spa canonical

**Status:** Low priority (affects historical data only)
**Location:** `outlet_groups.py:Spa T3 Dom group`, `database.py:canonicalize_outlet_name`
**Detail:**
- `SPA Domestic` canonicalizes → `Domestic Spa - T1` (T1 Dep terminal)
- `Dom Spa` canonicalizes → `Dom Spa` (→ `T3 Int Dep` via terminal mapping)
- These are in the `Spa T3 Dom` group which should use T3 Int Dep
- Canonical `Domestic Spa - T1` maps to T1 Dep — wrong for a T3 Dom spa row
**Fix:** Add disambiguation: if outlet is in `Spa T3 Dom` group context, ensure `SPA Domestic` maps to `Domestic Spa - T3` not `Domestic Spa - T1`.

---

### ISSUE-004 — `NAP - Premium Lounge` terminal maps to T3 Int Dep (should be T3 Arr)

**Status:** Low priority (rare name variant)
**Location:** `terminal_mapping.py`, `_DELHI_OUTLET_TO_TERMINAL`
**Detail:** `NAP - Premium Lounge` is a variant of Nap Rooms LA01 (arrivals area) but its terminal mapping returns `T3 Int Dep` instead of `T3 Arr`. Revenue is found correctly (via other variants in `T3 Nap LA01` group).
**Fix:** Add `"NAP - Premium Lounge": _SENTINEL_T3_ARR` in `_DELHI_OUTLET_TO_TERMINAL`.

---

### ISSUE-005 — AOP proration uses first month only for cross-month periods

**Status:** Low priority (day-wise and month-wise modes not affected)
**Location:** `8_Business_Performance.py:85-90`
**Detail:** When a date range spans two months (e.g. Jan 28 – Feb 3), the AOP proration uses January's days-in-month (31) for the whole period, slightly overstating the target for the February days.
**Fix:** Sum prorated AOP per month: `Σ (days_in_month_i / total_days_in_period × monthly_AOP_i)`.

---

### ISSUE-006 — `_render_ehpl_metric_cards()` still exists but is no longer called

**Status:** Dead code — no functional impact
**Location:** `8_Business_Performance.py:536-560`
**Detail:** TOTAL EHPL now renders as a bold table row. The metric card rendering function is unused.
**Fix:** Remove `_render_ehpl_metric_cards()` in the next cleanup pass.

---

### ISSUE-007 — `Regular Lounge` maps to `TERMINAL_2` in terminal_mapping.py (dead code)

**Status:** Dead code — no functional impact
**Location:** `terminal_mapping.py:105`
**Detail:** `"Regular Lounge": TERMINAL_2` is wrong (it's a T1D lounge, not T2), but this entry is never reached because `revenue_master` stores the canonical name `Domestic Lounge - T1 L4&5` which correctly maps to T1 Dep.
**Fix:** Change to `TERMINAL_1` or remove the dead entry.

---

### ISSUE-008 — `"Sleeping Pod - Premium Lounge"` maps to T3 Int Dep (should be T3 Arr)

**Status:** Low priority (rare name variant)
**Location:** `terminal_mapping.py`, `_DELHI_OUTLET_TO_TERMINAL`
**Detail:** This is a variant of Nap Rooms LA12 (arrivals area) but its terminal mapping returns `T3 Int Dep`. Revenue still appears under LA12 group row.

---

## Resolved Issues (for reference)

| Issue | Resolution | Date |
|-------|-----------|------|
| Traffic `—` for Encalm Prive T1, Xenia, AI International, T2D | Added canonical names to terminal_mapping.py | Jul 2026 |
| AOP `—` for all outlets on Page 8 | Page 8 now loads AOP directly from aop_target table | Jul 2026 |
| `NameError: _co` on Page 8 | Moved imports to top of `_build_location_report()` | Jul 2026 |
| `NameError: log_exception` on Page 8 | Added to `from modules.app_logger import ...` | Jul 2026 |
| `IndentationError` on Page 8 (Python 3.14 + Streamlit) | Replaced docstring with `#` comments | Jul 2026 |
| `Regular Lounge` showing as separate row | Added `"Regular Lounge": "Encalm Lounge (T1 D)"` to OUTLET_DISPLAY_NAMES | Jul 2026 |
| `International Bar - INL5&6` showing as separate row | Added display name override | Jul 2026 |
| TOTAL EHPL not visible in Page 8 table | Removed metric-card filter; TOTAL EHPL now in table | Jul 2026 |
| Atithya + EHPL subtotal traffic summed instead of MAX | Added `_ALL_AIRPORT_GROUPS` logic to `_subtotal_traffic()` | Jul 2026 |
| Page 7 PEN%/SPP wrong due to outlet-specific traffic | Changed to `join_revenue_with_traffic()` | Jul 2026 |

---

## Limitations

1. **AOP cross-month proration** — slightly incorrect for weekly ranges spanning two months (see ISSUE-005)
2. **Historical data with `SPA Domestic`** — may appear under wrong spa row if raw name not matched
3. **GOA Sky Plates** — not included in GOA MIS rows (no GOA Sky Plates group in `GOA_GROUPS`)
4. **No automated backup** — DB must be backed up manually (see deployment guide)
5. **PDF parser requires structured layout** — scanned/image PDFs need OCR which has lower confidence
6. **SQLite does not support concurrent writes** — multi-user uploads may queue; use PostgreSQL for production
7. **`aop_target_daily` blocks per-outlet AOP on pages 1–7** — if daily AOP is uploaded, `join_revenue_with_aop()` returns only `__location_total__` sentinel, hiding per-outlet AOP breakdown on non-Page-8 views
