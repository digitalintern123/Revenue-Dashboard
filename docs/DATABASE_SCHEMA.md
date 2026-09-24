# DATABASE_SCHEMA.md
# Encalm Revenue Analytics — Database Schema

> All ORM definitions in `modules/database.py`. Schema auto-created by `init_db()`.

---

## Connection

```python
# database.py:55-103
_DATABASE_URL = _get_database_url()
# Priority: st.secrets["DATABASE_URL"] → os.environ["DATABASE_URL"] → data/revenue_analytics.db
_IS_POSTGRES  = _DATABASE_URL.startswith(("postgresql", "postgres"))
```

**Local:** `data/revenue_analytics.db` (SQLite)
**Production:** PostgreSQL via `DATABASE_URL` secret. SSL enforced: `sslmode=require` auto-appended.

---

## ER Diagram

```
revenue_master ─────────────────────────────────────────────────────────────
│ id (PK) │ date │ segment │ business_unit │ outlet │ location │ pax │ revenue │ aop │ traffic │ source_file │ uploaded_at
│                          UNIQUE (date, segment, outlet, location)
│                          INDEX ix_rm_date_seg_loc (date, segment, location)
│                          INDEX ix_rm_date_outlet (date, outlet)

airport_traffic ─────────────────────────────────────────────────────────────
│ id (PK) │ date │ period_end │ granularity │ location │ terminal │ traffic │ source_file │ uploaded_at
│                          UNIQUE (date, location, terminal, granularity)
│                          INDEX ix_at_date_loc (date, location)

aop_target ──────────────────────────────────────────────────────────────────
│ id (PK) │ location │ segment │ business_unit │ outlet │ year │ month │ aop │ source_file │ uploaded_at
│                          UNIQUE (location, outlet, year, month)
│                          INDEX ix_aop_loc_ym (location, year, month)

aop_target_daily ────────────────────────────────────────────────────────────
│ id (PK) │ location │ date │ aop │ source_file │ uploaded_at
│                          UNIQUE (location, date)

upload_history ──────────────────────────────────────────────────────────────
│ id (PK) │ file_name │ report_date │ row_count │ total_revenue │ primary_total │ total_pax │ uploaded_at │ status │ upload_type │ uploaded_by
│                          INDEX ix_uh_user_at (uploaded_by, uploaded_at)

login_attempts ──────────────────────────────────────────────────────────────
│ id (PK) │ username │ attempt_at

active_sessions ─────────────────────────────────────────────────────────────
│ id (PK) │ username │ session_token (UNIQUE) │ created_at │ last_seen_at
```

---

## Table 1: `revenue_master`

**Class:** `RevenueMaster` — `database.py:125`

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | Integer | No | PK, autoincrement |
| `date` | Date | No | The business date of the record |
| `segment` | String | No | `"EHPL"` \| `"Sky Plates"` \| `"Encalm Eats"` |
| `business_unit` | String | Yes | `"Lounges"` \| `"Atithya"` \| `"Others"` \| same as segment |
| `outlet` | String | No | **Canonical name** (post-`canonicalize_outlet_name()`) |
| `location` | String | No | `"Delhi"` \| `"Hyderabad"` \| `"Goa"` |
| `pax` | Float | Yes | Encalm customers served (not total airport traffic) |
| `revenue` | Float | Yes | Revenue in INR |
| `aop` | Float | Yes | Legacy: AOP from historical Excel. Normally NULL. |
| `traffic` | Float | Yes | Legacy: rarely populated. Use `airport_traffic` table. |
| `source_file` | String | Yes | Original uploaded filename |
| `uploaded_at` | String | Yes | ISO UTC timestamp of upload |

**Constraints:**
- `UNIQUE (date, segment, outlet, location)` → Re-uploading same day = safe no-op
- `INDEX ix_rm_date_seg_loc` on `(date, segment, location)` → Group-by analytics queries
- `INDEX ix_rm_date_outlet` on `(date, outlet)` → Outlet Performance page

**Critical design note:** `outlet` is always the **canonical name** from `canonicalize_outlet_name()`. Raw file names like `"INL 5&6"` are stored as `"International Lounge"`. Pages always query by canonical name.

---

## Table 2: `airport_traffic`

**Class:** `AirportTraffic` — `database.py:165`

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | Integer | No | PK |
| `date` | Date | No | For daily: the day. For monthly: first day of month. |
| `period_end` | Date | Yes | NULL for daily. Last day of month for monthly. |
| `granularity` | String | No | `"daily"` \| `"monthly"` |
| `location` | String | No | `"Delhi"` \| `"Hyderabad"` \| `"Goa"` |
| `terminal` | String | No | `"T1 Dep"` \| `"T3 Dom Dep"` \| `"Domestic"` \| `""` (not NULL!) |
| `traffic` | Float | No | Total airport visitors through this terminal |
| `source_file` | String | Yes | |
| `uploaded_at` | String | Yes | |

