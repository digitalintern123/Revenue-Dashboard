# Encalm Group — Revenue Analytics

A Streamlit web app for Encalm Group's airport businesses. Staff upload the
daily revenue workbook, AOP (budget) master, airport traffic and the Encalm
Eats DSR; the app stores them in one database and shows revenue, PAX, AOP
variance, penetration and spend-per-pax by location, outlet and period.

- **Locations:** Delhi, Hyderabad, Goa, Bhogapuram
- **Businesses:** EHPL (lounges, spa, nap & shower, Atithya, Enwrap, porter,
  others), Sky Plates (in-flight catering), Encalm Eats (F&B outlets)
- **Live site:** dashboard.encalmhospitality.com (Windows VPS, IIS in front)

## Pages

| Page | Address | What it is for |
|---|---|---|
| Upload Data | `/Uploads` (default) | Revenue (daily or full workbook), AOP targets, traffic, database stats |
| Previous Uploads | `/Previous_Uploads` | Upload history, dates in the database, preview, choose the active date |
| EHPL | `/EHPL` | Outlet table per location with sections, totals, AOP, PEN %, SPP; terminal table |
| Encalm Eats | `/Encalm_Eats` | Outlet table from the DSR (or the revenue upload), AOP per outlet; DSR upload tab |
| Sky Plates | `/Sky_Plates` | Sky Plates revenue and AOP per location |

Everything sits behind a sign-in screen; the menu appears only after signing in.

## Documentation

| Document | For |
|---|---|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Staff using the app: uploads, reading the dashboards, FAQ |
| [docs/SERVER_RUNBOOK.md](docs/SERVER_RUNBOOK.md) | Running the Windows server: updates via Plesk Git, restart, backup/restore, IIS, troubleshooting |
| [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) | Architecture and module map — start here as a developer |
| [docs/DATA_MAPPINGS.md](docs/DATA_MAPPINGS.md) | How file lines become outlets and table rows; outlet lists per location; AOP and DSR mapping |
| [docs/BUSINESS_RULES.md](docs/BUSINESS_RULES.md) | KPI formulas, comparisons, AOP proration, import validation |
| [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | Tables, keys, connection settings |
| [docs/UI_SPECIFICATION.md](docs/UI_SPECIFICATION.md) | Page layouts, branding, table conventions |
| [docs/AI_RULES.md](docs/AI_RULES.md) | Rules and coding standards for anyone (or any AI) changing the code |
| [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) | Open issues and limitations |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | What changed, version by version |
| [assets/README.md](assets/README.md) | Logo files, colours, icons |

## Running locally

Requires Python 3.11 or newer.

```bash
pip install -r requirements.txt
python create_secrets.py        # creates .streamlit/secrets.toml with a hashed login
streamlit run Home.py
```

Open http://localhost:8501 and sign in.

- **Database:** with no `DATABASE_URL` set, the app uses SQLite at
  `data/revenue_analytics.db` (or `$DATA_DIR/revenue_analytics.db`) and makes a
  daily copy in `data/backups/`. Set `DATABASE_URL` (environment variable or
  `secrets.toml`) to use PostgreSQL instead.
- **Logins:** `.streamlit/secrets.toml` (`[auth.users]`, `[auth.admins]`) —
  never commit it; `.streamlit/secrets.toml.example` shows the format.
- **Tests:** `python -m pytest tests -q` (285 tests).

## Project layout

```
Home.py                  entry point: page setup, styling, menu (st.navigation)
views/                   the five pages (Uploads, Previous_Uploads, EHPL, Encalm_Eats, Sky_Plates)
modules/                 parsers, database, dashboards, UI helpers (see docs/PROJECT_CONTEXT.md)
assets/                  logos and Lucide icons
tests/                   unit, integration and smoke tests
watchdog.ps1             Windows: restarts the app if it stops; runs deploy_sync.ps1
deploy_sync.ps1          Windows: applies updates pulled by Plesk Git, restarts the app
backup_db.ps1            Windows: database backup script (see the runbook)
deploy/                  Linux alternative (systemd, nginx) — not used on the current server
scripts/migrate_to_sqlite.py   one-off copy from PostgreSQL to SQLite
render.yaml              Render blueprint (optional test hosting)
```

Page files live in `views/`, not `pages/`: a `pages/` folder would make
Streamlit also serve each page on its own, unstyled (see the runbook).
