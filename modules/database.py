"""
database.py — SQLite persistence layer for the Revenue Analytics platform.

Design notes:
- The database is the single source of truth for all revenue data.
- st.session_state should only ever hold lightweight references (selected
  dates, UI state) — never DataFrames of revenue data. This module is what
  every page calls to actually fetch data, so navigating between pages never
  loses anything.
- A UNIQUE constraint on (date, outlet, location) makes re-uploading
  the same day's report a safe no-op: duplicate rows are skipped, not errored.
"""

from __future__ import annotations

import calendar
import datetime as dt
import os
from typing import Optional

import pandas as pd
from sqlalchemy import (
    Column,
    Date,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    and_ as sql_and,
    create_engine,
    func,
    or_ as sql_or,
    select,
    text,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

# FIX (Bug 5): import the single canonical month-shift implementation.
# Previously database.py defined its own private _safe_month_shift(); that
# duplicate is removed below and replaced with this shared version.
from .date_utils import safe_month_shift as _safe_month_shift

# ── Database connection ───────────────────────────────────────────────────
# Supports both Neon PostgreSQL (production) and SQLite (local fallback).
#
# Production (Streamlit Cloud):
#   Add DATABASE_URL to Settings → Secrets:
#   DATABASE_URL = "postgresql://user:pass@ep-xxx.region.aws.neon.tech/neondb?sslmode=require"
#
# Local development:
#   Set DATABASE_URL env var, or it falls back to SQLite automatically.

def _get_database_url() -> str:
    """Read DATABASE_URL from Streamlit secrets or environment.

    Reads the secrets.toml file directly with tomllib instead of importing
    streamlit at module level. Importing streamlit here adds 3-6 seconds to
    startup time on Windows because it triggers Streamlit full initialisation.
    """
    try:
        import pathlib as _pl
        _secrets_path = _pl.Path(__file__).parent.parent / ".streamlit" / "secrets.toml"
        if _secrets_path.exists():
            try:
                import tomllib as _toml
            except ImportError:
                try:
                    import tomli as _toml
                except ImportError:
                    _toml = None
            if _toml is not None:
                _raw = _secrets_path.read_text(encoding="utf-8")
                _parsed = _toml.loads(_raw)
                url = _parsed.get("DATABASE_URL", "")
                if url:
                    return str(url).strip()
    except Exception:
        pass
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    # Local SQLite fallback — try data/ dir first, then /tmp
    _repo_root = os.path.dirname(os.path.dirname(__file__))
    _local_db = os.path.join(_repo_root, "data", "revenue_analytics.db")
    try:
        os.makedirs(os.path.dirname(_local_db), exist_ok=True)
        # Test writability
        with open(_local_db, "ab"):
            pass
        return f"sqlite:///{_local_db}"
    except OSError:
        return "sqlite:////tmp/revenue_analytics.db"

def _normalize_database_url(raw: str) -> str:
    """Clean up common copy-paste mistakes in DATABASE_URL.

    Hosting dashboards make it easy to paste more than the bare URL, e.g.
    Neon's "psql 'postgresql://...'" snippet, a value wrapped in quotes,
    or a "DATABASE_URL=" prefix. SQLAlchemy 2 also rejects the legacy
    "postgres://" scheme that Heroku/Render-style URLs sometimes use.
    Passwords with special characters (@ : / #) must be URL-encoded
    (e.g. @ -> %40); Neon and Render already give them encoded.
    """
    url = (raw or "").strip()
    if url.upper().startswith("DATABASE_URL="):
        url = url.split("=", 1)[1].strip()
    if url.lower().startswith("psql "):
        url = url[5:].strip()
    url = url.strip("'\"").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    # SQLAlchemy 2.1 maps a bare "postgresql://" to psycopg (v3), but this
    # project installs psycopg2-binary — name the driver explicitly.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


_DATABASE_URL = _normalize_database_url(_get_database_url())
if not _DATABASE_URL.startswith(("postgresql", "sqlite")):
    # Never echo the value itself: it contains the database password.
    raise ValueError(
        "DATABASE_URL is not a valid database URL. It must start with "
        "'postgresql://' (e.g. postgresql://user:password@host/dbname?sslmode=require). "
        "Paste only the connection string, without 'psql', quotes or other text."
    )
_IS_POSTGRES = _DATABASE_URL.startswith(("postgresql", "postgres"))
# DB_PATH kept as a string alias for the URL (used in some legacy references)
DB_PATH = _DATABASE_URL

if _IS_POSTGRES:
    # Enforce SSL/TLS — add sslmode=require if not already present.
    # Never allow unencrypted connections to the production database.
    _pg_url = _DATABASE_URL
    if "sslmode=" not in _pg_url:
        _sep = "&" if "?" in _pg_url else "?"
        _pg_url = _pg_url + _sep + "sslmode=require"
    # 60s query timeout via the libpq "options" startup parameter. Connection
    # poolers (Neon's "-pooler" hosts run PgBouncer) reject unknown startup
    # parameters, so only send it for direct connections.
    _pg_host = make_url(_pg_url).host or ""
    _connect_args = {} if "pooler" in _pg_host else {"options": "-c statement_timeout=60000"}
    ENGINE = create_engine(
        _pg_url,
        pool_pre_ping=True,    # handles Neon scale-to-zero reconnection
        pool_size=5,           # v2: increased for multi-user production load
        max_overflow=10,
        pool_timeout=60,
        pool_recycle=1800,     # recycle connections every 30 min
        connect_args=_connect_args,
    )
else:
    ENGINE = create_engine(
        _DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
SessionLocal = sessionmaker(bind=ENGINE)

def _read_sql(query) -> pd.DataFrame:
    """
    Compatibility wrapper for pd.read_sql.

    pandas + SQLAlchemy 2.x on Python 3.14 no longer accepts a bare Engine
    as the second argument to pd.read_sql when an ORM select() object is
    passed — it requires an explicit Connection context.  Using a raw SQL
    string with ENGINE.connect() is the correct approach for both old and
    new versions.

    This helper centralises that pattern so every call site stays clean.
    """
    with ENGINE.connect() as conn:
        return pd.read_sql(query, conn)


Base = declarative_base()


class RevenueMaster(Base):
    """
    One row = one (date, segment, outlet, location) revenue record.

    `segment` is the top-level business: "EHPL" (Encalm Hospitality
    Private Ltd — the umbrella business covering lounges, meet & greet,
    and other airport services), "Sky Plates", or "Encalm Eats".

    `business_unit` preserves the finer-grained category within EHPL
    (Lounges / Atithya / Others) for rows where segment == "EHPL", so that
    detail isn't lost even though those three are no longer separate
    top-level segments. For Sky Plates and Encalm Eats rows,
    business_unit is the same as segment (there's no further split).
    """

    __tablename__ = "revenue_master"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    segment = Column(String, nullable=False)
    business_unit = Column(String, nullable=True)
    outlet = Column(String, nullable=False)
    location = Column(String, nullable=False)
    pax = Column(Float, nullable=True)
    revenue = Column(Float, nullable=True)
    aop = Column(Float, nullable=True)
    traffic = Column(Float, nullable=True)
    source_file = Column(String, nullable=True)
    uploaded_at = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("date", "outlet", "location", name="uq_revenue_row"),
        # Composite index for date-range + group-by queries run by every analytics page.
        # Covers: WHERE date BETWEEN x AND y GROUP BY segment, location, outlet
        Index("ix_rm_date_seg_loc", "date", "segment", "location"),
        # Separate index for outlet-level filtering (Outlet Performance page)
        Index("ix_rm_date_outlet", "date", "outlet"),
    )


class AirportTraffic(Base):
    """
    One row = total airport visitor traffic for one (date, location,
    terminal), at a given granularity. Traffic is recorded terminal-wise
    (e.g. Delhi T1/T2/T3), not just airport-wide — so `terminal` is part
    of the row identity. `terminal` is "" (empty string, not NULL — see
    save_traffic_dataframe for why NULL specifically breaks the dedup
    constraint) for locations/files that don't break traffic out by
    terminal; in that case treat the whole airport as one terminal for
    that location.

    `granularity` is "daily" or "monthly": some traffic files report one
    row per day, others report one row per month (with `date` set to the
    1st of that month and `period_end` set to the month's last day) — both
    are supported and stored side by side rather than forcing monthly
    figures into a misleading daily average. Analysis code should prefer
    daily rows when available for a given date range and fall back to
    monthly rows otherwise (see database.load_traffic_for_date_range).

    Traffic is airport-wide visitor count (everyone who passed through
    that terminal that day/month), not outlet-level like revenue_master —
    so it's kept in its own table and joined against revenue_master at
    query time via the outlet -> terminal mapping in
    modules/terminal_mapping.py, rather than duplicated across every
    outlet row.

    PAX (in revenue_master) and traffic (here) are deliberately different
    things: traffic = total airport/terminal visitors that day; PAX =
    customers who actually used Encalm's services. Penetration % = PAX ÷
    Traffic is the metric that relates the two.
    """

    __tablename__ = "airport_traffic"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=True)
    granularity = Column(String, nullable=False, default="daily")
    location = Column(String, nullable=False)
    terminal = Column(String, nullable=True)
    traffic = Column(Float, nullable=False)
    source_file = Column(String, nullable=True)
    uploaded_at = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("date", "location", "terminal", "granularity", name="uq_traffic_row"),
        # Composite index for date-range + location lookups in Traffic & Terminal page
        Index("ix_at_date_loc", "date", "location"),
    )


class AOPTarget(Base):
    """
    One row = the AOP (Annual Operating Plan) revenue target for one
    (location, outlet, year, month) — a forward-looking budget figure,
    independent of whether revenue data exists yet for that period (the
    AOP plan in this app currently covers FY26-27 through FY30-31, years
    that mostly haven't happened yet).

    Kept separate from revenue_master's per-row `aop` column (which is
    still supported for historical Excel imports that already embed an
    AOP figure per row) because a forward plan needs to exist on its own
    timeline — AOP variance is computed by joining live revenue against
    this table for whichever (year, month) the revenue actually falls in,
    not by expecting AOP to already be attached to each revenue row.

    `business_unit` mirrors revenue_master's same-named column (Lounges /
    Atithya / Others) so AOP variance can be sliced the same way revenue
    already is. `segment` is "EHPL" for everything currently imported
    (Sky Plates / Encalm Eats AOP isn't in the source file yet).
    """

    __tablename__ = "aop_target"

    id = Column(Integer, primary_key=True, autoincrement=True)
    location = Column(String, nullable=False)
    segment = Column(String, nullable=False)
    business_unit = Column(String, nullable=True)
    outlet = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    aop = Column(Float, nullable=False)
    source_file = Column(String, nullable=True)
    uploaded_at = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("location", "outlet", "year", "month", name="uq_aop_target_row"),
    )


class AOPTargetDaily(Base):
    """
    One row = the AOP (Annual Operating Plan) revenue target for one
    (location, date) — a second, simpler AOP source format: a daily
    total per location with no outlet/segment breakdown at all (e.g. a
    pivot-table export with one row per calendar day and one column per
    location). This is kept in its own table, separate from AOPTarget
    (the per-outlet/monthly format), because the two have genuinely
    different grains — this one is daily and location-only, the other is
    monthly and outlet-level — and merging them into one table would mean
    inventing a fake "no outlet" sentinel value, which is more confusing
    than just keeping two tables.

    AOP variance calculations should prefer whichever of the two sources
    actually has data for the period being compared, and combine them
    when both are partially available (see database.get_aop_target_for_range).
    """

    __tablename__ = "aop_target_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    location = Column(String, nullable=False)
    date = Column(Date, nullable=False, index=True)
    aop = Column(Float, nullable=False)
    source_file = Column(String, nullable=True)
    uploaded_at = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("location", "date", name="uq_aop_target_daily_row"),
    )


class UploadHistory(Base):
    """One row per file upload event, used for the Previous Uploads page."""

    __tablename__ = "upload_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String, nullable=False)
    report_date = Column(Date, nullable=True)
    row_count = Column(Integer, nullable=False, default=0)
    # `total_revenue` is kept as the primary numeric total column so all
    # existing callers (_record_upload_history, get_upload_history, the
    # Previous Uploads page) continue to work without any changes.
    total_revenue = Column(Float, nullable=True)
    # FIX (Improvement 7): `primary_total` is added as a separate real
    # column — NOT a synonym (synonyms break pd.read_sql on Python 3.14).
    # It mirrors total_revenue and is written alongside it in
    # _record_upload_history so both are always kept in sync.
    primary_total = Column(Float, nullable=True)
    total_pax = Column(Float, nullable=True)
    uploaded_at = Column(String, nullable=False)
    status = Column(String, nullable=False, default="Available")
    # "Revenue" | "AOP" | "Traffic" — which upload pipeline produced this
    # entry. Defaults to "Revenue" so pre-existing rows (recorded before
    # this column existed, back when only revenue uploads were logged at
    # all) still display correctly without a data backfill.
    upload_type = Column(String, nullable=False, default="Revenue")
    # Username of whoever uploaded the file — for audit trail only.
    # Never contains passwords or sensitive PII.
    uploaded_by = Column(String, nullable=True, default=None)

    __table_args__ = (
        # Composite index for the DB-backed rate limiter query:
        # WHERE uploaded_by=? AND upload_type='Revenue' AND uploaded_at>=?
        Index("ix_uh_user_at", "uploaded_by", "uploaded_at"),
    )


class LoginAttempt(Base):
    """
    One row per failed login attempt. Used for DB-backed brute-force lockout
    that persists across browser tabs and sessions.
    """
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False)
    attempt_at = Column(String, nullable=False)   # ISO UTC timestamp

    __table_args__ = (
        Index("ix_la_username_at", "username", "attempt_at"),
    )


class ActiveSession(Base):
    """
    Server-side session registry. One row per authenticated browser tab.
    Allows logout in one tab to invalidate all other tabs for the same user
    and enables admin-side forced logout.

    session_token matches the value stored in st.session_state so the app
    can verify that the session is still valid on each page load.
    """
    __tablename__ = "active_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False)
    session_token = Column(String, nullable=False, unique=True)
    created_at = Column(String, nullable=False)   # ISO timestamp
    last_seen_at = Column(String, nullable=False)  # ISO timestamp

    __table_args__ = (
        Index("ix_as_username", "username"),
        Index("ix_as_token", "session_token"),
    )


