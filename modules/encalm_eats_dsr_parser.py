"""
modules/encalm_eats_dsr_parser.py
===================================
Dedicated parser for the Encalm Eats Master DSR Excel workbook.

DSR Structure (per sheet = one day):
    Row 1:  "Master DSR" (title, ignored)
    Row 2:  Location :  |  Encalm Eats (Delhi)
    Row 3:  Date :      |  <date>
    Row 4:  Unit | Total Cover | Net Total Amount (Without Tax)  [+ MTD/YTD cols on later dates]
    Row 5:  Encalm Eats | <total covers> | <total rev>          <- GRAND TOTAL — skip
    Row 6+: "Outlet Wise Detail" label, then outlet rows
            Some sheets have section-header rows:
              "Delhi Store's" / "Bhogapuram" — SECTION SUBTOTALS — skip
            Individual outlet rows carry covers + revenue.

Location mapping (inferred from section headers):
    Default (no section header): Delhi
    After "Delhi Store's" header:   Delhi
    After "Bhogapuram" header:      Bhogapuram
    Early sheets (Jul 1-4 approx):  "Cafeteria Bhogapuram" = Bhogapuram SECTION TOTAL — skip
    Individual outlets under Bhogapuram:
        "Cafeteria Admin Block - Ala Carte"  -> Bhogapuram
        "Cafeteria Admin Block - Sales"      -> Bhogapuram

Outlet canonical names (normalise case/spacing variants):
    "Indisip T2 - Bus Gate"      -> "IndiSip T2 - Bus Gate"
    "Indisip T2 - Pre Checkin"   -> "IndiSip T2 - Pre Checkin"
    "Indisip T3 - Mezzanine Floor" -> "IndiSip T3 - Mezzanine Floor"
    "Events/ODC"                 -> "Event/ODC"

Rows to skip (section/grand totals — never individual outlets):
    "Encalm Eats", "Delhi Store's", "Delhi Stores", "Bhogapuram",
    "Cafeteria Bhogapuram" (early-sheet Bhogapuram section total)

Output schema per record:
    date, outlet, location, segment, covers, net_revenue,
    mtd_revenue, ytd_revenue, source_file, source_sheet
"""
from __future__ import annotations

import datetime as dt
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import pandas as pd


# ---------------------------------------------------------------------------
# Section / subtotal detection
# ---------------------------------------------------------------------------

# These names are SECTION HEADERS or GRAND TOTALS — never individual outlets.
# Any row whose outlet name (stripped) matches one of these is skipped.
_SECTION_TOTAL_NAMES: frozenset[str] = frozenset({
    "encalm eats",
    "outlet wise detail",
    "delhi store's",
    "delhi stores",
    "delhi",
    "bhogapuram",
    "cafeteria bhogapuram",   # early-sheet Bhogapuram section total
})

# After which section header does the location change?
_DELHI_HEADERS: frozenset[str] = frozenset({
    "delhi store's", "delhi stores", "delhi",
})
_BHOGAPURAM_HEADERS: frozenset[str] = frozenset({
    "bhogapuram",
})

# Individual outlets that belong to Bhogapuram regardless of section header
_BHOGAPURAM_OUTLETS: frozenset[str] = frozenset({
    "cafeteria admin block - ala carte",
    "cafeteria admin block - sales",
})

# Canonical outlet name map (lowercase key -> display name)
_CANONICAL: dict[str, str] = {
    "indisip t2 - bus gate":         "IndiSip T2 - Bus Gate",
    "indisip t2 - pre checkin":      "IndiSip T2 - Pre Checkin",
    "indisip t3 - mezzanine floor":  "IndiSip T3 - Mezzanine Floor",
    "events/odc":                    "Event/ODC",
}

# Known individual outlet names (canonical lowercase) — anything NOT in this
# list that also isn't a known section header gets flagged as an unknown outlet.
_KNOWN_OUTLETS_LC: frozenset[str] = frozenset({
    "indisip t2 - bus gate",
    "indisip t2 - pre checkin",
    "indisip t3 - mezzanine floor",
    "indisip t3 - int. ifk 02, gate 03",
    "chaayos t3",
    "event/odc",
    "events/odc",
    "ald",
    "cafeteria admin block - ala carte",
    "cafeteria admin block - sales",
})


