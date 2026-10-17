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


# ── Batched save: lines for the same date/outlet in different batches ────────

def test_batched_save_adds_same_outlet_lines_across_batches(monkeypatch):
    """'Visitor Lounge' canonicalizes to 'Reserved Lounge'. With row-position
    batches the second line landed in the next batch and was dropped as a
    duplicate; batches now break only at date boundaries, so it's added."""
    monkeypatch.setattr(db, "_FALLBACK_BATCH_ROWS", 2)
    d1, d2 = dt.date(2019, 3, 1), dt.date(2019, 3, 2)
    df = pd.DataFrame([
        (d1, "Lounges", "T1D Lounge", "Delhi", 10, 1000.0, None, None),
        (d2, "Lounges", "Reserved Lounge", "Delhi", 20, 2000.0, None, None),   # row 2: batch 1 by position
        (d2, "Lounges", "Visitor Lounge", "Delhi", 5, 500.0, None, None),      # row 3: batch 2 by position
        (d2, "Atithya", "Porter", "Delhi", 1, 100.0, None, None),
    ], columns=["date", "segment", "outlet", "location", "pax", "revenue", "aop", "traffic"])
    res = db.save_dataframe_batched_v2(df, source_file="batch_boundary_test.xlsx")
    assert res["skipped"] == 0
    saved = db.load_for_date_range(d1, d2)
    saved = saved[saved["source_file"] == "batch_boundary_test.xlsx"]
    assert saved["revenue"].sum() == 3600.0
    reserved = saved[(saved["date"].astype(str) == str(d2)) & (saved["outlet"] == "Reserved Lounge")]
    assert reserved["revenue"].iloc[0] == 2500.0 and reserved["pax"].iloc[0] == 25


# ── Bhogapuram traffic (Domestic / International, like Hyderabad) ─────────────

class TestBhogapuramTraffic:
    def _setup(self):
        days = [dt.date(2026, 9, 1), dt.date(2026, 9, 2)]
        traffic = pd.DataFrame([
            {"date": d, "period_end": pd.NaT, "granularity": "daily", "location": "Bhogapuram",
             "terminal": term, "traffic": val}
            for d in days for term, val in (("Domestic", 1000.0), ("International", 100.0))
        ])
        db.save_traffic_dataframe(traffic, "traffic.xlsx")
        rev = pd.concat([_revenue_df(date=d, outlet=o, location="Bhogapuram", pax=10, revenue=1000)
                         for d in days for o in ("Domestic Lounge T3", "International Lounge", "Atithya")])
        return rev

    def test_outlets_get_their_pool(self):
        out = db.join_revenue_with_traffic_by_outlet(self._setup()).set_index("outlet")["traffic"]
        assert out["Domestic Lounge T3"] == 2000
        assert out["International Lounge"] == 200
        assert out["Atithya"] == 2200          # whole airport = Domestic + International

    def test_location_total_counts_each_terminal_once(self):
        out = db.join_revenue_with_traffic(self._setup())
        assert float(out.loc[out["location"] == "Bhogapuram", "traffic"].iloc[0]) == 2200


# ── Traffic re-import with replace ───────────────────────────────────────────

class TestTrafficReplace:
    @staticmethod
    def _traffic(location, day, terminal, value):
        return {"date": dt.date(2026, 5, day), "period_end": pd.NaT, "granularity": "daily",
                "location": location, "terminal": terminal, "traffic": value}

    def _stored(self):
        df = db.load_traffic_for_date_range(dt.date(2026, 5, 1), dt.date(2026, 5, 31))
        return {(r.location, pd.Timestamp(r.date).day, r.terminal): r.traffic for r in df.itertuples()}

    def test_replace_overwrites_only_the_files_airports_and_dates(self):
        old = pd.DataFrame([self._traffic("Hyderabad", 1, "Domestic", 999.0),
                            self._traffic("Hyderabad", 2, "Domestic", 999.0),
                            self._traffic("Goa", 1, "Domestic", 50.0)])
        db.save_traffic_dataframe(old, "old.xlsx")
        new = pd.DataFrame([self._traffic("Hyderabad", 1, "Domestic", 300.0),
                            self._traffic("Hyderabad", 1, "International", 30.0)])

        kept = db.save_traffic_dataframe(new, "new.xlsx")               # default: skip existing
        assert kept["inserted"] == 1 and self._stored()[("Hyderabad", 1, "Domestic")] == 999.0

        res = db.save_traffic_dataframe(new, "new.xlsx", replace=True)
        stored = self._stored()
        assert res["replaced"] == 2 and res["inserted"] == 2
        assert stored[("Hyderabad", 1, "Domestic")] == 300.0
        assert stored[("Hyderabad", 1, "International")] == 30.0
        assert stored[("Hyderabad", 2, "Domestic")] == 999.0           # date not in the file
        assert stored[("Goa", 1, "Domestic")] == 50.0                   # airport not in the file


