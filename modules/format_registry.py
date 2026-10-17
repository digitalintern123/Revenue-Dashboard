"""
format_registry.py — what is in an uploaded file, sheet by sheet.

For the upload "Analyse" panel: every sheet of the workbook is listed with
the layout the app recognised, which reader handled it, how confident the
app is, the rows and dates it gave, and whether it is imported. A sheet the
app does not understand is listed as such — nothing is skipped silently.

It reports what the existing parsers did (data_processor, traffic_parser,
aop_parser, encalm_eats_dsr_parser); it never changes their results.
"""
from __future__ import annotations

import io
from typing import Optional

import pandas as pd

IMPORTED = "Imported"
NOT_USED = "Not used"
NOT_RECOGNISED = "Not recognised"
EMPTY = "Empty"

COLUMNS = ["Sheet", "What the app found", "Confidence", "Rows", "Dates", "Result"]


def _sheet_names(file_bytes: bytes, file_name: str) -> list[str]:
    if not file_name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return []
    try:
        return pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl").sheet_names
    except Exception:
        return []


def _is_blank(file_bytes: bytes, sheet: str) -> bool:
    try:
        return pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=None,
                             nrows=10, engine="openpyxl").dropna(how="all").empty
    except Exception:
        return False


def _period(dates) -> str:
    d = pd.to_datetime(pd.Series(list(dates)), errors="coerce").dropna()
    if d.empty:
        return ""
    a, b = d.min(), d.max()
    return f"{a:%d %b %Y}" if a == b else f"{a:%d %b %Y} – {b:%d %b %Y}"


def _pct(c: Optional[float]) -> str:
    return "—" if c is None else f"{c:.0%}"


def _row(sheet, found, conf, rows, dates, result) -> dict:
    return dict(zip(COLUMNS, [sheet, found, _pct(conf), f"{rows:,}" if rows else "",
                              dates, result]))


def identify_revenue(file_bytes: bytes, file_name: str, result, confidence=None) -> pd.DataFrame:
    """Sheets of a revenue upload. `result` is the ProcessResult."""
    conf = confidence if confidence is not None else result.confidence
    used = [s.strip().strip("'") for s in (result.source_sheet or "").split(",") if s.strip()]
    rows_n = len(result.df) if result.df is not None else 0
    dates = _period(result.df["date"]) if rows_n else ""
    sheets = _sheet_names(file_bytes, file_name)
    if not sheets:                                 # PDF / CSV / other: one "sheet"
        return pd.DataFrame([_row(file_name, result.layout or "—", conf, rows_n, dates,
                                  IMPORTED if result.success else NOT_RECOGNISED)])
    out = []
    for sh in sheets:
        if sh in used or (not used and result.success and sh == sheets[0]):
            out.append(_row(sh, result.layout or "Revenue table", conf, rows_n, dates,
                            IMPORTED if result.success else NOT_RECOGNISED))
        elif _is_blank(file_bytes, sh):
            out.append(_row(sh, "", None, 0, "", EMPTY))
        else:
            hint = ("Looks like AOP targets — upload in the AOP Targets tab"
                    if "aop" in sh.lower() else
                    f"Revenue was read from sheet '{used[0]}'" if used else "")
            out.append(_row(sh, hint, None, 0, "", NOT_USED))
    return pd.DataFrame(out, columns=COLUMNS)


