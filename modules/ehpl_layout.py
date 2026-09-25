"""
modules/ehpl_layout.py
======================
Renders the EHPL page as ONE single hierarchical table per location.

Hierarchy (TOTAL always comes first, then its breakdown):
    TOTAL EHPL
    TOTAL LOUNGES  → Lounge rows (desc revenue)
    TOTAL SPA      → Spa rows
    TOTAL NAP & SHOWER → Nap rows
    TOTAL ATITHYA  → Atithya rows
    TOTAL ENWRAP   → Enwrap rows
    TOTAL BUSINESS CENTRE → BC rows
    TOTAL RDC      → RDC rows

Columns with comparison (PAX comparison first):
    Outlet / Category
    | PAX (cur) | PAX (cmp) | PAX Chg%
    | Revenue (cur) | Revenue (cmp) | Rev Chg%
    | Traffic | Traffic (cmp) | Traffic Chg%
    | PEN% (cur) | PEN% (cmp) | PEN Chg%
    | SPP (cur) | SPP (cmp) | SPP Chg%
    | AOP | Variance

Without comparison (single date):
    Outlet / Category | PAX | Revenue | Traffic | PEN% | SPP | AOP | Variance

Sort: always descending revenue — no UI control.
Terminal-wise: separate table below.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from modules import database, revenue_analysis as ra
from modules.formatting import format_money, format_pax, format_pct, format_spp
from modules.app_logger import log_exception

# ---------------------------------------------------------------------------
# Row type constants
# ---------------------------------------------------------------------------
RT_GRAND    = "grand"
RT_TOTAL    = "total"
RT_OUTLET   = "outlet"
RT_TERMINAL = "terminal"

CANONICAL_SECTION_ORDER = [
    "LOUNGES", "SPA", "NAP & SHOWER", "ATITHYA SERVICES",
    "ENWRAP", "PORTER", "BAR", "OTHERS",
]

TOTAL_LABELS = {
    "LOUNGES":           "TOTAL LOUNGES",
    "SPA":               "TOTAL SPA",
    "NAP & SHOWER":      "TOTAL NAP & SHOWER",
    "ATITHYA SERVICES":  "TOTAL ATITHYA",
    "ENWRAP":            "TOTAL ENWRAP",
    "PORTER":            "TOTAL PORTER",
    "BAR":               "TOTAL BAR",
    "OTHERS":            "TOTAL OTHERS",
}

DELHI_SECTIONS = {
    "LOUNGES": [
        "T1D (Lounges)", "Encalm Prive (T1)", "Amex Lounge T1",
        "T2 (Lounges)",
        "T3 Domestic DL02/3/4", "T3 D49", "T3 Air India Dom",
        "Lounge Rupay", "Lounge Amex Centurion",
        "T3 International", "Encalm Prive T3", "Encalm Xenia", "AI International",
        "T3 Arrivals LA22", "Reserved Lounge",
    ],
    "SPA": ["Spa T3 INT", "Spa T3 Dom", "Spa T1"],
    "NAP & SHOWER": ["T3 Nap LA01", "T3 Nap LA12"],
    "ATITHYA SERVICES": ["Atithya (M&G)", "Atithya (Porter)", "Atithya (Buggy)"],
    "ENWRAP": ["Enwrap"],
    # Bar outlets shown as separate section (revenue-only from PDF)
    "BAR": [
        "Bar T3 Dom", "Bar T3 INT", "Bar T3 Prive",
        "Bar T2", "Bar T1", "Bar D49", "Bar Rupay",
    ],
    # Others
    "OTHERS": ["Airport Lodge", "Business Centre", "RDC"],
}

# Subsidiary group keys — NEVER shown on EHPL page
_SUBSIDIARY_GROUPS: frozenset[str] = frozenset({
    "Encalm Eats (Delhi)", "Sky Plates (Delhi)",
})

HYD_SECTIONS = {
    "LOUNGES": ["Domestic Lounge", "International Lounge", "Encalm Prive"],
    "ATITHYA SERVICES": ["Atithya"],
    "ENWRAP": ["Baggage Wrapping"],
    "PORTER": ["Porter"],
}

GOA_SECTIONS = {
    "LOUNGES":          ["Domestic Lounge", "International Lounge"],
    "ATITHYA SERVICES": ["Atithya"],
    "PORTER":           ["Porter"],
    "ENWRAP":           ["Baggage Wrapping"],
}

BHOGAPURAM_SECTIONS = {
    # Bhogapuram only has these EHPL outlets
    "LOUNGES":          ["Domestic Lounge", "International Lounge"],
    "ATITHYA SERVICES": ["Atithya"],
    "PORTER":           ["Porter"],
    "ENWRAP":           ["Baggage Wrapping"],
}

# Name-fragment detection kept as fallback for older data that may not yet
# match the new group keys — supplements, never replaces, the group mapping.
_BC_FRAGS  = ["business centre", "business center"]
_RDC_FRAGS = ["round d clock", "rdc"]
_AIRPORT_LODGE_FRAGS = ["airport lodge"]

def _is_bc(name: str) -> bool:
    return any(f in name.strip().lower() for f in _BC_FRAGS)

def _is_rdc(name: str) -> bool:
    return any(f in name.strip().lower() for f in _RDC_FRAGS)

def _is_airport_lodge(name: str) -> bool:
    return any(f in name.strip().lower() for f in _AIRPORT_LODGE_FRAGS)

def _is_subsidiary(name: str) -> bool:
    """Return True for outlet display names that belong to Encalm Eats / Sky Plates."""
    lc = name.strip().lower()
    return lc in {"encalm eats", "encalm sky plates", "sky plates"}


# ---------------------------------------------------------------------------
# Section total — always from outlet rows, never from other totals
# Also carries comparison fields through unchanged from the source rows
# ---------------------------------------------------------------------------
def _section_total(sec_name: str, outlet_rows: list[dict]) -> dict:
    label = TOTAL_LABELS.get(sec_name, f"TOTAL {sec_name}")

    cur_rev = sum(r.get("cur_rev") or 0 for r in outlet_rows)
    cmp_rev = sum(r.get("cmp_rev") or 0 for r in outlet_rows if r.get("cmp_rev"))
    cur_pax = sum(r.get("cur_pax") or 0 for r in outlet_rows)
    cmp_pax = sum(r.get("cmp_pax") or 0 for r in outlet_rows if r.get("cmp_pax"))
    aop_sum = sum(r.get("aop") or 0 for r in outlet_rows if r.get("aop"))

    # Deduplicate shared traffic pools
    tvc = list({r["cur_traffic"] for r in outlet_rows if r.get("cur_traffic") is not None})
    tvp = list({r["cmp_traffic"] for r in outlet_rows if r.get("cmp_traffic") is not None})
    cur_traf = tvc[0] if len(tvc) == 1 else (sum(tvc) if tvc else None)
    cmp_traf = tvp[0] if len(tvp) == 1 else (sum(tvp) if tvp else None)

    pen_c = ra.safe_div(cur_pax, cur_traf) * 100 if cur_traf else None
    pen_p = ra.safe_div(cmp_pax, cmp_traf) * 100 if cmp_traf else None
    spp_c = ra.safe_div(cur_rev, cur_traf) if cur_traf else None
    spp_p = ra.safe_div(cmp_rev, cmp_traf) if cmp_traf else None

    return {
        "Performance": label,
        "cur_rev": cur_rev, "cmp_rev": cmp_rev or None,
        "rev_yoy": ra.pct_change(cur_rev, cmp_rev or None),
        "cur_pax": cur_pax, "cmp_pax": cmp_pax or None,
        "pax_yoy": ra.pct_change(cur_pax, cmp_pax or None),
        "cur_traffic": cur_traf, "cmp_traffic": cmp_traf,
        "traffic_chg": ra.pct_change(cur_traf, cmp_traf),
        "pen_cur": pen_c, "pen_cmp": pen_p,
        "pen_chg": ra.pct_change(pen_c, pen_p),
        "spp_cur": spp_c, "spp_cmp": spp_p,
        "spp_chg": ra.pct_change(spp_c, spp_p),
        "aop": aop_sum or None,
        "aop_var": ra.pct_change(cur_rev, aop_sum) if aop_sum else None,
    }


def _sort_desc(rows: list[dict]) -> list[dict]:
    """Always sort by current Revenue descending."""
    return sorted(rows, key=lambda r: (r.get("cur_rev") or 0), reverse=True)


# ---------------------------------------------------------------------------
# Build flat ordered row list
# ---------------------------------------------------------------------------
def _build_table_rows(
    all_rows: list[dict],
    sections: dict[str, list[str]],
) -> list[dict]:
    gk_to_section: dict[str, str] = {}
    for sec_name, gks in sections.items():
        for gk in gks:
            gk_to_section[gk] = sec_name

    section_outlets: dict[str, list[dict]] = {sec: [] for sec in sections}

    for row in all_rows:
        if row.get("_is_subtotal"):
            continue
        perf = row.get("Performance", "").strip()

        # Skip Subsidiary outlets — they belong to Encalm Eats / Sky Plates pages
        gk = row.get("_section", "")
        if gk in _SUBSIDIARY_GROUPS or _is_subsidiary(perf):
            continue

        sec = gk_to_section.get(gk)
        if sec:
            section_outlets.setdefault(sec, []).append(row)
            continue

        # Fallback name-based detection for older data not yet in group keys
        if _is_bc(perf):
            section_outlets.setdefault("OTHERS", []).append(row)
        elif _is_rdc(perf):
            section_outlets.setdefault("OTHERS", []).append(row)
        elif _is_airport_lodge(perf):
            section_outlets.setdefault("OTHERS", []).append(row)

    grand_row = next(
        (r for r in all_rows if r.get("_is_grand") and r.get("_is_subtotal")),
        None,
    )

    result: list[dict] = []

    # TOTAL EHPL always first
    if grand_row:
        result.append({**grand_row, "_row_type": RT_GRAND, "Performance": "TOTAL EHPL"})

    # Each section: TOTAL row first, then outlet breakdown (descending revenue)
    for sec_name in CANONICAL_SECTION_ORDER:
        outlets = section_outlets.get(sec_name, [])
        if not outlets:
            continue
        total_row = _section_total(sec_name, outlets)
        result.append({**total_row, "_row_type": RT_TOTAL})
        for o in _sort_desc(outlets):
            result.append({**o, "_row_type": RT_OUTLET})

    return result


# ---------------------------------------------------------------------------
# Terminal rows
# ---------------------------------------------------------------------------
def _get_terminal_rows(location: str, cur_df: pd.DataFrame,
                       cmp_df: "pd.DataFrame | None") -> list[dict]:
    """
    Build terminal-wise rows by grouping outlet revenue/PAX by physical terminal,
    then pulling traffic directly from the traffic DB for each terminal.

    Physical terminals shown:
      Delhi:     T1, T2, T3 Domestic, T3 International, T3 Arrivals
      Hyderabad: Domestic, International
      Goa:       Domestic
    """
    if cur_df is None or cur_df.empty:
        return []

    loc_norm = location.title()

    # ── Sentinel -> physical terminal(s) mapping ────────────────────────────
    # Each sentinel maps to the physical terminal labels used in the traffic DB.
    # These are the terminal names stored by the CLEAN traffic file.
    SENTINEL_TO_PHYSICAL = {
        # Delhi
        "T1 Dep":              "T1",
        "T1 Arr":              "T1",
        "T2 Dep":              "T2",
        "T2 Arr":              "T2",
        "T3 Dom Dep":          "T3 Domestic",
        "T3 Dom Arr":          "T3 Domestic",
        "T3 Int Dep":          "T3 International",
        "T3 Int Arr":          "T3 International",
        "T3 Arr":              "T3 Arrivals",
        "T3 Total":            "T3 Total",
        "All":                 "All Terminals",
        "All Dep":             "All Departures",
        "Porter Pool":         "Porter (All Terminals)",
        "T3 Dom+Int Dep":      "T3",
        # Hyderabad / Goa
        "Domestic":            "Domestic",
        "International":       "International",
        "Main Terminal":       "Main Terminal",
    }

    try:
        from modules import terminal_mapping as tm
        ot_cur = database.join_revenue_with_traffic_by_outlet(cur_df)
        ot_cmp = database.join_revenue_with_traffic_by_outlet(cmp_df) \
            if (cmp_df is not None and not cmp_df.empty) else pd.DataFrame()
    except Exception:
        return []

    if ot_cur is None or ot_cur.empty:
        return []

    skip_sentinels = {"Other", "Unmapped", "", "None", "nan"}

    def _physical(row):
        try:
            sentinel = tm.get_terminal_for_outlet(str(row["outlet"]), loc_norm)
            if not sentinel or sentinel in skip_sentinels:
                return None
            return SENTINEL_TO_PHYSICAL.get(sentinel, sentinel)
        except Exception:
            return None

    ot_cur["_phys"] = ot_cur.apply(_physical, axis=1)
    disp = ot_cur[ot_cur["_phys"].notna()].copy()
    if disp.empty:
        return []

    def _agg(grp):
        rev = grp["revenue"].sum()
        pax = grp["pax"].sum()
        return pd.Series({"cur_rev": rev, "cur_pax": pax})

    term_agg = disp.groupby("_phys").apply(_agg).reset_index()

    # Compare period
    cmp_map: dict = {}
    if not ot_cmp.empty:
        ot_cmp["_phys"] = ot_cmp.apply(_physical, axis=1)
        cd = ot_cmp[ot_cmp["_phys"].notna()]
        if not cd.empty:
            ca = cd.groupby("_phys").apply(_agg).reset_index()
            cmp_map = {
                row["_phys"]: {"cmp_rev": row["cur_rev"], "cmp_pax": row["cur_pax"]}
                for _, row in ca.iterrows()
            }

    # Get traffic directly from traffic DB by physical terminal name
    try:
        date_min = cur_df["date"].min()
        date_max = cur_df["date"].max()
        traf_df = database.load_traffic_for_date_range(date_min, date_max)
        traf_df = traf_df[traf_df["location"].str.title() == loc_norm]

        # Map physical terminal names to traffic DB terminal names
        PHYS_TO_DB = {
            "T1":              ["T1"],
            "T2":              ["T2 Domestic", "T2"],
            "T3 Domestic":     ["T3 Domestic"],
            "T3 International":["T3 International"],
            "T3 Arrivals":     ["T3 Domestic", "T3 International"],
            "Domestic":        ["Domestic"],
            "International":   ["International"],
        }

        def _get_traf(phys: str) -> float | None:
            db_names = PHYS_TO_DB.get(phys)
            if not db_names:
                return None
            total = 0.0
            found = False
            seen = set()
            for db_name in db_names:
                rows = traf_df[traf_df["terminal"] == db_name]
                if not rows.empty and db_name not in seen:
                    total += float(rows["traffic"].sum())
                    found = True
                    seen.add(db_name)
            return total if found else None

    except Exception:
        def _get_traf(phys):
            return None

    rows = []
    for _, row in term_agg.sort_values("cur_rev", ascending=False).iterrows():
        phys = str(row["_phys"])
        cr   = float(row.get("cur_rev") or 0)
        cp   = float(row.get("cur_pax") or 0)
        ctv  = _get_traf(phys)
        cm   = cmp_map.get(phys, {})
        pr   = cm.get("cmp_rev")
        pp   = cm.get("cmp_pax")
        pen_c = ra.safe_div(cp, ctv) * 100 if ctv else None
        pen_p = ra.safe_div(pp, ctv) * 100 if ctv and pp else None
        spp_c = ra.safe_div(cr, ctv) if ctv else None
        spp_p = ra.safe_div(pr, ctv) if ctv and pr else None

        rows.append({
            "Performance": phys, "_row_type": RT_TERMINAL,
            "cur_rev": cr,  "cmp_rev":  pr,
            "rev_yoy": ra.pct_change(cr, pr),
            "cur_pax": cp,  "cmp_pax":  pp,
            "pax_yoy": ra.pct_change(cp, pp),
            "cur_traffic": ctv, "cmp_traffic": ctv,
            "traffic_chg": None,
            "pen_cur": pen_c, "pen_cmp": pen_p,
            "pen_chg": ra.pct_change(pen_c, pen_p),
            "spp_cur": spp_c, "spp_cmp": spp_p,
            "spp_chg": ra.pct_change(spp_c, spp_p),
            "aop": None, "aop_var": None,
        })
    return rows


# ---------------------------------------------------------------------------
# Column builders — PAX comparison first, then Revenue, Traffic, PEN, SPP
# ---------------------------------------------------------------------------
def _build_columns(rows: list[dict], cur_label: str, cmp_label: str):
    """
    Returns (display_rows, col_order, pct_cols) based on whether
    comparison data exists in any row.
    """
    has_cmp = any(r.get("cmp_rev") is not None or r.get("cmp_pax") is not None
                  for r in rows if not r.get("_row_type") == RT_TERMINAL or True)
    has_traffic = any(r.get("cur_traffic") is not None for r in rows)
    has_aop = any(r.get("aop") is not None for r in rows)

    def _fm(v):   return format_money(v) if v else "—"
    def _fp(v):   return format_pax(v)   if v else "—"
    def _fpct(v):
        if v is None or (isinstance(v, float) and v != v): return "—"
        return format_pct(v)
    def _fpen(v): return f"{v:.2f}%" if v is not None and v == v else "—"
    def _fs(v):   return format_spp(v)  if v else "—"

    display_rows = []
    for r in rows:
        rt = r.get("_row_type", RT_OUTLET)
        label = r.get("Performance", "")
        if rt in (RT_OUTLET, RT_TERMINAL):
            label = f"    {label.strip()}"

        row_out = {"Outlet / Category": label}

        # PAX first (with comparison)
        row_out[f"PAX ({cur_label})"] = _fp(r.get("cur_pax"))
        if has_cmp:
            row_out[f"PAX ({cmp_label})"] = _fp(r.get("cmp_pax"))
            row_out["PAX Chg %"] = _fpct(r.get("pax_yoy"))

        # Revenue
        row_out[f"Revenue ({cur_label})"] = _fm(r.get("cur_rev"))
        if has_cmp:
            row_out[f"Revenue ({cmp_label})"] = _fm(r.get("cmp_rev"))
            row_out["Rev Chg %"] = _fpct(r.get("rev_yoy"))

        # Traffic
        if has_traffic:
            row_out[f"Traffic ({cur_label})"] = _fp(r.get("cur_traffic"))
            if has_cmp:
                row_out[f"Traffic ({cmp_label})"] = _fp(r.get("cmp_traffic"))
                row_out["Traffic Chg %"] = _fpct(r.get("traffic_chg"))

        # Penetration %
        if has_traffic:
            row_out[f"PEN % ({cur_label})"] = _fpen(r.get("pen_cur"))
            if has_cmp:
                row_out[f"PEN % ({cmp_label})"] = _fpen(r.get("pen_cmp"))
                row_out["PEN Chg %"] = _fpct(r.get("pen_chg"))

        # SPP
        if has_traffic:
            row_out[f"SPP ({cur_label})"] = _fs(r.get("spp_cur"))
            if has_cmp:
                row_out[f"SPP ({cmp_label})"] = _fs(r.get("spp_cmp"))
                row_out["SPP Chg %"] = _fpct(r.get("spp_chg"))

        # AOP + Variance
        if has_aop:
            row_out["AOP"] = _fm(r.get("aop")) if r.get("aop") else "—"
            row_out["Variance"] = _fpct(r.get("aop_var"))

        display_rows.append(row_out)

    # Build ordered column list
    col_order = ["Outlet / Category",
                 f"PAX ({cur_label})"]
    if has_cmp:
        col_order += [f"PAX ({cmp_label})", "PAX Chg %"]
    col_order += [f"Revenue ({cur_label})"]
    if has_cmp:
        col_order += [f"Revenue ({cmp_label})", "Rev Chg %"]
    if has_traffic:
        col_order += [f"Traffic ({cur_label})"]
        if has_cmp:
            col_order += [f"Traffic ({cmp_label})", "Traffic Chg %"]
        col_order += [f"PEN % ({cur_label})"]
        if has_cmp:
            col_order += [f"PEN % ({cmp_label})", "PEN Chg %"]
        col_order += [f"SPP ({cur_label})"]
        if has_cmp:
            col_order += [f"SPP ({cmp_label})", "SPP Chg %"]
    if has_aop:
        col_order += ["AOP", "Variance"]

    pct_cols = [c for c in col_order if c.endswith("Chg %") or c == "Variance"]
    return display_rows, col_order, pct_cols


# ---------------------------------------------------------------------------
# Render one table
# ---------------------------------------------------------------------------
def _render_table(rows: list[dict], cur_label: str, cmp_label: str):
    if not rows:
        st.info("No data for this period.")
        return

    display_rows, col_order, pct_cols = _build_columns(rows, cur_label, cmp_label)
    row_types = [r.get("_row_type", RT_OUTLET) for r in rows]

    df = pd.DataFrame(display_rows)
    # ensure all columns exist
    for c in col_order:
        if c not in df.columns:
            df[c] = "—"
    df = df[col_order]

    def _row_style(row):
        rt = row_types[row.name]
        if rt == RT_GRAND:
            s = ("font-weight: bold; background-color: #1e3a5f; "
                 "color: white; border-top: 2px solid #0f2744;")
        elif rt == RT_TOTAL:
            s = ("font-weight: bold; background-color: #dbeafe; "
                 "color: #1e40af; border-top: 1px solid #93c5fd;")
        else:
            s = ""
        return [s] * len(row)

    def _pct_color(v):
        if isinstance(v, str) and v.startswith("+"):
            return "color: #16a34a; font-weight: 600"
        if isinstance(v, str) and v.startswith("-"):
            return "color: #dc2626; font-weight: 600"
        return ""

    styled = df.style.apply(_row_style, axis=1)
    for col in pct_cols:
        if col in df.columns:
            styled = styled.map(_pct_color, subset=[col])

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Outlet / Category": st.column_config.TextColumn(
                "Outlet / Category", width="large", pinned=True
            ),
        },
        column_order=col_order,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def render_ehpl_location(
    location: str,
    all_rows: list[dict],
    cur_df: pd.DataFrame,
    cmp_df: "pd.DataFrame | None",
    cur_label: str,
    cmp_label: str,
    sort_order: str = "Descending",   # kept for signature compat; always descending
):
    if not all_rows:
        st.info(f"No EHPL data for {location} in this period.")
        return

    loc_norm = location.title()
    if loc_norm == "Delhi":
        sections = DELHI_SECTIONS
    elif loc_norm == "Hyderabad":
        sections = HYD_SECTIONS
    elif loc_norm == "Bhogapuram":
        sections = BHOGAPURAM_SECTIONS
    else:
        sections = GOA_SECTIONS

    st.caption(
        f"Current: {cur_label}.  Compare: {cmp_label}.  "
        "AOP Variance = (Revenue - AOP Target) / AOP Target.  "
        "PEN % = PAX / Terminal Traffic x 100.  "
        "Outlets sorted by Revenue (highest first)."
    )

    table_rows = _build_table_rows(all_rows, sections)
    _render_table(table_rows, cur_label, cmp_label)

    # Terminal-wise — separate table
    st.markdown("##### Terminal-wise Performance")
    terminal_rows = _get_terminal_rows(location, cur_df, cmp_df)
    if terminal_rows:
        _render_table(terminal_rows, cur_label, cmp_label)
        st.caption(
            "PEN % = PAX / Terminal Traffic x 100.  "
            "SPP = Revenue / Terminal Traffic."
        )
    else:
        st.info("No terminal data available for this location and period.")
