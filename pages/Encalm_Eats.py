"""
pages/Encalm_Eats.py — Encalm Eats analytics + DSR upload.

Analytics tab: reads from encalm_eats_dsr table (outlet-level DSR data)
when available for the selected date, falling back to revenue_master
(aggregated "Encalm Eats" row) when DSR data is absent.

DSR upload tab: dedicated Encalm Eats Master DSR import.
"""
import streamlit as st

st.set_page_config(page_title="Encalm Eats", layout="wide")

from modules.auth import require_login, render_user_badge
from modules.session import bootstrap_session

require_login()
bootstrap_session()
render_user_badge()

from modules import ui
ui.page_header("Encalm Eats", "Encalm Eats outlet performance by location.")

tab_analytics, tab_dsr = st.tabs([":material/monitoring: Analytics", ":material/upload: Upload DSR"])

# ---------------------------------------------------------------------------
# Analytics tab
# ---------------------------------------------------------------------------
with tab_analytics:
    import pandas as pd
    from modules import cached_db, comparison_widget, database, date_picker
    from modules.session import default_active_date, set_active_date
    from modules.business_dashboard import (
        _render_filters_and_load,
        _filter_by_location,
        _render_kpi_cards,
        _render_subsidiary_table,
        _render_overview_charts,
    )

    segment   = "Encalm Eats"
    page_key  = "eats"

    # Use DSR dates when available; fall back to revenue_master dates
    try:
        dsr_dates = cached_db.get_encalm_eats_dsr_dates()
    except Exception:
        dsr_dates = []

    eats_dates = dsr_dates if dsr_dates else cached_db.get_available_dates()

    if not eats_dates:
        st.warning(
            "No Encalm Eats data found. "
            "Upload a DSR file in the **📤 Upload DSR** tab first."
        )
        st.stop()

    if dsr_dates:
        st.caption(
            f"📋 Showing DSR dates ({len(dsr_dates)} days available). "
            "Only dates with uploaded DSR data are selectable."
        )

    location, ranges, current_df_all, compare_df_all, aop_df = \
        _render_filters_and_load(page_key, available_dates=eats_dates)

    cur_label = ranges["current_label"]
    cmp_label = ranges["compare_label"]

    # ------------------------------------------------------------------
    # Load DSR data for the selected date range.
    # DSR data is outlet-level (individual outlets per day).
    # revenue_master data is aggregated (one "Encalm Eats" row per day).
    # Prefer DSR data when it exists; fall back to revenue_master.
    # ------------------------------------------------------------------
    try:
        dsr_cur = cached_db.load_encalm_eats_dsr_for_range(
            ranges["current_start"], ranges["current_end"]
        )
        dsr_cmp = cached_db.load_encalm_eats_dsr_for_range(
            ranges["compare_start"], ranges["compare_end"]
        )
    except Exception:
        dsr_cur = pd.DataFrame()
        dsr_cmp = pd.DataFrame()

    # Rename DSR columns to match what _render_subsidiary_table expects:
    # net_revenue -> revenue,  covers -> pax
    def _normalise_dsr(df: pd.DataFrame, loc: str) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        df = df.rename(columns={"net_revenue": "revenue", "covers": "pax"})
        df["pax"] = pd.to_numeric(df["pax"], errors="coerce").fillna(0)
        df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0)
        if loc != "All Locations":
            df = df[df["location"].str.title() == loc.title()]
        return df

    use_dsr = not dsr_cur.empty

    if use_dsr:
        seg_cur = _normalise_dsr(dsr_cur, location)
        seg_cmp = _normalise_dsr(dsr_cmp, location) if not dsr_cmp.empty else pd.DataFrame()
        data_source_note = "📋 Showing outlet-level data from uploaded DSR."
    else:
        # Fall back to revenue_master (aggregated)
        def _seg_filter(df):
            if df.empty or "segment" not in df.columns:
                return df
            return df[df["segment"] == segment].copy()

        loc_cur = _filter_by_location(current_df_all, location)
        loc_cmp = _filter_by_location(compare_df_all, location)
        seg_cur = _seg_filter(loc_cur)
        seg_cmp = _seg_filter(loc_cmp) if not loc_cmp.empty else pd.DataFrame()
        data_source_note = (
            "⚠️ No DSR data for this period — showing aggregated data from revenue upload. "
            "Upload the Master DSR in the **Upload DSR** tab for outlet-level breakdown."
        )

    if seg_cur.empty:
        st.warning(f"No Encalm Eats data for **{location}** in the selected period.")
        st.caption(data_source_note)
    else:
        st.caption(data_source_note)

        # KPI cards — use revenue/pax column names
        _render_kpi_cards(
            seg_cur.rename(columns={"revenue": "revenue", "pax": "pax"}),
            seg_cmp if not seg_cmp.empty else None,
            None, cur_label, cmp_label, show_traffic=False,
        )
        _render_overview_charts(
            seg_cur, seg_cmp if not seg_cmp.empty else None, location, ranges,
            lambda df: df[df["segment"] == segment] if (not df.empty and "segment" in df.columns) else df,
        )

        def _render_one(loc_name: str):
            loc_norm = loc_name.title()
            if location == "All Locations":
                df_c = seg_cur[seg_cur["location"].str.title() == loc_norm].copy()
                df_p = seg_cmp[seg_cmp["location"].str.title() == loc_norm].copy() \
                    if not seg_cmp.empty else None
            else:
                df_c = seg_cur
                df_p = seg_cmp if not seg_cmp.empty else None

            ui.section(loc_name)
            _render_subsidiary_table(
                segment, loc_name, df_c, df_p, None, cur_label, cmp_label
            )

        if location == "All Locations":
            _name_fix = {"Bogapuram": "Bhogapuram"}
            from modules.business_dashboard import _sort_locations
            available = _sort_locations([
                _name_fix.get(l, l)
                for l in seg_cur["location"].str.strip().str.title().unique() if l
            ]) if not seg_cur.empty else []
            for loc_name in available:
                _render_one(loc_name)
        else:
            _render_one(location)

