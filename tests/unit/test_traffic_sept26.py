"""Traffic workbook in the Sep-2026 layout: Delhi day grid with the month as a
date in A1, Hyderabad / Vizag side-by-side Domestic | International, and a
warning for sheets that give no rows."""

import datetime as dt
import io

import openpyxl
import pytest

from modules import terminal_mapping as tm
from modules import traffic_parser as tp

DAYS = 3


def _workbook(extra_sheet: str | None = None) -> io.BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Delhi"
    ws.append([dt.datetime(2026, 9, 1)])                       # month as a real date
    ws.append(["Day", "T3 International", None, "T3 Domestic", None,
               "T2 Domestic", None, "Terminal 1", None, "G.Total"])
    ws.append([None, "Dep.", "Arr.", "Dep.", "Arr.", "Dep.", "Arr.", "Dep.", "Arr.", None])
    for d in range(1, DAYS + 1):
        ws.append([d, 100, 90, 80, 70, 60, 50, 40, 30, "  520"])
    ws.append(["Total", "300", "270", "240", "210", "180", "150", "120", "90", "1,560"])

    for name in ("Hyd", "Vizag"):
        s = wb.create_sheet(name)
        s.append(["DOMESTIC PAX (Schedule)", None, None, "International PAX (Schedule)", None, None])
        s.append([None, "ARRIVAL", "DEPARTURE", "TOTAL", "ARRIVAL", "DEPARTURE", "TOTAL"])
        for d in range(1, DAYS + 1):
            s.append([dt.datetime(2026, 9, d), 10, 20, 30, 1, 2, 3])
        s.append(["Total", 30, 60, 90, 3, 6, 9])

    if extra_sheet:
        s = wb.create_sheet(extra_sheet)
        s.append(["Something", "else"])
        s.append(["not", "traffic"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _totals(df):
    return df.groupby(["location", "terminal"])["traffic"].sum().to_dict()


def test_delhi_day_grid_uses_date_in_a1_as_month():
    df = tp.parse_traffic_auto(_workbook(), "sept.xlsx")
    delhi = df[df["location"] == "Delhi"]
    assert len(delhi) == 8 * DAYS
    assert {d.month for d in delhi["date"]} == {9} and {d.year for d in delhi["date"]} == {2026}
    t = _totals(delhi)
    assert t[("Delhi", "T3 Int Dep")] == 300 and t[("Delhi", "T1 Arr")] == 90


def test_vizag_sheet_is_bhogapuram_and_hyd_stays_hyderabad():
    df = tp.parse_traffic_auto(_workbook(), "sept.xlsx")
    t = _totals(df)
    for loc in ("Hyderabad", "Bhogapuram"):
        assert t[(loc, "Domestic")] == 30 * DAYS        # arrival + departure, not TOTAL
        assert t[(loc, "International")] == 3 * DAYS
    assert len(df) == 8 * DAYS + 2 * 2 * DAYS
    assert df.attrs["skipped_sheets"] == []


def test_unrecognised_sheet_is_reported():
    df = tp.parse_traffic_auto(_workbook(extra_sheet="Notes"), "sept.xlsx")
    assert any("'Notes'" in m for m in df.attrs["skipped_sheets"])


def test_airport_sheet_with_no_rows_is_reported():
    buf = _workbook()
    wb = openpyxl.load_workbook(buf)
    wb.create_sheet("Goa").append(["just a title"])
    out = io.BytesIO(); wb.save(out); out.seek(0)
    df = tp.parse_traffic_auto(out, "sept.xlsx")
    assert any("'Goa' (Goa)" in m for m in df.attrs["skipped_sheets"])


@pytest.mark.parametrize("outlet,terminal", [
    ("Domestic Lounge T3", "Domestic"),
    ("International Lounge", "International"),
    ("Reserved Lounge", "International"),
    ("Atithya", "All"),
    ("Porter", "All"),
    ("Baggage Wrapping", "All"),
    ("Domestic Spa - T3", tm.MAIN_TERMINAL),     # not listed → whole airport
])
def test_bhogapuram_terminal_mapping(outlet, terminal):
    assert tm.get_terminal_for_outlet(outlet, "Bhogapuram") == terminal


def test_may26_hyd_layout_heading_above_departure_column():
    """'Domestic' / 'International' sit right above the Departure columns
    (Departure before Arrival). The International heading must not make
    its Departure column count as Domestic."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "HYD Traffic May-26"
    ws.append([None, "Domestic", None, "International", None])
    ws.append(["Date", "Departure", "Arrival", "Departure", "Arrival"])
    for d in range(1, DAYS + 1):
        ws.append([dt.datetime(2026, 5, d), 100, 200, 10, 20])
    ws.append(["Total", 300, 600, 30, 60])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    t = _totals(tp.parse_traffic_auto(buf, "may.xlsx"))
    assert t[("Hyderabad", "Domestic")] == 300 * DAYS
    assert t[("Hyderabad", "International")] == 30 * DAYS
