# CODING_STANDARDS.md
# Encalm Revenue Analytics — Coding Standards

---

## 1. Python Version & Style

- **Target:** Python 3.11+ (uses `tomllib` stdlib, `match` statements in places)
- **Type hints:** Required for all public functions. Use `Optional[X]` for nullable, `X | None` acceptable in 3.10+
- **Docstrings:** Required for all public functions. Include parameter types and return description.
- **Line length:** 100 characters (project-wide, not enforced by linter but followed by convention)
- **Imports:** Standard library first, then third-party, then local. Separated by blank lines.

---

## 2. Module Structure (every page follows this pattern)

```python
# pages/N_Name.py
# Page description as comments (NOT a triple-quote docstring — causes IndentationError on Python 3.14)

from __future__ import annotations
import streamlit as st

from modules.auth import require_login, render_user_badge
from modules.session import bootstrap_session, set_active_date, default_active_date
from modules import database, revenue_analysis as ra
from modules.comparison_widget import render_comparison_selector
from modules.formatting import format_money, format_pax, format_pct
from modules.app_logger import safe_run, log_exception, show_friendly_error

st.set_page_config(page_title="...", page_icon="...", layout="wide")
require_login()
bootstrap_session()
render_user_badge()

# --- page content ---
```

---

## 3. Error Handling

### Use `safe_run()` for sections that might fail:
```python
with safe_run("Context description", error_type="comparison_error"):
    risky_code()
```

### For Page 8 location tabs specifically:
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

### Error type keys (from `app_logger.py`):
- `"no_data"` — empty query result
- `"traffic_columns"` — traffic/PEN/SPP columns failed
- `"comparison_error"` — comparison table build failed
- `"db_error"` — SQLAlchemy operational error
- `"corrupted_file"` — unreadable upload
- `"generic"` — catchall

---

## 4. Number Formatting

**ALL numbers displayed to users MUST go through `formatting.py`:**

```python
from modules.formatting import format_money, format_pax, format_pct, format_spp

format_money(value)    # → "₹49,35,256" or "—"  (revenue in INR)
format_pax(value)      # → "1,22,385" or "—"     (customer count)
format_pct(value)      # → "+8.70%" or "—"       (fractional input: 0.087)
format_spp(value)      # → "95.57" or "—"        (SPP in INR)
```

Indian grouping convention:
- Last 3 digits → one group: `256`
- Every subsequent 2 digits → a group: `49,35,256`
- NOT Western: `4,935,256` ❌

---

## 5. Database Conventions

### Never use string interpolation in SQL:
```python
# WRONG:
conn.execute(f"SELECT * FROM {table_name}")

# RIGHT:
conn.execute(text(f"SELECT * FROM {table_name}"))  # and validate table_name against allowlist
```

### Table name allowlist (in `database.py`):
```python
_ALLOWED_TABLE_NAMES = {"revenue_master", "airport_traffic", "aop_target", ...}
if table_name not in _ALLOWED_TABLE_NAMES:
    raise ValueError(f"Invalid table name: {table_name}")
```

### Always use parameterised queries:
```python
stmt = select(RevenueMaster).where(
    sql_and(
        RevenueMaster.date >= start_date,
        RevenueMaster.date <= end_date,
    )
)
```

### `_read_sql()` for pandas integration:
```python
# Use this helper (not ENGINE directly) for pandas read_sql compatibility:
from modules.database import _read_sql
df = _read_sql(stmt)
```

---

## 6. Streamlit Conventions

### Never modify `st.session_state` directly outside of `session.py`:
```python
# WRONG (in a page):
st.session_state["revenue_data"] = df

# RIGHT:
# Data is fetched fresh per page run and cached by cached_db.py
```

### Cache invalidation after writes:
```python
from modules.cached_db import clear_data_cache
clear_data_cache()
st.rerun()
```

### `st.cache_data` TTL:
All `cached_db.py` wrappers use `ttl=60` (1-minute cache). Don't bypass these with direct `database.*` calls in pages — the cache drastically reduces DB load.

---

## 7. Testing Standards

### Location: `tests/unit/` and `tests/integration/`

### Every new function in `revenue_analysis.py` must have a test:
```python
class TestMyNewFunction:
    def test_normal_case(self):
        df = _make_df([{"revenue": 100_000, "pax": 50}])
        result = ra.my_new_function(df)
        assert result["value"] == pytest.approx(expected, rel=1e-4)

    def test_empty_df(self):
        df = pd.DataFrame()
        result = ra.my_new_function(df)
        assert result == {}  # or whatever empty behavior is expected

    def test_none_inputs(self):
        assert ra.my_new_function(None) == {}
```

### Every DB function must have an integration test:
```python
def test_my_db_function(db):  # `db` fixture from conftest.py
    db.save_dataframe(_revenue_df(), "test.xlsx")
    result = db.my_new_query()
    assert len(result) == 1
    assert result.iloc[0]["outlet"] == "Expected Canonical Name"
```

### Running tests:
```bash
python -m pytest tests/ -v          # all 158 tests
python -m pytest tests/unit/ -v     # unit only (fast)
python -m pytest tests/integration/ # DB integration
```

---

## 8. Outlet Group Conventions

When modifying `outlet_groups.py`:

1. **Group keys** (`DELHI_GROUPS`, `HYD_GROUPS`, `GOA_GROUPS`) — use descriptive names matching the Excel report label
2. **Raw DB names in group lists** — include all known variants (canonical + raw + historical)
3. **`OUTLET_DISPLAY_NAMES`** — lowercase keys are NOT used here; exact case matters
4. **`LOCATION_DISPLAY_OVERRIDES`** — location-specific overrides win over `OUTLET_DISPLAY_NAMES`
5. **Simulate before committing** — run the simulation script to verify display names

```python
python3 -c "
from modules.outlet_groups import DELHI_ROW_ORDER, DELHI_SUBTOTALS, get_display_name
sub = {s[0] for s in DELHI_SUBTOTALS}
for r in DELHI_ROW_ORDER:
    tag = 'SUB' if r in sub else 'ROW'
    print(f'{tag}  {r if r in sub else get_display_name(r, \"Delhi\")}')
"
```

---

## 9. Security Conventions

### Password handling:
- Never store plaintext passwords anywhere
- Use `python modules/generate_password_hash.py` to create hash entries for `secrets.toml`
- Hash format: `"<salt>$pbkdf2:<hex>"` (PBKDF2-HMAC-SHA256, 260,000 iterations)

### File uploads:
- Always validate with `_validate_upload()` in `data_processor.py`
- Magic bytes check: PDF starts `%PDF`, Excel starts `PK\x03\x04`
- Null-byte density: >10% → rejected

### HTML in Streamlit:
```python
# When using unsafe_allow_html=True, ALWAYS escape user data:
import html
safe_name = html.escape(outlet_name)
st.markdown(f"<b>{safe_name}</b>", unsafe_allow_html=True)
```

---

## 10. Commit Message Convention

```
Type(scope): description

Type:
  fix     — Bug fix
  feat    — New feature
  refactor— Code cleanup (no behavior change)
  test    — Test additions/changes
  docs    — Documentation only
  chore   — Config/dependency updates

Scope:
  page8, database, auth, terminal_mapping, outlet_groups, revenue_analysis, etc.

Examples:
  fix(page8): TOTAL EHPL now shown as table row instead of metric cards
  fix(terminal_mapping): add canonical outlet names for HYD/GOA
  feat(outlet_groups): add Porter as separate row in HYD MIS
  docs(ai_rules): add rule for AOP loading on page 8
```