def identify_traffic(file_bytes: bytes, file_name: str, df: Optional[pd.DataFrame],
                     confidence: Optional[float] = None) -> pd.DataFrame:
    """Sheets of a traffic upload: airport, reader, rows, dates."""
    from modules import traffic_parser as tp
    readers = (df.attrs.get("readers") or {}) if df is not None else {}
    skipped = " ".join((df.attrs.get("skipped_sheets") or []) if df is not None else [])
    out = []
    for sh in _sheet_names(file_bytes, file_name):
        loc = tp._sheet_location(sh)
        if _is_blank(file_bytes, sh):
            out.append(_row(sh, "", None, 0, "", EMPTY))
        elif loc and loc in readers:
            part = df[df["location"].astype(str) == loc]
            gran = ", ".join(sorted(set(part["granularity"].astype(str))))
            out.append(_row(sh, f"{loc}: {readers[loc]} ({gran})", confidence,
                            len(part), _period(part["date"]), IMPORTED))
        elif f"'{sh}'" in skipped:
            out.append(_row(sh, f"{loc or 'No airport in the sheet name'}: layout not recognised",
                            None, 0, "", NOT_RECOGNISED))
        else:
            out.append(_row(sh, "", None, 0, "", NOT_USED))
    # Airports read from a sheet without the airport in its name (flat tables)
    named = {tp._sheet_location(s) for s in _sheet_names(file_bytes, file_name)}
    for loc, reader in readers.items():
        if loc not in named:
            part = df[df["location"].astype(str) == loc]
            out.append(_row("(table)", f"{loc}: {reader}", confidence, len(part),
                            _period(part["date"]), IMPORTED))
    return pd.DataFrame(out, columns=COLUMNS)


AOP_FORMATS = {
    "outlet_monthly": "AOP master — outlet × month (Geographical / Business Segment / Unit-ID)",
    "daily_outlet_pivot": "AOP — daily outlet pivot",
    "daily_pivot": "AOP — daily total per location",
}


def identify_aop(file_bytes: bytes, file_name: str, parsed: Optional[dict],
                 extra_sheets: Optional[dict] = None) -> pd.DataFrame:
    """Sheets of an AOP upload. `parsed` = aop_parser.parse_aop_auto result
    (EHPL); `extra_sheets` = {sheet: description} read by other AOP readers
    (Sky Plates / Encalm Eats)."""
    used = parsed.get("sheet_name") if parsed else None
    extra = extra_sheets or {}
    out = []
    for sh in _sheet_names(file_bytes, file_name):
        if sh == used:
            rows = parsed["aop_rows"]
            span = ""
            if not rows.empty and "year" in rows:
                ym = sorted(set(zip(rows["year"].astype(int), rows["month"].astype(int))))
                span = (f"{pd.Timestamp(ym[0][0], ym[0][1], 1):%b %Y} – "
                        f"{pd.Timestamp(ym[-1][0], ym[-1][1], 1):%b %Y}")
            elif not rows.empty and "date" in rows:
                span = _period(rows["date"])
            out.append(_row(sh, AOP_FORMATS.get(parsed.get("format"), parsed.get("format")),
                            0.95, len(rows), span, IMPORTED))
        elif sh in extra:
            out.append(_row(sh, extra[sh], 0.95, 0, "", IMPORTED))
        elif _is_blank(file_bytes, sh):
            out.append(_row(sh, "", None, 0, "", EMPTY))
        else:
            out.append(_row(sh, "", None, 0, "", NOT_USED))
    return pd.DataFrame(out, columns=COLUMNS)


def identify_dsr(file_bytes: bytes, file_name: str, result) -> pd.DataFrame:
    """Day sheets of an Encalm Eats DSR upload."""
    by_sheet: dict[str, list] = {}
    for r in result.records:
        by_sheet.setdefault(getattr(r, "source_sheet", "") or "", []).append(r)
    out = []
    for sh in _sheet_names(file_bytes, file_name):
        recs = by_sheet.get(sh, [])
        if recs:
            out.append(_row(sh, "Encalm Eats DSR — outlet rows (covers, net revenue)", 0.95,
                            len(recs), _period([r.date for r in recs]), IMPORTED))
        elif _is_blank(file_bytes, sh):
            out.append(_row(sh, "", None, 0, "", EMPTY))
        else:
            out.append(_row(sh, "", None, 0, "", NOT_USED))
    if not out and result.records:                 # records without sheet names
        out.append(_row(file_name, "Encalm Eats DSR", 0.95, len(result.records),
                        _period([r.date for r in result.records]), IMPORTED))
    return pd.DataFrame(out, columns=COLUMNS)