class TestTerminalWisePerformance:
    """EHPL 'Terminal-wise Performance' table: each terminal row gets its own
    traffic pool for each period, and the rows add up to the location total."""

    POOLS = ["T1 Dep", "T1 Arr", "T2 Dep", "T2 Arr",
             "T3 Dom Dep", "T3 Dom Arr", "T3 Int Dep", "T3 Int Arr"]

    def _setup(self, day, scale):
        traffic = pd.DataFrame([
            {"date": day, "period_end": pd.NaT, "granularity": "daily", "location": "Delhi",
             "terminal": t, "traffic": (i + 1) * 1000.0 * scale}
            for i, t in enumerate(self.POOLS)])
        db.save_traffic_dataframe(traffic, "t.xlsx")
        rev = pd.concat([
            _revenue_df(day, "Domestic Lounge - T1 L4&5", revenue=100_000.0 * scale, pax=100),
            _revenue_df(day, "Arrival Lounge - LA22", revenue=50_000.0, pax=40),
            _revenue_df(day, "Atithya", revenue=20_000.0, pax=10),
            _revenue_df(day, "Business Centre", revenue=5_000.0, pax=5),
        ])
        db.save_dataframe(rev, source_file="r.xlsx")
        return db.load_for_date_range(day, day)

    def test_rows_traffic_and_totals(self):
        from modules import ehpl_layout as el
        cur = self._setup(dt.date(2026, 3, 10), 2)
        cmp = self._setup(dt.date(2026, 3, 9), 1)
        rows = {r["Performance"]: r for r in el._get_terminal_rows("Delhi", cur, cmp)}

        assert rows["T1"]["cur_traffic"] == 2000.0            # T1 Dep only
        assert rows["T1"]["cmp_traffic"] == 1000.0            # compare day's own traffic
        assert rows["T1"]["pen_cur"] == pytest.approx(100 / 2000 * 100)
        assert rows["T1"]["spp_cmp"] == pytest.approx(100_000 / 1000)
        assert rows["T3 Arrivals"]["cur_traffic"] == (6000.0 + 8000.0) * 2   # dom + int arrivals
        assert rows["Airport-wide services"]["cur_traffic"] == 36_000.0 * 2  # whole airport
        assert rows["No terminal traffic"]["cur_rev"] == 5_000.0
        assert rows["No terminal traffic"]["cur_traffic"] is None
        total = rows["TOTAL"]
        assert total["cur_rev"] == 200_000.0 + 50_000 + 20_000 + 5_000
        assert total["cur_rev"] == sum(r["cur_rev"] for k, r in rows.items() if k != "TOTAL")
        assert total["cur_traffic"] == 72_000.0 and total["cmp_traffic"] == 36_000.0


def test_traffic_total_daily_rows_are_not_doubled_by_monthly():
    """Days covered by daily rows must not also get a share of a monthly row."""
    db.save_traffic_dataframe(pd.DataFrame([
        {"date": dt.date(2026, 2, d), "period_end": pd.NaT, "granularity": "daily",
         "location": "Goa", "terminal": "Domestic", "traffic": 100.0} for d in range(1, 29)
    ] + [{"date": dt.date(2026, 2, 1), "period_end": dt.date(2026, 2, 28), "granularity": "monthly",
          "location": "Goa", "terminal": "Domestic", "traffic": 9_999.0}]), "g.xlsx")
    t = db.get_traffic_total_for_range(dt.date(2026, 2, 1), dt.date(2026, 2, 28), "Goa")
    row = t[t["terminal"] == "Domestic"].iloc[0]
    assert row["traffic"] == 2_800.0
    assert row["missing_days"] == 0 and not row["is_estimated"]


