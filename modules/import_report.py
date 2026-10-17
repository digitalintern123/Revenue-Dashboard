"""
import_report.py — "rows not imported" report for revenue uploads.

Parsers and data_processor._validate_and_clean record every row they drop
(or import only partly) here, with the source row number and the reason,
so the Upload page can show exactly what did not make it into the
database instead of losing rows silently. Pure pandas — no Streamlit/DB.
"""
from __future__ import annotations

import datetime as dt
from typing import Iterable, Optional

import pandas as pd

# Helper columns carried alongside parsed rows until cleanup removes them.
ROW_COL = "_excel_row"      # 1-based row number in the source sheet
DATE_RAW_COL = "_date_raw"  # the date cell exactly as it was in the file
HELPER_COLS = (ROW_COL, DATE_RAW_COL)

REPORT_COLUMNS = ["Excel row", "Date in file", "Location", "Business", "Outlet",
                  "PAX", "Revenue", "Result", "Reason"]

NOT_IMPORTED = "Not imported"

# Accepted date range for revenue rows: anything outside is a typo or a
# corrupted cell (e.g. year 3601), never real data.
MIN_VALID_DATE = dt.date(2015, 1, 1)
MAX_FUTURE_DAYS = 365


def max_valid_date(today: Optional[dt.date] = None) -> dt.date:
    return (today or dt.date.today()) + dt.timedelta(days=MAX_FUTURE_DAYS)


def show(value) -> str:
    """A cell value as the user would recognise it from the file."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, dt.datetime)):
        return value.strftime("%Y-%m-%d") if (value.hour, value.minute, value.second) == (0, 0, 0) \
            else value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:.2f}"
    return str(value).strip()


def frame(rows: pd.DataFrame, reason, result: str = NOT_IMPORTED,
          *, date_col: str = "date", location_col: str = "location",
          segment_col: str = "segment", outlet_col: str = "outlet",
          pax_col: str = "pax", revenue_col: str = "revenue") -> pd.DataFrame:
    """Report rows for `rows` (a slice of a parsed/raw frame). `reason` is a
    string or a function row -> string."""
    if rows is None or rows.empty:
        return pd.DataFrame(columns=REPORT_COLUMNS)

    def col(name):
        return rows[name] if name in rows.columns else pd.Series([None] * len(rows), index=rows.index)

    date_src = rows[DATE_RAW_COL] if DATE_RAW_COL in rows.columns else col(date_col)
    out = pd.DataFrame({
        "Excel row": col(ROW_COL).map(lambda v: int(v) if pd.notna(v) else None) if ROW_COL in rows.columns
                     else [None] * len(rows),
        "Date in file": [show(v) for v in date_src],
        "Location": [show(v) for v in col(location_col)],
        "Business": [show(v) for v in col(segment_col)],
        "Outlet": [show(v) for v in col(outlet_col)],
        "PAX": [show(v) for v in col(pax_col)],
        "Revenue": [show(v) for v in col(revenue_col)],
        "Result": result,
        "Reason": [reason(r) for _, r in rows.iterrows()] if callable(reason) else reason,
    }, index=rows.index)
    return out.reset_index(drop=True)


def combine(parts: Iterable[Optional[pd.DataFrame]]) -> pd.DataFrame:
    """Join report pieces; rows that matter most (real figures) first."""
    parts = [p for p in parts if p is not None and not p.empty]
    if not parts:
        return pd.DataFrame(columns=REPORT_COLUMNS)
    out = pd.concat(parts, ignore_index=True)
    empty_line = out["Reason"].str.startswith("No PAX and no revenue")
    out = out.assign(_empty=empty_line, _row=pd.to_numeric(out["Excel row"], errors="coerce"))
    out = out.sort_values(["_empty", "_row"], kind="stable", na_position="last")
    return out.drop(columns=["_empty", "_row"]).reset_index(drop=True)


def summary(report: pd.DataFrame) -> list[str]:
    """One line per reason group, e.g. '16 × Date is not a valid date'."""
    if report is None or report.empty:
        return []
    groups = report["Reason"].str.replace(r"\s*\(.*$", "", regex=True).str.replace(r"\s*'.*$", "", regex=True)
    counts = groups.value_counts()
    return [f"{n:,} × {reason}" for reason, n in counts.items()]
