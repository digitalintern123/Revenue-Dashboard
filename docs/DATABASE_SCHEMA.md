# Database Schema

All models and SQL live in `modules/database.py` — no other module talks to
the database directly.

---

## 1. Connection

`database._resolve_database_url()`:

1. `DATABASE_URL` from `st.secrets`, then the environment. Pasted variants are
   accepted (a whole `psql '…'` command, quotes, `postgres://`); the URL is
   pinned to `postgresql+psycopg2://`. An invalid value raises an error that
   names where it came from **without showing the password**.
2. No `DATABASE_URL` → **SQLite** at `$DATA_DIR/revenue_analytics.db`, or
   `data/revenue_analytics.db` in the repo (`sqlite_data_dir()`).

| | PostgreSQL | SQLite |
|---|---|---|
| Used by | optional (e.g. Neon on Render) | the live Windows server |
| Settings | `sslmode=require` unless the host is local; 60 s statement timeout (not sent to `-pooler` hosts, which reject it); pool 5 + 10, pre-ping, recycle 30 min | WAL journal, `synchronous=NORMAL`, 30 s busy timeout |
| Backups | external (`pg_dump`) | `backup_sqlite()` — online copy to `data/backups/revenue_analytics_YYYY-MM-DD.db`, newest 7, made once a day by `session._daily_sqlite_backup` |

Schema: `init_db()` creates missing tables and `_migrate_schema()` adds
missing columns; it runs once per server process (`session._init_db_once`).
`scripts/migrate_to_sqlite.py` copies a PostgreSQL database into SQLite and
checks row counts and totals.

---

## 2. Tables

### `revenue_master` — one row per date × outlet × location

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| date | date | indexed |
| segment | str | EHPL / Sky Plates / Encalm Eats |
| business_unit | str | Lounges / Atithya / Others / Sky Plates / Encalm Eats |
| outlet | str | canonical name (`canonicalize_outlet_name`) |
| location | str | Delhi / Hyderabad / Goa / Bhogapuram |
| pax, revenue | float | |
| aop, traffic | float | legacy columns; AOP and traffic live in their own tables |
| source_file, uploaded_at | str | |

Unique (date, outlet, location). Indexes (date, segment, location),
(date, outlet). Lines for the same key are added together before saving.

### `airport_traffic`

date, period_end, granularity (daily/monthly), location, terminal, traffic,
source_file, uploaded_at. Unique (date, location, terminal, granularity).

### `aop_target` — monthly AOP per outlet

location, segment, business_unit, outlet, year, month, aop (rupees),
source_file, uploaded_at. Unique (location, outlet, year, month).
Holds EHPL (from `aop_parser`) and Sky Plates / Encalm Eats (from
`eats_skyplates_aop_parser`) targets.

### `aop_target_daily`

location, date, aop. Unique (location, date). Daily-total AOP format.

### `encalm_eats_dsr` — Encalm Eats DSR, outlet × day

date, outlet, location, segment ("Encalm Eats"), covers, net_revenue,
mtd_revenue, ytd_revenue (reference only), source_file, source_sheet,
inserted_at. Unique (date, outlet, location); re-uploads skip existing rows.

### `upload_history`

file_name, report_date, row_count, total_revenue, primary_total, total_pax,
uploaded_at, status, upload_type (Revenue / AOP / Traffic), uploaded_by.
Index (uploaded_by, uploaded_at) for the upload rate limit.

### `parse_template` — saved layouts

kind (revenue / traffic), name (unique per kind), fingerprint (JSON list of
normalised headers), mapping (JSON: header → role, terminal; role for date
headers), header_row, constants (JSON), created_by, created_at, last_used,
times_used. Written when a user confirms a column mapping and ticks
*Remember this layout* (`database.save_parse_template`); matched by
`layout_learning.find_template` (≥ 90 % of headers in common).

### `login_attempts`

username, attempt_at — failed sign-ins for the lockout.

### `active_sessions`

username, session_token (unique), created_at, last_seen_at — signed-in
sessions; deleting a row signs that session out within a minute.

---

## 3. Key read functions

| Function | Returns |
|---|---|
| `load_for_date_range(start, end)` | revenue rows in the range |
| `load_aop_targets_for_range(start, end)` | `aop_target` rows for the months in the range |
| `load_encalm_eats_dsr_for_range(start, end)` | DSR rows |
| `get_traffic_total_for_range(start, end, location)` | best available traffic per location/terminal |
| `join_revenue_with_traffic_by_outlet(df)` | per-outlet traffic for each outlet's terminal pool |
| `get_available_dates()`, `get_available_dates_for_segment(segment)` | dates with revenue rows |

Pages call these through `modules/cached_db.py` (cached 10 minutes, cleared by
`clear_data_cache()` after every upload).