def _canonicalize(name: str) -> str:
    """Return the canonical display name for an outlet."""
    lc = name.strip().lower()
    return _CANONICAL.get(lc, name.strip())


def _is_section_total(name: str) -> bool:
    return name.strip().lower() in _SECTION_TOTAL_NAMES


def _location_for_outlet(name: str, current_section: str) -> str:
    """Return 'Bhogapuram' or 'Delhi' based on outlet name and current section."""
    lc = name.strip().lower()
    if lc in _BHOGAPURAM_OUTLETS:
        return "Bhogapuram"
    return current_section


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DSRRecord:
    date: dt.date
    outlet: str
    location: str
    segment: str = "Encalm Eats"
    covers: float | None = None
    net_revenue: float | None = None
    mtd_revenue: float | None = None
    ytd_revenue: float | None = None
    source_file: str = ""
    source_sheet: str = ""


@dataclass
class DSRParseResult:
    success: bool
    file_name: str
    records: list[DSRRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Validation summary
    sheets_parsed: int = 0
    sheets_skipped: int = 0
    rows_extracted: int = 0
    rows_skipped_total: int = 0
    rows_skipped_subtotal: int = 0
    rows_invalid: int = 0

    # Source totals for cross-check
    source_grand_total_covers: float | None = None
    source_grand_total_revenue: float | None = None
    parsed_total_covers: float = 0.0
    parsed_total_revenue: float = 0.0

    @property
    def df(self) -> pd.DataFrame:
        if not self.records:
            return pd.DataFrame()
        return pd.DataFrame([r.__dict__ for r in self.records])


# ---------------------------------------------------------------------------
# Single-sheet parser
# ---------------------------------------------------------------------------

def _parse_sheet(ws, sheet_name: str, source_file: str) -> tuple[list[DSRRecord], list[str], list[str], float | None, float | None]:
    """
    Parse one daily sheet.
    Returns (records, errors, warnings, grand_total_covers, grand_total_revenue).
    """
    import datetime as dt

    records: list[DSRRecord] = []
    errors: list[str] = []
    warns: list[str] = []
    grand_covers: float | None = None
    grand_revenue: float | None = None

    rows = list(ws.iter_rows(values_only=True))

    # --- Extract date ---
    sheet_date: dt.date | None = None
    location_header: str = "Delhi"  # default

    for row in rows[:6]:
        if row[1] is None:
            continue
        b = str(row[1]).strip()
        if "Date" in b:
            d = row[2]
            if isinstance(d, dt.datetime):
                sheet_date = d.date()
            elif isinstance(d, dt.date):
                sheet_date = d
            elif isinstance(d, str):
                for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y"):
                    try:
                        sheet_date = dt.datetime.strptime(d.strip(), fmt).date()
                        break
                    except ValueError:
                        pass

    if sheet_date is None:
        # Try parsing from sheet name itself (DD-MM-YYYY)
        try:
            sheet_date = dt.datetime.strptime(sheet_name.strip(), "%d-%m-%Y").date()
        except ValueError:
            errors.append(f"Could not detect date in sheet '{sheet_name}'")
            return records, errors, warns, grand_covers, grand_revenue

    # --- Find grand total row (Row 5 = 'Encalm Eats') ---
    for row in rows[:8]:
        if row[1] is None:
            continue
        b = str(row[1]).strip()
        if b.lower() == "encalm eats":
            try:
                grand_covers = float(row[2]) if row[2] is not None else None
            except (TypeError, ValueError):
                pass
            try:
                grand_revenue = float(row[3]) if row[3] is not None else None
            except (TypeError, ValueError):
                pass
            break

    # --- Parse outlet rows (after "Outlet Wise Detail") ---
    in_detail = False
    current_section = "Delhi"  # default location

    for row in rows:
        b_raw = row[1]
        if b_raw is None:
            continue
        b = str(b_raw).strip()
        b_lc = b.lower()

        if "outlet wise detail" in b_lc:
            in_detail = True
            continue

        if not in_detail:
            continue

        if not b:
            continue

        # Section header detection
        if b_lc in _DELHI_HEADERS:
            current_section = "Delhi"
            continue
        if b_lc in _BHOGAPURAM_HEADERS:
            current_section = "Bhogapuram"
            continue

        # Skip known section/grand totals
        if _is_section_total(b):
            continue

        # Determine location
        location = _location_for_outlet(b, current_section)

        # Covers
        covers_raw = row[2]
        covers: float | None = None
        if covers_raw is not None:
            try:
                covers = float(covers_raw)
                if covers == 0.0:
                    covers = None
            except (TypeError, ValueError):
                pass

        # Net revenue (col D = index 3)
        rev_raw = row[3]
        net_rev: float | None = None
        if rev_raw is not None:
            try:
                net_rev = float(rev_raw)
                if net_rev == 0.0:
                    net_rev = None
            except (TypeError, ValueError):
                pass

        # MTD revenue (col E = index 4) — present from ~day 15
        mtd_raw = row[4] if len(row) > 4 else None
        mtd_rev: float | None = None
        if mtd_raw is not None:
            try:
                mtd_rev = float(mtd_raw)
            except (TypeError, ValueError):
                pass

        # YTD revenue (col G = index 6)
        ytd_raw = row[6] if len(row) > 6 else None
        ytd_rev: float | None = None
        if ytd_raw is not None:
            try:
                ytd_rev = float(ytd_raw)
            except (TypeError, ValueError):
                pass

        # Skip rows with no revenue and no covers
        if net_rev is None and covers is None:
            continue

        # Warn about unknown outlet names
        if b_lc not in _KNOWN_OUTLETS_LC:
            warns.append(f"Sheet '{sheet_name}': unknown outlet '{b}' — included as-is")

        canonical = _canonicalize(b)

        records.append(DSRRecord(
            date=sheet_date,
            outlet=canonical,
            location=location,
            segment="Encalm Eats",
            covers=covers,
            net_revenue=net_rev,
            mtd_revenue=mtd_rev,
            ytd_revenue=ytd_rev,
            source_file=source_file,
            source_sheet=sheet_name,
        ))

    return records, errors, warns, grand_covers, grand_revenue


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_dsr(file: BinaryIO | str | Path, file_name: str = "") -> DSRParseResult:
    """
    Parse an Encalm Eats Master DSR workbook.

    Parameters
    ----------
    file : file-like object or path
    file_name : display name for error messages and source_file metadata

    Returns
    -------
    DSRParseResult  containing records + validation summary
    """
    import openpyxl

    fname = file_name or (str(file) if isinstance(file, (str, Path)) else "uploaded_dsr.xlsx")
    result = DSRParseResult(success=False, file_name=fname)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
    except Exception as e:
        result.errors.append(f"Cannot open workbook: {e}")
        return result

    grand_covers_last: float | None = None
    grand_revenue_last: float | None = None

    for sheet_name in wb.sheetnames:
        # Only process sheets whose names look like dates (DD-MM-YYYY)
        try:
            dt.datetime.strptime(sheet_name.strip(), "%d-%m-%Y")
        except ValueError:
            result.sheets_skipped += 1
            result.warnings.append(f"Skipped non-date sheet: '{sheet_name}'")
            continue

        ws = wb[sheet_name]
        recs, errs, warns, gcov, grev = _parse_sheet(ws, sheet_name, fname)

        result.sheets_parsed += 1
        result.records.extend(recs)
        result.errors.extend(errs)
        result.warnings.extend(warns)
        result.rows_extracted += len(recs)

        # Use last non-None grand totals for cross-check
        if gcov is not None:
            grand_covers_last = gcov
        if grev is not None:
            grand_revenue_last = grev

    if not result.records:
        result.errors.append("No outlet records extracted from any sheet.")
        return result

    # Aggregate parsed totals — use only daily net_revenue (not MTD/YTD)
    result.parsed_total_covers  = sum(r.covers or 0 for r in result.records)
    result.parsed_total_revenue = sum(r.net_revenue or 0 for r in result.records)

    # The source file's last-sheet grand total is the YTD; the DSR grand total
    # for the full month is the MTD of the last sheet.  We store both for info.
    result.source_grand_total_covers  = grand_covers_last
    result.source_grand_total_revenue = grand_revenue_last

    result.success = True
    return result
