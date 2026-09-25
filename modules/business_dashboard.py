"""
modules/business_dashboard.py
==============================
Reusable business dashboard engine for EHPL, Encalm Eats, Sky Plates.

Architecture
------------
    _build_location_report()   <- exact copy from 8_Business_Performance.py
    _subtotal_traffic()        <- exact copy from 8_Business_Performance.py
    _render_mis_table()        <- exact copy from 8_Business_Performance.py
    render_kpi_cards()         <- location-total KPI cards
    render_ehpl_page()         <- EHPL full layout (with terminal section)
    render_subsidiary_page()   <- Encalm Eats / Sky Plates (no terminals)

All calculation logic is imported from existing modules.
Nothing is hardcoded — all values come from the database.
"""
from __future__ import annotations

import calendar as _cal
import datetime as dt
import traceback as _tb

import pandas as pd
import streamlit as st

from modules import comparison_widget, database, date_picker, revenue_analysis as ra
from modules.formatting import format_money, format_pax, format_pct, format_spp
from modules.outlet_groups import (
    DELHI_GROUPS, DELHI_SUBTOTALS, DELHI_ROW_ORDER,
    HYD_GROUPS, HYD_SUBTOTALS, HYD_ROW_ORDER,
    GOA_GROUPS, GOA_SUBTOTALS, GOA_ROW_ORDER,
    get_display_name,
)
from modules.session import bootstrap_session, default_active_date, set_active_date
from modules.app_logger import log_exception, show_friendly_error
from modules.auth import require_login, render_user_badge
from modules import table_style
from modules import charts, ui
from modules.cached_db import get_available_dates as _cached_available_dates
from modules.cached_db import load_for_date_range as _cached_load_range

LOCATIONS = ["All Locations", "Delhi", "Hyderabad", "Goa", "Bhogapuram"]

# Canonical display order — Delhi first, then Hyderabad, Goa, Bhogapuram
_LOCATION_ORDER = ["Delhi", "Hyderabad", "Goa", "Bhogapuram"]

def _sort_locations(locs: list[str]) -> list[str]:
    """Sort locations in canonical order. Unknowns appended at end."""
    order = {l: i for i, l in enumerate(_LOCATION_ORDER)}
    return sorted(locs, key=lambda l: order.get(l, 99))


# Groups whose traffic covers the WHOLE AIRPORT — exact copy from page 8
_ALL_AIRPORT_GROUPS: frozenset[str] = frozenset({
    "Atithya (M&G)",
    "Atithya",
})


# ---------------------------------------------------------------------------
# _subtotal_traffic — exact copy from 8_Business_Performance.py
# ---------------------------------------------------------------------------
def _subtotal_traffic(
    source_groups: list[str],
    group_traffic_map: dict[str, float | None],
) -> float | None:
    values = [v for g in source_groups
              if (v := group_traffic_map.get(g)) is not None]
    if not values:
        return None
    unique_vals = list(dict.fromkeys(values))
    if len(unique_vals) == 1:
        return unique_vals[0]
    if any(g in _ALL_AIRPORT_GROUPS for g in source_groups):
        return max(unique_vals)
    max_val = max(unique_vals)
    total = sum(unique_vals)
    if max_val >= 0.8 * total:
        return max_val
    return total