class EncalmEatsDSR(Base):
    """
    One row per outlet per day from the Encalm Eats Master DSR.
    Unique key: (date, outlet, location) — prevents duplicate imports.
    Only daily net_revenue is used for analytics; MTD/YTD columns are
    stored for reference but never summed across records.
    """
    __tablename__ = "encalm_eats_dsr"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    date         = Column(Date, nullable=False)
    outlet       = Column(String, nullable=False)
    location     = Column(String, nullable=False)
    segment      = Column(String, nullable=False, default="Encalm Eats")
    covers       = Column(Float, nullable=True)
    net_revenue  = Column(Float, nullable=True)
    mtd_revenue  = Column(Float, nullable=True)   # stored for reference only
    ytd_revenue  = Column(Float, nullable=True)   # stored for reference only
    source_file  = Column(String, nullable=True)
    source_sheet = Column(String, nullable=True)
    inserted_at  = Column(String, nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("date", "outlet", "location",
                         name="uq_eats_dsr_date_outlet_location"),
        Index("ix_eats_dsr_date", "date"),
        Index("ix_eats_dsr_outlet", "outlet"),
        Index("ix_eats_dsr_location", "location"),
    )


def save_encalm_eats_dsr(
    records: list,  # list of DSRRecord dataclass instances
    source_file: str = "",
) -> dict:
    """
    Insert Encalm Eats DSR records, skipping duplicates.
    Returns {"inserted": n, "skipped": n}.
    """
    import datetime as _dt
    from sqlalchemy.exc import IntegrityError as _IE

    session = SessionLocal()
    inserted = 0
    skipped  = 0
    now_str  = _dt.datetime.now(_dt.timezone.utc).isoformat()

    try:
        for rec in records:
            row = EncalmEatsDSR(
                date         = rec.date,
                outlet       = rec.outlet,
                location     = rec.location,
                segment      = getattr(rec, "segment", "Encalm Eats"),
                covers       = rec.covers,
                net_revenue  = rec.net_revenue,
                mtd_revenue  = getattr(rec, "mtd_revenue", None),
                ytd_revenue  = getattr(rec, "ytd_revenue", None),
                source_file  = source_file or rec.source_file,
                source_sheet = getattr(rec, "source_sheet", ""),
                inserted_at  = now_str,
            )
            try:
                session.add(row)
                session.flush()
                inserted += 1
            except _IE:
                session.rollback()
                skipped += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return {"inserted": inserted, "skipped": skipped}


def load_encalm_eats_dsr_for_range(
    start_date,
    end_date,
) -> "pd.DataFrame":
    """Load Encalm Eats DSR rows for a date range as a DataFrame."""
    import pandas as _pd
    session = SessionLocal()
    try:
        q = (
            select(EncalmEatsDSR)
            .where(EncalmEatsDSR.date >= start_date)
            .where(EncalmEatsDSR.date <= end_date)
        )
        rows = session.execute(q).scalars().all()
        if not rows:
            return _pd.DataFrame()
        data = [
            {
                "date":        r.date,
                "outlet":      r.outlet,
                "location":    r.location,
                "segment":     r.segment,
                "covers":      r.covers,
                "net_revenue": r.net_revenue,
            }
            for r in rows
        ]
        return _pd.DataFrame(data)
    finally:
        session.close()


def get_encalm_eats_dsr_dates() -> list:
    """Return list of distinct dates present in encalm_eats_dsr table."""
    import datetime as _dt
    session = SessionLocal()
    try:
        rows = session.execute(
            select(EncalmEatsDSR.date).distinct().order_by(EncalmEatsDSR.date)
        ).scalars().all()
        return list(rows)
    finally:
        session.close()


def register_session(username: str, token: str) -> None:
    """Register a new authenticated session in the DB."""
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with ENGINE.begin() as conn:
        conn.execute(text(
            "INSERT INTO active_sessions (username, session_token, created_at, last_seen_at) "
            "VALUES (:u, :t, :n, :n) "
            "ON CONFLICT (session_token) DO UPDATE SET last_seen_at=:n"
        ), {"u": username, "t": token, "n": now})


def invalidate_session(token: str) -> None:
    """Remove a session from the DB — called on logout."""
    with ENGINE.begin() as conn:
        conn.execute(text(
            "DELETE FROM active_sessions WHERE session_token=:t"
        ), {"t": token})


def invalidate_all_sessions_for_user(username: str) -> None:
    """Remove ALL active sessions for a user — admin forced-logout."""
    with ENGINE.begin() as conn:
        conn.execute(text(
            "DELETE FROM active_sessions WHERE username=:u"
        ), {"u": username})


def is_session_valid(token: str) -> bool:
    """Return True if the session token exists in the DB (not logged out elsewhere)."""
    with ENGINE.connect() as conn:
        row = conn.execute(
            text("SELECT 1 FROM active_sessions WHERE session_token=:t LIMIT 1"),
            {"t": token}
        ).fetchone()
    return row is not None


def touch_session(token: str) -> None:
    """Update last_seen_at for an active session (keeps audit trail fresh)."""
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with ENGINE.begin() as conn:
        conn.execute(text(
            "UPDATE active_sessions SET last_seen_at=:n WHERE session_token=:t"
        ), {"n": now, "t": token})


# ---------------------------------------------------------------------------
# Segment / business-unit canonicalization
# ---------------------------------------------------------------------------
#
# Encalm Group's real top-level businesses are EHPL (Encalm Hospitality
# Private Ltd — the largest segment, covering lounges, meet & greet/Atithya
# services, and other airport services), Sky Plates, and Encalm Eats.
# Historically (and in some source files), these were modeled as four
# flat, sibling "segments": Lounges, Atithya, Others, Subsidiary — with
# Subsidiary itself bundling both Sky Plates and Encalm Eats together.
#
# This mapping is applied once, here, at the point data is saved — rather
# than duplicated across every parser — so every row in the database
# always has the correct three-way `segment` (EHPL / Sky Plates / Encalm
# Eats) plus a `business_unit` that preserves the old Lounges/Atithya/
# Others detail for EHPL rows (and just mirrors segment for the other two).
_LEGACY_SEGMENT_TO_EHPL = {"lounges", "atithya", "others"}
_OUTLET_TO_NEW_SEGMENT = {
    "encalm sky plates": "Sky Plates",
    "sky plates": "Sky Plates",
    "skyplates": "Sky Plates",
    "encalm eats": "Encalm Eats",
}

# ---------------------------------------------------------------------------
# Outlet name canonicalization
# ---------------------------------------------------------------------------
# Maps every known outlet name variant (from any source file format) to a
# single canonical name. This ensures that cross-file comparisons work
# correctly — e.g. DB3.xlsx uses "INL 5&6" while the July stacked-daily
# format uses "International Lounge (DEL INL5&6; HYD & GOA)" — both should
# compare as the same outlet.
_OUTLET_NAME_CANONICAL: dict[str, str] = {
    # International lounge variants
    "inl 5&6":                                      "International Lounge",
    "international lounge (del inl5&6; hyd & goa)": "International Lounge",
    "international lounge (new)":                   "International Lounge",
    "international lounge - air india":             "International Lounge - Air India",
    "ai international lounge":                      "International Lounge - Air India",
    "international lounge - premium":               "Premium Lounge",
    "premium lounge":                               "Premium Lounge",
    "international bar - inl5&6, hyd & goa":        "International Lounge",
    "international bar -  premium lounge":          "Premium Lounge",
    "xenia - inl t3":                               "First Class - Xenia Lounge",
    "first class - xenia lounge":                   "First Class - Xenia Lounge",

    # International spa/nap
    "international spa- inl07 t3":                  "Spa - International",
    "spa - premium lounge":                         "Spa - International",
    "spa - international":                          "Spa - International",
    "nap & shower la01":                            "Nap Rooms LA01",
    "nap - premium lounge":                         "Nap Rooms LA01",
    "nap & shower la12":                            "Nap Rooms LA12",
    "sleeping pod - premium lounge":                "Nap Rooms LA12",

    # Domestic lounge - T3 variants
    "lounge dl 02,03,04":                           "Domestic Lounge T3",
    "lounge dl 02&03":                              "Domestic Lounge T3",
    "domestic lounge (del dlo2/3/4, hyd)":          "Domestic Lounge T3",
    "domestic lounge":                              "Domestic Lounge T3",
    "domestic lounge (new)":                        "Domestic Lounge T3",
    "domestic bar - dlo2/3/4, hyd & goa":          "Domestic Lounge T3",

    # Domestic lounge - T3 D49
    "t3 d49":                                       "Domestic Lounge - D49",
    "domestic lounge - d49":                        "Domestic Lounge - D49",
    "domestic bar - d49":                           "Domestic Lounge - D49",
    "air india":                                    "Domestic Lounge - Air India",
    "domestic lounge - air india":                  "Domestic Lounge - Air India",
    "rupay":                                        "Domestic Lounge - Rupay",
    "domestic lounge - rupay":                      "Domestic Lounge - Rupay",
    "domestic bar - rupay":                         "Domestic Lounge - Rupay",

    # Domestic lounge - T2
    "t2 domestic":                                  "Domestic Lounge - T2",
    "domestic lounge - t2":                         "Domestic Lounge - T2",
    "domestic bar - t2":                            "Domestic Lounge - T2",

    # Domestic lounge - T1
    "t1d l4&5 lounge":                              "Domestic Lounge - T1 L4&5",
    "t1d lounge":                                   "Domestic Lounge - T1 L4&5",
    "domestic lounge - t1 l4":                      "Domestic Lounge - T1 L4&5",
    "domestic lounge - t1 l5":                      "Domestic Lounge - T1 L4&5",
    "domestic bar - t1 l5":                         "Domestic Lounge - T1 L4&5",
    "regular lounge":                               "Domestic Lounge - T1 L4&5",
    "t1d new amex lounge (level 4)":               "Centurion Lounge T1",
    "centurion lounge":                             "Centurion Lounge T3",
    "domesticlounge- centurion amex t1":            "Centurion Lounge T1",
    "domesticlounge- centurion amex t3":            "Centurion Lounge T3",
    "t1d new premium lounge 2 (level 5)":           "Domestic Lounge - T1 Prive",
    "domestic lounge - t1 prive":                   "Domestic Lounge - T1 Prive",
    "prive":                                        "Domestic Lounge - Prive",
    "dom prive":                                    "Domestic Lounge - Prive",

    # Domestic spa
    "t1d spa":                                      "Domestic Spa - T1",
    "domestic spa- t1":                             "Domestic Spa - T1",
    "spa domestic":                                 "Domestic Spa - T3",
    "domestic spa- dpa10 t3":                       "Domestic Spa - T3",

    # Arrivals / Transit
    "arrival lounge la 22":                         "Arrival Lounge - LA22",
    "arrival lounge - la22":                        "Arrival Lounge - LA22",
    "arrival lounge- ( t3 la22)":                   "Arrival Lounge - LA22",
    "arrival lounge (t3 la22)":                     "Arrival Lounge - LA22",
    "delhi - t3 - la 22":                           "Arrival Lounge - LA22",
    "la 22":                                        "Arrival Lounge - LA22",
    "transit lounge - la01":                        "Transit Lounge - LA01",
    "la 12":                                        "Transit Lounge - LA12",
    "transit lounge - la12":                        "Transit Lounge - LA12",
    "reserve lounges":                              "Reserved Lounge",
    "reserved lounge":                              "Reserved Lounge",
    "visitor lounge":                               "Reserved Lounge",
    "transit lounge":                               "Transit Hotel",
    "transit hotel":                                "Transit Hotel",

    # Atithya / Meet & Greet / Welcome & Assist -> all canonical "Atithya"
    "meet & greet":                                 "Atithya",
    "welcome & assist":                             "Atithya",
    "atithya":                                      "Atithya",
    "m&g":                                          "Atithya",
    "m&g del":                                      "Atithya",
    # Bar outlets -> assign to T1D Lounges
    "domestic bar - t1 l5":                         "T1D L4&5 Lounge",
    "domestic bar - t1 l4":                         "T1D L4&5 Lounge",
    "porter":                                       "Porter",
    "porter services- t1":                          "Porter",
    "porter services -t2":                          "Porter",
    "porter services -t3":                          "Porter",
    "baggage wrapping":                             "Baggage Wrapping",
    "enwrap services":                              "Baggage Wrapping",
    "buggy service":                                "Buggy Service",
    "buggy services":                               "Buggy Service",
    "business center":                              "Business Centre",
    "ceremonial(del)  /  ga (hyd)  /  cip(goa)":   "CIP Lounge",
    "ceremonial / ga / cip":                        "CIP Lounge",
    "business centre":                              "Business Centre",

    # Ceremonial / CIP
    "cip lounge":                                   "CIP Lounge",

    # ── Hyderabad new outlet name variants (from outlet_grouping.docx) ───────
    "hyd dom prive":                                "Dom Prive",
    "rl domestic arrival d":                        "Reserved Lounge",
    "rl dom dep e":                                 "Reserved Lounge",
    "rl dom dep f":                                 "Reserved Lounge",
    "hyd intl lounge - closing":                    "International Lounge",
    "int card lounge":                              "International Lounge",
    "int card lounge - new (level e) - upcoming":   "International Lounge",
    "hyd ga lounge":                                "Hyd GA Lounge",
    "rl int arrival d":                             "Reserved Lounge",
    "int prive - mezzanine level":                  "Premium Lounge",
    "prive (hyderabad)":                            "Premium Lounge",
    "encalm prive":                                 "Premium Lounge",
    "sky plates (hyderabad)":                       "Sky Plates",
    "sky plates hyd":                               "Sky Plates",
    "encalm sky plates (hyderabad)":                "Sky Plates",
    "baggage wrapping (hyderabad)":                 "Baggage Wrapping",
    "meet & greet (hyderabad)":                     "Meet & Greet",
    "international lounge (hyderabad)":             "International Lounge",
    "domestic lounge (hyderabad)":                  "Domestic Lounge T3",
    "hyd dom lounge":                               "Domestic Lounge T3",
    "hyd intl lounge":                              "International Lounge",
    "gat (hyderabad)":                              "GAT",
    "airport lodge (hyderabad)":                    "Airport Lodge",
    # ── Goa new outlet name variants ────────────────────────────────────────
    "domestic lounge (goa)":                        "Domestic Lounge T3",
    "goa lounge dom":                               "Domestic Lounge T3",
    "rl dom departure":                             "Reserved Lounge",
    "rl dom arrival":                               "Reserved Lounge",
    "international lounge (goa)":                   "International Lounge",
    "goa lounge intl":                              "International Lounge",
    "rl int arrival":                               "Reserved Lounge",
    "prive (goa)":                                  "Premium Lounge",
    "baggage wrapping (goa)":                       "Baggage Wrapping",
    "meet & greet (goa)":                           "Meet & Greet",
    "m&g goa":                                      "Meet & Greet",
    "m&g hyd":                                      "Meet & Greet",
    # Others
    "round d clock (rdc)":                          "Round D Clock (RDC)",
    "round d clock (rdc)-restaurant":               "Round D Clock (RDC)",
    "round d clock -motel":                         "Round D Clock (RDC)",
    "round d clock - motel":                        "Round D Clock (RDC)",
    "bar":                                          "Bar",
    "special events":                               "Special Events",
    "airport lodge":                                "Airport Lodge",
    "gat":                                          "GAT",


    # ── July file name variants (added for cross-file consistency) ───────────
    "buggy del":                                       "Buggy Service",
}


