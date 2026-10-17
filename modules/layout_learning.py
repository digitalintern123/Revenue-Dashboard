"""
layout_learning.py — read a layout the app has never seen, with the user's
confirmation, and remember it.

1. read_grid / guess_header_row / table_at: the sheet as a header row plus
   data rows.
2. propose(): a role per column (Date, Location, Outlet, PAX, Revenue, ... /
   Date, Location, Terminal, Traffic), with a confidence, guessed from the
   headers and the values (universal_parser's role inference).
3. The user confirms or corrects the roles on the upload screen.
4. apply(): builds the app's standard rows from the confirmed mapping.
5. fingerprint() / match_score(): a confirmed mapping is saved as a
   "saved layout" (database.parse_template) and recognised automatically
   the next time a file with (nearly) the same headers is uploaded.

Pure pandas — no Streamlit, no database (see database.py for the
parse_template table).
"""
from __future__ import annotations

import datetime as dt
import io
import re
from typing import Optional

import pandas as pd

from modules import universal_parser as up

IGNORE = "Ignore"

# Revenue roles. The two "… for the date in the header" roles read layouts
# with one column per day (dates across the top).
R_DATE, R_LOCATION, R_BUSINESS, R_OUTLET = "Date", "Location", "Business", "Outlet"
R_PAX, R_REVENUE, R_AOP = "PAX", "Revenue", "AOP"
R_REV_BY_DATE, R_PAX_BY_DATE = "Revenue (date in header)", "PAX (date in header)"
REVENUE_ROLES = [IGNORE, R_DATE, R_LOCATION, R_BUSINESS, R_OUTLET, R_PAX, R_REVENUE, R_AOP,
                 R_REV_BY_DATE, R_PAX_BY_DATE]

# Traffic roles. Several Traffic columns are allowed: each is stored under the
# terminal named in its "Terminal" label (columns with the same label are
# added together, e.g. Domestic arrivals + Domestic departures).
T_DATE, T_LOCATION, T_TERMINAL, T_TRAFFIC = "Date", "Location", "Terminal", "Traffic"
TRAFFIC_ROLES = [IGNORE, T_DATE, T_LOCATION, T_TERMINAL, T_TRAFFIC]

_UNIVERSAL_TO_REVENUE = {"date": R_DATE, "location": R_LOCATION, "segment": R_BUSINESS,
                         "business_unit": R_BUSINESS, "outlet": R_OUTLET, "pax": R_PAX,
                         "revenue": R_REVENUE, "aop": R_AOP}


class LayoutError(ValueError):
    """The confirmed mapping cannot produce rows (explained to the user)."""


# ---------------------------------------------------------------------------
# Reading the sheet
# ---------------------------------------------------------------------------
def is_workbook(name: str) -> bool:
    return name.lower().endswith((".xlsx", ".xlsm", ".xls"))


def sheet_names(file_bytes: bytes, name: str) -> list[str]:
    if not is_workbook(name):
        return []
    return pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl").sheet_names


def read_grid(file_bytes: bytes, name: str, sheet: Optional[str] = None) -> pd.DataFrame:
    """The raw cells of one sheet (or a CSV/TSV/TXT file), no header."""
    if is_workbook(name):
        return pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet or 0, header=None,
                             dtype=object, engine="openpyxl")
    text = file_bytes.decode("utf-8-sig", errors="replace")
    return pd.read_csv(io.StringIO(text), sep=None, engine="python", header=None, dtype=object)


def guess_header_row(grid: pd.DataFrame) -> int:
    """0-based row that looks most like column headers."""
    try:
        return up._find_table(grid)[0]
    except Exception:
        for i in range(min(len(grid), 40)):
            if grid.iloc[i].notna().sum() >= 2:
                return i
        return 0


def header_labels(cells) -> list[str]:
    """Header cells as unique, readable labels ("Column 3" for a blank)."""
    out, seen = [], {}
    for j, c in enumerate(cells):
        if c is None or (isinstance(c, float) and pd.isna(c)) or str(c).strip() == "":
            label = f"Column {j + 1}"
        elif isinstance(c, (pd.Timestamp,)) or hasattr(c, "strftime"):
            label = pd.Timestamp(c).strftime("%Y-%m-%d")
        else:
            label = str(c).strip()
        n = seen.get(label, 0)
        seen[label] = n + 1
        out.append(label if n == 0 else f"{label} ({n + 1})")
    return out