# ---------------------------------------------------------------------------
# _build_location_report — exact copy from 8_Business_Performance.py
# ---------------------------------------------------------------------------
def _build_location_report(
    location: str,
    groups: dict[str, list[str]],
    subtotals: list[tuple[str, list[str]]],
    row_order: list[str],
    cur_df: pd.DataFrame,
    cmp_df: pd.DataFrame | None,
    aop_df_loc: pd.DataFrame | None,
) -> list[dict]:
    if cur_df.empty:
        return []

    from modules.database import canonicalize_outlet_name as _co
    from modules.outlet_groups import get_display_name as _gdn

    cur_agg = cur_df.groupby("outlet", as_index=False).agg(
        revenue=("revenue", "sum"), pax=("pax", "sum")
    )
    cmp_agg = (
        cmp_df.groupby("outlet", as_index=False).agg(
            revenue=("revenue", "sum"), pax=("pax", "sum")
        )
        if cmp_df is not None and not cmp_df.empty
        else pd.DataFrame(columns=["outlet", "revenue", "pax"])
    )

    aop_map: dict[str, float] = {}
    if aop_df_loc is not None and not aop_df_loc.empty and "aop" in aop_df_loc.columns:
        aop_map = aop_df_loc.groupby("outlet")["aop"].sum().to_dict()
        for raw_outlet, val in list(aop_map.items()):
            canon = _co(raw_outlet)
            if canon not in aop_map:
                aop_map[canon] = val

    def _cur(outlet):
        rows = cur_agg[cur_agg["outlet"] == outlet]
        if not rows.empty:
            return rows
        canon = _co(outlet)
        if canon != outlet:
            rows = cur_agg[cur_agg["outlet"] == canon]
            if not rows.empty:
                return rows
        disp = _gdn(outlet, location)
        if disp != outlet and disp != canon:
            rows = cur_agg[cur_agg["outlet"] == disp]
        return rows

    def _cmp(outlet):
        rows = cmp_agg[cmp_agg["outlet"] == outlet]
        if not rows.empty:
            return rows
        canon = _co(outlet)
        if canon != outlet:
            rows = cmp_agg[cmp_agg["outlet"] == canon]
            if not rows.empty:
                return rows
        disp = _gdn(outlet, location)
        if disp != outlet and disp != canon:
            rows = cmp_agg[cmp_agg["outlet"] == disp]
        return rows

    subtotal_label_set = {s[0] for s in subtotals}
    group_totals: dict[str, dict] = {}
    group_traffic_cur: dict[str, float | None] = {}
    group_traffic_cmp: dict[str, float | None] = {}

    try:
        _outlet_traf_cur = database.join_revenue_with_traffic_by_outlet(cur_df)
        _outlet_traf_cmp = database.join_revenue_with_traffic_by_outlet(cmp_df) \
            if cmp_df is not None and not cmp_df.empty else pd.DataFrame()
    except Exception:
        _outlet_traf_cur = pd.DataFrame()
        _outlet_traf_cmp = pd.DataFrame()

    def _build_traffic_lookup(ot_df: pd.DataFrame) -> dict[str, float | None]:
        if ot_df is None or ot_df.empty or "traffic" not in ot_df.columns:
            return {}
        return {
            str(row["outlet"]): (float(row["traffic"]) if pd.notna(row["traffic"]) else None)
            for _, row in ot_df.iterrows()
        }

    _traf_cur_lookup = _build_traffic_lookup(_outlet_traf_cur)
    _traf_cmp_lookup = _build_traffic_lookup(_outlet_traf_cmp)

    seen_display: set[str] = set()
    all_rows: list[dict] = []

    for _gk in row_order:
        if _gk not in {s[0] for s in subtotals} and _gk in groups:
            group_totals[_gk] = {
                "cur_rev": 0, "cmp_rev": 0, "cur_pax": 0, "cmp_pax": 0, "aop": 0
            }
            group_traffic_cur[_gk] = None
            group_traffic_cmp[_gk] = None

    for group_key in row_order:
        sub_def = next((s for s in subtotals if s[0] == group_key), None)
        if sub_def is not None:
            sub_label, src_groups = sub_def
            sub_cur_rev = sum(group_totals.get(g, {}).get("cur_rev", 0) for g in src_groups)
            sub_cmp_rev = sum(group_totals.get(g, {}).get("cmp_rev", 0) for g in src_groups)
            sub_cur_pax = sum(group_totals.get(g, {}).get("cur_pax", 0) for g in src_groups)
            sub_cmp_pax = sum(group_totals.get(g, {}).get("cmp_pax", 0) for g in src_groups)
            sub_aop     = sum(group_totals.get(g, {}).get("aop", 0) for g in src_groups)
            sub_cur_traf = _subtotal_traffic(src_groups, group_traffic_cur)
            sub_cmp_traf = _subtotal_traffic(src_groups, group_traffic_cmp)

            sub_pen_cur = ra.safe_div(sub_cur_pax, sub_cur_traf) * 100 if sub_cur_traf else None
            sub_pen_cmp = ra.safe_div(sub_cmp_pax, sub_cmp_traf) * 100 if sub_cmp_traf else None
            sub_spp_cur = ra.safe_div(sub_cur_rev, sub_cur_traf) if sub_cur_traf else None
            sub_spp_cmp = ra.safe_div(sub_cmp_rev, sub_cmp_traf) if sub_cmp_traf else None

            is_grand = sub_label in ("TOTAL EHPL", "TOTAL", "Total")
            all_rows.append({
                "Performance":  sub_label,
                "_is_subtotal": True,
                "_is_grand":    is_grand,
                "_section":     None,
                "cur_rev": sub_cur_rev, "cmp_rev": sub_cmp_rev or None,
                "rev_yoy": ra.pct_change(sub_cur_rev, sub_cmp_rev or None),
                "cur_pax": sub_cur_pax, "cmp_pax": sub_cmp_pax or None,
                "pax_yoy": ra.pct_change(sub_cur_pax, sub_cmp_pax or None),
                "cur_traffic": sub_cur_traf, "cmp_traffic": sub_cmp_traf,
                "traffic_chg": ra.pct_change(sub_cur_traf, sub_cmp_traf),
                "pen_cur": sub_pen_cur, "pen_cmp": sub_pen_cmp,
                "pen_chg": ra.pct_change(sub_pen_cur, sub_pen_cmp),
                "spp_cur": sub_spp_cur, "spp_cmp": sub_spp_cmp,
                "spp_chg": ra.pct_change(sub_spp_cur, sub_spp_cmp),
                "aop": sub_aop or None,
                "aop_var": ra.pct_change(sub_cur_rev, sub_aop) if sub_aop else None,
            })
            continue

        if group_key not in groups:
            continue
        outlets = groups[group_key]
        g_rows: list[dict] = []

        for outlet in outlets:
            cur_row = _cur(outlet)
            if cur_row.empty:
                continue
            cur_rev = float(cur_row["revenue"].sum())
            cur_pax = float(cur_row["pax"].sum())
            cmp_row = _cmp(outlet)
            cmp_rev = float(cmp_row["revenue"].sum()) if not cmp_row.empty else None
            cmp_pax = float(cmp_row["pax"].sum()) if not cmp_row.empty else None
            if cur_rev == 0 and (cmp_rev is None or cmp_rev == 0):
                continue

            display = get_display_name(outlet, location)
            if display in seen_display:
                continue
            seen_display.add(display)

            traf_c = (_traf_cur_lookup.get(outlet) or
                      _traf_cur_lookup.get(_co(outlet)) or
                      _traf_cur_lookup.get(_gdn(outlet, location)))
            traf_p = (_traf_cmp_lookup.get(outlet) or
                      _traf_cmp_lookup.get(_co(outlet)) or
                      _traf_cmp_lookup.get(_gdn(outlet, location)))

            pen_c = ra.safe_div(cur_pax, traf_c) * 100 if traf_c else None
            pen_p = ra.safe_div(cmp_pax, traf_p) * 100 if traf_p else None
            spp_c = ra.safe_div(cur_rev, traf_c) if traf_c else None
            spp_p = ra.safe_div(cmp_rev, traf_p) if traf_p else None
            aop = (aop_map.get(outlet) or
                   aop_map.get(_co(outlet)) or
                   aop_map.get(_gdn(outlet, location)))

            row = {
                "Performance":  f"  {display}",
                "_is_subtotal": False,
                "_is_grand":    False,
                "_section":     group_key,
                "cur_rev": cur_rev, "cmp_rev": cmp_rev,
                "rev_yoy": ra.pct_change(cur_rev, cmp_rev),
                "cur_pax": cur_pax, "cmp_pax": cmp_pax,
                "pax_yoy": ra.pct_change(cur_pax, cmp_pax),
                "cur_traffic": traf_c, "cmp_traffic": traf_p,
                "traffic_chg": ra.pct_change(traf_c, traf_p),
                "pen_cur": pen_c, "pen_cmp": pen_p,
                "pen_chg": ra.pct_change(pen_c, pen_p),
                "spp_cur": spp_c, "spp_cmp": spp_p,
                "spp_chg": ra.pct_change(spp_c, spp_p),
                "aop": aop,
                "aop_var": ra.pct_change(cur_rev, aop) if aop else None,
            }
            g_rows.append(row)
            all_rows.append(row)

        if g_rows:
            group_totals[group_key] = {
                "cur_rev": sum(r["cur_rev"] or 0 for r in g_rows),
                "cmp_rev": sum(r["cmp_rev"] or 0 for r in g_rows if r["cmp_rev"]),
                "cur_pax": sum(r["cur_pax"] or 0 for r in g_rows),
                "cmp_pax": sum(r["cmp_pax"] or 0 for r in g_rows if r["cmp_pax"]),
                "aop":     sum(r["aop"] or 0 for r in g_rows if r["aop"]),
            }
            group_traffic_cur[group_key] = next(
                (r["cur_traffic"] for r in g_rows if r["cur_traffic"]), None
            )
            group_traffic_cmp[group_key] = next(
                (r["cmp_traffic"] for r in g_rows if r["cmp_traffic"]), None
            )

    return all_rows