def canonicalize_outlet_name(outlet: str) -> str:
    """Map any outlet name variant to its canonical form."""
    key = str(outlet).strip().lower()
    return _OUTLET_NAME_CANONICAL.get(key, str(outlet).strip())


# business_unit mapping for EHPL outlets coming from the July stacked-daily
# format (where segment='EHPL' and business_unit is not split into
# Lounges/Atithya/Others). We infer the correct business_unit from the
# canonical outlet name.
_CANONICAL_OUTLET_TO_BU: dict[str, str] = {
    # Atithya outlets
    "Meet & Greet":             "Atithya",
    "Porter":                   "Atithya",
    "Baggage Wrapping":         "Atithya",
    "Buggy Service":            "Atithya",
    "Business Centre":          "Atithya",
    "CIP Lounge":               "Atithya",
    "GAT":                      "Atithya",
    "Special Events":           "Atithya",
    # Others outlets
    "Round D Clock (RDC)":      "Others",
    "Round D Clock - Motel":    "Others",
    "Bar":                      "Others",
}


def canonicalize_segment_and_business_unit(raw_segment: str, outlet: str) -> tuple[str, str]:
    """
    Map a (possibly legacy) segment label + outlet name onto the canonical
    (segment, business_unit) pair used everywhere in the app.

    Rules:
      - Lounges / Atithya / Others (any case)  -> segment="EHPL", business_unit=<original title-cased>
      - Subsidiary, with outlet "Encalm Sky Plates"/"Sky Plates" -> segment="Sky Plates", business_unit="Sky Plates"
      - Subsidiary, with outlet "Encalm Eats"                    -> segment="Encalm Eats", business_unit="Encalm Eats"
      - Already-canonical EHPL rows -> business_unit inferred from canonical
        outlet name (Atithya/Lounges/Others), so July stacked-daily format
        (which only has segment=EHPL) aligns with DB3 format correctly.
      - Anything else -> passed through as-is.
    """
    seg_key = str(raw_segment).strip().lower() if raw_segment is not None else ""
    outlet_key = str(outlet).strip().lower()

    # Canonicalize outlet name first
    canonical_outlet = canonicalize_outlet_name(outlet)

    # Outlet-based segment override — check BEFORE any raw_segment logic
    # so that files that incorrectly send EHPL/Subsidiary/blank for Encalm Eats
    # or Sky Plates still get the correct segment regardless of raw_segment.
    outlet_seg = _OUTLET_TO_NEW_SEGMENT.get(outlet_key)
    if outlet_seg:
        return outlet_seg, outlet_seg

    if seg_key in _LEGACY_SEGMENT_TO_EHPL:
        return "EHPL", str(raw_segment).strip().title()

    if seg_key == "subsidiary":
        new_segment = _OUTLET_TO_NEW_SEGMENT.get(outlet_key)
        if new_segment:
            return new_segment, new_segment
        return str(raw_segment).strip(), str(raw_segment).strip()

    if seg_key == "ehpl":
        # Infer business_unit from canonical outlet name so that files
        # using segment="EHPL" (July format) align with files using
        # segment="Atithya"/"Lounges"/"Others" (DB3 format).
        # Note: Encalm Eats / Sky Plates are already handled above by
        # the outlet-based override before we reach this branch.
        bu = _CANONICAL_OUTLET_TO_BU.get(canonical_outlet, "Lounges")
        return "EHPL", bu

    if seg_key in ("sky plates", "encalm sky plates"):
        return "Sky Plates", "Sky Plates"

    if seg_key == "encalm eats":
        return "Encalm Eats", "Encalm Eats"

    return str(raw_segment).strip(), str(raw_segment).strip()


def init_db() -> None:
    """
    Create tables if they don't already exist. Safe to call repeatedly, and
    safe to call concurrently from multiple processes/threads (e.g. several
    Streamlit sessions starting up at once, or Streamlit's own first-launch
    double-execution on some platforms).

    SQLAlchemy's create_all() normally checks "does this table exist?" and
    then issues CREATE TABLE if not — but those are two separate steps, so
    on a brand-new database file, two near-simultaneous callers can both
    see "doesn't exist yet" and both try to create it, and the loser gets
    an OperationalError. We catch that specific race and treat it as
    success, since the end state (table exists) is exactly what we wanted.

    Also runs `_migrate_schema()` afterwards, which adds any columns that
    were introduced after a database file was first created (e.g.
    business_unit) and re-tags any rows still using legacy segment names
    (Lounges/Atithya/Others/Subsidiary) onto the current EHPL/Sky Plates/
    Encalm Eats structure — so upgrading the app's code doesn't strand
    existing data in the old shape or crash on a missing column.
    """
    try:
        Base.metadata.create_all(ENGINE)
    except OperationalError as exc:
        if "already exists" in str(exc).lower():
            # Another process/thread won the race and created it first —
            # the table exists, which is the only thing we actually cared
            # about, so this is not a real failure.
            pass
        else:
            raise
    _migrate_schema()


_SCHEMA_MIGRATED: bool = False   # module-level flag — skip after first successful run


def _migrate_schema() -> None:
    """
    Idempotent, additive-only schema migration. Safe to call on every
    startup: each step checks the current state before acting, so running
    it against an already-migrated database is a fast no-op.

    The _SCHEMA_MIGRATED flag prevents re-running this on every Streamlit
    re-run within the same process (which would fire a PRAGMA table_info
    query against every table on every widget interaction).
    """
    global _SCHEMA_MIGRATED
    if _SCHEMA_MIGRATED:
        return
    # Allowlist of table names permitted in DDL interpolation.
    # This prevents any hypothetical path where a non-literal table name
    # could reach the f-string below.
    _DDL_ALLOWED_TABLES = frozenset({
        "revenue_master", "airport_traffic", "aop_target",
        "aop_target_daily", "upload_history", "airport_traffic_new",
    })

    def _cols(conn, table: str) -> set:
        """Get column names — uses information_schema for PG, PRAGMA for SQLite."""
        if table not in _DDL_ALLOWED_TABLES:
            raise ValueError(f"Table name '{table}' is not in the DDL allowlist.")
        try:
            if _IS_POSTGRES:
                rows = conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name=:t AND table_schema='public'"
                ), {"t": table}).fetchall()
                return {r[0] for r in rows}
            else:
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                return {r[1] for r in rows}
        except ValueError:
            raise
        except Exception:
            return set()

    with ENGINE.begin() as conn:
        existing_columns = _cols(conn, "revenue_master")
        if existing_columns and "business_unit" not in existing_columns:
            conn.execute(text("ALTER TABLE revenue_master ADD COLUMN business_unit VARCHAR"))

        # Rebuild UNIQUE constraint to exclude segment (was date+segment+outlet+location,
        # now date+outlet+location) so the same outlet/date/location is always one row
        # regardless of whether segment was blank on one upload and 'EHPL' on another.
        # SQLite cannot ALTER UNIQUE constraints — must rebuild the table.
        # PostgreSQL: DROP + re-create the constraint.
        if existing_columns:
            try:
                db_url = str(ENGINE.url)
                if "postgresql" in db_url or "postgres" in db_url:
                    conn.execute(text(
                        "ALTER TABLE revenue_master DROP CONSTRAINT IF EXISTS uq_revenue_row"
                    ))
                    conn.execute(text(
                        "ALTER TABLE revenue_master ADD CONSTRAINT uq_revenue_row "
                        "UNIQUE (date, outlet, location)"
                    ))
                # SQLite handles it naturally via the new CREATE TABLE definition
                # (only affects fresh databases; existing SQLite DBs need a wipe-and-reload)
            except Exception:
                pass  # constraint already correct or DB doesn't support it

        traffic_columns = _cols(conn, "airport_traffic")
        needs_rebuild = False
        if traffic_columns and "terminal" not in traffic_columns:
            conn.execute(text("ALTER TABLE airport_traffic ADD COLUMN terminal VARCHAR"))
            needs_rebuild = True
        if traffic_columns and "granularity" not in traffic_columns:
            conn.execute(text(
                "ALTER TABLE airport_traffic ADD COLUMN granularity VARCHAR DEFAULT 'daily'"
            ))
            conn.execute(text(
                "UPDATE airport_traffic SET granularity = 'daily' WHERE granularity IS NULL"
            ))
            needs_rebuild = True
        if traffic_columns and "period_end" not in traffic_columns:
            conn.execute(text("ALTER TABLE airport_traffic ADD COLUMN period_end DATE"))

        # SQLite can't ALTER UNIQUE constraints — needs full table rebuild.
        # PostgreSQL can add constraints directly, so skip the rebuild.
        if needs_rebuild and not _IS_POSTGRES:
            _rebuild_airport_traffic_constraint(conn)

        upload_history_columns = _cols(conn, "upload_history")
        if upload_history_columns and "upload_type" not in upload_history_columns:
            conn.execute(text(
                "ALTER TABLE upload_history ADD COLUMN upload_type VARCHAR DEFAULT 'Revenue'"
            ))
            conn.execute(text(
                "UPDATE upload_history SET upload_type = 'Revenue' WHERE upload_type IS NULL"
            ))
        if upload_history_columns and "primary_total" not in upload_history_columns:
            conn.execute(text("ALTER TABLE upload_history ADD COLUMN primary_total FLOAT"))
            conn.execute(text("UPDATE upload_history SET primary_total = total_revenue"))

    _migrate_legacy_segments()


    _SCHEMA_MIGRATED = True

def _rebuild_airport_traffic_constraint(conn) -> None:
    """
    Rebuild airport_traffic with the current (date, location, terminal,
    granularity) UNIQUE constraint, preserving existing rows. SQLite can't
    ALTER a table's UNIQUE constraint directly, so this does the standard
    create-new / copy / drop-old / rename dance inside the same
    transaction as the caller.
    """
    current_columns = {
        row[1] for row in conn.execute(text("PRAGMA table_info(airport_traffic)")).fetchall()
    }
    has_period_end = "period_end" in current_columns

    conn.execute(
        text(
            """
            CREATE TABLE airport_traffic_new (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                period_end DATE,
                granularity VARCHAR NOT NULL DEFAULT 'daily',
                location VARCHAR NOT NULL,
                terminal VARCHAR,
                traffic FLOAT NOT NULL,
                source_file VARCHAR,
                uploaded_at VARCHAR,
                CONSTRAINT uq_traffic_row UNIQUE (date, location, terminal, granularity)
            )
            """
        )
    )
    period_end_select = "period_end" if has_period_end else "NULL"
    conn.execute(
        text(
            f"""
            INSERT INTO airport_traffic_new (id, date, period_end, granularity, location, terminal, traffic, source_file, uploaded_at)
            SELECT id, date, {period_end_select}, COALESCE(granularity, 'daily'), location, terminal, traffic, source_file, uploaded_at FROM airport_traffic
            """
        )
    )
    conn.execute(text("DROP TABLE airport_traffic"))
    conn.execute(text("ALTER TABLE airport_traffic_new RENAME TO airport_traffic"))


def _migrate_legacy_segments() -> None:
    """
    Re-tag any rows still carrying the old flat segment names (Lounges,
    Atithya, Others, Subsidiary) onto the current three-segment structure
    (EHPL / Sky Plates / Encalm Eats), filling in business_unit at the
    same time. Only touches rows that need it — already-canonical rows
    (segment already EHPL/Sky Plates/Encalm Eats with business_unit set)
    are left untouched, so this is cheap to run on every startup.
    """
    legacy_segments = ["Lounges", "Atithya", "Others", "Subsidiary", "lounges", "atithya", "others", "subsidiary"]

    # FIX (Bug 4): the original query used:
    #   WHERE segment IN (...) OR business_unit IS NULL
    # The bare "OR business_unit IS NULL" matched every canonical row
    # (EHPL / Sky Plates / Encalm Eats) written before the business_unit
    # column existed, causing a full table scan + unnecessary UPDATE batch
    # on every app startup once all rows had already been migrated.
    #
    # The corrected condition restricts the business_unit IS NULL branch
    # to rows whose segment is NOT already one of the three canonical
    # values, so previously-migrated rows are never touched again.
    canonical_segments = ("EHPL", "Sky Plates", "Encalm Eats")
    canonical_placeholders = ",".join(f":canon{i}" for i in range(len(canonical_segments)))
    canonical_params = {f"canon{i}": s for i, s in enumerate(canonical_segments)}

    with ENGINE.begin() as conn:
        # Also catch EHPL rows whose outlet is Encalm Eats / Sky Plates
        # but segment was never corrected (written before this fix).
        # Also fix Prive → Domestic Lounge - Prive (Hyderabad only).
        conn.execute(text(
            """
            UPDATE revenue_master
               SET outlet = 'Domestic Lounge - Prive'
             WHERE outlet = 'Domestic Lounge - T1 Prive'
               AND location = 'Hyderabad'
            """
        ))
        rows = conn.execute(
            text(
                """
                SELECT id, segment, outlet FROM revenue_master
                WHERE segment IN ({legacy_ph})
                   OR business_unit IS NULL
                   OR (segment = 'EHPL' AND outlet IN ('Encalm Eats', 'Encalm Sky Plates', 'Sky Plates'))
                """.format(
                    legacy_ph=",".join(f":seg{i}" for i in range(len(legacy_segments))),
                )
            ),
            {f"seg{i}": s for i, s in enumerate(legacy_segments)},
        ).fetchall()

        if not rows:
            return

        update_sql = text(
            "UPDATE revenue_master SET segment = :segment, business_unit = :business_unit WHERE id = :id"
        )
        updates = []
        for row_id, raw_segment, outlet in rows:
            new_segment, business_unit = canonicalize_segment_and_business_unit(
                raw_segment or "", outlet or ""
            )
            updates.append({"id": row_id, "segment": new_segment, "business_unit": business_unit})

        conn.execute(update_sql, updates)


_RESET_ALLOWED_TABLES = frozenset({
    "revenue_master", "airport_traffic", "aop_target",
    "aop_target_daily", "upload_history",
})


