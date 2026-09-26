# pages/Uploads.py — standalone Uploads page (extracted from Home.py)
# Keeps the full upload workflow visible in nav without relying on Home.
import streamlit as st
st.set_page_config(page_title="Uploads", page_icon="📤", layout="wide")
from modules.auth import require_login, render_user_badge
from modules.session import bootstrap_session
require_login()
bootstrap_session()
render_user_badge()
# Re-render the upload sections from Home.py by importing its upload logic.
# Home.py is the Streamlit entry point; we exec the upload portion here
# so the logic lives in one place (Home.py) and this page just surfaces it.
from modules import ui
ui.page_header("Upload Data", "Upload revenue reports, AOP targets, and traffic files. Formats are auto-detected.")
# Import and run the upload panels defined in a shared module
from modules import cached_db, data_processor, database
from modules.auth import current_user as _current_user
from modules import upload_status
import io as _io
from modules.session import set_active_date
from modules.cached_db import clear_data_cache
from modules.app_logger import safe_run

# ── Rate limit helper ─────────────────────────────────────────────────────────
def _check_rate_limit():
    return database.check_upload_rate_limit(_current_user() or "")

tab_rev, tab_hist, tab_aop, tab_traffic, tab_db = st.tabs([
    ":material/receipt_long: Daily Revenue",
    ":material/history_edu: Historical Import",
    ":material/flag: AOP Targets",
    ":material/flight: Traffic",
    ":material/database: Database",
])

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — Daily Revenue Upload
# ─────────────────────────────────────────────────────────────────────────────
with tab_rev:
    st.caption("PDF, Excel, CSV and other supported formats — auto-detected.")

    uploaded_files = st.file_uploader(
        "Daily revenue reports",
        type=["pdf","xlsx","xls","xlsm","csv","tsv","txt","docx","html","htm",
              "xml","json","png","jpg","jpeg","tiff","tif","msg"],
        accept_multiple_files=True, key="up_revenue",
    )
    daily_chosen_sheets = {}
    if uploaded_files:
        for i, f in enumerate(uploaded_files):
            upload_status.render_file_selected(f.name, getattr(f,"size",None))
            sheet_names = upload_status.get_sheet_names(f)
            if sheet_names:
                daily_chosen_sheets[f.name] = upload_status.render_sheet_selector(
                    f.name, sheet_names, key_prefix=f"up_daily_{i}", allow_auto_detect=True)

    if st.button("🚀 Process & Analyze", type="primary", disabled=not uploaded_files):
        _ok, _msg = _check_rate_limit()
        if not _ok:
            st.error(f"🚫 {_msg}")
            st.stop()
        any_success = False
        latest_date = None
        pending = []
        for file_obj in uploaded_files:
            with st.spinner(f"⏳ Processing {file_obj.name}…"):
                result = data_processor.process_uploaded_file(
                    file_obj, file_obj.name, save_to_db=True,
                    excel_sheet_name=daily_chosen_sheets.get(file_obj.name))
            pending.append((file_obj.name, result))
            if result.success:
                any_success = True
                if result.report_date and (latest_date is None or result.report_date > latest_date):
                    latest_date = result.report_date
        if latest_date:
            set_active_date(latest_date)
        st.session_state["_up_revenue_results"] = pending
        if any_success:
            clear_data_cache()
            st.toast("Processing complete.", icon="✅")
        st.rerun()

    if "_up_revenue_results" in st.session_state:
        for file_name, result in st.session_state["_up_revenue_results"]:
            date_line = [f"**Report date:** {result.report_date}"] if result.success and result.report_date else []
            upload_status.render_result_from_process_result(
                result, extra_lines=date_line, expected_format=upload_status.FORMAT_DAILY_REPORT)
            if result.success and result.df is not None:
                with st.expander(f"Preview — {file_name}"):
                    st.dataframe(result.df, use_container_width=True)
        if st.button("✖️ Dismiss", key="up_rev_dismiss"):
            del st.session_state["_up_revenue_results"]
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — Historical Excel Import
# ─────────────────────────────────────────────────────────────────────────────
with tab_hist:
    st.caption("Bulk-import a historical revenue workbook — sheet and format auto-detected.")

    hist_files = st.file_uploader("Upload workbook(s)", type=["xlsx","xls"],
        key="up_historical", accept_multiple_files=True)
    hist_chosen_sheets = {}
    if hist_files:
        from modules import excel_parser
        for i, hist_file in enumerate(hist_files):
            upload_status.render_file_selected(hist_file.name, getattr(hist_file,"size",None))
            hist_sheet_names = upload_status.get_sheet_names(hist_file)
            if hist_sheet_names:
                hist_chosen_sheets[hist_file.name] = upload_status.render_sheet_selector(
                    hist_file.name, hist_sheet_names, key_prefix=f"up_hist_{i}",
                    label=f"📑 Sheet for **{hist_file.name}**", allow_auto_detect=True)

    if st.button("📥 Import Historical Data", disabled=not hist_files) and hist_files:
        pending_hist = []
        _hist_latest = None
        for hist_file in hist_files:
            _bytes = hist_file.read()
            _name  = hist_file.name
            _sheet = hist_chosen_sheets.get(_name)
            st.info(f"📂 Parsing **{_name}** ({len(_bytes)/1024/1024:.1f} MB)…")
            with st.spinner("🔍 Detecting layout…"):
                result = data_processor.process_uploaded_file(
                    _io.BytesIO(_bytes), _name, save_to_db=False, excel_sheet_name=_sheet)
            if not result.success or result.df is None:
                st.error(f"❌ Parse failed: {result.message}")
                pending_hist.append(result)
                continue
            st.success(f"✅ Parsed **{len(result.df):,} rows** — saving…")
            _prog = st.progress(0.0, text="Saving…")
            _stat = st.empty()
            def _on_prog(pct, msg):
                _prog.progress(pct, text=f"💾 {msg}")
                _stat.caption(msg)
            try:
                save_result = database.save_dataframe_batched_v2(
                    result.df, source_file=_name, progress_callback=_on_prog)
                _prog.progress(1.0, text="✅ Done!")
                _stat.empty()
                result = data_processor.ProcessResult(
                    success=True, file_name=_name, stage="saving",
                    message=(f"Parsed {len(result.df):,} rows. "
                             f"{save_result['inserted']:,} new, {save_result['skipped']:,} skipped."),
                    df=result.df, report_date=result.report_date,
                    inserted=save_result["inserted"], skipped=save_result["skipped"])
            except Exception as _exc:
                _prog.empty()
                result = data_processor.ProcessResult(
                    success=False, file_name=_name, stage="saving",
                    message=f"Parsed OK but save failed: {_exc}")
            pending_hist.append(result)
            if result.success and result.report_date and (
                    _hist_latest is None or result.report_date > _hist_latest):
                _hist_latest = result.report_date
        if _hist_latest:
            set_active_date(_hist_latest)
        st.session_state["_up_hist_results"] = pending_hist
        clear_data_cache()  # new data must show on every page immediately
        st.rerun()

    if "_up_hist_results" in st.session_state:
        for _r in st.session_state["_up_hist_results"]:
            upload_status.render_result_from_process_result(
                _r, expected_format=upload_status.FORMAT_HISTORICAL_EXCEL)
            if _r.success and _r.df is not None:
                with st.expander(f"📋 Preview — {_r.file_name}", expanded=True):
                    st.dataframe(_r.df, use_container_width=True)
        if st.button("✖️ Dismiss", key="up_hist_dismiss"):
            del st.session_state["_up_hist_results"]
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — AOP Import
# ─────────────────────────────────────────────────────────────────────────────
with tab_aop:
    st.caption("Upload the AOP budget workbook — monthly or daily formats auto-detected.")

    _AOP_FMT = {"outlet_monthly":"per-outlet/monthly","daily_outlet_pivot":"daily outlet pivot","daily_pivot":"daily-total"}
    aop_files = st.file_uploader("AOP workbook(s) (.xlsx)", type=["xlsx","xls"],
        key="up_aop", accept_multiple_files=True)
    aop_chosen_sheets = {}
    if aop_files:
        from modules import aop_parser
        for i, aop_file in enumerate(aop_files):
            upload_status.render_file_selected(aop_file.name, getattr(aop_file,"size",None))
            try:
                candidates = aop_parser.list_aop_candidate_sheets(aop_file)
            except aop_parser.AOPParseError as exc:
                upload_status.render_result(False, aop_file.name, str(exc), stage="reading",
                    expected_format=upload_status.FORMAT_AOP)
                candidates = []
            valid = [c for c in candidates if c["format"] is not None]
            if candidates:
                all_names = [c["sheet_name"] for c in candidates]
                fmt_by_sheet = {c["sheet_name"]: c["format"] for c in candidates}
                default = valid[0]["sheet_name"] if valid else None
                if len(all_names) == 1:
                    aop_chosen_sheets[aop_file.name] = all_names[0]
                    fmt = fmt_by_sheet.get(all_names[0])
                    if fmt:
                        st.caption(f"📄 **{aop_file.name}** — sheet **'{all_names[0]}'** ({_AOP_FMT.get(fmt, fmt)}).")
                else:
                    labels = {n: f"{n} ({_AOP_FMT.get(fmt_by_sheet[n], fmt_by_sheet[n])} format)" if fmt_by_sheet.get(n) else f"{n} (unknown)" for n in all_names}
                    default_idx = all_names.index(default) if default in all_names else 0
                    aop_chosen_sheets[aop_file.name] = st.selectbox(
                        f"📑 Sheet for **{aop_file.name}**", options=all_names,
                        index=default_idx, format_func=lambda s: labels[s],
                        key=f"up_aop_sheet_{i}")

    if st.button("📥 Import AOP Targets", disabled=not aop_chosen_sheets):
        from modules import aop_parser
        pending_aop = []
        for aop_file in aop_files:
            sheet = aop_chosen_sheets.get(aop_file.name)
            if not sheet:
                continue
            if hasattr(aop_file,"seek"):
                aop_file.seek(0)
            with st.spinner(f"⏳ Importing '{aop_file.name}'…"):
                try:
                    parsed = aop_parser.parse_aop_auto(aop_file, sheet_name=sheet)
                    if parsed["format"] in ("outlet_monthly","daily_outlet_pivot"):
                        sr = database.save_aop_targets(parsed["aop_rows"], aop_file.name)
                    else:
                        sr = database.save_aop_targets_daily(parsed["aop_rows"], aop_file.name)
                    pending_aop.append({"success":True,"file_name":aop_file.name,
                        "inserted":sr["inserted"],"skipped":sr["skipped"],
                        "rows_parsed":len(parsed["aop_rows"]),
                        "units_multiplier":parsed["units_multiplier"],
                        "skipped_rows":parsed["skipped_rows"],"aop_rows":parsed["aop_rows"]})
                except Exception as exc:
                    pending_aop.append({"success":False,"file_name":aop_file.name,
                        "message":str(exc),"stage":"saving"})
        st.session_state["_up_aop_results"] = pending_aop
        clear_data_cache()  # new data must show on every page immediately
        st.rerun()

    if "_up_aop_results" in st.session_state:
        for _ar in st.session_state["_up_aop_results"]:
            if _ar["success"]:
                upload_status.render_result(True, _ar["file_name"], "",
                    inserted=_ar["inserted"], skipped=_ar["skipped"],
                    extra_lines=[f"**Rows parsed:** {_ar['rows_parsed']:,}",
                                 f"**Units:** ×{_ar['units_multiplier']:,.0f}"])
                if not _ar["skipped_rows"].empty:
                    with st.expander(f"⚠️ {len(_ar['skipped_rows'])} out-of-scope rows"):
                        st.dataframe(_ar["skipped_rows"], use_container_width=True, hide_index=True)
            else:
                upload_status.render_result(False, _ar["file_name"], _ar["message"],
                    stage=_ar["stage"], expected_format=upload_status.FORMAT_AOP)
        if st.button("✖️ Dismiss", key="up_aop_dismiss"):
            del st.session_state["_up_aop_results"]
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — Traffic Import
# ─────────────────────────────────────────────────────────────────────────────
with tab_traffic:
    st.caption("Upload airport traffic files — all formats auto-detected.")

    traffic_files = st.file_uploader("Traffic file(s) (.xlsx / .xls)",
        type=["xlsx","xls"], key="up_traffic", accept_multiple_files=True)
    if traffic_files:
        for _tf in traffic_files:
            upload_status.render_file_selected(_tf.name, getattr(_tf,"size",None))

    if st.button("📥 Import Traffic Data", disabled=not traffic_files) and traffic_files:
        from modules import traffic_parser
        pending_t = []
        for _tf in traffic_files:
            if hasattr(_tf,"seek"):
                _tf.seek(0)
            with st.spinner(f"⏳ Importing '{_tf.name}'…"):
                try:
                    _parsed = traffic_parser.parse_traffic_auto(_tf, _tf.name)
                    _err = None
                except Exception as _exc:
                    _parsed, _err = None, (str(_exc), "reading")
                if _parsed is not None:
                    try:
                        _sr = database.save_traffic_dataframe(_parsed, _tf.name)
                        pending_t.append({"success":True,"file_name":_tf.name,
                            "inserted":_sr["inserted"],"skipped":_sr["skipped"],
                            "rows_parsed":len(_parsed),"parsed_df":_parsed})
                    except Exception as _exc2:
                        pending_t.append({"success":False,"file_name":_tf.name,
                            "message":str(_exc2),"stage":"saving"})
                else:
                    _msg, _stage = _err
                    pending_t.append({"success":False,"file_name":_tf.name,
                        "message":_msg,"stage":_stage})
        st.session_state["_up_traffic_results"] = pending_t
        clear_data_cache()  # new data must show on every page immediately
        st.rerun()

    if "_up_traffic_results" in st.session_state:
        for _tr in st.session_state["_up_traffic_results"]:
            if _tr["success"]:
                upload_status.render_result(True, _tr["file_name"], "",
                    inserted=_tr["inserted"], skipped=_tr["skipped"],
                    extra_lines=[f"**Rows parsed:** {_tr['rows_parsed']:,}"])
                with st.expander(f"📋 Preview — {_tr['file_name']}", expanded=True):
                    st.dataframe(_tr["parsed_df"], use_container_width=True, hide_index=True)
            else:
                upload_status.render_result(False, _tr["file_name"], _tr["message"],
                    stage=_tr["stage"], expected_format=upload_status.FORMAT_TRAFFIC)
        if st.button("✖️ Dismiss", key="up_traffic_dismiss"):
            del st.session_state["_up_traffic_results"]
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — Database Stats
# ─────────────────────────────────────────────────────────────────────────────
with tab_db:
    with safe_run("Database stats", error_type="db_error"):
        stats = cached_db.get_db_stats()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Rows", f"{stats['total_rows']:,}")
        m2.metric("Distinct Dates", f"{stats['distinct_dates']:,}")
        m3.metric("Earliest", str(stats["min_date"]) if stats["min_date"] else "—")
        m4.metric("Latest", str(stats["max_date"]) if stats["max_date"] else "—")