# ---------------------------------------------------------------------------
# _render_mis_table — exact copy from 8_Business_Performance.py
# ---------------------------------------------------------------------------
def _render_mis_table(rows: list[dict], cur_label: str, cmp_label: str, location: str = ""):
    if not rows:
        st.info("No data for this period.")
        return

    df = pd.DataFrame(rows)
    has_traffic = df["cur_traffic"].notna().any()
    has_aop     = df["aop"].notna().any()

    def _fmt_pct(v):
        if v is None or (isinstance(v, float) and v != v):
            return "—"
        return format_pct(v)

    def _fmt_money(v): return format_money(v) if v else "—"
    def _fmt_pax(v):   return format_pax(v)   if v else "—"
    def _fmt_pen(v):   return f"{v:.2f}%" if v and v == v else "—"
    def _fmt_spp(v):   return format_spp(v)   if v else "—"
    def _fmt_traf(v):  return format_pax(v)   if v else "—"

    out = df.copy()
    out[f"Rev ({cur_label})"] = out["cur_rev"].apply(_fmt_money)
    out[f"Rev ({cmp_label})"] = out["cmp_rev"].apply(_fmt_money)
    out["Rev YOY%"]           = out["rev_yoy"].apply(_fmt_pct)
    out[f"PAX ({cur_label})"] = out["cur_pax"].apply(_fmt_pax)
    out[f"PAX ({cmp_label})"] = out["cmp_pax"].apply(_fmt_pax)
    out["PAX YOY%"]           = out["pax_yoy"].apply(_fmt_pct)

    display_cols = [
        "Performance",
        f"Rev ({cur_label})", f"Rev ({cmp_label})", "Rev YOY%",
    ]

    if has_aop:
        out["AOP Target"] = out["aop"].apply(_fmt_money)
        out["AOP Var %"]  = out["aop_var"].apply(_fmt_pct)
        display_cols += ["AOP Target", "AOP Var %"]

    display_cols += [f"PAX ({cur_label})", f"PAX ({cmp_label})", "PAX YOY%"]

    if has_traffic:
        out[f"Traffic ({cur_label})"] = out["cur_traffic"].apply(_fmt_traf)
        out[f"Traffic ({cmp_label})"] = out["cmp_traffic"].apply(_fmt_traf)
        out["Traffic Δ%"]             = out["traffic_chg"].apply(_fmt_pct)
        out[f"PEN % ({cur_label})"]   = out["pen_cur"].apply(_fmt_pen)
        out[f"PEN % ({cmp_label})"]   = out["pen_cmp"].apply(_fmt_pen)
        out["PEN Δ%"]                 = out["pen_chg"].apply(_fmt_pct)
        out[f"SPP ({cur_label})"]     = out["spp_cur"].apply(_fmt_spp)
        out[f"SPP ({cmp_label})"]     = out["spp_cmp"].apply(_fmt_spp)
        out["SPP Δ%"]                 = out["spp_chg"].apply(_fmt_pct)
        display_cols += [
            f"Traffic ({cur_label})", f"Traffic ({cmp_label})", "Traffic Δ%",
            f"PEN % ({cur_label})", f"PEN % ({cmp_label})", "PEN Δ%",
            f"SPP ({cur_label})", f"SPP ({cmp_label})", "SPP Δ%",
        ]

    pct_cols = [c for c in ["Rev YOY%", "PAX YOY%", "Traffic Δ%",
                              "PEN Δ%", "SPP Δ%", "AOP Var %"]
                if c in out.columns]

    display_df = out[display_cols].reset_index(drop=True)

    def _style_rows(s):
        styles = []
        for i in range(len(s)):
            is_sub   = df.iloc[i]["_is_subtotal"]
            is_grand = df.iloc[i]["_is_grand"]
            if is_grand:
                styles.append(
                    "font-weight: bold; border-top: 2px solid #ccc; "
                    "background-color: #f0f4ff;"
                )
            elif is_sub:
                styles.append("font-weight: bold;")
            else:
                styles.append("")
        return styles

    pct_green_red = {
        col: lambda v: (
            "color: #16a34a" if isinstance(v, str) and v.startswith("+")
            else ("color: #dc2626" if isinstance(v, str) and v.startswith("-") else "")
        )
        for col in pct_cols
    }

    styled = display_df.style.apply(
        lambda _: _style_rows(display_df["Performance"]), axis=0
    )
    for col, fn in pct_green_red.items():
        if col in display_df.columns:
            styled = styled.map(fn, subset=[col])

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Performance": st.column_config.TextColumn(
                "Performance", width="medium", pinned=True
            ),
        },
        column_order=display_cols,
    )

    if has_traffic:
        st.caption(
            "PEN % = PAX / Terminal Traffic x 100.  "
            "SPP = Revenue / Terminal Traffic.  "
            "Traffic = outlet's assigned terminal pool."
        )