def table_at(grid: pd.DataFrame, header_row: int) -> tuple[list[str], pd.DataFrame]:
    headers = header_labels(list(grid.iloc[header_row]))
    data = grid.iloc[header_row + 1:].reset_index(drop=True)
    data.columns = range(data.shape[1])
    data = data.dropna(how="all")
    return headers, data


# ---------------------------------------------------------------------------
# Proposal
# ---------------------------------------------------------------------------
def _samples(series: pd.Series, n: int = 3) -> str:
    from modules.import_report import show
    vals = [show(v) for v in series.dropna().head(n)]
    return " | ".join(v[:20] for v in vals)


def _header_date(label: str):
    """Date in a column header. ISO text (how header_labels writes real date
    cells) is read as year-month-day, anything else day-first."""
    s = str(label).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            return dt.date.fromisoformat(s)
        except ValueError:
            return None
    return up._to_date(s) if re.search(r"\d", s) else None


def _header_is_date(label: str) -> bool:
    return _header_date(label) is not None


def propose(headers: list[str], data: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Suggested role and confidence per column."""
    rows = []
    if kind == "revenue":
        assign, maps, _ = up._infer_roles(headers, data)
        by_col = {j: (_UNIVERSAL_TO_REVENUE.get(r), maps[r].confidence)
                  for r, j in assign.items() if _UNIVERSAL_TO_REVENUE.get(r)}
        date_headers = [j for j, h in enumerate(headers) if _header_is_date(h)]
        wide = len(date_headers) >= 3
        for j, h in enumerate(headers):
            role, conf = by_col.get(j, (IGNORE, 0.0))
            if wide and j in date_headers:
                role, conf = R_REV_BY_DATE, 0.6
            rows.append({"Column": h, "Sample values": _samples(data[j]), "Role": role,
                         "Confidence": round(conf, 2)})
    else:
        for j, h in enumerate(headers):
            p = up._content_profile(data[j])
            hl = h.lower()
            if p["date"] >= 0.7 or "date" in hl:
                role, conf = T_DATE, max(p["date"], 0.6)
            elif p["loc"] >= 0.5 or any(w in hl for w in ("airport", "location", "station")):
                role, conf = T_LOCATION, max(p["loc"], 0.6)
            elif p["num"] >= 0.7:
                role, conf = T_TRAFFIC, 0.6 if any(w in hl for w in ("pax", "traffic", "arr", "dep")) else 0.4
            elif p["text"] >= 0.6 and p["uniq"] <= 0.5 or "terminal" in hl:
                role, conf = T_TERMINAL, 0.5
            else:
                role, conf = IGNORE, 0.0
            rows.append({"Column": h, "Sample values": _samples(data[j]), "Role": role,
                         "Confidence": round(conf, 2),
                         "Terminal": _terminal_from_header(h) if role == T_TRAFFIC else ""})
    return pd.DataFrame(rows)


def _terminal_from_header(h: str) -> str:
    hl = h.lower()
    if "int" in hl:
        return "International"
    if "dom" in hl:
        return "Domestic"
    return ""


# ---------------------------------------------------------------------------
# Applying a confirmed mapping
# ---------------------------------------------------------------------------
def _col(mapping: pd.DataFrame, role: str) -> list[int]:
    return [i for i, r in enumerate(mapping["Role"]) if r == role]


def apply(headers: list[str], data: pd.DataFrame, mapping: pd.DataFrame, kind: str,
          constants: Optional[dict] = None, header_row: int = 0) -> pd.DataFrame:
    """Standard rows from the confirmed mapping. Raises LayoutError with a
    plain explanation when a required field has neither a column nor a value."""
    constants = {k: v for k, v in (constants or {}).items() if v not in (None, "")}
    if list(mapping["Column"]) != list(headers):
        raise LayoutError("The column list changed — analyse the file again.")
    excel_row = pd.Series(range(len(data)), index=data.index) + header_row + 2
    if kind == "revenue":
        return _apply_revenue(data, mapping, constants, excel_row, headers)
    return _apply_traffic(data, mapping, constants)


def _one(mapping, role, required, constants, key):
    cols = _col(mapping, role)
    if len(cols) > 1:
        raise LayoutError(f"Only one column can be '{role}' ({len(cols)} chosen).")
    if not cols and required and key not in constants:
        raise LayoutError(f"Choose a '{role}' column, or type a value for it below.")
    return cols[0] if cols else None


def _apply_revenue(data, mapping, constants, excel_row, headers) -> pd.DataFrame:
    from modules import import_report
    c_loc = _one(mapping, R_LOCATION, True, constants, "location")
    c_bus = _one(mapping, R_BUSINESS, False, constants, "business")
    c_out = _one(mapping, R_OUTLET, False, constants, "outlet")
    c_pax = _one(mapping, R_PAX, False, constants, "pax")
    c_rev = _one(mapping, R_REVENUE, False, constants, "revenue")
    c_aop = _one(mapping, R_AOP, False, constants, "aop")
    by_date = _col(mapping, R_REV_BY_DATE) + _col(mapping, R_PAX_BY_DATE)

    def text(c, key):
        if c is not None:
            return data[c].map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v))
                               else str(v).strip())
        return pd.Series([constants.get(key)] * len(data), index=data.index)

    def num(c):
        if c is None:
            return pd.Series([None] * len(data), index=data.index, dtype=object)
        return data[c].map(up._to_number)

    base = pd.DataFrame({
        "location": text(c_loc, "location").map(lambda v: up._match_location(v) or v),
        "segment": text(c_bus, "business"),
        "outlet": text(c_out, "outlet"),
        import_report.ROW_COL: excel_row,
    }, index=data.index)
    if c_out is None and "outlet" not in constants:
        base["outlet"] = base["segment"]
    if base["segment"].isna().all():
        base["segment"] = base["outlet"].map(up._segment_from_outlet)

    if by_date:
        parts = []
        for c in by_date:
            day = _header_date(headers[c])
            if day is None:
                raise LayoutError(f"Column '{headers[c]}' does not have a date as its header.")
            measure = "revenue" if c in _col(mapping, R_REV_BY_DATE) else "pax"
            parts.append(base.assign(date=day, **{measure: data[c].map(up._to_number)}))
        out = pd.concat(parts, ignore_index=True)
        keys = ["date", "location", "segment", "outlet", import_report.ROW_COL]
        for m in ("pax", "revenue"):
            if m not in out:
                out[m] = None
        out = out.groupby(keys, dropna=False, as_index=False)[["pax", "revenue"]].sum(min_count=1)
        out["aop"] = None
    else:
        c_date = _one(mapping, R_DATE, True, constants, "date")
        if c_rev is None and c_pax is None:
            raise LayoutError("Choose a 'Revenue' or 'PAX' column.")
        out = base.assign(
            date=data[c_date].map(up._to_date) if c_date is not None
            else up._to_date(constants.get("date")),
            pax=num(c_pax), revenue=num(c_rev), aop=num(c_aop))
        out[import_report.DATE_RAW_COL] = data[c_date] if c_date is not None else constants.get("date")
    cols = ["date", "segment", "outlet", "location", "pax", "revenue", "aop",
            import_report.ROW_COL] + ([import_report.DATE_RAW_COL]
                                      if import_report.DATE_RAW_COL in out else [])
    return out[cols].reset_index(drop=True)


def _apply_traffic(data, mapping, constants) -> pd.DataFrame:
    c_date = _one(mapping, T_DATE, True, constants, "date")
    c_loc = _one(mapping, T_LOCATION, True, constants, "location")
    c_term = _one(mapping, T_TERMINAL, False, constants, "terminal")
    traffic_cols = _col(mapping, T_TRAFFIC)
    if not traffic_cols:
        raise LayoutError("Choose at least one 'Traffic' column.")
    if c_term is not None and len(traffic_cols) > 1:
        raise LayoutError("With a 'Terminal' column, choose exactly one 'Traffic' column.")
    dates = data[c_date].map(up._to_date) if c_date is not None else up._to_date(constants["date"])
    locs = (data[c_loc].map(lambda v: up._match_location(v) or (str(v).strip() if pd.notna(v) else None))
            if c_loc is not None else constants["location"])
    parts = []
    for c in traffic_cols:
        if c_term is not None:
            term = data[c_term].map(lambda v: "" if pd.isna(v) else str(v).strip())
        else:
            term = str(mapping["Terminal"].iloc[c] if "Terminal" in mapping else "").strip()
        parts.append(pd.DataFrame({"date": dates, "location": locs, "terminal": term,
                                   "traffic": data[c].map(up._to_number)}))
    out = pd.concat(parts, ignore_index=True)
    out = out.dropna(subset=["date", "location", "traffic"])
    out = out[out["location"].astype(str).str.strip() != ""]
    gran = constants.get("granularity", "daily")
    out = (out.groupby(["date", "location", "terminal"], as_index=False)["traffic"].sum())
    out["granularity"] = gran
    out["period_end"] = (pd.to_datetime(out["date"]) + pd.offsets.MonthEnd(0)).dt.date \
        if gran == "monthly" else pd.NaT
    return out


# ---------------------------------------------------------------------------
# Saved layouts
# ---------------------------------------------------------------------------
def _norm_header(h: str) -> str:
    h = re.sub(r"\s+", " ", str(h).strip().lower())
    return "" if re.fullmatch(r"column \d+( \(\d+\))?", h) else h


def fingerprint(headers: list[str]) -> list[str]:
    """Header labels that identify a layout (blank columns and dates left out,
    so a day-per-column sheet matches whatever month it holds)."""
    return [n for n in (_norm_header(h) for h in headers) if n and not _header_is_date(n)]


def match_score(a: list[str], b: list[str]) -> float:
    """Share of headers two layouts have in common (1.0 = identical set)."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))


def mapping_for_headers(saved_mapping: dict, headers: list[str], kind: str) -> pd.DataFrame:
    """A saved {header: [role, terminal]} mapping laid over a new file's
    headers. Headers the template does not know get 'Ignore'; date headers
    take the template's by-date role."""
    by_norm = {_norm_header(k): v for k, v in saved_mapping.get("columns", {}).items()}
    date_role = saved_mapping.get("date_header_role")
    rows = []
    for h in headers:
        role, term = by_norm.get(_norm_header(h), [IGNORE, ""])
        if date_role and _header_is_date(h):
            role = date_role
        row = {"Column": h, "Sample values": "", "Role": role, "Confidence": 1.0}
        if kind == "traffic":
            row["Terminal"] = term
        rows.append(row)
    return pd.DataFrame(rows)


def mapping_to_saved(mapping: pd.DataFrame) -> dict:
    cols, date_role = {}, None
    for _, r in mapping.iterrows():
        if r["Role"] in (R_REV_BY_DATE, R_PAX_BY_DATE) and _header_is_date(r["Column"]):
            date_role = r["Role"]
            continue
        cols[str(r["Column"])] = [r["Role"], str(r.get("Terminal", "") or "")]
    return {"columns": cols, "date_header_role": date_role}


def find_template(file_bytes: bytes, name: str, templates: list[dict],
                  sheet: Optional[str] = None, min_score: float = 0.9) -> Optional[dict]:
    """The best saved layout for this file: tries every sheet (or `sheet`) at
    the template's header row. Returns {template, sheet, header_row, headers,
    data, score} or None when nothing matches at least `min_score`."""
    if not templates:
        return None
    sheets = [sheet] if sheet else (sheet_names(file_bytes, name) or [None])
    best = None
    for sh in sheets:
        try:
            grid = read_grid(file_bytes, name, sh)
        except Exception:
            continue
        for t in templates:
            hr = int(t.get("header_row") or 0)
            if hr >= len(grid):
                continue
            headers, data = table_at(grid, hr)
            score = match_score(fingerprint(headers), t["fingerprint"])
            if score >= min_score and (best is None or score > best["score"]):
                best = {"template": t, "sheet": sh, "header_row": hr, "headers": headers,
                        "data": data, "score": score}
    return best