# ---------------------------------------------------------------------------
# DSR Upload tab
# ---------------------------------------------------------------------------
with tab_dsr:
    st.header("Upload Encalm Eats Master DSR")
    st.caption(
        "Upload the daily Master DSR workbook (.xlsx). "
        "Each sheet must be named DD-MM-YYYY. "
        "Duplicate records (same date + outlet + location) are skipped automatically. "
        "After uploading, switch to the **Analytics** tab and select the matching date "
        "to see the outlet-level breakdown."
    )

    uploaded = st.file_uploader(
        "Select DSR workbook",
        type=["xlsx", "xls"],
        key="eats_dsr_uploader",
    )

    if uploaded:
        st.info(f"**{uploaded.name}** — {uploaded.size / 1024:.1f} KB")

        if st.button("🚀 Parse & Import DSR", type="primary", key="eats_dsr_btn"):
            from modules.encalm_eats_dsr_parser import parse_dsr
            from modules.database import save_encalm_eats_dsr, init_db

            init_db()

            with st.spinner("Parsing DSR workbook..."):
                try:
                    result = parse_dsr(uploaded, uploaded.name)
                except Exception as exc:
                    st.error(f"Parser error: {exc}")
                    import traceback
                    st.code(traceback.format_exc())
                    st.stop()

            if not result.success:
                st.error("DSR parsing failed.")
                for e in result.errors:
                    st.error(e)
                st.stop()

            st.success(
                f"Parsed — **{result.rows_extracted:,}** outlet records "
                f"across **{result.sheets_parsed}** daily sheets."
            )

            df = result.df
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sheets",        result.sheets_parsed)
            c2.metric("Records",       f"{result.rows_extracted:,}")
            c3.metric("Total Covers",  f"{result.parsed_total_covers:,.0f}")
            c4.metric("Total Revenue", f"₹{result.parsed_total_revenue:,.0f}")

            if result.source_grand_total_revenue is not None:
                st.caption(
                    f"DSR last-sheet grand total — "
                    f"Covers: **{result.source_grand_total_covers or 0:,.0f}** | "
                    f"Revenue: **₹{result.source_grand_total_revenue:,.0f}**"
                )

            st.caption(
                f"Period: **{df['date'].min()}** to **{df['date'].max()}** | "
                f"Locations: **{', '.join(sorted(df['location'].unique()))}** | "
                f"Outlets: **{', '.join(sorted(df['outlet'].unique()))}**"
            )

            if result.warnings:
                with st.expander(f"⚠️ {len(result.warnings)} warnings"):
                    for w in result.warnings:
                        st.caption(w)

            with st.expander("Preview (first 20 rows)"):
                st.dataframe(
                    df[["date", "outlet", "location", "covers", "net_revenue"]].head(20),
                    use_container_width=True, hide_index=True,
                )

            with st.spinner("Saving to database..."):
                try:
                    save_result = save_encalm_eats_dsr(result.records, uploaded.name)
                except Exception as exc:
                    st.error(f"Database save failed: {exc}")
                    import traceback
                    st.code(traceback.format_exc())
                    st.stop()

            ins = save_result["inserted"]
            skp = save_result["skipped"]
            if ins > 0:
                from modules.cached_db import clear_data_cache
                clear_data_cache()

            if ins > 0:
                st.success(
                    f"✅ Saved **{ins:,}** new records. "
                    f"Skipped **{skp:,}** duplicates. "
                    f"Switch to **Analytics** tab to view the outlet breakdown."
                )
            elif skp > 0:
                st.warning(
                    f"All {skp:,} records already exist — this DSR has already been uploaded."
                )
            else:
                st.info("No records were saved.")