# ---------------------------------------------------------------------------
# AOP loader (shared)
# ---------------------------------------------------------------------------
def _load_aop(ranges: dict) -> pd.DataFrame:
    try:
        _raw_aop = database.load_aop_targets_for_range(
            ranges["current_start"], ranges["current_end"]
        )
        if _raw_aop is not None and not _raw_aop.empty:
            _year          = ranges["current_start"].year
            _month         = ranges["current_start"].month
            _days_in_month = _cal.monthrange(_year, _month)[1]
            _days_selected = (ranges["current_end"] - ranges["current_start"]).days + 1
            _prorate       = min(_days_selected / _days_in_month, 1.0)
            _raw_aop["aop"] = pd.to_numeric(_raw_aop["aop"], errors="coerce") * _prorate
            _raw_aop = _raw_aop[_raw_aop["aop"].notna() & (_raw_aop["aop"] > 0)]
            from modules.database import canonicalize_outlet_name as _co_aop
            _raw_aop["location"] = _raw_aop["location"].astype(str).str.strip().str.title()
            _raw_aop["outlet"]   = _raw_aop["outlet"].astype(str).str.strip().apply(_co_aop)
            return _raw_aop[["location", "outlet", "aop"]].copy()
    except Exception:
        pass
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# KPI card row — location total
# ---------------------------------------------------------------------------
def _render_kpi_cards(
    cur_df: pd.DataFrame,
    cmp_df: pd.DataFrame | None,
    aop_df_loc: pd.DataFrame | None,
    cur_label: str,
    cmp_label: str,
    show_traffic: bool = True,
):
    if cur_df is None or cur_df.empty:
        return

    cur_rev = float(cur_df["revenue"].sum())
    cur_pax = float(cur_df["pax"].sum())
    cmp_rev = float(cmp_df["revenue"].sum()) if (cmp_df is not None and not cmp_df.empty) else None
    cmp_pax = float(cmp_df["pax"].sum())     if (cmp_df is not None and not cmp_df.empty) else None

    aop_total = None
    if aop_df_loc is not None and not aop_df_loc.empty and "aop" in aop_df_loc.columns:
        aop_total = float(aop_df_loc["aop"].sum())

    cur_traf = None
    if show_traffic:
        try:
            tdf = database.join_revenue_with_traffic_by_outlet(cur_df)
            if tdf is not None and not tdf.empty and "traffic" in tdf.columns:
                # Deduplicate traffic pools — sum unique values per location
                cur_traf = float(tdf.drop_duplicates(subset=["traffic"])["traffic"].sum())
        except Exception:
            pass

    rev_chg = ra.pct_change(cur_rev, cmp_rev)
    pax_chg = ra.pct_change(cur_pax, cmp_pax)
    aop_var = ra.pct_change(cur_rev, aop_total) if aop_total else None
    pen     = ra.safe_div(cur_pax, cur_traf) * 100 if cur_traf else None
    spp     = ra.safe_div(cur_rev, cur_traf) if cur_traf else None

    ui.section("Overview")
    # One card per metric in a single row. Labels stay short so they never
    # truncate; the period is in the summary line above and in each tooltip.
    cards = [
        dict(label="Revenue", value=format_money(cur_rev),
             delta=format_pct(rev_chg) if rev_chg is not None else None,
             help=f"{cur_label}. Compare period ({cmp_label}): "
                  f"{format_money(cmp_rev) if cmp_rev else '—'}"),
        dict(label="PAX", value=format_pax(cur_pax),
             delta=format_pct(pax_chg) if pax_chg is not None else None,
             help=f"{cur_label}. Compare period ({cmp_label}): "
                  f"{format_pax(cmp_pax) if cmp_pax else '—'}"),
    ]
    if aop_total:
        cards.append(dict(
            label="AOP Target", value=format_money(aop_total),
            delta=(f"{format_pct(aop_var)} vs AOP" if aop_var is not None else None),
            help="Prorated AOP target for this period; delta is revenue variance vs AOP",
        ))
    else:
        cards.append(dict(label="AOP Target", value="—", help="No AOP target data for this period"))

    if show_traffic:
        cards += [
            dict(label="Traffic", value=format_pax(cur_traf) if cur_traf else "—",
                 help="Terminal traffic for this location"),
            dict(label="PEN %", value=f"{pen:.2f}%" if pen is not None else "—",
                 help="PAX / Traffic x 100"),
            dict(label="SPP", value=format_spp(spp) if spp is not None else "—",
                 help="Revenue / Traffic"),
        ]
    else:
        cards.append(dict(label="PAX (compare)",
                          value=format_pax(cmp_pax) if cmp_pax else "—", help=cmp_label))

    # Up to 4 cards fit on one row; 5–6 cards wrap into rows of 3 so the
    # rupee values are never truncated.
    per_row = len(cards) if len(cards) <= 4 else 3
    for i in range(0, len(cards), per_row):
        for col, card in zip(st.columns(per_row), cards[i:i + per_row]):
            with col:
                st.metric(card["label"], card["value"], delta=card.get("delta"),
                          help=card.get("help"))