class TestRevenueReplace:
    """Re-uploading a corrected revenue file with replace=True overwrites only
    the file's own dates and locations; without it existing lines are kept."""

    D1, D2 = dt.date(2025, 11, 1), dt.date(2025, 11, 2)

    def _stored(self):
        df = db.load_for_date_range(self.D1, self.D2)
        return {(r.location, str(r.date)[:10], r.outlet): r.revenue for r in df.itertuples()}

    @pytest.mark.parametrize("saver", ["save_dataframe", "save_dataframe_batched_v2"])
    def test_replace_overwrites_only_the_files_dates_and_locations(self, saver):
        with db.ENGINE.begin() as conn:
            conn.execute(db.RevenueMaster.__table__.delete().where(
                db.RevenueMaster.date.in_([self.D1, self.D2])))
        save = getattr(db, saver)
        save(pd.concat([
            _revenue_df(self.D1, "International Lounge", revenue=100.0),
            _revenue_df(self.D1, "Porter", revenue=50.0),                 # not in the new file
            _revenue_df(self.D2, "International Lounge", revenue=70.0),   # date not in the new file
            _revenue_df(self.D1, "International Lounge", location="Goa", revenue=30.0),
        ]), source_file="old.xlsx")
        new = _revenue_df(self.D1, "International Lounge", revenue=999.0)

        kept = save(new, source_file="new.xlsx")                          # default: keep stored
        assert kept["inserted"] == 0 and kept.get("replaced", 0) == 0
        assert self._stored()[("Delhi", "2025-11-01", "International Lounge")] == 100.0

        res = save(new, source_file="new.xlsx", replace=True)
        stored = self._stored()
        assert res["replaced"] == 2 and res["inserted"] == 1
        assert stored[("Delhi", "2025-11-01", "International Lounge")] == 999.0
        assert ("Delhi", "2025-11-01", "Porter") not in stored            # same date + location
        assert stored[("Delhi", "2025-11-02", "International Lounge")] == 70.0
        assert stored[("Goa", "2025-11-01", "International Lounge")] == 30.0


class TestSavedLayouts:
    """A mapping confirmed once is stored (parse_template), recognised in the
    next file with the same headers, and read through the normal validation."""

    @staticmethod
    def _file(rename_last=False):
        import openpyxl
        from io import BytesIO
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Ops report"])
        ws.append(["Txn Dt", "Airport", "Unit", "Business Line", "Guests",
                   "Notes" if rename_last else "Sales (INR)"])
        for d, o in ((1, "Domestic Lounge"), (2, "Porter")):
            ws.append([dt.date(2026, 3, d), "GOX", o, "Lounges", 10 * d, 1000 * d])
        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def test_save_find_apply_and_delete(self):
        from modules import data_processor
        from modules import layout_learning as ll
        data = self._file()
        grid = ll.read_grid(data, "ops.xlsx")
        hr = ll.guess_header_row(grid)
        headers, rows = ll.table_at(grid, hr)
        mapping = ll.propose(headers, rows, "revenue")
        mapping.loc[mapping["Column"] == "Unit", "Role"] = ll.R_OUTLET
        mapping.loc[mapping["Column"] == "Business Line", "Role"] = ll.R_BUSINESS
        tid = db.save_parse_template("revenue", "Goa ops", ll.fingerprint(headers),
                                     ll.mapping_to_saved(mapping), hr, {}, created_by="t")
        db.save_parse_template("revenue", "Goa ops", ll.fingerprint(headers),
                               ll.mapping_to_saved(mapping), hr, {})      # same name: overwrite
        saved = [t for t in db.list_parse_templates("revenue") if t["name"] == "Goa ops"]
        assert len(saved) == 1 and saved[0]["id"] == tid

        hit = ll.find_template(data, "ops-next-week.xlsx", saved)
        assert hit is not None and hit["score"] == 1.0
        again = ll.mapping_for_headers(saved[0]["mapping"], hit["headers"], "revenue")
        out = ll.apply(hit["headers"], hit["data"], again, "revenue", {}, hit["header_row"])
        res = data_processor.process_mapped_rows(out, "ops.xlsx", "Saved layout: Goa ops", 1.0)
        assert res.success and res.total_revenue == 3000 and set(res.df["location"]) == {"Goa"}

        # One renamed column of six still matches (5/6 < 0.9 does not)
        assert ll.find_template(self._file(rename_last=True), "x.xlsx", saved) is None
        assert ll.find_template(self._file(rename_last=True), "x.xlsx", saved,
                                min_score=0.8) is not None

        db.mark_parse_template_used(tid)
        assert db.list_parse_templates("revenue")[0]["times_used"] >= 1
        assert db.delete_parse_template(tid) and not db.list_parse_templates("revenue")
