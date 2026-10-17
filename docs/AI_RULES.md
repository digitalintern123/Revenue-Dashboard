# Rules & Coding Standards

For anyone — person or AI assistant — changing this code. Each rule exists
because breaking it caused a real bug.

---

## A. Before and after every change

1. **Run the tests:** `python -m pytest tests -q` → **290 passed**. Never
   skip, disable or loosen a test to make it pass.
2. **Check the running app** for UI changes (`streamlit run Home.py`, sign in,
   open the page you touched) — tests do not render pages.
3. **Docs:** update the doc that describes what you changed (see README index)
   and add a line to `docs/CHANGELOG.md`.

## B. Pages and navigation

4. **Page files live in `views/`, never `pages/`.** A `pages/` folder makes
   Streamlit serve each file on its own (unstyled, no menu). Register new
   pages in `Home.py` with `st.Page(..., url_path=...)` and add a Lucide icon
   in `ui.sidebar_nav_icons`.
5. **Page start order:** `st.set_page_config(...)`, then `require_login()`,
   `bootstrap_session()`, `render_user_badge()`, then content. Nothing is
   rendered before `require_login()`.
6. **Page-level comments as `#` lines**, not a module docstring before
   `set_page_config` (caused an IndentationError on Python 3.14 + Streamlit).

## C. Data and tables

7. **EHPL rows are built from the data.** `business_dashboard._build_location_report`
   counts every stored outlet exactly once; never go back to looking up
   revenue through lists of alias names (that dropped and double-counted
   outlets). To place or rename an outlet, change `outlet_groups.py` /
   `ehpl_layout.py` ([DATA_MAPPINGS.md](DATA_MAPPINGS.md) §7).
8. **Grand totals = every row.** Never compute a location total from a fixed
   list of groups.
9. **New outlet spellings** go into `database._OUTLET_NAME_CANONICAL`, plus
   `terminal_mapping.py` for traffic.
10. **Nothing is dropped silently on import.** Any row a parser or validator
    leaves out must be reported through `modules/import_report.py`
    (Excel row + reason).
11. **`revenue_analysis.py` stays database-free** (pure functions, unit-testable).
12. **Thresholds:** use `ra.GROWTH_THRESHOLD` / `ra.DECLINE_THRESHOLD`, never
    literal 0.05.
13. **Percentages are fractions** (0.12 = 12 %) until `format_pct` displays them.
14. **AOP for EHPL** comes from `_load_aop` filtered to EHPL; Sky Plates and
    Encalm Eats AOP come from `eats_skyplates_aop_parser.load_segment_aop`.
15. **`airport_traffic.terminal`** uses `""` (not NULL) for location-level rows.

## D. Streamlit and performance

16. **Read through `modules/cached_db.py`** on render paths; call
    `clear_data_cache()` after every database write, before `st.rerun()`.
17. **Do not store DataFrames in `st.session_state`** (memory per user);
    re-read through the cache.
18. **Wrap fallible sections** in `app_logger.safe_run(context, error_type=...)`
    or `log_exception` + `show_friendly_error` (types: `no_data`,
    `traffic_columns`, `comparison_error`, `db_error`, `corrupted_file`,
    `generic`).
19. **Numbers shown to users** go through `modules/formatting.py`
    (`format_money` — Indian grouping ₹49,35,256; `format_pax`, `format_pct`,
    `format_spp`).
20. **Escape user data** in `unsafe_allow_html` strings with `html.escape`.

## E. Database

21. **Only `database.py` talks SQL.** Parameterised queries only — never
    string-format values into SQL.
22. **Schema changes:** add the column to the model and to `_migrate_schema()`
    so existing databases are upgraded on start.
23. Uploads are validated by `data_processor._validate_upload` (size,
    extension, magic bytes).

## F. Server scripts and secrets

24. **PowerShell scripts (`*.ps1`) must be plain ASCII** — Windows PowerShell
    5.1 misreads UTF-8 punctuation (a long dash broke the watchdog for a month).
25. **Never commit secrets:** `.streamlit/secrets.toml`, database URLs with
    passwords, API keys. Passwords are stored only as PBKDF2 hashes
    (`create_secrets.py`).
26. **Server settings files** `alert_webhook.txt`, `backup_offsite.txt`,
    `deploy_source.txt` are git-ignored; never commit them.
27. Server-only files (`data/`, `start_app.bat`, `backups/`, `logs/`) are not
    in git; updates must not touch them (`deploy_sync.ps1` only fast-forwards
    tracked files).

## G. Style

- Python 3.11+, type hints and docstrings on public functions, ~100-character
  lines, imports grouped stdlib / third-party / local.
- Match the surrounding code: naming, comment density, helper functions.
- New `revenue_analysis` functions get unit tests; new database functions get
  integration tests (`tests/integration`, temporary SQLite).
- Commit messages: a short summary line, then what changed and why.