# ---------------------------------------------------------------------------
# Terminal-wise section (EHPL only)
# ---------------------------------------------------------------------------
def _render_terminal_section(
    location: str,
    cur_df: pd.DataFrame,
    cmp_df: pd.DataFrame | None,
    cur_label: str,
    cmp_label: str,
):
    ui.section("Terminal-wise Performance")

    if cur_df is None or cur_df.empty:
        st.info("No data for terminal analysis.")
        return

    try:
        outlet_traf = database.join_revenue_with_traffic_by_outlet(cur_df)
        cmp_outlet_traf = database.join_revenue_with_traffic_by_outlet(cmp_df) \
            if (cmp_df is not None and not cmp_df.empty) else pd.DataFrame()
    except Exception:
        st.info("Terminal data not available.")
        return

    if outlet_traf is None or outlet_traf.empty:
        st.info("No terminal data available for this location and period.")
        return

    # Aggregate by terminal label from terminal_mapping
    try:
        from modules import terminal_mapping as tm

        def _get_term(row):
            try:
                t = tm.get_terminal_for_outlet(str(row["outlet"]), location.title())
                return t if t else "Other"
            except Exception:
                return "Other"

        outlet_traf["_terminal"] = outlet_traf.apply(_get_term, axis=1)
        skip = {"Other", "Unmapped", "", "None", "nan"}
        display_df = outlet_traf[~outlet_traf["_terminal"].astype(str).isin(skip)].copy()

        if display_df.empty:
            # Fallback: show raw outlet-level traffic
            rows = []
            for _, row in outlet_traf.iterrows():
                traf = row.get("traffic")
                rev  = row.get("revenue", 0) or 0
                pax  = row.get("pax", 0) or 0
                traf_v = float(traf) if traf is not None and pd.notna(traf) else None
                pen  = ra.safe_div(pax, traf_v) * 100 if traf_v else None
                spp  = ra.safe_div(rev, traf_v) if traf_v else None
                rows.append({
                    "Outlet": str(row.get("outlet", "")),
                    f"Rev ({cur_label})": format_money(rev) if rev else "—",
                    "Traffic": format_pax(traf_v) if traf_v else "—",
                    "PEN %": f"{pen:.2f}%" if pen is not None else "—",
                    "SPP": format_spp(spp) if spp is not None else "—",
                })
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info("No terminal breakdown available for this location.")
            return

        def _agg(grp):
            rev  = grp["revenue"].sum()
            pax  = grp["pax"].sum()
            tvs  = grp["traffic"].dropna().unique()
            traf = float(max(tvs)) if len(tvs) > 0 else None
            return pd.Series({"revenue": rev, "pax": pax, "traffic": traf})

        term_agg = display_df.groupby("_terminal").apply(_agg).reset_index()
        term_agg = term_agg.sort_values("revenue", ascending=False)

        # Compare period
        cmp_term_map: dict = {}
        if not cmp_outlet_traf.empty:
            cmp_outlet_traf["_terminal"] = cmp_outlet_traf.apply(_get_term, axis=1)
            cmp_disp = cmp_outlet_traf[
                ~cmp_outlet_traf["_terminal"].astype(str).isin(skip)
            ]
            if not cmp_disp.empty:
                cmp_agg_df = cmp_disp.groupby("_terminal").apply(_agg).reset_index()
                cmp_term_map = {
                    row["_terminal"]: {
                        "revenue": row["revenue"],
                        "traffic": row["traffic"],
                    }
                    for _, row in cmp_agg_df.iterrows()
                }

        rows = []
        for _, row in term_agg.iterrows():
            term  = str(row["_terminal"])
            rev   = float(row.get("revenue") or 0)
            pax   = float(row.get("pax") or 0)
            traf  = row.get("traffic")
            tv    = float(traf) if traf is not None and not pd.isna(traf) else None
            pen   = ra.safe_div(pax, tv) * 100 if tv else None
            spp   = ra.safe_div(rev, tv) if tv else None
            cmp_d = cmp_term_map.get(term, {})
            cmp_r = cmp_d.get("revenue")
            rev_chg = ra.pct_change(rev, cmp_r) if cmp_r else None
            r = {
                "Terminal": term,
                f"Rev ({cur_label})": format_money(rev) if rev else "—",
                "Traffic": format_pax(tv) if tv else "—",
                "PEN %": f"{pen:.2f}%" if pen is not None else "—",
                "SPP": format_spp(spp) if spp is not None else "—",
            }
            if cmp_r is not None:
                r[f"Rev ({cmp_label})"] = format_money(cmp_r)
                r["Rev Chg %"] = format_pct(rev_chg) if rev_chg is not None else "—"
            rows.append(r)

        if rows:
            term_df = pd.DataFrame(rows)
            pct_cols = [c for c in ["Rev Chg %"] if c in term_df.columns]
            st.dataframe(
                table_style.style_pct_columns(term_df, pct_cols),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Terminal": st.column_config.TextColumn("Terminal", width="medium"),
                },
            )
            st.caption("PEN % = PAX / Terminal Traffic x 100.  SPP = Revenue / Traffic.")
        else:
            st.info("No terminal breakdown available.")

    except Exception as e:
        log_exception(e, context=f"Terminal section {location}")
        st.info("Terminal data not available for this location.")