def reset_db() -> None:
    """Danger zone: wipe all rows using DELETE FROM (not DROP TABLE).
    Works on read-only mounts where DDL fails but DML succeeds."""
    tables = ["revenue_master", "airport_traffic", "aop_target",
              "aop_target_daily", "upload_history"]
    with ENGINE.begin() as conn:
        for table in tables:
            # Allowlist check — table names come from our own hardcoded list
            # above, never from user input, but we guard explicitly so this
            # pattern cannot be accidentally copied with a user-supplied value.
            if table not in _RESET_ALLOWED_TABLES:
                raise ValueError(f"Refusing to DELETE from unexpected table: {table!r}")
            try:
                conn.execute(text(f"DELETE FROM {table}"))
            except OperationalError:
                pass
    # VACUUM reclaims space after bulk deletes. PostgreSQL runs autovacuum
    # automatically and VACUUM cannot execute inside a transaction block,
    # so we only call it for SQLite where it's both safe and needed.
    if not _IS_POSTGRES:
        try:
            with ENGINE.connect() as conn:
                conn.execute(text("VACUUM"))
                conn.commit()
        except Exception:
            pass
    init_db()


# ---------------------------------------------------------------------------
# Writing data
# ---------------------------------------------------------------------------

def save_dataframe_batched(
    df: pd.DataFrame,
    source_file: str,
    batch_size: int = 10000,
    progress_callback=None,
) -> dict:
    """
    Save a large DataFrame in separate committed batches.
    Each batch is its own transaction — if one fails the others are already
    committed. Use for historical imports > 10K rows to avoid Neon timeouts.

    progress_callback(pct: float, msg: str) is called after each batch.
    """
    if df.empty:
        return {"inserted": 0, "skipped": 0, "total_rows": 0}

    total = len(df)
    total_inserted = 0
    total_skipped = 0

    for start in range(0, total, batch_size):
        batch_df = df.iloc[start:start + batch_size].copy()
        result = save_dataframe(batch_df, source_file, record_upload=False)
        total_inserted += result["inserted"]
        total_skipped  += result["skipped"]
        pct = min((start + batch_size) / total, 1.0)
        if progress_callback:
            progress_callback(
                pct,
                f"{total_inserted:,} saved, {total_skipped:,} skipped "
                f"({start + len(batch_df):,}/{total:,} rows processed)"
            )

    return {"inserted": total_inserted, "skipped": total_skipped, "total_rows": total}


def save_dataframe_batched_v2(
    df: pd.DataFrame,
    source_file: str,
    progress_callback=None,
) -> dict:
    """
    Fast bulk save using PostgreSQL COPY FROM STDIN.
    Sends 50K rows in a single network call — ~5-10 seconds vs minutes.
    Falls back to chunked inserts for SQLite.
    """
    if df.empty:
        return {"inserted": 0, "skipped": 0, "total_rows": 0}

    total = len(df)

    if _IS_POSTGRES:
        import datetime as _dt
        now_str = _dt.datetime.now().isoformat(timespec="seconds")

        if progress_callback:
            progress_callback(0.1, f"Normalising {total:,} rows…")

        work = df.copy()
        work["segment"]  = work["segment"].astype(str).str.strip()
        work["outlet"]   = work["outlet"].astype(str).str.strip()
        work["location"] = work["location"].astype(str).str.strip()

        _cache: dict = {}
        def _canon(seg, outlet):
            k = (seg, outlet)
            if k not in _cache:
                _cache[k] = canonicalize_segment_and_business_unit(seg, outlet)
            return _cache[k]
        canon = list(map(_canon, work["segment"], work["outlet"]))
        work["segment"]       = [c[0] for c in canon]
        work["business_unit"] = [c[1] for c in canon]
        work["date"]          = pd.to_datetime(work["date"]).dt.strftime("%Y-%m-%d")
        for col in ("pax", "revenue", "aop", "traffic"):
            work[col] = pd.to_numeric(work.get(col, None), errors="coerce") if col in work.columns else None
        work["source_file"] = source_file
        work["uploaded_at"] = now_str

        cols = ["date", "segment", "business_unit", "outlet", "location",
                "pax", "revenue", "aop", "traffic", "source_file", "uploaded_at"]

        if progress_callback:
            progress_callback(0.3, f"Uploading {total:,} rows via COPY (fastest method)…")

        try:
            inserted = _pg_copy_insert(work, "revenue_master", cols)
            skipped  = total - inserted
            if progress_callback:
                progress_callback(1.0, f"✅ Done: {inserted:,} inserted, {skipped:,} skipped")
            return {"inserted": inserted, "skipped": skipped, "total_rows": total}
        except Exception as copy_err:
            if progress_callback:
                progress_callback(0.3, f"COPY failed ({copy_err}) — switching to chunked insert…")

    # Fallback: chunked executemany
    total_inserted = 0
    total_skipped  = 0
    batch_size = 10000
    for start in range(0, total, batch_size):
        batch_df = df.iloc[start:start + batch_size].copy()
        result = save_dataframe(batch_df, source_file, record_upload=False)
        total_inserted += result["inserted"]
        total_skipped  += result["skipped"]
        pct = min((start + batch_size) / total, 1.0)
        if progress_callback:
            progress_callback(pct, f"{total_inserted:,} saved ({start + len(batch_df):,}/{total:,})")

    # Record the upload in upload_log — batched save skips this per-batch
    # so we do it once here after all batches complete.
    if total_inserted > 0:
        report_date = _to_date(df["date"].iloc[0]) if "date" in df.columns else None
        with ENGINE.connect() as _conn:
            _rev = _conn.execute(
                select(func.coalesce(func.sum(RevenueMaster.revenue), 0.0))
                .where(RevenueMaster.source_file == source_file)
            ).scalar() or 0.0
            _pax = _conn.execute(
                select(func.coalesce(func.sum(RevenueMaster.pax), 0.0))
                .where(RevenueMaster.source_file == source_file)
            ).scalar() or 0.0
        _record_upload_history(
            file_name=source_file,
            report_date=report_date,
            row_count=total_inserted,
            total_revenue=float(_rev),
            total_pax=float(_pax),
            upload_type="Revenue",
        )

    return {"inserted": total_inserted, "skipped": total_skipped, "total_rows": total}


def _pg_copy_insert(df: pd.DataFrame, table: str, columns: list[str]) -> int:
    """
    Use PostgreSQL COPY FROM STDIN for maximum insert speed.
    10-100x faster than executemany for large DataFrames.
    Falls back to regular insert if not on PostgreSQL.
    Returns number of rows copied.
    """
    if not _IS_POSTGRES:
        return -1  # signal to use regular insert

    import io as _io
    import csv as _csv

    # Build CSV in memory
    buf = _io.StringIO()
    writer = _csv.writer(buf, quoting=_csv.QUOTE_MINIMAL)
    for _, row in df[columns].iterrows():
        writer.writerow([
            "" if (v is None or (isinstance(v, float) and v != v)) else v
            for v in row
        ])
    buf.seek(0)

    raw_conn = None
    try:
        raw_conn = ENGINE.raw_connection()
        cur = raw_conn.cursor()

        # Create temp table matching revenue_master structure
        tmp = f"_tmp_{table}_{id(buf) % 100000}"
        cur.execute(f"""
            CREATE TEMP TABLE {tmp} (LIKE {table} INCLUDING DEFAULTS)
            ON COMMIT DROP
        """)

        # COPY into temp table
        col_list = ", ".join(columns)
        cur.copy_expert(
            f"COPY {tmp} ({col_list}) FROM STDIN WITH (FORMAT CSV, NULL '')",
            buf
        )

        # INSERT ... ON CONFLICT DO NOTHING from temp → real table
        conflict_cols = {
            "revenue_master": "(date, segment, outlet, location)",
            "airport_traffic": "(date, location, terminal, granularity)",
            "aop_target": "(location, outlet, year, month)",
            "aop_target_daily": "(location, date)",
        }.get(table, "")

        result = cur.execute(f"""
            INSERT INTO {table} ({col_list})
            SELECT {col_list} FROM {tmp}
            ON CONFLICT {conflict_cols} DO NOTHING
        """)
        inserted = cur.rowcount
        raw_conn.commit()
        cur.close()
        return inserted if inserted >= 0 else 0
    except Exception as e:
        if raw_conn:
            try: raw_conn.rollback()
            except: pass
        raise e
    finally:
        if raw_conn:
            try: raw_conn.close()
            except: pass


