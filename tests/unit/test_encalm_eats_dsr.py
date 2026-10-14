"""
tests/unit/test_encalm_eats_dsr.py
====================================
Tests for the Encalm Eats Master DSR parser and database integration.
Uses the synthetic minimal workbook to avoid depending on a real file
being present in the test environment.
"""
from __future__ import annotations

import datetime as dt
import io
from unittest.mock import patch

import openpyxl
import pytest

from modules.encalm_eats_dsr_parser import (
    DSRRecord,
    _canonicalize,
    _is_section_total,
    _location_for_outlet,
    parse_dsr,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal in-memory DSR workbooks
# ---------------------------------------------------------------------------

def _make_dsr_workbook(sheets: list[dict]) -> io.BytesIO:
    """
    Build an in-memory Excel workbook mimicking the DSR structure.
    `sheets` is a list of dicts:
        {
            "name":    "01-07-2026",
            "date":    datetime(2026, 7, 1),
            "location": "Encalm Eats (Delhi)",
            "total_covers": 500,
            "total_rev": 100000,
            "outlets": [
                {"name": "IndiSip T2 - Bus Gate", "covers": 300, "rev": 60000},
                {"name": "IndiSip T2 - Pre Checkin", "covers": 200, "rev": 40000},
            ],
        }
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for s in sheets:
        ws = wb.create_sheet(title=s["name"])
        ws["B1"] = "Master DSR"
        ws["B2"] = "Location :"
        ws["C2"] = s.get("location", "Encalm Eats (Delhi)")
        ws["B3"] = "Date : "
        ws["C3"] = s.get("date", dt.datetime(2026, 7, 1))
        ws["B4"] = "Unit"
        ws["C4"] = "Total Cover\n"
        ws["D4"] = "Net Total Amount \n(Without Tax)"
        ws["B5"] = "Encalm Eats"
        ws["C5"] = s.get("total_covers", 0)
        ws["D5"] = s.get("total_rev", 0)
        ws["B7"] = "Outlet Wise Detail"
        for i, o in enumerate(s.get("outlets", []), start=8):
            ws[f"B{i}"] = o["name"]
            ws[f"C{i}"] = o.get("covers")
            ws[f"D{i}"] = o.get("rev")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Unit tests — pure functions
# ---------------------------------------------------------------------------

class TestCanonicalise:
    def test_indisip_bus_gate(self):
        assert _canonicalize("Indisip T2 - Bus Gate") == "IndiSip T2 - Bus Gate"

    def test_indisip_pre_checkin(self):
        assert _canonicalize("Indisip T2 - Pre Checkin") == "IndiSip T2 - Pre Checkin"

    def test_events_odc(self):
        assert _canonicalize("Events/ODC") == "Event/ODC"

    def test_already_canonical(self):
        assert _canonicalize("Chaayos T3") == "Chaayos T3"

    def test_strips_whitespace(self):
        assert _canonicalize("  ALD  ") == "ALD"

    def test_unknown_name_passthrough(self):
        assert _canonicalize("Some New Outlet") == "Some New Outlet"


class TestIsSectionTotal:
    @pytest.mark.parametrize("name", [
        "Encalm Eats", "encalm eats", "ENCALM EATS",
        "Delhi Store's", "Bhogapuram", "Cafeteria Bhogapuram",
        "Outlet Wise Detail",
    ])
    def test_known_totals(self, name):
        assert _is_section_total(name) is True

    @pytest.mark.parametrize("name", [
        "IndiSip T2 - Bus Gate", "Chaayos T3", "ALD",
        "Cafeteria Admin Block - Ala Carte",
    ])
    def test_known_outlets_not_totals(self, name):
        assert _is_section_total(name) is False


class TestLocationForOutlet:
    def test_bhogapuram_outlet_always_bhogapuram(self):
        assert _location_for_outlet("Cafeteria Admin Block - Ala Carte", "Delhi") == "Bhogapuram"
        assert _location_for_outlet("Cafeteria Admin Block - Sales", "Delhi") == "Bhogapuram"

    def test_delhi_outlet_follows_section(self):
        assert _location_for_outlet("Chaayos T3", "Delhi") == "Delhi"

    def test_outlet_inherits_current_section(self):
        assert _location_for_outlet("IndiSip T2 - Bus Gate", "Bhogapuram") == "Bhogapuram"


# ---------------------------------------------------------------------------
# Integration tests — parse_dsr with synthetic workbooks
# ---------------------------------------------------------------------------

class TestParseDSR:
    def test_successful_parse_single_sheet(self):
        buf = _make_dsr_workbook([{
            "name": "01-07-2026",
            "date": dt.datetime(2026, 7, 1),
            "total_covers": 500, "total_rev": 100000,
            "outlets": [
                {"name": "IndiSip T2 - Bus Gate", "covers": 300, "rev": 60000},
                {"name": "IndiSip T2 - Pre Checkin", "covers": 200, "rev": 40000},
            ],
        }])
        result = parse_dsr(buf, "test.xlsx")
        assert result.success is True
        assert result.rows_extracted == 2
        assert result.sheets_parsed == 1

    def test_correct_date_detection(self):
        buf = _make_dsr_workbook([{
            "name": "15-07-2026",
            "date": dt.datetime(2026, 7, 15),
            "total_covers": 100, "total_rev": 50000,
            "outlets": [{"name": "Chaayos T3", "covers": 100, "rev": 50000}],
        }])
        result = parse_dsr(buf, "test.xlsx")
        assert result.records[0].date == dt.date(2026, 7, 15)

    def test_date_from_sheet_name_fallback(self):
        """If the cell date is missing, date should come from sheet name."""
        buf = _make_dsr_workbook([{
            "name": "10-07-2026",
            "date": None,
            "total_covers": 50, "total_rev": 10000,
            "outlets": [{"name": "ALD", "covers": 50, "rev": 10000}],
        }])
        result = parse_dsr(buf, "test.xlsx")
        assert result.success is True
        assert result.records[0].date == dt.date(2026, 7, 10)

    def test_canonical_outlet_names(self):
        buf = _make_dsr_workbook([{
            "name": "01-07-2026",
            "date": dt.datetime(2026, 7, 1),
            "total_covers": 300, "total_rev": 80000,
            "outlets": [
                {"name": "Indisip T2 - Bus Gate", "covers": 200, "rev": 60000},
                {"name": "Events/ODC", "covers": 100, "rev": 20000},
            ],
        }])
        result = parse_dsr(buf, "test.xlsx")
        names = {r.outlet for r in result.records}
        assert "IndiSip T2 - Bus Gate" in names
        assert "Event/ODC" in names
        assert "Indisip T2 - Bus Gate" not in names
        assert "Events/ODC" not in names

    def test_section_totals_excluded(self):
        """Encalm Eats / Delhi Stores / Bhogapuram rows must not produce records."""
        buf = _make_dsr_workbook([{
            "name": "01-07-2026",
            "date": dt.datetime(2026, 7, 1),
            "total_covers": 300, "total_rev": 80000,
            "outlets": [
                {"name": "Encalm Eats", "covers": 300, "rev": 80000},   # grand total
                {"name": "IndiSip T2 - Bus Gate", "covers": 300, "rev": 80000},
            ],
        }])
        result = parse_dsr(buf, "test.xlsx")
        outlets = [r.outlet for r in result.records]
        assert "Encalm Eats" not in outlets
        assert "IndiSip T2 - Bus Gate" in outlets
        assert len(result.records) == 1

    def test_bhogapuram_outlet_location(self):
        buf = _make_dsr_workbook([{
            "name": "01-07-2026",
            "date": dt.datetime(2026, 7, 1),
            "total_covers": 200, "total_rev": 50000,
            "outlets": [
                {"name": "Cafeteria Admin Block - Ala Carte", "covers": 100, "rev": 25000},
                {"name": "Cafeteria Admin Block - Sales", "covers": 100, "rev": 25000},
            ],
        }])
        result = parse_dsr(buf, "test.xlsx")
        for r in result.records:
            assert r.location == "Bhogapuram"

    def test_multiple_sheets(self):
        sheets = [
            {"name": f"0{d}-07-2026", "date": dt.datetime(2026, 7, d),
             "total_covers": 100, "total_rev": 20000,
             "outlets": [{"name": "Chaayos T3", "covers": 100, "rev": 20000}]}
            for d in range(1, 6)
        ]
        buf = _make_dsr_workbook(sheets)
        result = parse_dsr(buf, "test.xlsx")
        assert result.sheets_parsed == 5
        assert result.rows_extracted == 5
        assert result.parsed_total_revenue == 100000.0

    def test_blank_rows_ignored(self):
        buf = _make_dsr_workbook([{
            "name": "01-07-2026",
            "date": dt.datetime(2026, 7, 1),
            "total_covers": 100, "total_rev": 30000,
            "outlets": [
                {"name": "Chaayos T3", "covers": 100, "rev": 30000},
                {"name": "", "covers": None, "rev": None},   # blank row
            ],
        }])
        result = parse_dsr(buf, "test.xlsx")
        assert result.rows_extracted == 1

    def test_zero_revenue_zero_covers_excluded(self):
        buf = _make_dsr_workbook([{
            "name": "01-07-2026",
            "date": dt.datetime(2026, 7, 1),
            "total_covers": 100, "total_rev": 30000,
            "outlets": [
                {"name": "Chaayos T3", "covers": 100, "rev": 30000},
                {"name": "ALD", "covers": 0, "rev": 0},  # zero = closed that day
            ],
        }])
        result = parse_dsr(buf, "test.xlsx")
        assert result.rows_extracted == 1

    def test_non_date_sheets_skipped(self):
        buf = _make_dsr_workbook([
            {"name": "01-07-2026", "date": dt.datetime(2026, 7, 1),
             "total_covers": 100, "total_rev": 20000,
             "outlets": [{"name": "Chaayos T3", "covers": 100, "rev": 20000}]},
        ])
        # Add a non-date sheet manually
        import openpyxl
        buf.seek(0)
        wb2 = openpyxl.load_workbook(buf)
        wb2.create_sheet("Summary")
        buf2 = io.BytesIO()
        wb2.save(buf2)
        buf2.seek(0)
        result = parse_dsr(buf2, "test.xlsx")
        assert result.sheets_skipped >= 1
        assert result.sheets_parsed == 1

    def test_revenue_totals_match_source(self):
        """parsed_total_revenue = sum of individual outlet net_revenues."""
        buf = _make_dsr_workbook([{
            "name": "01-07-2026",
            "date": dt.datetime(2026, 7, 1),
            "total_covers": 500, "total_rev": 100000,
            "outlets": [
                {"name": "IndiSip T2 - Bus Gate", "covers": 300, "rev": 60000},
                {"name": "IndiSip T2 - Pre Checkin", "covers": 200, "rev": 40000},
            ],
        }])
        result = parse_dsr(buf, "test.xlsx")
        assert result.parsed_total_revenue == 100000.0
        assert result.parsed_total_covers == 500.0

    def test_segment_is_encalm_eats(self):
        buf = _make_dsr_workbook([{
            "name": "01-07-2026",
            "date": dt.datetime(2026, 7, 1),
            "total_covers": 100, "total_rev": 20000,
            "outlets": [{"name": "Chaayos T3", "covers": 100, "rev": 20000}],
        }])
        result = parse_dsr(buf, "test.xlsx")
        assert all(r.segment == "Encalm Eats" for r in result.records)


# ---------------------------------------------------------------------------
# Database integration tests (use in-memory SQLite)
# ---------------------------------------------------------------------------

class TestDatabaseIntegration:
    @pytest.fixture(autouse=True)
    def _patch_engine(self, tmp_path):
        """Redirect DB to a temporary SQLite file for isolation."""
        import sqlalchemy
        from modules import database as db_mod

        test_db = f"sqlite:///{tmp_path}/test_eats.db"
        test_engine = sqlalchemy.create_engine(test_db, connect_args={"check_same_thread": False})
        db_mod.Base.metadata.create_all(test_engine)
        from sqlalchemy.orm import sessionmaker as sm
        TestSession = sm(bind=test_engine)

        with patch.object(db_mod, "ENGINE", test_engine), \
             patch.object(db_mod, "SessionLocal", TestSession):
            yield

    def _sample_records(self):
        return [
            DSRRecord(
                date=dt.date(2026, 7, 1),
                outlet="Chaayos T3",
                location="Delhi",
                covers=100.0,
                net_revenue=20000.0,
                source_file="test.xlsx",
                source_sheet="01-07-2026",
            ),
            DSRRecord(
                date=dt.date(2026, 7, 1),
                outlet="ALD",
                location="Delhi",
                covers=50.0,
                net_revenue=10000.0,
                source_file="test.xlsx",
                source_sheet="01-07-2026",
            ),
        ]

    def test_insert_records(self):
        from modules.database import save_encalm_eats_dsr
        result = save_encalm_eats_dsr(self._sample_records(), "test.xlsx")
        assert result["inserted"] == 2
        assert result["skipped"] == 0

    def test_duplicate_upload_skipped(self):
        from modules.database import save_encalm_eats_dsr
        save_encalm_eats_dsr(self._sample_records(), "test.xlsx")
        result2 = save_encalm_eats_dsr(self._sample_records(), "test.xlsx")
        assert result2["inserted"] == 0
        assert result2["skipped"] == 2

    def test_different_filename_same_data_skipped(self):
        """Duplicate detection is based on (date, outlet, location), not filename."""
        from modules.database import save_encalm_eats_dsr
        save_encalm_eats_dsr(self._sample_records(), "original.xlsx")
        result2 = save_encalm_eats_dsr(self._sample_records(), "renamed_copy.xlsx")
        assert result2["inserted"] == 0
        assert result2["skipped"] == 2

    def test_load_for_range(self):
        from modules.database import save_encalm_eats_dsr, load_encalm_eats_dsr_for_range
        save_encalm_eats_dsr(self._sample_records(), "test.xlsx")
        df = load_encalm_eats_dsr_for_range(dt.date(2026, 7, 1), dt.date(2026, 7, 31))
        assert len(df) == 2
        assert set(df["outlet"]) == {"Chaayos T3", "ALD"}

    def test_get_dates(self):
        from modules.database import save_encalm_eats_dsr, get_encalm_eats_dsr_dates
        save_encalm_eats_dsr(self._sample_records(), "test.xlsx")
        dates = get_encalm_eats_dsr_dates()
        assert dt.date(2026, 7, 1) in dates