# ---------------------------------------------------------------------------
# Subsidiary page table (Encalm Eats / Sky Plates)
# ---------------------------------------------------------------------------
def _render_subsidiary_table(
    segment: str,
    location_label: str,
    cur_df: pd.DataFrame,
    cmp_df: pd.DataFrame | None,
    aop_df_loc: pd.DataFrame | None,
    cur_label: str,
    cmp_label: str,
):
    """Simple outlet table for non-airport businesses. No terminal columns."""
    if cur_df is None or cur_df.empty:
        st.info(f"No {segment} data for {location_label} in this period.")
        return

    cur_agg = cur_df.groupby("outlet", as_index=False).agg(
        revenue=("revenue", "sum"), pax=("pax", "sum")
    ).sort_values("revenue", ascending=False)

    cmp_agg = (
        cmp_df.groupby("outlet", as_index=False).agg(
            revenue=("revenue", "sum"), pax=("pax", "sum")
        ) if (cmp_df is not None and not cmp_df.empty) else pd.DataFrame()
    )

    # AOP map
    aop_map: dict[str, float] = {}
    if aop_df_loc is not None and not aop_df_loc.empty and "aop" in aop_df_loc.columns:
        aop_map = aop_df_loc.groupby("outlet")["aop"].sum().to_dict()

    rows: list[dict] = []
    totals = {"cur_rev": 0.0, "cmp_rev": 0.0, "cur_pax": 0.0, "cmp_pax": 0.0, "aop": 0.0}
    has_cmp = False
    has_aop = bool(aop_map)

    for _, outlet_row in cur_agg.iterrows():
        outlet  = str(outlet_row["outlet"])
        cur_rev = float(outlet_row["revenue"] or 0)
        cur_pax = float(outlet_row["pax"] or 0)
        if cur_rev == 0:
            continue

        cmp_r = cmp_agg[cmp_agg["outlet"] == outlet] if not cmp_agg.empty else pd.DataFrame()
        cmp_rev = float(cmp_r["revenue"].sum()) if not cmp_r.empty else None
        cmp_pax = float(cmp_r["pax"].sum())     if not cmp_r.empty else None
        if cmp_rev is not None:
            has_cmp = True

        aop_val = aop_map.get(outlet)
        rev_chg = ra.pct_change(cur_rev, cmp_rev)
        pax_chg = ra.pct_change(cur_pax, cmp_pax)
        aop_var = ra.pct_change(cur_rev, aop_val) if aop_val else None

        r = {
            "Performance":  f"  {outlet}",
            "_is_subtotal": False,
            "_is_grand":    False,
        }
        r[f"PAX ({cur_label})"] = format_pax(cur_pax)
        if cmp_pax is not None:
            r[f"PAX ({cmp_label})"] = format_pax(cmp_pax)
        r["PAX Chg %"] = format_pct(pax_chg) if pax_chg is not None else "—"
        r[f"Rev ({cur_label})"] = format_money(cur_rev)
        if cmp_rev is not None:
            r[f"Rev ({cmp_label})"] = format_money(cmp_rev)
        r["Rev Chg %"] = format_pct(rev_chg) if rev_chg is not None else "—"
        if aop_val:
            r["AOP Target"] = format_money(aop_val)
            r["AOP Var %"]  = format_pct(aop_var) if aop_var is not None else "—"

        rows.append(r)
        totals["cur_rev"] += cur_rev
        totals["cur_pax"] += cur_pax
        if cmp_rev: totals["cmp_rev"] += cmp_rev
        if cmp_pax: totals["cmp_pax"] += cmp_pax
        if aop_val: totals["aop"]     += aop_val

    if not rows:
        st.info(f"No {segment} outlet data for {location_label} in this period.")
        return

    # Total row — built from accumulated totals, placed at TOP
    t_rev_chg = ra.pct_change(totals["cur_rev"], totals["cmp_rev"] or None)
    t_pax_chg = ra.pct_change(totals["cur_pax"], totals["cmp_pax"] or None)
    t_aop_var = ra.pct_change(totals["cur_rev"], totals["aop"] or None) if totals["aop"] else None
    total_row: dict = {
        "Performance":  f"TOTAL {segment}",
        "_is_subtotal": True,
        "_is_grand":    True,
    }
    total_row[f"PAX ({cur_label})"] = format_pax(totals["cur_pax"])
    if has_cmp:
        total_row[f"PAX ({cmp_label})"] = format_pax(totals["cmp_pax"]) if totals["cmp_pax"] else "—"
    total_row["PAX Chg %"] = format_pct(t_pax_chg) if t_pax_chg is not None else "—"
    total_row[f"Rev ({cur_label})"] = format_money(totals["cur_rev"])
    if has_cmp:
        total_row[f"Rev ({cmp_label})"] = format_money(totals["cmp_rev"]) if totals["cmp_rev"] else "—"
    total_row["Rev Chg %"] = format_pct(t_rev_chg) if t_rev_chg is not None else "—"
    if has_aop:
        total_row["AOP Target"] = format_money(totals["aop"]) if totals["aop"] else "—"
        total_row["AOP Var %"]  = format_pct(t_aop_var) if t_aop_var is not None else "—"
    # Prepend total at top, outlets below (sorted desc revenue — already done above)
    rows = [total_row] + rows

    display_df = pd.DataFrame(rows)
    meta_cols  = ["_is_subtotal", "_is_grand"]

    # Enforce explicit column order matching EHPL:
    # Performance | PAX (cur) | PAX (cmp) | PAX Chg% | Revenue (cur) | Revenue (cmp) | Rev Chg% | AOP | Variance
    def _ordered_cols(df):
        fixed = ["Performance"]
        # PAX group
        for c in [f"PAX ({cur_label})", f"PAX ({cmp_label})", "PAX Chg %"]:
            if c in df.columns:
                fixed.append(c)
        # Revenue group
        for c in [f"Rev ({cur_label})", f"Rev ({cmp_label})", "Rev Chg %"]:
            if c in df.columns:
                fixed.append(c)
        # AOP
        for c in ["AOP Target", "AOP Var %"]:
            if c in df.columns:
                fixed.append(c)
        return fixed

    show_cols = _ordered_cols(display_df)
    display_df_show = display_df[show_cols].reset_index(drop=True)
    meta = display_df[meta_cols].reset_index(drop=True)

    pct_cols = [c for c in ["Rev Chg %", "PAX Chg %", "AOP Var %"] if c in display_df_show.columns]

    def _style_rows(s):
        styles = []
        for i in range(len(s)):
            if meta.iloc[i]["_is_grand"]:
                styles.append(
                    "font-weight: bold; background-color: #1e3a5f; "
                    "color: white; border-top: 2px solid #0f2744;"
                )
            elif meta.iloc[i]["_is_subtotal"]:
                styles.append("font-weight: bold;")
            else:
                styles.append("")
        return styles

    pct_fn = lambda v: (
        "color: #16a34a" if isinstance(v, str) and v.startswith("+")
        else ("color: #dc2626" if isinstance(v, str) and v.startswith("-") else "")
    )

    styled = display_df_show.style.apply(
        lambda _: _style_rows(display_df_show["Performance"]), axis=0
    )
    for col in pct_cols:
        if col in display_df_show.columns:
            styled = styled.map(pct_fn, subset=[col])

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Performance": st.column_config.TextColumn("Performance", width="medium", pinned=True),
        },
        column_order=show_cols,
    )