**Why `terminal = ""` not NULL:**
SQLite treats every NULL as distinct in UNIQUE constraints. Two rows with `terminal = NULL` would not violate `UNIQUE (date, location, terminal, granularity)`. Using `""` (empty string) makes the constraint work correctly.

**Daily vs monthly granularity:**
- `get_traffic_total_for_range()` prefers daily rows. Falls back to prorated monthly rows.
- Monthly proration: `monthly_traffic × (days_covered / days_in_month)`

---

## Table 3: `aop_target`

**Class:** `AOPTarget` — `database.py:216`

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | Integer | No | PK |
| `location` | String | No | |
| `segment` | String | No | |
| `business_unit` | String | Yes | |
| `outlet` | String | No | **Canonical name** (canonicalized at save time) |
| `year` | Integer | No | |
| `month` | Integer | No | 1–12 |
| `aop` | Float | No | Monthly target in INR |
| `source_file` | String | Yes | |
| `uploaded_at` | String | Yes | |

**Constraint:** `UNIQUE (location, outlet, year, month)` — safe to re-upload same month

---

## Table 4: `aop_target_daily`

**Class:** `AOPTargetDaily` — `database.py:255`

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | Integer | No | PK |
| `location` | String | No | |
| `date` | Date | No | |
| `aop` | Float | No | Daily target (location-level, not per-outlet) |
| `source_file` | String | Yes | |
| `uploaded_at` | String | Yes | |

**Constraint:** `UNIQUE (location, date)`

**Important:** When this table has data for a period, `join_revenue_with_aop()` returns the `__location_total__` sentinel instead of per-outlet breakdown. Page 8 bypasses this by loading `aop_target` directly.

---

## Table 5: `upload_history`

**Class:** `UploadHistory` — `database.py:287`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `file_name` | String | Original filename |
| `report_date` | Date | Date of the data (null for traffic/AOP) |
| `row_count` | Integer | Rows inserted/processed |
| `total_revenue` | Float | Revenue total or AOP total or traffic total |
| `primary_total` | Float | Mirror of total_revenue (legacy alias) |
| `total_pax` | Float | PAX total |
| `uploaded_at` | String | ISO UTC timestamp |
| `status` | String | `"Available"` (default) |
| `upload_type` | String | `"Revenue"` \| `"AOP"` \| `"Traffic"` |
| `uploaded_by` | String | Username who uploaded |

**Index:** `ix_uh_user_at (uploaded_by, uploaded_at)` — for rate limit queries

---

## Table 6: `login_attempts`

**Class:** `LoginAttempt` — `database.py:324`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `username` | String | The username that failed |
| `attempt_at` | String | ISO UTC timestamp |

Used by: `record_failed_login()`, `get_lockout_status()`, `clear_failed_logins()` in `database.py`.

---

## Table 7: `active_sessions`

**Class:** `ActiveSession` — `database.py:340`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `username` | String | |
| `session_token` | String | `UNIQUE` — 64-char hex from `secrets.token_hex(32)` |
| `created_at` | String | ISO UTC timestamp |
| `last_seen_at` | String | ISO UTC timestamp — updated on every page load |

Used by: `register_session()`, `invalidate_session()`, `is_session_valid()`, `touch_session()` in `database.py`.

---

## Schema Migrations

**Function:** `_migrate_schema()` in `database.py:699`

- Runs once per session (guarded by `_SCHEMA_MIGRATED` flag at module level)
- **Additive only** — never drops columns or renames tables
- Adds missing columns with `ALTER TABLE ADD COLUMN` (SQLite compatible)
- Adds missing indexes
- Calls `_migrate_legacy_segments()` to convert old segment names to new ones

**Migrations performed:**
1. Add `business_unit` to `revenue_master` if missing
2. Add `upload_type`, `uploaded_by` to `upload_history` if missing
3. Add `primary_total` to `upload_history` if missing
4. Add `aop`, `traffic` to `revenue_master` if missing
5. Add `period_end`, `granularity` to `airport_traffic` if missing
6. Rebuild `airport_traffic` UNIQUE constraint (was wrong in early versions)
7. Create all indexes if missing

---

## Key Query Patterns

```python
# Load revenue for a date range (most common pattern)
df = database.load_for_date_range(start_date, end_date)
# Returns: all revenue_master rows between the dates (inclusive)

# Load with outlet-specific terminal traffic
df = database.join_revenue_with_traffic_by_outlet(revenue_df)
# Returns: one row per (outlet, location) with traffic for that outlet's terminal pool

# Load with location-level traffic (for service category PEN%/SPP)
df = database.join_revenue_with_traffic(revenue_df)
# Returns: one row per (date, location) with whole-airport traffic

# Load AOP for a date range
df = database.load_aop_targets_for_range(start_date, end_date)
# Returns: aop_target rows for the months covering that date range
```
