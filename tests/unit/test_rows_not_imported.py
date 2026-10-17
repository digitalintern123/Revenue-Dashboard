"""Revenue uploads report every row they leave out, and reject impossible dates."""

import datetime as dt
import io

import openpyxl
import pandas as pd

from modules import data_processor, import_report


def _workbook(rows) -> io.BytesIO:
    """Long-format 'Data' sheet like the real Revenue Dashboard workbook:
    a title row, a blank row, the header on row 3, data from row 4."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Revenue data"])
    ws.append([])
    ws.append(["Date", "Location", "Business", "Sub-Business", "PAX", "Revenue", "AOP", "Month"])
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


GOOD = dt.datetime(2026, 8, 31)


def _process(rows):
    return data_processor.process_uploaded_file(_workbook(rows), "test.xlsx", save_to_db=False)


def test_each_dropped_row_is_reported_with_excel_row_and_reason():
    result = _process([
        (GOOD, "Delhi", "Lounges", "T1D Lounge", 100, 1000, None, None),          # row 4: ok
        ("#VALUE!", "Delhi", "Atithya", "Porter", 10, 500, None, None),           # row 5: Excel error
        (dt.datetime(3601, 4, 17), "Delhi", "Lounges", "Bar", 5, 250, None, None),  # row 6: impossible
        (dt.datetime(1913, 5, 13), "Goa", "Lounges", "INL", 7, 300, None, None),  # row 7: too old
        (GOOD, "Delhi", "Lounges", "T2 Domestic", None, None, None, None),        # row 8: no figures
        (GOOD, "Goa", "Atithya", "Baggage Wrapping", 11, "`", None, None),        # row 9: revenue typo
        (GOOD, None, "Lounges", "Spa", 3, 90, None, None),                         # row 10: no location
        (None, None, None, None, None, None, None, None),                          # row 11: padding
        (GOOD, "Delhi", "Lounges", "T1D Lounge", 100, 1000, None, None),          # row 12: exact repeat
        ("zs", "Delhi", "Atithya", "Porter", 4, 40, None, None),                   # row 13: text date
    ])
    assert result.success
    rep = result.skipped_rows
    by_row = dict(zip(rep["Excel row"], rep["Reason"]))

    assert by_row[5].startswith("Date cell is empty or an Excel error")
    assert by_row[13] == "Date is not a valid date"
    assert by_row[6].startswith("Date outside the accepted range")
    assert by_row[7].startswith("Date outside the accepted range")
    assert by_row[8].startswith("No PAX and no revenue")
    assert by_row[9].startswith("Revenue is not a number")
    assert by_row[10] == "Location is blank"
    assert by_row[12].startswith("Exact duplicate")
    assert 4 not in by_row and 11 not in by_row     # good row and blank padding not listed

    # the typo row is imported with its PAX, everything else listed is not
    assert rep.loc[rep["Excel row"] == 9, "Result"].iloc[0] == "Imported without revenue"
    imported = result.df.sort_values("outlet").reset_index(drop=True)
    assert list(imported["outlet"]) == ["Baggage Wrapping", "T1D Lounge"]
    assert imported["revenue"].sum() == 1000
    assert result.report_date == GOOD.date()
    assert any("not imported" in w for w in result.warnings)


def test_impossible_dates_never_reach_the_parsed_rows():
    result = _process([
        (dt.datetime(2026, 8, 1), "Delhi", "Lounges", "Bar", 1, 10, None, None),
        (dt.datetime(8079, 2, 9), "Delhi", "Lounges", "Bar", 2, 20, None, None),
        (dt.datetime(2006, 3, 5), "Delhi", "Lounges", "Bar", 3, 30, None, None),
    ])
    dates = set(result.df["date"])
    assert dates == {dt.date(2026, 8, 1)}
    lo, hi = import_report.MIN_VALID_DATE, import_report.max_valid_date()
    assert all(lo <= d <= hi for d in dates)
    assert len(result.skipped_rows) == 2


def test_clean_file_has_empty_report():
    result = _process([
        (GOOD, "Delhi", "Lounges", "T1D Lounge", 100, 1000, None, None),
        (GOOD, "Hyderabad", "Atithya", "Meet & Greet", 5, 400, None, None),
    ])
    assert result.success and result.skipped_rows.empty
    assert not any("not imported" in w for w in result.warnings)


def test_summary_groups_reasons():
    rep = pd.DataFrame({
        "Reason": ["Date is not a valid date"] * 3
                  + ["Date outside the accepted range (01 Jan 2015 to 15 Oct 2027)"] * 2
    })
    assert import_report.summary(rep) == ["3 × Date is not a valid date",
                                          "2 × Date outside the accepted range"]