# ---------------------------------------------------------------------------
# Common filter + data load block
# ---------------------------------------------------------------------------
def _render_filters_and_load(page_key: str, available_dates: list | None = None):
    """
    Render Date + Location + Comparison filters.
    Location options are derived from actual data for the selected date.
    Pass `available_dates` to override the default (revenue_master dates) —
    used by Encalm Eats to show only DSR dates.
    Returns (location, ranges, current_df_all, compare_df_all, aop_df).
    """
    # ── Date first (drives which locations are available) ──────────────────
    if available_dates is None:
        available_dates = database.get_available_dates()
    if not available_dates:
        st.info("No data available. Upload a report on the Home page first.")
        st.stop()

    bar = st.container(border=True)
    with bar:
        col_date, col_type, col_loc = st.columns([3, 1.3, 1.3])
        with col_date:
            anchor_date = date_picker.render_date_dropdown(
                available_dates,
                key_prefix=f"{page_key}_anchor",
                label="Report Date",
                default_date=default_active_date(),
                compact=True,
            )
            set_active_date(anchor_date)

        col_cmp, _ = st.columns([3, 2.6])
        with col_cmp:
            ranges = comparison_widget.render_comparison_selector(
                anchor_date, key_prefix=f"{page_key}_cmp",
                type_container=col_type, compact=True,
            )

    # ── Load data ──────────────────────────────────────────────────────────
    current_df_all = database.load_for_date_range(
        ranges["current_start"], ranges["current_end"]
    )
    compare_df_all = database.load_for_date_range(
        ranges["compare_start"], ranges["compare_end"]
    )
    aop_df = _load_aop(ranges)

    # ── Dynamic location filter — only show locations with actual data ─────
    def _available_locs(df: pd.DataFrame) -> list[str]:
        if df.empty or "location" not in df.columns:
            return []
        return sorted(df["location"].str.strip().str.title().unique().tolist())

    cur_locs = _available_locs(current_df_all)
    # Normalise canonical spelling: Bogapuram in DB -> Bhogapuram in UI
    _name_fix = {"Bogapuram": "Bhogapuram"}
    cur_locs = _sort_locations([_name_fix.get(l, l) for l in cur_locs])

    location_options = ["All Locations"] + cur_locs if cur_locs else LOCATIONS

    with col_loc:
        # Preserve previous selection if still valid
        prev_key = f"{page_key}_location"
        prev_val = st.session_state.get(prev_key, "All Locations")
        default_idx = (
            location_options.index(prev_val)
            if prev_val in location_options
            else 0
        )
        location = st.selectbox(
            "Location",
            options=location_options,
            index=default_idx,
            key=prev_key,
        )

    ui.summary_line(ranges["current_label"], ranges["compare_label"], location)
    return location, ranges, current_df_all, compare_df_all, aop_df


def _render_overview_charts(
    cur_df: pd.DataFrame,
    cmp_df: pd.DataFrame | None,
    location: str,
    ranges: dict,
    row_filter,
) -> None:
    """Two charts side by side: revenue by location/outlet (current vs
    compare) and the 30-day daily revenue trend ending on the report date."""
    by = "location" if location == "All Locations" else "outlet"
    # Month/Year-wise periods can end in the future — anchor the trend on
    # the latest date that actually has data inside the current period.
    end = ranges["current_end"]
    try:
        _dates = [d for d in _cached_available_dates() if d <= end]
        if _dates:
            end = max(_dates)
    except Exception:
        pass
    try:
        trend = _cached_load_range(end - dt.timedelta(days=29), end)
        trend = _filter_by_location(row_filter(trend), location)
        if not trend.empty:
            trend = (trend.assign(date=pd.to_datetime(trend["date"]))
                          .groupby("date", as_index=False)["revenue"].sum())
    except Exception as e:
        log_exception(e, context="overview trend chart")
        trend = pd.DataFrame()

    if trend.empty:
        # No daily history for this business (e.g. DSR-only data) — bar only.
        with st.container(border=True):
            charts.revenue_by_group_bar(
                cur_df, cmp_df, by, ranges["current_label"], ranges["compare_label"],
                title=f"Revenue by {by}",
            )
        return

    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        charts.revenue_by_group_bar(
            cur_df, cmp_df, by, ranges["current_label"], ranges["compare_label"],
            title=f"Revenue by {by}",
        )
    with c2, st.container(border=True):
        charts.revenue_trend_line(
            trend, title="Daily revenue — last 30 days", highlight_date=end,
        )


def _filter_by_location(df: pd.DataFrame, location: str) -> pd.DataFrame:
    if df.empty or location == "All Locations":
        return df
    return df[df["location"].str.title() == location.title()].copy()


