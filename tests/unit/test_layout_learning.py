"""layout_learning: propose a column mapping for an unknown layout, apply a
confirmed mapping, and recognise a saved layout again."""

import datetime as dt
import io

import openpyxl
import pandas as pd
import pytest

from modules import layout_learning as ll


def _xlsx(rows, title="Sheet1"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _table(data, name="f.xlsx", sheet=None):
    grid = ll.read_grid(data, name, sheet)
    hr = ll.guess_header_row(grid)
    headers, rows = ll.table_at(grid, hr)
    return hr, headers, rows


OPS = _xlsx([["Daily ops report"], [],
             ["Txn Dt", "Airport", "Unit", "Guests", "Sales (INR)", "Remarks"]]
            + [[dt.date(2026, 8, d), "GOX", o, 100 + d, 50000 + d, "ok"]
               for d, o in ((1, "Domestic Lounge"), (2, "Porter"), (3, "Baggage Wrapping"))])


def test_proposal_for_renamed_headers():
    hr, headers, rows = _table(OPS)
    assert hr == 2
    m = ll.propose(headers, rows, "revenue").set_index("Column")["Role"]
    assert (m["Txn Dt"], m["Airport"], m["Unit"], m["Guests"], m["Sales (INR)"]) == \
        (ll.R_DATE, ll.R_LOCATION, ll.R_OUTLET, ll.R_PAX, ll.R_REVENUE)
    assert m["Remarks"] == ll.IGNORE


def test_apply_revenue_mapping_builds_standard_rows():
    hr, headers, rows = _table(OPS)
    out = ll.apply(headers, rows, ll.propose(headers, rows, "revenue"), "revenue", header_row=hr)
    assert list(out["location"].unique()) == ["Goa"]
    assert out["revenue"].sum() == 150006 and out["pax"].sum() == 306
    assert out["_excel_row"].tolist() == [4, 5, 6]          # Excel rows, for the report


def test_dates_across_columns_are_melted():
    data = _xlsx([["Outlet", "Location"] + [dt.date(2026, 8, i) for i in range(1, 5)],
                  ["Domestic Lounge", "Hyderabad", 100, 200, 300, 400]])
    hr, headers, rows = _table(data)
    m = ll.propose(headers, rows, "revenue")
    assert (m["Role"] == ll.R_REV_BY_DATE).sum() == 4
    out = ll.apply(headers, rows, m, "revenue", header_row=hr)
    assert len(out) == 4 and out["revenue"].sum() == 1000
    assert sorted(out["date"]) == [dt.date(2026, 8, i) for i in range(1, 5)]


def test_missing_location_needs_a_column_or_a_value():
    hr, headers, rows = _table(OPS)
    m = ll.propose(headers, rows, "revenue")
    m.loc[m["Column"] == "Airport", "Role"] = ll.IGNORE
    with pytest.raises(ll.LayoutError, match="Location"):
        ll.apply(headers, rows, m, "revenue", header_row=hr)
    out = ll.apply(headers, rows, m, "revenue", constants={"location": "Goa"}, header_row=hr)
    assert set(out["location"]) == {"Goa"}


def test_traffic_columns_with_terminal_labels_are_added():
    data = _xlsx([["Date", "Dom Arr", "Dom Dep", "Intl Arr", "Intl Dep"]]
                 + [[dt.date(2026, 8, d), 100, 110, 10, 11] for d in (1, 2)])
    hr, headers, rows = _table(data)
    m = ll.propose(headers, rows, "traffic")
    assert list(m["Terminal"][1:]) == ["Domestic", "Domestic", "International", "International"]
    out = ll.apply(headers, rows, m, "traffic", constants={"location": "Goa"}, header_row=hr)
    t = out.groupby("terminal")["traffic"].sum().to_dict()
    assert t == {"Domestic": 420, "International": 42}
    assert set(out["granularity"]) == {"daily"}


def test_saved_layout_matches_same_headers_and_tolerates_dates():
    _, headers, _ = _table(OPS)
    fp = ll.fingerprint(headers)
    assert ll.match_score(fp, fp) == 1.0
    assert ll.match_score(fp, ll.fingerprint(headers[:-1] + ["Notes"])) == pytest.approx(5 / 6)
    wide = ["Outlet", "Location", "2026-08-01", "2026-08-02"]
    assert ll.fingerprint(wide) == ["outlet", "location"]


def test_saved_mapping_round_trip_and_find_template():
    hr, headers, rows = _table(OPS)
    m = ll.propose(headers, rows, "revenue")
    saved = ll.mapping_to_saved(m)
    t = {"id": 1, "name": "Goa ops", "fingerprint": ll.fingerprint(headers), "mapping": saved,
         "header_row": hr, "constants": {}}
    hit = ll.find_template(OPS, "f.xlsx", [t])
    assert hit and hit["score"] == 1.0
    again = ll.mapping_for_headers(saved, hit["headers"], "revenue")
    assert list(again["Role"]) == list(m["Role"])
    assert ll.find_template(_xlsx([["a", "b"], [1, 2]]), "g.xlsx", [t]) is None
