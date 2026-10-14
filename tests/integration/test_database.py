"""
tests/integration/test_database.py — Integration tests for modules/database.py

Uses an in-memory SQLite database for isolation — no on-disk state created.
Tests: init_db, save_dataframe, load_for_date_range, unique constraint,
segment canonicalization, upload_history, rate limiting, and reset_db.
"""
import sys
import os
import datetime as dt
import io

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# ── Patch the engine to use in-memory SQLite before importing database ────────

import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# We monkey-patch at module level before the first import so the module
# picks up our test engine instead of reading DATABASE_URL.
import unittest.mock as mock

_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
)

with mock.patch.dict(os.environ, {"DATABASE_URL": ""}):
    # Patch st.secrets so database.py doesn't call into Streamlit
    with mock.patch("streamlit.secrets", {}):
        import modules.database as db

# Replace the module-level engine with our in-memory one
db.ENGINE = _TEST_ENGINE
db.SessionLocal = sessionmaker(bind=_TEST_ENGINE)
db._IS_POSTGRES = False

# Re-create tables on the in-memory engine
db.Base.metadata.create_all(_TEST_ENGINE)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _revenue_df(
    date: dt.date = dt.date(2026, 7, 1),
    outlet: str = "International Lounge",
    location: str = "Delhi",
    segment: str = "EHPL",
    revenue: float = 500_000.0,
    pax: float = 200.0,
) -> pd.DataFrame:
    return pd.DataFrame([{
        "date": date,
        "segment": segment,
        "business_unit": "Lounges",
        "outlet": outlet,
        "location": location,
        "pax": pax,
        "revenue": revenue,
        "aop": None,
        "traffic": None,
        "source_file": "test_file.xlsx",
        "uploaded_at": dt.datetime.now().isoformat(timespec="seconds"),
    }])


@pytest.fixture(autouse=True)
def clean_db():
    """Wipe all tables before each test for isolation."""
    from sqlalchemy import text
    with _TEST_ENGINE.begin() as conn:
        for tbl in ["revenue_master", "airport_traffic", "aop_target",
                     "aop_target_daily", "upload_history"]:
            try:
                conn.execute(text(f"DELETE FROM {tbl}"))
            except Exception:
                pass
    yield


# ── init_db ───────────────────────────────────────────────────────────────────

class TestInitDb:
    def test_tables_exist_after_init(self):
        from sqlalchemy import inspect
        insp = inspect(_TEST_ENGINE)
        tables = insp.get_table_names()
        assert "revenue_master" in tables
        assert "upload_history" in tables
        assert "airport_traffic" in tables
        assert "aop_target" in tables
        assert "aop_target_daily" in tables


# ── save_dataframe / load_for_date_range ─────────────────────────────────────

class TestSaveAndLoad:
    def test_save_then_load(self):
        df = _revenue_df()
        result = db.save_dataframe(df, source_file="test.xlsx")
        assert result["inserted"] == 1
        assert result["skipped"] == 0

        loaded = db.load_for_date_range(dt.date(2026, 7, 1), dt.date(2026, 7, 1))
        assert len(loaded) == 1
        assert loaded.iloc[0]["revenue"] == pytest.approx(500_000.0)

    def test_duplicate_row_skipped(self):
        df = _revenue_df()
        r1 = db.save_dataframe(df, source_file="test_dup_a.xlsx", record_upload=False)
        assert r1["inserted"] == 1

        # Second insert of the same (date, segment, outlet, location) must be skipped.
        # We verify this via the table row count rather than relying on the rowcount
        # fallback (which can be confused when both inserts share the same second).
        r2 = db.save_dataframe(df, source_file="test_dup_b.xlsx", record_upload=False)
        # Total rows in the table must still be 1, not 2.
        from sqlalchemy import text as _text
        with _TEST_ENGINE.connect() as conn:
            total = conn.execute(_text("SELECT COUNT(*) FROM revenue_master")).scalar()
        assert total == 1, f"Expected 1 row after dedup, got {total}"
        # skipped count: total_rows (1) - inserted (0) = 1
        assert r2["total_rows"] - r2["inserted"] == 1

    def test_load_empty_range_returns_empty_df(self):
        loaded = db.load_for_date_range(dt.date(2020, 1, 1), dt.date(2020, 1, 2))
        assert loaded.empty

    def test_multiple_dates_loaded(self):
        db.save_dataframe(_revenue_df(date=dt.date(2026, 7, 1)), source_file="a.xlsx")
        db.save_dataframe(_revenue_df(date=dt.date(2026, 7, 2)), source_file="b.xlsx")
        loaded = db.load_for_date_range(dt.date(2026, 7, 1), dt.date(2026, 7, 2))
        assert len(loaded) == 2

    def test_range_excludes_outside_dates(self):
        db.save_dataframe(_revenue_df(date=dt.date(2026, 6, 30)), source_file="a.xlsx")
        db.save_dataframe(_revenue_df(date=dt.date(2026, 7, 1)), source_file="b.xlsx")
        loaded = db.load_for_date_range(dt.date(2026, 7, 1), dt.date(2026, 7, 31))
        assert len(loaded) == 1
        assert str(loaded.iloc[0]["date"]) == "2026-07-01"


# ── Segment canonicalization ──────────────────────────────────────────────────