# ---------------------------------------------------------------------------
# Public: render_ehpl_page
# ---------------------------------------------------------------------------
def render_ehpl_page(page_key: str = "ehpl"):
    require_login()
    bootstrap_session()
    render_user_badge()

    from modules.ehpl_layout import render_ehpl_location
    from modules.outlet_groups import (
        DELHI_GROUPS, DELHI_SUBTOTALS, DELHI_ROW_ORDER,
        HYD_GROUPS, HYD_SUBTOTALS, HYD_ROW_ORDER,
        GOA_GROUPS, GOA_SUBTOTALS, GOA_ROW_ORDER,
        BHOGAPURAM_GROUPS, BHOGAPURAM_SUBTOTALS, BHOGAPURAM_ROW_ORDER,
    )

    ui.page_header(
        "EHPL",
        "Airport hospitality — Lounges, Spa, Nap & Shower, Atithya, "
        "Enwrap, Business Centre, RDC. "
        "PEN % = PAX / Terminal Traffic x 100.  SPP = Revenue / Terminal Traffic.",
    )

    location, ranges, current_df_all, compare_df_all, aop_df = \
        _render_filters_and_load(page_key)

    cur_label = ranges["current_label"]
    cmp_label = ranges["compare_label"]

    _non_ehpl = {"Encalm Eats", "Sky Plates", "Subsidiary"}

    def _ehpl_filter(df):
        if df.empty:
            return df
        if "segment" in df.columns:
            return df[~df["segment"].isin(_non_ehpl)].copy()
        return df

    loc_cur  = _filter_by_location(current_df_all, location)
    loc_cmp  = _filter_by_location(compare_df_all, location)
    ehpl_cur = _ehpl_filter(loc_cur)
    ehpl_cmp = _ehpl_filter(loc_cmp) if not loc_cmp.empty else pd.DataFrame()

    if ehpl_cur.empty:
        st.warning(f"No EHPL data for {location} in the selected period.")
        st.stop()

    cmp_df_arg = ehpl_cmp if not ehpl_cmp.empty else None

    _aop_loc = _filter_by_location(aop_df, location) if not aop_df.empty else None
    _render_kpi_cards(ehpl_cur, cmp_df_arg, _aop_loc, cur_label, cmp_label, show_traffic=True)
    _render_overview_charts(ehpl_cur, cmp_df_arg, location, ranges, _ehpl_filter)

    def _render_one_location(loc_name: str):
        loc_norm = loc_name.title()
        if loc_norm == "Delhi":
            groups, subtotals, row_order = DELHI_GROUPS, DELHI_SUBTOTALS, DELHI_ROW_ORDER
        elif loc_norm == "Hyderabad":
            groups, subtotals, row_order = HYD_GROUPS, HYD_SUBTOTALS, HYD_ROW_ORDER
        elif loc_norm == "Bhogapuram":
            groups, subtotals, row_order = BHOGAPURAM_GROUPS, BHOGAPURAM_SUBTOTALS, BHOGAPURAM_ROW_ORDER
        else:
            groups, subtotals, row_order = GOA_GROUPS, GOA_SUBTOTALS, GOA_ROW_ORDER

        df_c = ehpl_cur[ehpl_cur["location"].str.title() == loc_norm].copy() \
            if not ehpl_cur.empty else ehpl_cur
        df_p = cmp_df_arg[cmp_df_arg["location"].str.title() == loc_norm].copy() \
            if (cmp_df_arg is not None and not cmp_df_arg.empty) else None
        df_aop = aop_df[aop_df["location"].str.title() == loc_norm] \
            if (not aop_df.empty and "location" in aop_df.columns) else None

        if df_c.empty:
            st.info(f"No data for {loc_name}.")
            return

        try:
            all_rows = _build_location_report(
                loc_norm, groups, subtotals, row_order,
                df_c, df_p, df_aop,
            )
            render_ehpl_location(
                loc_name, all_rows, df_c, df_p, cur_label, cmp_label,
            )
        except Exception as e:
            log_exception(e, context=f"EHPL {loc_name}")
            show_friendly_error("comparison_error")
            with st.expander("Technical detail"):
                st.code(_tb.format_exc(), language="text")

    # The top Location dropdown is the single source of location selection.
    # For "All Locations", only show locations that have actual EHPL data
    # for the selected date — never show empty location sections.
    if location == "All Locations":
        _name_fix = {"Bogapuram": "Bhogapuram"}
        if not ehpl_cur.empty and "location" in ehpl_cur.columns:
            available = _sort_locations([
                _name_fix.get(l, l)
                for l in ehpl_cur["location"].str.strip().str.title().unique()
                if l
            ])
        else:
            available = []

        if not available:
            st.warning("No EHPL data available for the selected period.")
            st.stop()

        for loc_name in available:
            ui.section(loc_name)
            _render_one_location(loc_name)
    else:
        ui.section(location)
        _render_one_location(location)


# ---------------------------------------------------------------------------
# Public: render_subsidiary_page (Encalm Eats / Sky Plates)
# ---------------------------------------------------------------------------
def render_subsidiary_page(segment: str, page_key: str, icon: str = ""):
    require_login()
    bootstrap_session()
    render_user_badge()

    ui.page_header(
        segment,
        f"{segment} performance by location and outlet. "
        "No airport terminal metrics shown for this business.",
    )

    location, ranges, current_df_all, compare_df_all, aop_df = \
        _render_filters_and_load(page_key)

    cur_label = ranges["current_label"]
    cmp_label = ranges["compare_label"]

    # Filter by segment
    def _seg_filter(df):
        if df.empty or "segment" not in df.columns:
            return df
        return df[df["segment"] == segment].copy()

    loc_cur = _filter_by_location(current_df_all, location)
    loc_cmp = _filter_by_location(compare_df_all, location)
    seg_cur = _seg_filter(loc_cur)
    seg_cmp = _seg_filter(loc_cmp) if not loc_cmp.empty else pd.DataFrame()

    if seg_cur.empty:
        st.warning(f"No {segment} data for {location} in the selected period.")
        st.stop()

    # AOP is not applicable for Encalm Eats / Sky Plates — pass None throughout.
    aop_df_loc = None

    # KPI cards (no traffic, no AOP for non-airport segments)
    _render_kpi_cards(
        seg_cur, seg_cmp if not seg_cmp.empty else None,
        None, cur_label, cmp_label, show_traffic=False
    )
    _render_overview_charts(
        seg_cur, seg_cmp if not seg_cmp.empty else None, location, ranges, _seg_filter,
    )

    def _render_one_location(loc_name: str):
        loc_norm = loc_name.title()
        df_c = seg_cur[seg_cur["location"].str.title() == loc_norm].copy() \
            if location == "All Locations" else seg_cur
        df_p = seg_cmp[seg_cmp["location"].str.title() == loc_norm].copy() \
            if (not seg_cmp.empty and location == "All Locations") else (
                seg_cmp if not seg_cmp.empty else None
            )

        ui.section(loc_name)
        _render_subsidiary_table(
            segment, loc_name, df_c, df_p, None, cur_label, cmp_label
        )

    if location == "All Locations":
        _name_fix = {"Bogapuram": "Bhogapuram"}
        if not seg_cur.empty and "location" in seg_cur.columns:
            available = _sort_locations([
                _name_fix.get(l, l)
                for l in seg_cur["location"].str.strip().str.title().unique()
                if l
            ])
        else:
            available = []

        if not available:
            st.warning(f"No {segment} data available for the selected period.")
            st.stop()

        for loc_name in available:
            _render_one_location(loc_name)
    else:
        ui.section(location)
        _render_subsidiary_table(
            segment, location, seg_cur,
            seg_cmp if not seg_cmp.empty else None,
            None, cur_label, cmp_label
        )