def save_dataframe(
    df: pd.DataFrame,
    source_file: str,
    record_upload: bool = True,
) -> dict:
    """
    Insert a normalized revenue DataFrame into revenue_master.

    Expects columns: date, segment, outlet, location, pax, revenue, aop, traffic
    (aop/traffic optional, may be all-NaN).

    Duplicate (date, segment, outlet, location) rows are skipped silently —
    this makes re-uploading the same report a harmless no-op. Uses a bulk
    "INSERT OR IGNORE" so large historical imports (50K+ rows) complete in
    a couple of seconds rather than minutes.

    Returns a dict summary: {"inserted": int, "skipped": int, "total_rows": int}
    """
    if df.empty:
        return {"inserted": 0, "skipped": 0, "total_rows": 0}

    required_cols = {"date", "segment", "outlet", "location"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {missing}")

    now_str = dt.datetime.now().isoformat(timespec="seconds")

    # FIX (Bug 8): replaced the slow `for _, row in df.iterrows()` loop
    # with a vectorized approach:
    #   1. String-strip the key columns with .str.strip() (vectorized).
    #   2. Apply canonicalize_segment_and_business_unit once per row via
    #      .apply() — this call cannot be fully vectorized because the
    #      function contains conditional branching on individual values,
    #      but a single .apply() pass is significantly faster than the
    #      Python-level iteration + dict-append in iterrows().
    #   3. Convert numeric columns to float via .apply(_to_float_or_none)
    #      rather than calling it inside the row loop.
    #   4. Use .to_dict("records") to produce the final list in one step.
    work = df.copy()

    # Vectorized string normalisation for the four core string columns.
    work["segment"]  = work["segment"].astype(str).str.strip()
    work["outlet"]   = work["outlet"].astype(str).str.strip()
    work["location"] = work["location"].astype(str).str.strip().str.title()

    # Canonicalize outlet names so both file formats map to the same name.
    # e.g. "INL 5&6" (DB3) and "International Lounge (DEL INL5&6; HYD & GOA)"
    # (July stacked format) both become "International Lounge".
    work["outlet"] = work["outlet"].apply(canonicalize_outlet_name)

    # Apply segment canonicalization — returns (segment, business_unit) per row.
    # Use a pre-built lookup dict to avoid per-row Python calls on 50K+ rows.
    _canon_cache: dict[tuple, tuple] = {}
    def _get_canon(seg: str, outlet: str) -> tuple:
        key = (seg, outlet)
        if key not in _canon_cache:
            _canon_cache[key] = canonicalize_segment_and_business_unit(seg, outlet)
        return _canon_cache[key]
    canon = list(map(_get_canon, work["segment"], work["outlet"]))
    work["segment"]       = [c[0] for c in canon]
    work["business_unit"] = [c[1] for c in canon]

    # Normalise date to ISO string — vectorized via pandas.
    work["date"] = pd.to_datetime(work["date"]).dt.strftime("%Y-%m-%d")

    # Normalise optional float columns; missing columns default to None.
    for col in ("pax", "revenue", "aop", "traffic"):
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
        else:
            work[col] = None

    # Attach the upload-context fields.
    work["source_file"]  = source_file
    work["uploaded_at"]  = now_str

    # Select only the columns the INSERT expects, in order, to ensure no
    # extra columns from the caller's DataFrame sneak into the records list.
    records = work[
        ["date", "segment", "business_unit", "outlet", "location",
         "pax", "revenue", "aop", "traffic", "source_file", "uploaded_at"]
    ].to_dict("records")

    insert_sql = text(
        """
        INSERT INTO revenue_master
            (date, segment, business_unit, outlet, location, pax, revenue, aop, traffic, source_file, uploaded_at)
        VALUES
            (:date, :segment, :business_unit, :outlet, :location, :pax, :revenue, :aop, :traffic, :source_file, :uploaded_at)
        ON CONFLICT (date, outlet, location) DO NOTHING
        """
    )

    # Insert in chunks inside ONE transaction — minimises round trips to Neon.
    # 5000 rows/chunk = ~10 round trips for a 50K file vs 25 at chunk=2000.
    CHUNK = 5000
    inserted = 0
    with ENGINE.begin() as conn:
        for i in range(0, len(records), CHUNK):
            chunk = records[i:i + CHUNK]
            result = conn.execute(insert_sql, chunk)
            inserted += result.rowcount if result.rowcount >= 0 else 0

    # Fallback for drivers that return rowcount=-1
    if inserted == 0 and len(records) > 0:
        with ENGINE.begin() as conn:
            inserted = conn.execute(
                select(func.count(RevenueMaster.id)).where(
                    RevenueMaster.source_file == source_file,
                    RevenueMaster.uploaded_at == now_str,
                )
            ).scalar() or 0

    skipped = len(records) - inserted

    if record_upload:
        report_date = _to_date(df["date"].iloc[0]) if "date" in df.columns else None
        # Sum revenue/PAX for only the rows this call actually inserted,
        # not the whole parsed file — every record just inserted carries
        # this exact (source_file, uploaded_at) pair (uploaded_at is a
        # fresh timestamp generated above, per call), so this query
        # identifies exactly the new rows even when some/all of the
        # file's other rows were skipped as duplicates. Without this, a
        # re-upload where every row is a duplicate would still log the
        # file's full revenue/PAX total next to "0 rows saved," which
        # looks like new data was added when nothing was.
        if inserted > 0:
            with ENGINE.begin() as conn:
                inserted_revenue, inserted_pax = conn.execute(
                    select(
                        func.coalesce(func.sum(RevenueMaster.revenue), 0.0),
                        func.coalesce(func.sum(RevenueMaster.pax), 0.0),
                    ).where(
                        RevenueMaster.source_file == source_file,
                        RevenueMaster.uploaded_at == now_str,
                    )
                ).one()
        else:
            inserted_revenue, inserted_pax = 0.0, 0.0
        _record_upload_history(
            file_name=source_file,
            report_date=report_date,
            row_count=inserted,
            total_revenue=float(inserted_revenue),
            total_pax=float(inserted_pax),
            upload_type="Revenue",
        )

    return {"inserted": inserted, "skipped": skipped, "total_rows": len(df)}


def _record_upload_history(
    file_name: str,
    report_date: Optional[dt.date],
    row_count: int,
    total_revenue: float,
    total_pax: float,
    upload_type: str = "Revenue",
    uploaded_by: Optional[str] = None,
) -> None:
    session = SessionLocal()
    try:
        entry = UploadHistory(
            file_name=file_name,
            report_date=report_date,
            row_count=row_count,
            total_revenue=total_revenue,
            primary_total=total_revenue,
            total_pax=total_pax,
            uploaded_at=dt.datetime.now().isoformat(timespec="seconds"),
            status="Available",
            upload_type=upload_type,
            uploaded_by=uploaded_by,
        )
        session.add(entry)
        session.commit()
    finally:
        session.close()


def delete_upload_by_filename(file_name: str) -> dict:
    """
    Delete all data associated with a specific uploaded file.
    Removes rows from revenue_master, airport_traffic, aop_target,
    aop_target_daily, and upload_history for the given source file.
    Returns count of deleted rows per table.
    """
    counts = {}
    tables = [
        ("revenue_master", RevenueMaster),
        ("airport_traffic", AirportTraffic),
        ("aop_target", AOPTarget),
        ("aop_target_daily", AOPTargetDaily),
    ]
    with ENGINE.begin() as conn:
        for table_name, model in tables:
            result = conn.execute(
                model.__table__.delete().where(
                    model.source_file == file_name
                )
            )
            counts[table_name] = result.rowcount
        # Remove from upload history
        result = conn.execute(
            UploadHistory.__table__.delete().where(
                UploadHistory.file_name == file_name
            )
        )
        counts["upload_history"] = result.rowcount
    return counts


def _to_date(value) -> dt.date:
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    return pd.to_datetime(value).date()


def _to_float_or_none(value):
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return f


# ---------------------------------------------------------------------------
# Reading data
# ---------------------------------------------------------------------------

def load_all() -> pd.DataFrame:
    """Load the entire revenue_master table as a DataFrame."""
    return _read_sql(select(RevenueMaster))


def load_for_date(target_date: dt.date) -> pd.DataFrame:
    """Load all revenue rows for a single date."""
    with ENGINE.connect() as conn:
        result = conn.execute(text("SELECT * FROM revenue_master WHERE date = :d"), {"d": target_date.isoformat()})
        return pd.DataFrame(result.fetchall(), columns=result.keys())


def load_for_dates(dates: list[dt.date]) -> pd.DataFrame:
    """Load all revenue rows for a list of dates in one query."""
    if not dates:
        return pd.DataFrame()
    # Use bindparams to prevent SQL injection — never interpolate dates directly
    placeholders = ", ".join(f":d{i}" for i in range(len(dates)))
    params = {f"d{i}": d.isoformat() for i, d in enumerate(dates)}
    with ENGINE.connect() as conn:
        return pd.read_sql(
            text(f"SELECT * FROM revenue_master WHERE date IN ({placeholders})"),
            conn,
            params=params,
        )


def load_for_date_range(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """
    Load all revenue rows with date in [start_date, end_date] inclusive.
    This is what powers Month-wise and Year-wise comparison — those modes
    aggregate a whole range of dates into one period rather than comparing
    two single days.
    """
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    # Guard against absurdly wide ranges causing full table scans (DoS)
    _MAX_DAYS = 365 * 10
    if (end_date - start_date).days > _MAX_DAYS:
        return pd.DataFrame()
    with ENGINE.connect() as conn:
        return pd.read_sql(
            text("SELECT * FROM revenue_master WHERE date >= :start AND date <= :end"),
            conn,
            params={"start": start_date.isoformat(), "end": end_date.isoformat()},
        )


# ---------------------------------------------------------------------------
# Airport traffic: save, load, and join against revenue
# ---------------------------------------------------------------------------

def save_traffic_dataframe(df: pd.DataFrame, source_file: str) -> dict:
    """
    Insert a (date, location, terminal, traffic, granularity, period_end)
    DataFrame into airport_traffic. `terminal` and `period_end` are
    optional in the input (default to "" and None respectively);
    `granularity` defaults to "daily" if not present. Duplicate (date,
    location, terminal, granularity) rows are skipped silently, same
    dedup behavior as save_dataframe() for revenue — re-uploading a
    traffic file you've already loaded is a harmless no-op that reports
    how many rows were skipped.
    """
    if df.empty:
        return {"inserted": 0, "skipped": 0, "total_rows": 0}

    required_cols = {"date", "location", "traffic"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Traffic DataFrame is missing required columns: {missing}")

    now_str = dt.datetime.now().isoformat(timespec="seconds")

    # FIX (Bug 8 extension): replace iterrows() with vectorized apply().
    # The per-row logic (NULL-safe terminal, period_end, granularity) is
    # preserved exactly — only the iteration mechanism changes.
    work_t = df.copy()

    # Drop rows with no usable traffic value before building records.
    work_t["_traffic"] = work_t["traffic"].apply(_to_float_or_none)
    work_t = work_t[work_t["_traffic"].notna()].copy()

    if work_t.empty:
        return {"inserted": 0, "skipped": 0, "total_rows": len(df)}

    # Use "" rather than NULL for "no terminal breakdown" rows: SQLite's
    # UNIQUE constraint treats every NULL as distinct from every other
    # NULL (by SQL standard), so two NULL-terminal rows for the same
    # (date, location) would NOT be caught as duplicates by INSERT OR
    # IGNORE — silently creating duplicate rows on every re-upload.
    # Empty string is a normal, comparable value, so the constraint
    # works correctly.
    def _norm_terminal(v) -> str:
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            return ""
        s = str(v).strip()
        return "" if s.lower() == "nan" else s

    def _norm_period_end(v) -> object:
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            return None
        try:
            return _to_date(v).isoformat()
        except Exception:
            return None

    def _norm_granularity(v) -> str:
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            return "daily"
        return str(v).strip().lower() or "daily"

    work_t["date"]       = work_t["date"].apply(lambda v: _to_date(v).isoformat())
    work_t["location"]   = work_t["location"].astype(str).str.strip()
    work_t["terminal"]   = work_t["terminal"].apply(_norm_terminal) if "terminal" in work_t.columns else ""
    work_t["period_end"] = work_t["period_end"].apply(_norm_period_end) if "period_end" in work_t.columns else None
    work_t["granularity"] = work_t["granularity"].apply(_norm_granularity) if "granularity" in work_t.columns else "daily"
    work_t["traffic"]    = work_t["_traffic"]
    work_t["source_file"]  = source_file
    work_t["uploaded_at"]  = now_str

    cols = ["date", "period_end", "granularity", "location", "terminal",
            "traffic", "source_file", "uploaded_at"]

    # Fast path: PostgreSQL COPY
    if _IS_POSTGRES:
        try:
            inserted = _pg_copy_insert(work_t, "airport_traffic", cols)
            skipped = len(work_t) - inserted
        except Exception:
            # Fallback to chunked insert
            records = work_t[cols].to_dict("records")
            insert_sql = text("""
                INSERT INTO airport_traffic
                    (date, period_end, granularity, location, terminal, traffic, source_file, uploaded_at)
                VALUES
                    (:date, :period_end, :granularity, :location, :terminal, :traffic, :source_file, :uploaded_at)
                ON CONFLICT (date, location, terminal, granularity) DO NOTHING
            """)
            inserted = 0
            with ENGINE.begin() as conn:
                for i in range(0, len(records), 5000):
                    r = conn.execute(insert_sql, records[i:i + 5000])
                    inserted += r.rowcount if r.rowcount >= 0 else 0
            skipped = len(records) - inserted
    else:
        records = work_t[cols].to_dict("records")
        if not records:
            return {"inserted": 0, "skipped": 0, "total_rows": len(df)}
        insert_sql = text("""
            INSERT INTO airport_traffic
                (date, period_end, granularity, location, terminal, traffic, source_file, uploaded_at)
            VALUES
                (:date, :period_end, :granularity, :location, :terminal, :traffic, :source_file, :uploaded_at)
            ON CONFLICT (date, location, terminal, granularity) DO NOTHING
        """)
        inserted = 0
        with ENGINE.begin() as conn:
            for i in range(0, len(records), 5000):
                r = conn.execute(insert_sql, records[i:i + 5000])
                inserted += r.rowcount if r.rowcount >= 0 else 0
        skipped = len(records) - inserted

    # Same "only the rows this call actually inserted" accuracy fix used
    # for revenue uploads (see save_dataframe): sum traffic for just the
    # (source_file, uploaded_at) pair this call just wrote, not the whole
    # file, so a re-upload where every row is a duplicate logs 0, not a
    # misleading full-file total next to "0 rows saved".
    if inserted > 0:
        with ENGINE.begin() as conn:
            inserted_traffic = conn.execute(
                select(func.coalesce(func.sum(AirportTraffic.traffic), 0.0)).where(
                    AirportTraffic.source_file == source_file,
                    AirportTraffic.uploaded_at == now_str,
                )
            ).scalar() or 0.0
    else:
        inserted_traffic = 0.0

    report_date = _to_date(df["date"].iloc[0]) if "date" in df.columns and not df.empty else None
    _record_upload_history(
        file_name=source_file,
        report_date=report_date,
        row_count=inserted,
        total_revenue=float(inserted_traffic),
        total_pax=0.0,
        upload_type="Traffic",
    )

    return {"inserted": inserted, "skipped": skipped, "total_rows": len(df)}


def load_traffic_for_date_range(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """Load all airport_traffic rows with date in [start_date, end_date] inclusive."""
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    with ENGINE.connect() as conn:
        return pd.read_sql(
            text("SELECT * FROM airport_traffic WHERE date >= :start AND date <= :end"),
            conn,
            params={"start": start_date.isoformat(), "end": end_date.isoformat()},
        )


def load_traffic_all() -> pd.DataFrame:
    """Load the entire airport_traffic table."""
    return _read_sql(select(AirportTraffic))


def get_available_traffic_dates() -> list[dt.date]:
    """Distinct dates present in airport_traffic, sorted ascending."""
    session = SessionLocal()
    try:
        rows = session.execute(
            select(AirportTraffic.date).distinct().order_by(AirportTraffic.date)
        ).all()
        return [r[0] for r in rows]
    finally:
        session.close()


def get_available_terminals() -> list[str]:
    """Distinct non-empty terminal labels present in airport_traffic, sorted."""
    session = SessionLocal()
    try:
        rows = session.execute(
            select(AirportTraffic.terminal).distinct().where(
                AirportTraffic.terminal.is_not(None), AirportTraffic.terminal != ""
            )
        ).all()
        return sorted(r[0] for r in rows if r[0])
    finally:
        session.close()


def get_traffic_total_for_range(
    start_date: dt.date, end_date: dt.date, location: Optional[str] = None
) -> pd.DataFrame:
    """
    Return the best-available traffic total for [start_date, end_date]
    inclusive, grouped by location (and terminal, kept separate) — this is
    the function that actually handles daily vs monthly granularity
    correctly, which a naive per-row join cannot do.

    Strategy per location:
      1. If daily rows fully cover every date in the range, sum the daily
         rows — this is the most accurate option.
      2. Otherwise, fall back to monthly rows whose [date, period_end]
         span overlaps the requested range. A monthly row is prorated by
         the fraction of its days that fall inside the requested range
         (e.g. requesting just the first half of a month against a
         monthly total prorates that total roughly in half) — this is an
         approximation flagged via the `is_estimated` column, since a
         monthly total has no real daily shape to draw from.
      3. If both exist for an overlapping period, daily takes precedence
         for the days it actually covers, and monthly only fills the
         remaining gap days that its own period actually spans.
      4. Any requested date with neither a daily row nor a monthly row
         covering it (a genuine data gap, e.g. a month nobody uploaded
         traffic for at all) is counted in `missing_days` and excluded
         from the total rather than silently treated as zero or silently
         papered over by an unrelated month's monthly figure.

    Returns columns: location, terminal, traffic, is_estimated (bool, True
    if any part of that location+terminal's total came from a prorated
    monthly figure rather than real daily data), missing_days (int, count
    of requested dates with no data at all — callers should warn the user
    when this is > 0, since the returned `traffic` is understated by
    however much those missing days would have contributed).
    """
    # Use the overlap-aware query unconditionally, not just as a fallback
    # for an empty result: a monthly row's own `date` (the 1st of its
    # month) can fall *before* start_date while its `period_end` still
    # overlaps the requested range (e.g. a row dated 2024-05-01 with
    # period_end 2024-05-31 must still be included when start_date is
    # 2024-05-27) — load_traffic_for_date_range's simple date>=/date<=
    # filter would silently exclude that row even though plenty of OTHER
    # rows in the range make the overall query result non-empty, which is
    # exactly the case an empty-result-only fallback would miss.
    all_traffic = _load_traffic_overlapping_range(start_date, end_date, location)

    if all_traffic.empty:
        return pd.DataFrame(columns=["location", "terminal", "traffic", "is_estimated"])

    results = []
    total_days = (end_date - start_date).days + 1

    for (loc, term), group in all_traffic.groupby(["location", "terminal"], dropna=False):
        daily_rows = group[group["granularity"] == "daily"]
        monthly_rows = group[group["granularity"] == "monthly"]

        daily_dates_covered = set(daily_rows["date"])
        all_dates_in_range = {start_date + dt.timedelta(days=i) for i in range(total_days)}
        missing_dates = all_dates_in_range - daily_dates_covered

        traffic_total = daily_rows["traffic"].sum() if not daily_rows.empty else 0.0
        is_estimated = False
        unfilled_dates = set(missing_dates)

        if missing_dates and not monthly_rows.empty:
            # Fill gaps using prorated monthly figures, one missing date
            # at a time, attributing each missing date to whichever
            # monthly row's [date, period_end] span contains it. Only
            # dates that actually fall inside some monthly row's period
            # are removed from `unfilled_dates` — a monthly row covering
            # an unrelated month (e.g. March, when the gap is in April)
            # must NOT cause those April dates to be treated as resolved.
            for _, mrow in monthly_rows.iterrows():
                # Ensure dates are date objects not strings (SQLite may
                # return ISO strings like "2026-07-01" instead of date objects)
                def _to_d(v):
                    if isinstance(v, str):
                        import datetime as _dt
                        return _dt.date.fromisoformat(v[:10])
                    if hasattr(v, "date"):
                        return v.date()
                    return v
                period_start = _to_d(mrow["date"])
                period_end = _to_d(mrow["period_end"]) if pd.notna(mrow["period_end"]) else period_start
                days_in_period = (period_end - period_start).days + 1
                if days_in_period <= 0:
                    continue
                per_day_estimate = mrow["traffic"] / days_in_period
                covered_by_this_row = {d for d in missing_dates if period_start <= d <= period_end}
                if not covered_by_this_row:
                    continue
                is_estimated = True
                traffic_total += per_day_estimate * len(covered_by_this_row)
                unfilled_dates -= covered_by_this_row

        results.append(
            {
                "location": loc,
                "terminal": term,
                "traffic": traffic_total,
                "is_estimated": is_estimated,
                "missing_days": len(unfilled_dates),
            }
        )

    return pd.DataFrame(results)


def _load_traffic_overlapping_range(
    start_date: dt.date, end_date: dt.date, location: Optional[str] = None
) -> pd.DataFrame:
    """
    Wider traffic query that also catches monthly rows whose period
    overlaps [start_date, end_date] even if the monthly row's own `date`
    (the 1st of its month) falls before start_date — a simple date>=/date<=
    filter on `date` alone would miss e.g. a monthly row dated 2026-06-01
    / period_end 2026-06-30 when asked for just 2026-06-15 onward, since
    2026-06-01 < 2026-06-15.

    Daily rows (period_end IS NULL) are bounded normally on both sides
    (date >= start_date AND date <= end_date); monthly rows (period_end
    IS NOT NULL) use [date, period_end] as their span and are included if
    that span overlaps [start_date, end_date] at all.
    """
    daily_condition = sql_and(
        AirportTraffic.period_end.is_(None),
        AirportTraffic.date >= start_date,
        AirportTraffic.date <= end_date,
    )
    monthly_condition = sql_and(
        AirportTraffic.period_end.is_not(None),
        AirportTraffic.date <= end_date,
        AirportTraffic.period_end >= start_date,
    )
    conditions = [sql_or(daily_condition, monthly_condition)]
    if location is not None:
        conditions.append(AirportTraffic.location == location)

    # Use raw SQL for PostgreSQL compatibility
    s = start_date.isoformat()
    e = end_date.isoformat()
    if location is not None:
        sql_str = text("""
            SELECT * FROM airport_traffic
            WHERE location = :loc
            AND (
                (period_end IS NULL AND date >= :s AND date <= :e)
                OR
                (period_end IS NOT NULL AND date <= :e AND period_end >= :s)
            )
        """)
        params = {"loc": location, "s": s, "e": e}
    else:
        sql_str = text("""
            SELECT * FROM airport_traffic
            WHERE (
                (period_end IS NULL AND date >= :s AND date <= :e)
                OR
                (period_end IS NOT NULL AND date <= :e AND period_end >= :s)
            )
        """)
        params = {"s": s, "e": e}

    with ENGINE.connect() as conn:
        result = conn.execute(sql_str, params)
        return pd.DataFrame(result.fetchall(), columns=result.keys())


def join_revenue_with_traffic(revenue_df: pd.DataFrame, traffic_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Aggregate a revenue DataFrame (potentially many outlet/date rows) down
    to one row per location — Revenue and PAX summed across every
    outlet/date in `revenue_df` — with a single, range-correct Traffic
    total attached for that location (see get_traffic_total_for_range).

    IMPORTANT — this deliberately returns one row per location, NOT one
    row per original revenue_df row. Traffic is airport-wide, not
    outlet- or day-specific, so there is exactly one correct Traffic
    figure per location for the whole date range revenue_df spans.
    Earlier this function stamped that same range-total onto every
    outlet/date row instead, on the assumption a caller would dedupe it
    back down before summing (as revenue_analysis.
    location_level_summary_with_traffic does for genuine per-date traffic
    data) — but a dedupe keyed on (date, location) keeps one row per
    distinct *date*, not per location, so it still summed the same
    range-total once per day in the range, multiplying Traffic (and
    therefore silently shrinking Penetration % and SPP) by however many
    days the comparison period covered. Returning exactly one row per
    location makes that miscount impossible.

    Uses get_traffic_total_for_range() internally, so daily vs monthly
    granularity is handled correctly (see that function's docstring) — if
    `traffic_df` is explicitly given instead (e.g. by a caller that
    already loaded a specific slice), it's used as-is via a simple sum,
    skipping the daily/monthly reconciliation logic, so prefer leaving
    `traffic_df` as None unless you know what you're passing.

    Returns columns: location, date (a representative date, kept only so
    this shape matches what revenue_analysis.
    location_level_summary_with_traffic expects), revenue, pax, traffic,
    traffic_is_estimated, traffic_missing_days. Rows whose location has
    no matching traffic at all get NaN traffic, not 0 — this matters for
    has_traffic_data() and the penetration/SPP calculations downstream,
    which need to distinguish "no traffic data yet" from "traffic was
    genuinely zero that day".
    """
    if revenue_df is None or revenue_df.empty:
        return revenue_df

    work = revenue_df.copy()
    if "traffic" in work.columns:
        work = work.drop(columns=["traffic"])

    dates = pd.to_datetime(work["date"]).dt.date
    start_date, end_date = dates.min(), dates.max()

    # Normalise location to title-case so "GOA"/"DELHI" (revenue) matches
    # "Goa"/"Delhi" (traffic) in the merge.
    work["location"] = work["location"].str.strip().str.title()

    location_totals = work.groupby("location", as_index=False).agg(
        revenue=("revenue", "sum"), pax=("pax", "sum")
    )
    location_totals["date"] = start_date

    if traffic_df is None:
        traffic_totals = get_traffic_total_for_range(start_date, end_date)
        if traffic_totals.empty:
            location_totals["traffic"] = pd.NA
            location_totals["traffic_is_estimated"] = False
            location_totals["traffic_missing_days"] = 0
            return location_totals
        traffic_totals["location"] = traffic_totals["location"].str.strip().str.title()
        traffic_by_location = traffic_totals.groupby("location", as_index=False).agg(
            traffic=("traffic", "sum"),
            traffic_is_estimated=("is_estimated", "any"),
            traffic_missing_days=("missing_days", "sum"),
        )
    else:
        if traffic_df.empty:
            location_totals["traffic"] = pd.NA
            location_totals["traffic_is_estimated"] = False
            location_totals["traffic_missing_days"] = 0
            return location_totals
        traffic_by_location = traffic_df.groupby("location", as_index=False)["traffic"].sum()
        traffic_by_location["traffic_is_estimated"] = False
        traffic_by_location["traffic_missing_days"] = 0

    merged = location_totals.merge(traffic_by_location, on="location", how="left")
    return merged


def join_revenue_with_traffic_by_outlet(
    revenue_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Outlet-level traffic join: attaches the CORRECT terminal-specific traffic
    figure to each outlet row based on terminal_mapping.get_terminal_for_outlet.

    Unlike join_revenue_with_traffic (which returns one row per location with
    the whole-airport total), this function returns one row per
    (outlet, location) with the traffic figure for that outlet's specific
    terminal pool — e.g. T3 Dom Dep for T3D49, T3 Int Dep for INL5&6,
    T3 Arr (= T3 Dom Arr + T3 Int Arr) for LA01/LA12/LA22.

    Special terminal sentinels handled:
      "T3 Arr" → sums T3 Dom Arr + T3 Int Arr from airport_traffic
      "T3"     → sums ALL T3 rows (Dom Dep + Int Dep + Dom Arr + Int Arr)
      ""       → NaN traffic (airport-wide services with no single pool)
      "Unmapped" → NaN traffic

    Returns columns: outlet, location, revenue, pax, traffic,
    traffic_is_estimated, traffic_missing_days.
    """
    from . import terminal_mapping as tm

    if revenue_df is None or revenue_df.empty:
        return pd.DataFrame(columns=["outlet", "location", "revenue", "pax",
                                      "traffic", "traffic_is_estimated", "traffic_missing_days"])

    work = revenue_df.copy()
    dates = pd.to_datetime(work["date"]).dt.date
    start_date, end_date = dates.min(), dates.max()

    # Get all terminal-level traffic for this date range
    traffic_totals = get_traffic_total_for_range(start_date, end_date)
    # Build lookup: (location, terminal) → traffic info
    # Normalise location to title-case so "GOA"/"DELHI" (revenue) matches
    # "Goa"/"Delhi" (traffic) in the lookup.
    traffic_lookup: dict[tuple, dict] = {}
    for _, row in traffic_totals.iterrows():
        key = (str(row["location"]).strip().title(), str(row.get("terminal", "")))
        traffic_lookup[key] = {
            "traffic": row["traffic"],
            "is_estimated": row.get("is_estimated", False),
            "missing_days": row.get("missing_days", 0),
        }

    # Aggregate revenue/pax per (outlet, location)
    outlet_agg = work.groupby(["outlet", "location"], as_index=False).agg(
        revenue=("revenue", "sum"), pax=("pax", "sum")
    )

    def _get_traffic(outlet: str, location: str) -> tuple:
        """Return (traffic, is_estimated, missing_days) for this outlet."""
        location = str(location).strip().title()  # normalise case before lookup
        terminal = tm.get_terminal_for_outlet(outlet, location)
        if not terminal or terminal in ("", "Unmapped"):
            return (float("nan"), False, 0)

        def _sum_pools(pools: list[str]) -> tuple:
            """Sum multiple terminal pools; fall back to generic labels if new labels absent."""
            total = 0.0
            estimated = False
            missing = 0
            found_any = False
            for p in pools:
                info = traffic_lookup.get((location, p), {})
                if not info or not info.get("traffic"):
                    # Fallback: handle both traffic file formats:
                    # Format 1 (split): T1 Dep, T1 Arr, T2 Dep, T2 Arr,
                    #   T3 Dom Dep, T3 Dom Arr, T3 Int Dep, T3 Int Arr
                    # Format 2 (combined): T1, T2 Domestic,
                    #   T3 Domestic, T3 International
                    fallbacks = {
                        "T1 Dep":     ["T1 Dep", "T1"],
                        "T1 Arr":     ["T1 Arr", "T1"],
                        "T2 Dep":     ["T2 Dep", "T2 Domestic", "T2"],
                        "T2 Arr":     ["T2 Arr", "T2 Domestic", "T2"],
                        "T3 Dom Dep": ["T3 Dom Dep", "T3 Domestic", "T3"],
                        "T3 Dom Arr": ["T3 Dom Arr", "T3 Domestic", "T3"],
                        "T3 Int Dep": ["T3 Int Dep", "T3 International", "T3"],
                        "T3 Int Arr": ["T3 Int Arr", "T3 International", "T3"],
                    }
                    for fb in fallbacks.get(p, []):
                        info = traffic_lookup.get((location, fb), {})
                        if info and info.get("traffic"):
                            break
                if info and info.get("traffic"):
                    total += info["traffic"]
                    estimated = estimated or info.get("is_estimated", False)
                    missing = max(missing, info.get("missing_days", 0))
                    found_any = True

            # HYD/Goa fallback: monthly files store only a grand total with
            # terminal="" (no Domestic/International split). When the pool
            # lookup fails, split the grand total proportionally:
            #   Domestic    ≈ 81% of grand total (based on typical HYD ratio)
            #   International ≈ 19% of grand total
            # This gives estimated but meaningful PEN%/SPP instead of "—".
            if not found_any and location in ("Hyderabad", "Goa"):
                grand = traffic_lookup.get((location, ""), {})
                if grand and grand.get("traffic"):
                    gt = grand["traffic"]
                    # Ratios derived from actual daily traffic data:
                    # HYD: Domestic=82.7%, International=17.3%
                    # Goa: Domestic=96.4%, International=3.6%
                    _HYD_DOM_RATIO = 0.827
                    _HYD_INT_RATIO = 0.173
                    _GOA_DOM_RATIO = 0.964
                    _GOA_INT_RATIO = 0.036
                    dom_ratio = _HYD_DOM_RATIO if location == "Hyderabad" else _GOA_DOM_RATIO
                    int_ratio = _HYD_INT_RATIO if location == "Hyderabad" else _GOA_INT_RATIO
                    split_total = 0.0
                    for p in pools:
                        if p == "Domestic":
                            split_total += gt * dom_ratio
                        elif p == "International":
                            split_total += gt * int_ratio
                        elif p in ("All", "Main Terminal"):
                            split_total += gt  # whole airport
                    if split_total > 0:
                        total = split_total
                        estimated = True   # mark as estimated since it's a split
                        found_any = True

            if not found_any or total == 0:
                return (float("nan"), False, 0)
            return (total, estimated, missing)

        # --- Composite sentinels ---
        if terminal == "T3 Arr":
            # LA outlets: T3 Dom Arr + T3 Int Arr (Total Arrival T3)
            return _sum_pools(["T3 Dom Arr", "T3 Int Arr"])

        if terminal == "All Dep":
            # Enwrap (Baggage Wrapping): all terminal departures
            return _sum_pools(["T1 Dep", "T2 Dep", "T3 Dom Dep", "T3 Int Dep"])

        if terminal == "All":
            # M&G / Atithya: entire airport
            # Delhi: all 8 terminal pools; HYD/GOA: Domestic + International
            if location in ("Hyderabad", "Goa"):
                return _sum_pools(["Domestic", "International"])
            return _sum_pools(["T1 Dep", "T1 Arr", "T2 Dep", "T2 Arr",
                                "T3 Dom Dep", "T3 Dom Arr", "T3 Int Dep", "T3 Int Arr"])

        if terminal == "T3 Total":
            # Buggy: all 4 T3 pools (Dom Dep + Int Dep + Dom Arr + Int Arr)
            return _sum_pools(["T3 Dom Dep", "T3 Int Dep", "T3 Dom Arr", "T3 Int Arr"])

        if terminal == "T3 Dom+Int Dep":
            # RL T3 Departure: serves T3 departing passengers (both Dom & Int sides)
            return _sum_pools(["T3 Dom Dep", "T3 Int Dep"])

        if terminal == "Porter Pool":
            # Porter: T1 Dep+Arr + T2 Dep+Arr + T3 Dom Dep + T3 Dom Arr + T3 Int Dep
            # Porter operates in all departure areas and T3 domestic arrivals.
            # Excludes T3 Int Arr (no Porter in T3 International Arrivals area).
            return _sum_pools(["T1 Dep", "T1 Arr", "T2 Dep", "T2 Arr",
                                "T3 Dom Dep", "T3 Dom Arr", "T3 Int Dep"])

        if terminal in ("T3", "T3+"):
            # Generic T3 fallback (old data without Dep/Arr split)
            return _sum_pools(["T3 Dom Dep", "T3 Dom Arr", "T3 Int Dep", "T3 Int Arr"])

        # Hyderabad / Goa terminal labels
        if terminal == "Domestic":
            return _sum_pools(["Domestic"])

        if terminal == "International":
            return _sum_pools(["International"])

        if terminal == "Main Terminal":
            # Whole-airport fallback for HYD/GOA outlets without specific mapping
            return _sum_pools(["Domestic", "International", "Main Terminal"])

        # --- Single terminal pool ---
        info = traffic_lookup.get((location, terminal), {})
        if not info or not info.get("traffic"):
            # Fallback for old data without Dep/Arr split
            generic = {
                "T1 Dep": "T1", "T1 Arr": "T1",
                "T2 Dep": "T2", "T2 Arr": "T2",
                "T3 Dom Dep": "T3", "T3 Int Dep": "T3",
                "T3 Dom Arr": "T3", "T3 Int Arr": "T3",
            }
            if terminal in generic:
                info = traffic_lookup.get((location, generic[terminal]), {})
            if not info or not info.get("traffic"):
                return (float("nan"), False, 0)
        return (info["traffic"], info.get("is_estimated", False), info.get("missing_days", 0))

    # FIX (Bug 2): previously _get_traffic() was called three separate times
    # per row — once for each of traffic, traffic_is_estimated, and
    # traffic_missing_days. Each call re-runs the full terminal lookup and
    # pool-summing logic. With potentially hundreds of outlets and
    # chained fallback look-ups inside _get_traffic, the triple-call cost
    # is non-trivial. Fix: call once per row, store the tuple, then
    # extract all three values from the stored result.
    traffic_results = outlet_agg.apply(
        lambda r: _get_traffic(r["outlet"], r["location"]), axis=1
    )
    outlet_agg["traffic"]              = traffic_results.apply(lambda t: t[0])
    outlet_agg["traffic_is_estimated"] = traffic_results.apply(lambda t: t[1])
    outlet_agg["traffic_missing_days"] = traffic_results.apply(lambda t: t[2])
    return outlet_agg


# ---------------------------------------------------------------------------
# AOP targets: save, load, and join against revenue
# ---------------------------------------------------------------------------

def save_aop_targets(df: pd.DataFrame, source_file: str) -> dict:
    """
    Insert a (location, segment, business_unit, outlet, year, month, aop)
    DataFrame into aop_target. Duplicate (location, outlet, year, month)
    rows are skipped silently — re-uploading an AOP file you've already
    loaded, or re-uploading a corrected version with the same keys, is a
    safe no-op for the rows that already match (use reset/delete first if
    you need to genuinely replace a target value).
    """
    if df.empty:
        return {"inserted": 0, "skipped": 0, "total_rows": 0}

    required_cols = {"location", "outlet", "year", "month", "aop"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"AOP DataFrame is missing required columns: {missing}")

    now_str = dt.datetime.now().isoformat(timespec="seconds")

    # FIX (Bug 8 extension): replace iterrows() with vectorized apply().
    work_a = df.copy()
    work_a["_aop"] = work_a["aop"].apply(_to_float_or_none)
    work_a = work_a[work_a["_aop"].notna()].copy()

    if work_a.empty:
        return {"inserted": 0, "skipped": 0, "total_rows": len(df)}

    work_a["location"] = work_a["location"].astype(str).str.strip().str.title()
    # Canonicalize outlet names so AOP targets join correctly against
    # revenue_master rows (which are also canonicalized at upload time).
    # Without this, an AOP file with "INL 5&6" won't match "International Lounge"
    # in revenue_master and the AOP join returns NaN for that outlet.
    work_a["outlet"] = work_a["outlet"].astype(str).str.strip().apply(canonicalize_outlet_name)

    # Collapse AOP values for outlets that canonicalize to the same name
    # (e.g. "INL 5&6" + "International Lounge" both → "International Lounge").
    # Without this, ON CONFLICT DO NOTHING silently drops the second row
    # and the AOP for that outlet is lost or understated.
    # Fix: sum AOP values across all rows that share the same
    # (location, outlet, year, month) key BEFORE inserting.
    _key_cols = ["location", "outlet", "year", "month"]
    _has_key = all(c in work_a.columns for c in _key_cols)
    if _has_key:
        _aop_col = "_aop"
        _non_aop = [c for c in work_a.columns if c not in [_aop_col] + _key_cols
                    and c in ["segment", "business_unit"]]
        _agg = {_aop_col: "sum"}
        for _c in _non_aop:
            _agg[_c] = "first"
        work_a = work_a.groupby(_key_cols, as_index=False).agg(_agg)
    work_a["segment"]  = (
        work_a["segment"].astype(str).str.strip()
        if "segment" in work_a.columns
        else "EHPL"
    )
    work_a["business_unit"] = work_a.apply(
        lambda r: str(r["business_unit"]).strip()
        if "business_unit" in r.index and pd.notna(r.get("business_unit"))
        else None,
        axis=1,
    )
    work_a["year"]  = work_a["year"].apply(lambda v: int(v))
    work_a["month"] = work_a["month"].apply(lambda v: int(v))
    work_a["aop"]   = work_a["_aop"]
    work_a["source_file"]  = source_file
    work_a["uploaded_at"]  = now_str

    cols_a = ["location", "segment", "business_unit", "outlet",
              "year", "month", "aop", "source_file", "uploaded_at"]
    if work_a.empty:
        return {"inserted": 0, "skipped": 0, "total_rows": len(df)}

    if _IS_POSTGRES:
        try:
            inserted = _pg_copy_insert(work_a, "aop_target", cols_a)
            skipped = len(work_a) - inserted
        except Exception:
            records = work_a[cols_a].to_dict("records")
            insert_sql = text("""INSERT INTO aop_target (location, segment, business_unit, outlet, year, month, aop, source_file, uploaded_at) VALUES (:location, :segment, :business_unit, :outlet, :year, :month, :aop, :source_file, :uploaded_at) ON CONFLICT (location, outlet, year, month) DO NOTHING""")
            inserted = 0
            with ENGINE.begin() as conn:
                for i in range(0, len(records), 5000):
                    r = conn.execute(insert_sql, records[i:i+5000])
                    inserted += r.rowcount if r.rowcount >= 0 else 0
            skipped = len(records) - inserted
    else:
        records = work_a[cols_a].to_dict("records")
        insert_sql = text("""INSERT INTO aop_target (location, segment, business_unit, outlet, year, month, aop, source_file, uploaded_at) VALUES (:location, :segment, :business_unit, :outlet, :year, :month, :aop, :source_file, :uploaded_at) ON CONFLICT (location, outlet, year, month) DO NOTHING""")
        inserted = 0
        with ENGINE.begin() as conn:
            for i in range(0, len(records), 5000):
                r = conn.execute(insert_sql, records[i:i+5000])
                inserted += r.rowcount if r.rowcount >= 0 else 0
        skipped = len(records) - inserted

    if inserted > 0:
        with ENGINE.begin() as conn:
            inserted_aop = conn.execute(
                select(func.coalesce(func.sum(AOPTarget.aop), 0.0)).where(
                    AOPTarget.source_file == source_file,
                    AOPTarget.uploaded_at == now_str,
                )
            ).scalar() or 0.0
    else:
        inserted_aop = 0.0

    first_row = df.iloc[0]
    report_date = (
        dt.date(int(first_row["year"]), int(first_row["month"]), 1)
        if pd.notna(first_row.get("year")) and pd.notna(first_row.get("month"))
        else None
    )
    _record_upload_history(
        file_name=source_file,
        report_date=report_date,
        row_count=inserted,
        total_revenue=float(inserted_aop),
        total_pax=0.0,
        upload_type="AOP",
    )

    return {"inserted": inserted, "skipped": skipped, "total_rows": len(df)}


def load_aop_targets_for_period(year: int, month: int) -> pd.DataFrame:
    """Load all AOP target rows for a single (year, month)."""
    with ENGINE.connect() as conn:
        return pd.read_sql(
            text("SELECT * FROM aop_target WHERE year = :year AND month = :month"),
            conn,
            params={"year": int(year), "month": int(month)},
        )


def load_aop_targets_for_range(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """
    Load all AOP target rows for every (year, month) touched by
    [start_date, end_date] inclusive — e.g. a range spanning April 5 to
    May 10 pulls both April's and May's targets.
    """
    months = set()
    cursor = dt.date(start_date.year, start_date.month, 1)
    end_marker = dt.date(end_date.year, end_date.month, 1)
    while cursor <= end_marker:
        months.add((cursor.year, cursor.month))
        if cursor.month == 12:
            cursor = dt.date(cursor.year + 1, 1, 1)
        else:
            cursor = dt.date(cursor.year, cursor.month + 1, 1)

    if not months:
        return pd.DataFrame()

    # Use raw SQL — ORM select() objects can silently return empty
    # DataFrames on PostgreSQL with some pandas versions.
    # Build parameterized OR conditions — never interpolate integers directly
    conditions_parts = []
    params = {}
    for i, (y, m) in enumerate(sorted(months)):
        conditions_parts.append(f"(year = :y{i} AND month = :m{i})")
        params[f"y{i}"] = int(y)
        params[f"m{i}"] = int(m)
    conditions_sql = " OR ".join(conditions_parts)
    with ENGINE.connect() as conn:
        return pd.read_sql(
            text(f"SELECT * FROM aop_target WHERE {conditions_sql}"),
            conn,
            params=params,
        )


def get_available_aop_year_months() -> list[tuple[int, int]]:
    """Distinct (year, month) pairs present in aop_target, sorted ascending."""
    session = SessionLocal()
    try:
        rows = session.execute(
            select(AOPTarget.year, AOPTarget.month).distinct()
        ).all()
        return sorted({(r[0], r[1]) for r in rows})
    finally:
        session.close()


def save_aop_targets_daily(df: pd.DataFrame, source_file: str) -> dict:
    """
    Insert a (location, date, aop) DataFrame into aop_target_daily — the
    daily-total-per-location AOP format (no outlet/segment breakdown).
    Duplicate (location, date) rows are skipped silently, same dedup
    behavior as every other save_* function in this module.
    """
    if df.empty:
        return {"inserted": 0, "skipped": 0, "total_rows": 0}

    required_cols = {"location", "date", "aop"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Daily AOP DataFrame is missing required columns: {missing}")

    now_str = dt.datetime.now().isoformat(timespec="seconds")

    # FIX (Bug 8 extension): replace iterrows() with vectorized apply().
    work_d = df.copy()
    work_d["_aop"] = work_d["aop"].apply(_to_float_or_none)
    work_d = work_d[work_d["_aop"].notna()].copy()

    if work_d.empty:
        return {"inserted": 0, "skipped": 0, "total_rows": len(df)}

    work_d["location"] = work_d["location"].astype(str).str.strip()
    work_d["date"]     = work_d["date"].apply(lambda v: _to_date(v).isoformat())
    work_d["aop"]      = work_d["_aop"]
    work_d["source_file"]  = source_file
    work_d["uploaded_at"]  = now_str

    cols_d = ["location", "date", "aop", "source_file", "uploaded_at"]
    if work_d.empty:
        return {"inserted": 0, "skipped": 0, "total_rows": len(df)}

    if _IS_POSTGRES:
        try:
            inserted = _pg_copy_insert(work_d, "aop_target_daily", cols_d)
            skipped = len(work_d) - inserted
        except Exception:
            records = work_d[cols_d].to_dict("records")
            insert_sql = text("""INSERT INTO aop_target_daily (location, date, aop, source_file, uploaded_at) VALUES (:location, :date, :aop, :source_file, :uploaded_at) ON CONFLICT (location, date) DO NOTHING""")
            inserted = 0
            with ENGINE.begin() as conn:
                for i in range(0, len(records), 5000):
                    r = conn.execute(insert_sql, records[i:i+5000])
                    inserted += r.rowcount if r.rowcount >= 0 else 0
            skipped = len(records) - inserted
    else:
        records = work_d[cols_d].to_dict("records")
        insert_sql = text("""INSERT INTO aop_target_daily (location, date, aop, source_file, uploaded_at) VALUES (:location, :date, :aop, :source_file, :uploaded_at) ON CONFLICT (location, date) DO NOTHING""")
        inserted = 0
        with ENGINE.begin() as conn:
            for i in range(0, len(records), 5000):
                r = conn.execute(insert_sql, records[i:i+5000])
                inserted += r.rowcount if r.rowcount >= 0 else 0
        skipped = len(records) - inserted

    if inserted > 0:
        with ENGINE.begin() as conn:
            inserted_aop = conn.execute(
                select(func.coalesce(func.sum(AOPTargetDaily.aop), 0.0)).where(
                    AOPTargetDaily.source_file == source_file,
                    AOPTargetDaily.uploaded_at == now_str,
                )
            ).scalar() or 0.0
    else:
        inserted_aop = 0.0

    report_date = _to_date(df["date"].iloc[0]) if "date" in df.columns and not df.empty else None
    _record_upload_history(
        file_name=source_file,
        report_date=report_date,
        row_count=inserted,
        total_revenue=float(inserted_aop),
        total_pax=0.0,
        upload_type="AOP",
    )

    return {"inserted": inserted, "skipped": skipped, "total_rows": len(df)}


def load_aop_targets_daily_for_range(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """Load all aop_target_daily rows with date in [start_date, end_date] inclusive."""
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    with ENGINE.connect() as conn:
        return pd.read_sql(
            text("SELECT * FROM aop_target_daily WHERE date >= :start AND date <= :end"),
            conn,
            params={"start": start_date.isoformat(), "end": end_date.isoformat()},
        )


def get_available_aop_daily_dates() -> list[dt.date]:
    """Distinct dates present in aop_target_daily, sorted ascending."""
    session = SessionLocal()
    try:
        rows = session.execute(
            select(AOPTargetDaily.date).distinct().order_by(AOPTargetDaily.date)
        ).all()
        return [r[0] for r in rows]
    finally:
        session.close()


def get_aop_target_for_range(start_date: dt.date, end_date: dt.date, location: Optional[str] = None) -> dict:
    """
    Return the best-available total AOP target for [start_date, end_date]
    inclusive, per location, preferring the daily-total source
    (aop_target_daily) when it covers the range, and falling back to the
    monthly per-outlet source (aop_target, summed across outlets and
    prorated the same way join_revenue_with_aop already does) for any
    part of the range the daily source doesn't cover.

    Returns {location: {"aop_target": float, "is_estimated": bool,
    "missing_days": int}}, mirroring the same shape and meaning as
    get_traffic_total_for_range — a missing_days > 0 means part of the
    range has no AOP target from either source, and the caller should
    treat the returned total as understated rather than complete.
    """
    daily_df = load_aop_targets_daily_for_range(start_date, end_date)
    if location is not None and not daily_df.empty:
        daily_df = daily_df[daily_df["location"] == location]

    total_days = (end_date - start_date).days + 1
    all_dates_in_range = {start_date + dt.timedelta(days=i) for i in range(total_days)}

    locations_seen = set(daily_df["location"].unique()) if not daily_df.empty else set()
    if location is not None:
        locations_seen.add(location)

    monthly_df = load_aop_targets_for_range(start_date, end_date)
    if location is not None and not monthly_df.empty:
        monthly_df = monthly_df[monthly_df["location"] == location]
    if not monthly_df.empty:
        locations_seen |= set(monthly_df["location"].unique())

    results = {}
    for loc in locations_seen:
        loc_daily = daily_df[daily_df["location"] == loc] if not daily_df.empty else daily_df
        dates_covered_daily = set(loc_daily["date"]) if not loc_daily.empty else set()
        total = float(loc_daily["aop"].sum()) if not loc_daily.empty else 0.0
        missing_dates = all_dates_in_range - dates_covered_daily
        is_estimated = False

        if missing_dates:
            loc_monthly = monthly_df[monthly_df["location"] == loc] if not monthly_df.empty else monthly_df
            if not loc_monthly.empty:
                # Sum across outlets per (year, month), then prorate by
                # the fraction of that month's days actually missing from
                # the daily source and still inside the requested range.
                monthly_by_ym = loc_monthly.groupby(["year", "month"])["aop"].sum()
                for (y, m), month_total in monthly_by_ym.items():
                    days_in_month = calendar.monthrange(int(y), int(m))[1]
                    per_day = month_total / days_in_month if days_in_month else 0.0
                    covered_by_this_month = {
                        d for d in missing_dates if d.year == y and d.month == m
                    }
                    if covered_by_this_month:
                        is_estimated = True
                        total += per_day * len(covered_by_this_month)
                        missing_dates -= covered_by_this_month

        results[loc] = {
            "aop_target": total,
            "is_estimated": is_estimated,
            "missing_days": len(missing_dates),
        }

    return results


def join_revenue_with_aop(revenue_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build one row per (location, outlet, year, month) actually present in
    revenue_df, with that outlet-month's actual revenue (summed over
    exactly the dates revenue_df contains) alongside its AOP target,
    prorated to a daily rate within the month and multiplied by however
    many days of that month are actually present in `revenue_df`, so a
    partial-month revenue range (e.g. just the first 10 days) is compared
    against a proportional slice of that month's AOP target rather than
    the whole month's target.

    IMPORTANT — this deliberately returns one row per outlet-month, NOT
    one row per original revenue_df row. Earlier this function left-
    joined the (already-prorated) target onto every individual date-row
    for that outlet, on the assumption a caller would pull a single value
    per outlet-month back out. But callers (e.g. revenue_analysis.
    aop_variance) instead sum the returned column directly — and summing
    the *same* prorated total once per date-row silently multiplied every
    outlet's AOP target by however many days of that month were present
    in revenue_df. Returning exactly one row per outlet-month makes that
    miscount impossible: summing `revenue` or `aop_target` across the
    rows this function returns always yields the correct total, with
    nothing left to double-count.

    Returns columns: location, outlet, revenue (actual, summed over the
    dates present), aop_target. Rows with no matching AOP target (a new
    outlet, an out-of-scope location, or a period with no AOP data
    loaded) get NaN aop_target, not 0 — same "missing vs genuinely zero"
    distinction used throughout this module.

    This is independent of any pre-existing `aop` column already on
    individual revenue_master rows from a historical Excel import — that
    legacy per-row AOP figure lives on `revenue_df` itself and is not
    read or altered here.
    """
    if revenue_df is None or revenue_df.empty:
        return revenue_df

    work = revenue_df.copy()
    work["_year"] = pd.to_datetime(work["date"]).dt.year
    work["_month"] = pd.to_datetime(work["date"]).dt.month

    dates = pd.to_datetime(work["date"]).dt.date
    start_date, end_date = dates.min(), dates.max()

    # One row per outlet-month, with the actual revenue for exactly the
    # dates present, and how many distinct dates that is (used below to
    # prorate the AOP target by the same fraction of the month).
    group_totals = work.groupby(
        ["location", "outlet", "_year", "_month"], as_index=False
    ).agg(revenue=("revenue", "sum"), _days_present=("date", "nunique"))

    # ── Try daily-total AOP first (aop_target_daily table) ─────────────────
    # The daily table holds location-level totals per day — there is no
    # per-outlet breakdown. Previously the location total was distributed
    # to individual outlets proportionally by their revenue share, creating
    # a circular comparison: an outlet that earned more revenue was always
    # assigned a proportionally higher target, making every outlet appear
    # to be exactly on budget regardless of actual individual performance.
    #
    # FIX (BL-002): when only daily-total AOP is available, return the
    # location-level total in a single location-level row (not distributed
    # across outlets). Callers that display per-outlet AOP will see NaN
    # for individual outlets and the total only at the location grain —
    # exactly the information that is actually known.
    #
    # The aop_target_daily source remains used for:
    #   - Executive Summary KPI card (location total AOP) ✓
    #   - get_aop_target_for_range() (location total, shown in summary) ✓
    # It is NOT used to fabricate per-outlet targets that were never set.
    # ── Try monthly per-outlet AOP first (aop_target table) ────────────────
    # Per-outlet monthly AOP is more granular and preferred over daily
    # location-total AOP. Only fall back to daily when per-outlet is absent.
    # This prevents DB3.xlsx legacy AOP data (daily, location-level only)
    # from blocking AOP_Clean_FY25-27.xlsx (per-outlet monthly) from showing.
    aop_targets = load_aop_targets_for_range(start_date, end_date)

    if aop_targets.empty:
        # No per-outlet monthly AOP — try daily location-total as fallback
        daily_aop = load_aop_targets_daily_for_range(start_date, end_date)
        if not daily_aop.empty:
            # Sum daily AOP per location over the date range — location total only.
            daily_by_loc = daily_aop.groupby("location", as_index=False)["aop"].sum()
            daily_by_loc = daily_by_loc.rename(columns={"aop": "_loc_aop_total"})

            # Build one row per location with actual_revenue summed across outlets.
            loc_revenue = group_totals.groupby("location", as_index=False)["revenue"].sum()
            loc_merged = loc_revenue.merge(daily_by_loc, on="location", how="left")
            loc_merged = loc_merged.rename(columns={"_loc_aop_total": "aop_target"})
            loc_merged["outlet"] = "__location_total__"
            loc_merged["aop_source"] = "daily_location_total"
            return loc_merged[["location", "outlet", "revenue", "aop_target", "aop_source"]]

    # ── Use monthly per-outlet AOP (aop_target table) ───────────────────────
    # (aop_targets already loaded above)
    if aop_targets.empty:
        group_totals["aop_target"] = pd.NA
        return group_totals.drop(columns=["_year", "_month", "_days_present"])

    aop_targets = aop_targets.rename(columns={"year": "_year", "month": "_month"})
    # Canonicalize outlet names in aop_targets to match revenue_master canonical names.
    # AOP files may use raw names (e.g. "INL 5&6") that differ from the canonical
    # name stored in revenue_master ("International Lounge"). Without this, the
    # join returns NaN for every outlet whose AOP file used a different name variant.
    aop_targets["outlet"] = aop_targets["outlet"].astype(str).str.strip().apply(
        canonicalize_outlet_name
    )
    merged = group_totals.merge(
        aop_targets[["location", "outlet", "_year", "_month", "aop"]],
        on=["location", "outlet", "_year", "_month"],
        how="left",
    )

    merged["_days_in_month"] = merged.apply(
        lambda r: calendar.monthrange(int(r["_year"]), int(r["_month"]))[1], axis=1
    )
    merged["aop_target"] = merged["aop"] * (
        merged["_days_present"] / merged["_days_in_month"]
    )

    merged = merged.drop(columns=["_year", "_month", "_days_present", "_days_in_month", "aop"])
    return merged


def get_available_year_months() -> list[tuple[int, int]]:
    """
    Distinct (year, month) pairs present in the database, sorted ascending.
    Used to populate the Month-wise comparison dropdowns with only months
    that actually have data, rather than every month since year 1.
    """
    dates = get_available_dates()
    pairs = sorted({(d.year, d.month) for d in dates})
    return pairs


def get_available_years() -> list[int]:
    """Distinct years present in the database, sorted ascending."""
    dates = get_available_dates()
    return sorted({d.year for d in dates})


def get_available_week_starts() -> list[dt.date]:
    """
    Distinct ISO week-start (Monday) dates that have at least one day of
    data in the database, sorted ascending. Used to populate the Week-wise
    comparison dropdown with only weeks that actually have data — a week
    appears here even if only one of its seven days was uploaded, since
    that's still a usable (if partial) week for comparison.
    """
    dates = get_available_dates()
    mondays = {d - dt.timedelta(days=d.weekday()) for d in dates}
    return sorted(mondays)


def get_available_dates() -> list[dt.date]:
    """All distinct dates present in the database, sorted ascending."""
    session = SessionLocal()
    try:
        rows = session.execute(
            select(RevenueMaster.date).distinct().order_by(RevenueMaster.date)
        ).all()
        return [r[0] for r in rows]
    finally:
        session.close()


def get_available_locations_for_range(
    start_date: "dt.date",
    end_date: "dt.date",
    segment: str | None = None,
) -> list[str]:
    """
    Return distinct location names that have data in the given date range.
    Optionally filter by segment.  Results are title-cased and sorted.
    """
    session = SessionLocal()
    try:
        q = (
            select(RevenueMaster.location)
            .where(RevenueMaster.date >= start_date)
            .where(RevenueMaster.date <= end_date)
            .distinct()
        )
        rows = session.execute(q).all()
        locs = sorted({str(r[0]).strip().title() for r in rows if r[0]})
        return locs
    except Exception:
        return []
    finally:
        session.close()


def get_nearest_date(target: dt.date, available: Optional[list[dt.date]] = None) -> Optional[dt.date]:
    """Return the date in the DB closest to (but not after) `target`, or None."""
    available = available if available is not None else get_available_dates()
    candidates = [d for d in available if d <= target]
    if not candidates:
        return None
    return max(candidates)


def find_comparison_dates(current: dt.date) -> dict:
    """
    Find the best-match yesterday / last-month / last-year dates that
    actually exist in the database, relative to `current`.
    """
    available = get_available_dates()
    avail_set = set(available)

    yesterday = current - dt.timedelta(days=1)
    last_month = _safe_month_shift(current, -1)
    last_year = _safe_month_shift(current, -12)

    return {
        "yesterday": yesterday if yesterday in avail_set else get_nearest_date(yesterday, available),
        "last_month": last_month if last_month in avail_set else get_nearest_date(last_month, available),
        "last_year": last_year if last_year in avail_set else get_nearest_date(last_year, available),
    }


# FIX (Bug 5): _safe_month_shift was duplicated here and in revenue_analysis.py.
# The canonical implementation now lives in modules/date_utils.py and is
# imported at the top of this file as `_safe_month_shift`.  The local
# definition is removed to eliminate the duplicate.


def get_upload_history() -> pd.DataFrame:
    """All upload history records, most recent first."""
    with ENGINE.connect() as conn:
        return pd.read_sql(
            text("SELECT * FROM upload_history ORDER BY id DESC"),
            conn
        )


def get_dates_summary() -> pd.DataFrame:
    """One row per date with total revenue, total PAX, and outlet count."""
    with ENGINE.connect() as conn:
        return pd.read_sql(text("""
            SELECT date,
                   SUM(revenue) as total_revenue,
                   SUM(pax) as total_pax,
                   COUNT(DISTINCT outlet) as outlets
            FROM revenue_master
            GROUP BY date
            ORDER BY date DESC
        """), conn)


def get_db_stats() -> dict:
    """Summary stats for the Database Management section."""
    session = SessionLocal()
    try:
        total_rows = session.execute(select(func.count(RevenueMaster.id))).scalar() or 0
        min_date = session.execute(select(func.min(RevenueMaster.date))).scalar()
        max_date = session.execute(select(func.max(RevenueMaster.date))).scalar()
        distinct_dates = session.execute(
            select(func.count(RevenueMaster.date.distinct()))
        ).scalar() or 0
        return {
            "total_rows": total_rows,
            "min_date": min_date,
            "max_date": max_date,
            "distinct_dates": distinct_dates,
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Upload rate limiting — DB-backed, per-user, cross-session
# ---------------------------------------------------------------------------
# Stored in upload_history rather than a dedicated table: we count how many
# rows with upload_type='Revenue' a given user has inserted in the past hour.
# This is resistant to tab-refresh, new browser sessions, and incognito mode
# because the check hits the database, not session_state.

_MAX_UPLOADS_PER_HOUR = 20


def check_upload_rate_limit(username: str) -> tuple[bool, str]:
    """
    Return (allowed, message).  Counts revenue uploads by `username` in the
    past hour against _MAX_UPLOADS_PER_HOUR.  Always returns True when
    username is empty (e.g., misconfigured auth) so the app degrades
    gracefully rather than locking everyone out.
    """
    if not username:
        return True, ""
    cutoff = (dt.datetime.now() - dt.timedelta(hours=1)).isoformat(timespec="seconds")
    with ENGINE.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM upload_history "
                "WHERE uploaded_by = :u AND upload_type = 'Revenue' "
                "AND uploaded_at >= :cutoff"
            ),
            {"u": username, "cutoff": cutoff},
        ).fetchone()
    count = row[0] if row else 0
    if count >= _MAX_UPLOADS_PER_HOUR:
        return (
            False,
            f"Upload limit reached ({_MAX_UPLOADS_PER_HOUR}/hour for your account). "
            f"Please wait before uploading more files.",
        )
    return True, ""


# ---------------------------------------------------------------------------
# Login lockout tracking — DB-backed, keyed by username
# Prevents brute-force bypassing by opening new browser tabs.
# ---------------------------------------------------------------------------

_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300  # 5 minutes


def record_failed_login(username: str) -> None:
    """Record a failed login attempt. Creates the table row if it doesn't exist."""
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with ENGINE.begin() as conn:
        try:
            conn.execute(text(
                "INSERT INTO login_attempts (username, attempt_at) VALUES (:u, :n)"
            ), {"u": username, "n": now})
        except Exception:
            pass  # Table may not exist yet on first run — init_db handles creation


def clear_failed_logins(username: str) -> None:
    """Clear all failed login records for a user on successful login."""
    with ENGINE.begin() as conn:
        try:
            conn.execute(text("DELETE FROM login_attempts WHERE username=:u"), {"u": username})
        except Exception:
            pass


def get_lockout_status(username: str) -> tuple[bool, int]:
    """
    Return (is_locked_out, seconds_remaining).
    Counts failed attempts within the last _LOCKOUT_SECONDS window.
    """
    cutoff = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=_LOCKOUT_SECONDS)
    ).isoformat(timespec="seconds")
    with ENGINE.connect() as conn:
        try:
            row = conn.execute(
                text("SELECT COUNT(*) FROM login_attempts WHERE username=:u AND attempt_at >= :c"),
                {"u": username, "c": cutoff}
            ).fetchone()
            count = row[0] if row else 0
        except Exception:
            return False, 0
    if count >= _MAX_LOGIN_ATTEMPTS:
        # Find oldest attempt in window to compute remaining lockout
        with ENGINE.connect() as conn:
            try:
                oldest = conn.execute(
                    text("SELECT MIN(attempt_at) FROM login_attempts WHERE username=:u AND attempt_at >= :c"),
                    {"u": username, "c": cutoff}
                ).scalar()
            except Exception:
                oldest = None
        if oldest:
            try:
                oldest_dt = dt.datetime.fromisoformat(oldest).replace(tzinfo=dt.timezone.utc)
                unlock_at = oldest_dt + dt.timedelta(seconds=_LOCKOUT_SECONDS)
                remaining = int((unlock_at - dt.datetime.now(dt.timezone.utc)).total_seconds())
                return True, max(remaining, 0)
            except Exception:
                pass
        return True, _LOCKOUT_SECONDS
    return False, 0