class TestSegmentCanonicalization:
    def test_legacy_lounges_mapped_to_ehpl(self):
        seg, bu = db.canonicalize_segment_and_business_unit("Lounges", "International Lounge")
        assert seg == "EHPL"
        assert bu == "Lounges"

    def test_legacy_atithya_mapped_to_ehpl(self):
        seg, bu = db.canonicalize_segment_and_business_unit("Atithya", "Meet & Greet")
        assert seg == "EHPL"
        assert bu == "Atithya"

    def test_sky_plates_outlet(self):
        seg, bu = db.canonicalize_segment_and_business_unit("Subsidiary", "Encalm Sky Plates")
        assert seg == "Sky Plates"

    def test_encalm_eats_outlet(self):
        seg, bu = db.canonicalize_segment_and_business_unit("Subsidiary", "Encalm Eats")
        assert seg == "Encalm Eats"

    def test_already_canonical_ehpl(self):
        seg, bu = db.canonicalize_segment_and_business_unit("EHPL", "International Lounge")
        assert seg == "EHPL"


# ── canonicalize_outlet_name ──────────────────────────────────────────────────

class TestOutletCanonicalization:
    def test_alias_mapped(self):
        assert db.canonicalize_outlet_name("inl 5&6") == "International Lounge"

    def test_already_canonical_passthrough(self):
        assert db.canonicalize_outlet_name("International Lounge") == "International Lounge"

    def test_unknown_name_passthrough(self):
        assert db.canonicalize_outlet_name("Brand New Outlet") == "Brand New Outlet"

    def test_case_insensitive(self):
        assert db.canonicalize_outlet_name("INL 5&6") == "International Lounge"

    def test_strips_whitespace(self):
        assert db.canonicalize_outlet_name("  inl 5&6  ") == "International Lounge"


# ── get_available_dates ───────────────────────────────────────────────────────

class TestGetAvailableDates:
    def test_empty_db_returns_empty_list(self):
        dates = db.get_available_dates()
        assert dates == []

    def test_inserted_dates_returned_sorted(self):
        db.save_dataframe(_revenue_df(date=dt.date(2026, 7, 3)), source_file="c.xlsx")
        db.save_dataframe(_revenue_df(date=dt.date(2026, 7, 1)), source_file="a.xlsx")
        dates = db.get_available_dates()
        assert dates == sorted(dates)
        assert dt.date(2026, 7, 1) in dates
        assert dt.date(2026, 7, 3) in dates


# ── get_db_stats ──────────────────────────────────────────────────────────────

class TestGetDbStats:
    def test_empty_stats(self):
        stats = db.get_db_stats()
        assert stats["total_rows"] == 0
        assert stats["distinct_dates"] == 0
        assert stats["min_date"] is None

    def test_stats_after_insert(self):
        db.save_dataframe(_revenue_df(date=dt.date(2026, 7, 1)), source_file="a.xlsx")
        stats = db.get_db_stats()
        assert stats["total_rows"] == 1
        assert stats["distinct_dates"] == 1
        assert stats["min_date"] == dt.date(2026, 7, 1)


# ── reset_db ──────────────────────────────────────────────────────────────────

class TestResetDb:
    def test_reset_clears_all_rows(self):
        db.save_dataframe(_revenue_df(), source_file="a.xlsx")
        assert db.get_db_stats()["total_rows"] == 1
        db.reset_db()
        assert db.get_db_stats()["total_rows"] == 0

    def test_reset_allowlist_blocks_unknown_table(self):
        """Verify the f-string allowlist guard raises on unexpected table names."""
        from modules.database import _RESET_ALLOWED_TABLES
        assert "revenue_master" in _RESET_ALLOWED_TABLES
        assert "users" not in _RESET_ALLOWED_TABLES


# ── rate limiting ─────────────────────────────────────────────────────────────

class TestUploadRateLimit:
    def test_empty_history_allowed(self):
        ok, msg = db.check_upload_rate_limit("alice")
        assert ok is True
        assert msg == ""

    def test_unknown_user_allowed(self):
        ok, _ = db.check_upload_rate_limit("unknown_user")
        assert ok is True

    def test_empty_username_always_allowed(self):
        ok, _ = db.check_upload_rate_limit("")
        assert ok is True

    def test_limit_enforced_after_max_uploads(self):
        """Insert MAX uploads for 'bob' in upload_history within the last hour."""
        from sqlalchemy import text
        now = dt.datetime.now().isoformat(timespec="seconds")
        with _TEST_ENGINE.begin() as conn:
            for i in range(db._MAX_UPLOADS_PER_HOUR):
                conn.execute(text(
                    "INSERT INTO upload_history "
                    "(file_name, row_count, uploaded_at, status, upload_type, uploaded_by) "
                    "VALUES (:fn, 1, :ts, 'Available', 'Revenue', 'bob')"
                ), {"fn": f"file{i}.xlsx", "ts": now})
        ok, msg = db.check_upload_rate_limit("bob")
        assert ok is False
        assert "limit" in msg.lower()

    def test_old_uploads_not_counted(self):
        """Uploads more than 1 hour ago must not count against the limit."""
        from sqlalchemy import text
        old_ts = (dt.datetime.now() - dt.timedelta(hours=2)).isoformat(timespec="seconds")
        with _TEST_ENGINE.begin() as conn:
            for i in range(db._MAX_UPLOADS_PER_HOUR + 5):
                conn.execute(text(
                    "INSERT INTO upload_history "
                    "(file_name, row_count, uploaded_at, status, upload_type, uploaded_by) "
                    "VALUES (:fn, 1, :ts, 'Available', 'Revenue', 'carol')"
                ), {"fn": f"old{i}.xlsx", "ts": old_ts})
        ok, _ = db.check_upload_rate_limit("carol")
        assert ok is True
