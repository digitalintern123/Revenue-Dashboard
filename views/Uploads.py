# views/Uploads.py — standalone Uploads page (extracted from Home.py)
# Keeps the full upload workflow visible in nav without relying on Home.
import streamlit as st
from modules import ui as _ui
st.set_page_config(page_title="Uploads · Encalm", page_icon=_ui.LOGO_MARK, layout="wide")
from modules.auth import require_login, render_user_badge
from modules.session import bootstrap_session
require_login()
bootstrap_session()
render_user_badge()
# Re-render the upload sections from Home.py by importing its upload logic.
# Home.py is the Streamlit entry point; we exec the upload portion here
# so the logic lives in one place (Home.py) and this page just surfaces it.
from modules import ui
ui.page_header("Upload Data", "Upload revenue reports, AOP targets, and traffic files. Formats are auto-detected.", icon="upload")
# Import and run the upload panels defined in a shared module
from modules import cached_db, data_processor, database
from modules.auth import current_user as _current_user
from modules import upload_status
import io as _io
from modules.session import set_active_date
from modules.cached_db import clear_data_cache
from modules.app_logger import safe_run
from modules import analyse_panel, format_registry, upload_checks, layout_learning, mapping_editor
import json
import pandas as pd

# ── Rate limit helper ─────────────────────────────────────────────────────────
def _check_rate_limit():
    return database.check_upload_rate_limit(_current_user() or "")


# ── Analyse step (cached briefly so Save reuses it without re-reading) ──────
SAVED_LAYOUT = "Saved layout: "


def _is_admin() -> bool:
    """Users listed in [auth.admins] admins = [...] in secrets.toml."""
    try:
        admins = st.secrets.get("auth", {}).get("admins", {}).get("admins", [])
    except Exception:
        admins = []
    return (_current_user() or "") in set(admins or [])


def _templates_json(kind: str) -> str:
    try:
        return json.dumps(database.list_parse_templates(kind))
    except Exception:
        return "[]"


def _needs_mapping(res) -> bool:
    """Not read, or read only by the generic readers with low confidence."""
    if not res.success:
        return True
    if res.layout == data_processor.LAYOUT_GENERIC:
        return True
    return res.layout.startswith(data_processor.LAYOUT_UNIVERSAL) and (res.confidence or 0) < 0.8


def _remember_layout(kind: str, name: str, state: dict, file_bytes: bytes, file_name: str):
    grid = layout_learning.read_grid(file_bytes, file_name, state.get("sheet"))
    headers, _ = layout_learning.table_at(grid, state["header_row"])
    mapping = pd.DataFrame(state["mapping"])
    database.save_parse_template(
        kind, name, layout_learning.fingerprint(headers), layout_learning.mapping_to_saved(mapping),
        state["header_row"], state.get("constants") or {}, created_by=_current_user() or "")


def _mark_template_used(kind: str, layout_label: str):
    name = layout_label[len(SAVED_LAYOUT):].rsplit(" (", 1)[0]
    for t in database.list_parse_templates(kind):
        if t["name"] == name:
            database.mark_parse_template_used(t["id"])


@st.cache_data(max_entries=4, ttl=1800, show_spinner=False)
def _analyse_revenue(file_bytes: bytes, name: str, sheet, templates_json: str):
    """Known layouts first; a saved layout when only the generic readers
    managed (or nothing did). Returns (result, ident, analysis, needs_mapping)."""
    res = data_processor.process_uploaded_file(_io.BytesIO(file_bytes), name,
                                               save_to_db=False, excel_sheet_name=sheet)
    if _needs_mapping(res):
        hit = layout_learning.find_template(file_bytes, name, json.loads(templates_json), sheet)
        if hit:
            t = hit["template"]
            mapping = layout_learning.mapping_for_headers(t["mapping"], hit["headers"], "revenue")
            try:
                rows = layout_learning.apply(hit["headers"], hit["data"], mapping, "revenue",
                                             t["constants"], hit["header_row"])
                mapped = data_processor.process_mapped_rows(
                    rows, name, f"{SAVED_LAYOUT}{t['name']} ({hit['score']:.0%} of headers match)",
                    hit["score"], source_sheet=hit["sheet"])
                if mapped.success:
                    res = mapped
            except layout_learning.LayoutError:
                pass
    an = upload_checks.analyse_revenue(res, file_bytes)
    ident = format_registry.identify_revenue(file_bytes, name, res, an.confidence)
    return res, ident, an, _needs_mapping(res)


@st.cache_data(max_entries=4, ttl=1800, show_spinner=False)
def _analyse_revenue_mapped(file_bytes: bytes, name: str, state_json: str):
    """A revenue file read with the column mapping the user confirmed."""
    state = json.loads(state_json)
    try:
        grid = layout_learning.read_grid(file_bytes, name, state.get("sheet"))
        headers, data = layout_learning.table_at(grid, state["header_row"])
        rows = layout_learning.apply(headers, data, pd.DataFrame(state["mapping"]), "revenue",
                                     state.get("constants"), state["header_row"])
    except layout_learning.LayoutError as exc:
        return None, None, None, str(exc)
    res = data_processor.process_mapped_rows(rows, name, "Column mapping confirmed by you", 1.0,
                                             source_sheet=state.get("sheet"))
    an = upload_checks.analyse_revenue(res, file_bytes)
    an.confidence = 1.0 if res.success else None
    ident = format_registry.identify_revenue(file_bytes, name, res, an.confidence)
    return res, ident, an, None


@st.cache_data(max_entries=4, ttl=1800, show_spinner=False)
def _analyse_aop(file_bytes: bytes, name: str, sheet):
    from modules import aop_parser
    from modules import eats_skyplates_aop_parser as esp_parser
    try:
        parsed = aop_parser.parse_aop_auto(_io.BytesIO(file_bytes), sheet_name=sheet)
    except Exception as exc:
        return None, None, str(exc)
    esp = None
    if parsed["format"] == "outlet_monthly":
        try:
            esp = esp_parser.parse_eats_and_skyplates_aop(_io.BytesIO(file_bytes))
        except Exception:
            esp = None
    an = upload_checks.analyse_aop(parsed, esp, database.get_available_aop_year_months())
    return format_registry.identify_aop(file_bytes, name, parsed), an, None


@st.cache_data(max_entries=4, ttl=1800, show_spinner=False)
def _analyse_traffic(file_bytes: bytes, name: str, templates_json: str = "[]"):
    """Known traffic layouts first, then a saved layout. Returns
    (df, ident, analysis, error)."""
    from modules import traffic_parser
    df, err = None, None
    try:
        df = traffic_parser.parse_traffic_auto(_io.BytesIO(file_bytes), name)
    except Exception as exc:
        err = str(exc)
    if df is None or df.empty:
        hit = layout_learning.find_template(file_bytes, name, json.loads(templates_json))
        if hit:
            t = hit["template"]
            mapping = layout_learning.mapping_for_headers(t["mapping"], hit["headers"], "traffic")
            try:
                df = layout_learning.apply(hit["headers"], hit["data"], mapping, "traffic",
                                           t["constants"], hit["header_row"])
                df.attrs["readers"] = {str(l): f"{SAVED_LAYOUT}{t['name']}"
                                       for l in df["location"].astype(str).unique()}
                err = None
            except layout_learning.LayoutError as exc:
                err = f"Saved layout '{t['name']}' matched but could not be applied: {exc}"
    if df is None or df.empty:
        return None, None, None, err or "No traffic rows found."
    an = upload_checks.analyse_traffic(df)
    ident = format_registry.identify_traffic(file_bytes, name, df, an.confidence)
    return df, ident, an, None


@st.cache_data(max_entries=4, ttl=1800, show_spinner=False)
def _analyse_traffic_mapped(file_bytes: bytes, name: str, state_json: str):
    state = json.loads(state_json)
    try:
        grid = layout_learning.read_grid(file_bytes, name, state.get("sheet"))
        headers, data = layout_learning.table_at(grid, state["header_row"])
        df = layout_learning.apply(headers, data, pd.DataFrame(state["mapping"]), "traffic",
                                   state.get("constants"), state["header_row"])
    except layout_learning.LayoutError as exc:
        return None, None, None, str(exc)
    if df.empty:
        return None, None, None, "With this mapping no traffic rows remain."
    df.attrs["readers"] = {str(l): "Column mapping confirmed by you"
                           for l in df["location"].astype(str).unique()}
    an = upload_checks.analyse_traffic(df)
    an.confidence = 1.0
    ident = format_registry.identify_traffic(file_bytes, name, df, an.confidence)
    return df, ident, an, None


tab_rev, tab_aop, tab_traffic, tab_db = st.tabs(
    ["Daily Revenue", "AOP Targets", "Traffic", "Database"],
    key="upload_tabs",
)
ui.tab_icons("upload_tabs", ["receipt", "target", "plane", "database"])

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
    rev_replace = st.checkbox(
        "Replace existing revenue for the dates and locations in this file",
        value=False, key="up_revenue_replace",
        help=("Off: lines already stored are kept and the file's copy of them is "
              "skipped. On: everything stored for each date + location in the file "
              "is deleted first, so a corrected file overwrites earlier figures "
              "(a line the file no longer has for that date is removed too)."))
    daily_chosen_sheets = {}
    if uploaded_files:
        for i, f in enumerate(uploaded_files):
            upload_status.render_file_selected(f.name, getattr(f,"size",None))
            sheet_names = upload_status.get_sheet_names(f)
            if sheet_names:
                daily_chosen_sheets[f.name] = upload_status.render_sheet_selector(
                    f.name, sheet_names, key_prefix=f"up_daily_{i}", allow_auto_detect=True)

    # Analyse first (nothing saved), then Save the analysed result
    if st.button("🔍 Analyse", type="primary", disabled=not uploaded_files, key="up_rev_analyse"):
        st.session_state["_up_rev_pending"] = [
            (f.name, daily_chosen_sheets.get(f.name)) for f in uploaded_files]
        st.session_state.pop("_up_revenue_results", None)

    _rev_pending = st.session_state.get("_up_rev_pending") or []
    _rev_files = {f.name: f for f in (uploaded_files or [])}
    _rev_ready = []                    # (name, sheet, mapping-state json or None)
    _rev_templates = _templates_json("revenue") if _rev_pending else "[]"
    for _i, (_name, _sheet) in enumerate(_rev_pending):
        _f = _rev_files.get(_name)
        if _f is None:
            continue                       # file removed from the uploader
        _bytes = _f.getvalue()
        _state = mapping_editor.get_state("revenue", _name)
        _sj = mapping_editor.state_json(_state) if _state else None
        with st.spinner(f"🔍 Analysing {_name}…"):
            if _sj:
                _res, _ident, _an, _err = _analyse_revenue_mapped(_bytes, _name, _sj)
                _needs = True
            else:
                _res, _ident, _an, _needs = _analyse_revenue(_bytes, _name, _sheet, _rev_templates)
                _err = None
        if _err:
            st.error(f"**{_name}** — {_err}")
        elif _res.success:
            analyse_panel.render(_name, _ident, _an, preview=_res.df, key=f"rev{_i}")
            _rev_ready.append((_name, _sheet, _sj))
            if _res.skipped_rows is not None and not _res.skipped_rows.empty:
                upload_status.render_skipped_rows(_res.skipped_rows, _name)
        else:
            upload_status.render_result_from_process_result(
                _res, expected_format=upload_status.FORMAT_DAILY_REPORT)
        if _needs:
            mapping_editor.render("revenue", _bytes, _name, key=f"revmap{_i}",
                                  default_sheet=_sheet or (_res.source_sheet if _res else None),
                                  expanded=bool(_err) or _res is None or not _res.success)
    _rev_remember = {}
    for _name, _sheet, _sj in _rev_ready:
        if _sj:
            st.markdown(f"**{_name}** — save this column mapping for next time?")
            _rev_remember[_name] = mapping_editor.remember_inputs("revenue", _name, f"revrem_{_name}")
    if _rev_pending:
        _c1, _c2 = st.columns([1, 4])
        _save = _c1.button("💾 Save", type="primary", disabled=not _rev_ready, key="up_rev_save")
        if _c2.button("✖️ Cancel", key="up_rev_cancel"):
            st.session_state.pop("_up_rev_pending", None)
            st.rerun()
        if _save:
            _ok, _msg = _check_rate_limit()
            if not _ok:
                st.error(f"🚫 {_msg}")
                st.stop()
            any_success, latest_date, pending = False, None, []
            for _name, _sheet, _sj in _rev_ready:
                _bytes = _rev_files[_name].getvalue()
                if _sj:
                    _res = _analyse_revenue_mapped(_bytes, _name, _sj)[0]
                else:
                    _res = _analyse_revenue(_bytes, _name, _sheet, _rev_templates)[0]
                with st.spinner(f"💾 Saving {_name}…"):
                    result = data_processor.save_analysed(_res, replace=rev_replace)
                if result.success and _sj and _rev_remember.get(_name):
                    _remember_layout("revenue", _rev_remember[_name], json.loads(_sj), _bytes, _name)
                    result.warnings.append(f"Layout remembered as '{_rev_remember[_name]}'.")
                if result.success and _res.layout.startswith(SAVED_LAYOUT):
                    _mark_template_used("revenue", _res.layout)
                result.df = None           # keep session state small (AI_RULES 17)
                pending.append((_name, result))
                if result.success:
                    any_success = True
                    if result.report_date and (latest_date is None or result.report_date > latest_date):
                        latest_date = result.report_date
                st.session_state.pop(mapping_editor.state_key("revenue", _name), None)
            if latest_date:
                set_active_date(latest_date)
            st.session_state["_up_revenue_results"] = pending
            st.session_state.pop("_up_rev_pending", None)
            _analyse_revenue.clear()
            _analyse_revenue_mapped.clear()
            if any_success:
                clear_data_cache()
                st.toast("Saved.", icon="✅")
            st.rerun()

    if "_up_revenue_results" in st.session_state:
        for file_name, result in st.session_state["_up_revenue_results"]:
            date_line = [f"**Report date:** {result.report_date}"] if result.success and result.report_date else []
            if result.success and result.replaced:
                date_line.append(f"**Replaced:** {result.replaced:,} earlier row(s) for the "
                                 f"dates and locations in this file")
            upload_status.render_result_from_process_result(
                result, extra_lines=date_line, expected_format=upload_status.FORMAT_DAILY_REPORT)
        if st.button("✖️ Dismiss", key="up_rev_dismiss"):
            del st.session_state["_up_revenue_results"]
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — AOP Import
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

    aop_replace = st.checkbox(
        "Replace existing AOP for the months in this file",
        value=True, key="up_aop_replace",
        help=("Clears stored monthly AOP targets for every month this file covers, then "
              "imports the file. Without this, rows that already exist are kept unchanged, "
              "so a corrected AOP file cannot update earlier values."),
    )

    if st.button("🔍 Analyse", type="primary", disabled=not aop_chosen_sheets, key="up_aop_analyse"):
        st.session_state["_up_aop_pending"] = dict(aop_chosen_sheets)
        st.session_state.pop("_up_aop_results", None)

    _aop_pending = st.session_state.get("_up_aop_pending") or {}
    _aop_by_name = {f.name: f for f in (aop_files or [])}
    for _i, (_name, _sheet) in enumerate(_aop_pending.items()):
        if _name not in _aop_by_name:
            continue
        with st.spinner(f"🔍 Analysing {_name}…"):
            _ident, _an, _err = _analyse_aop(_aop_by_name[_name].getvalue(), _name, _sheet)
        if _err:
            upload_status.render_result(False, _name, _err, stage="reading",
                                        expected_format=upload_status.FORMAT_AOP)
        else:
            analyse_panel.render(_name, _ident, _an, key=f"aop{_i}")
    _aop_ready = bool(_aop_pending) and set(_aop_pending) <= set(_aop_by_name)
    if _aop_pending and st.button("✖️ Cancel", key="up_aop_cancel"):
        st.session_state.pop("_up_aop_pending", None)
        st.rerun()

    if _aop_pending and st.button("💾 Save", type="primary", disabled=not _aop_ready,
                                  key="up_aop_save"):
        st.session_state.pop("_up_aop_pending", None)
        from modules import aop_parser
        from modules import eats_skyplates_aop_parser as _esp_parser
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
                    is_monthly = parsed["format"] in ("outlet_monthly","daily_outlet_pivot")

                    # Sky Plates (IFK) + Encalm Eats (F&B) rows from the same master file
                    esp, esp_error = None, None
                    if parsed["format"] == "outlet_monthly":
                        try:
                            if hasattr(aop_file, "seek"):
                                aop_file.seek(0)
                            esp = _esp_parser.parse_eats_and_skyplates_aop(aop_file)
                        except Exception as esp_exc:
                            esp_error = str(esp_exc)

                    deleted = 0
                    if is_monthly and aop_replace:
                        months = set(zip(parsed["aop_rows"]["year"], parsed["aop_rows"]["month"]))
                        if esp is not None and not esp["aop_rows"].empty:
                            months |= set(zip(esp["aop_rows"]["year"], esp["aop_rows"]["month"]))
                        deleted = database.delete_aop_targets_for_months(months)

                    if is_monthly:
                        sr = database.save_aop_targets(parsed["aop_rows"], aop_file.name)
                    else:
                        sr = database.save_aop_targets_daily(parsed["aop_rows"], aop_file.name)

                    esp_saved = None
                    if esp is not None:
                        esp_saved = _esp_parser.save_eats_skyplates_aop(
                            None, source_file=aop_file.name, parsed=esp)

                    extra = [
                        f"**EHPL AOP rows parsed:** {len(parsed['aop_rows']):,}",
                        f"**Units:** ×{parsed['units_multiplier']:,.0f}",
                    ]
                    if deleted:
                        extra.append(f"**Replaced:** {deleted:,} earlier AOP rows for the same months")
                    if esp_saved:
                        extra.append(
                            f"**Sky Plates AOP rows:** {esp_saved['sky_plates_count']:,} · "
                            f"**Encalm Eats AOP rows:** {esp_saved['encalm_eats_count']:,} "
                            f"(saved {esp_saved['db_inserted']:,})")
                    elif esp_error:
                        extra.append(f"⚠️ Sky Plates / Encalm Eats AOP not imported: {esp_error}")

                    pending_aop.append({
                        "success": True, "file_name": aop_file.name,
                        "inserted": sr["inserted"], "skipped": sr["skipped"],
                        "rows_parsed": len(parsed["aop_rows"]),
                        "units_multiplier": parsed["units_multiplier"],
                        "skipped_rows": parsed["skipped_rows"],
                        "extra_lines": extra,
                        "esp_mapping": esp["mapping"] if esp else None,
                        "esp_warnings": esp["warnings"] if esp else [],
                    })
                except Exception as exc:
                    pending_aop.append({"success":False,"file_name":aop_file.name,
                        "message":str(exc),"stage":"saving"})
        st.session_state["_up_aop_results"] = pending_aop
        _analyse_aop.clear()
        clear_data_cache()  # new data must show on every page immediately
        st.rerun()

    if "_up_aop_results" in st.session_state:
        for _ar in st.session_state["_up_aop_results"]:
            if _ar["success"]:
                upload_status.render_result(True, _ar["file_name"], "",
                    inserted=_ar["inserted"], skipped=_ar["skipped"],
                    extra_lines=_ar.get("extra_lines", [
                        f"**Rows parsed:** {_ar['rows_parsed']:,}",
                        f"**Units:** ×{_ar['units_multiplier']:,.0f}",
                    ]))
                for _w in _ar.get("esp_warnings") or []:
                    st.warning(_w)
                _map = _ar.get("esp_mapping")
                if _map is not None and not _map.empty:
                    _n_unmatched = int((_map["matched_to_dsr"] == False).sum())
                    from modules.eats_skyplates_aop_parser import IMPORTED as _IMPORTED
                    _n_noted = int((_map["result"] != _IMPORTED).sum()) if "result" in _map.columns else 0
                    with st.expander(f"🍽️ Sky Plates / Encalm Eats outlet mapping "
                                     f"({len(_map)} AOP rows, {_n_unmatched} with no DSR outlet, "
                                     f"{_n_noted} not imported)"):
                        _show = _map.rename(columns={
                            "segment": "Segment", "location": "Location", "section": "Section",
                            "aop_name": "AOP name", "dashboard_outlet": "Dashboard outlet",
                            "matched_to_dsr": "Matches DSR outlet", "note": "Note in AOP file",
                            "result": "Result",
                            "fy26_27_lakhs": "FY26-27 (₹ L)", "excel_row": "Excel row"})
                        st.dataframe(_show, use_container_width=True, hide_index=True)
                if not _ar["skipped_rows"].empty:
                    with st.expander(f"ℹ️ {len(_ar['skipped_rows'])} rows not imported as EHPL AOP"):
                        st.dataframe(_ar["skipped_rows"], use_container_width=True, hide_index=True)
            else:
                upload_status.render_result(False, _ar["file_name"], _ar["message"],
                    stage=_ar["stage"], expected_format=upload_status.FORMAT_AOP)
        if st.button("✖️ Dismiss", key="up_aop_dismiss"):
            del st.session_state["_up_aop_results"]
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — Traffic Import
# ─────────────────────────────────────────────────────────────────────────────
with tab_traffic:
    st.caption("Upload airport traffic files — all formats auto-detected.")

    traffic_files = st.file_uploader("Traffic file(s) (.xlsx / .xls)",
        type=["xlsx","xls"], key="up_traffic", accept_multiple_files=True)
    if traffic_files:
        for _tf in traffic_files:
            upload_status.render_file_selected(_tf.name, getattr(_tf,"size",None))

    traffic_replace = st.checkbox(
        "Replace existing traffic for the dates and airports in this file",
        value=True, key="up_traffic_replace",
        help=("Deletes stored traffic for each airport and date this file covers, then "
              "imports the file. Without this, rows that already exist are kept unchanged, "
              "so a corrected traffic file cannot update earlier figures."),
    )

    if st.button("🔍 Analyse", type="primary", disabled=not traffic_files, key="up_traffic_analyse"):
        st.session_state["_up_traffic_pending"] = [f.name for f in traffic_files]
        st.session_state.pop("_up_traffic_results", None)

    _t_pending = st.session_state.get("_up_traffic_pending") or []
    _t_files = {f.name: f for f in (traffic_files or [])}
    _t_ready = []                      # (name, mapping-state json or None)
    _t_templates = _templates_json("traffic") if _t_pending else "[]"
    for _i, _name in enumerate(_t_pending):
        _f = _t_files.get(_name)
        if _f is None:
            continue
        _bytes = _f.getvalue()
        _state = mapping_editor.get_state("traffic", _name)
        _sj = mapping_editor.state_json(_state) if _state else None
        with st.spinner(f"🔍 Analysing {_name}…"):
            if _sj:
                _df, _ident, _an, _err = _analyse_traffic_mapped(_bytes, _name, _sj)
            else:
                _df, _ident, _an, _err = _analyse_traffic(_bytes, _name, _t_templates)
        if _err:
            upload_status.render_result(False, _name, _err, stage="reading",
                                        expected_format=upload_status.FORMAT_TRAFFIC)
        else:
            analyse_panel.render(_name, _ident, _an, preview=_df, key=f"tr{_i}")
            _t_ready.append((_name, _sj))
        if _err or _sj:
            mapping_editor.render("traffic", _bytes, _name, key=f"trmap{_i}", expanded=bool(_err))
    _t_remember = {}
    for _name, _sj in _t_ready:
        if _sj:
            st.markdown(f"**{_name}** — save this column mapping for next time?")
            _t_remember[_name] = mapping_editor.remember_inputs("traffic", _name, f"trrem_{_name}")
    if _t_pending:
        _c1, _c2 = st.columns([1, 4])
        _save = _c1.button("💾 Save", type="primary", disabled=not _t_ready, key="up_traffic_save")
        if _c2.button("✖️ Cancel", key="up_traffic_cancel"):
            st.session_state.pop("_up_traffic_pending", None)
            st.rerun()
        if _save:
            pending_t = []
            for _name, _sj in _t_ready:
                _bytes = _t_files[_name].getvalue()
                _parsed = (_analyse_traffic_mapped(_bytes, _name, _sj) if _sj
                           else _analyse_traffic(_bytes, _name, _t_templates))[0]
                try:
                    with st.spinner(f"💾 Saving {_name}…"):
                        _sr = database.save_traffic_dataframe(_parsed, _name, replace=traffic_replace)
                    if _sj and _t_remember.get(_name):
                        _remember_layout("traffic", _t_remember[_name], json.loads(_sj), _bytes, _name)
                    for _r in set((_parsed.attrs.get("readers") or {}).values()):
                        if _r.startswith(SAVED_LAYOUT):
                            _mark_template_used("traffic", _r)
                    pending_t.append({"success": True, "file_name": _name,
                        "inserted": _sr["inserted"], "skipped": _sr["skipped"],
                        "rows_parsed": len(_parsed),
                        "skipped_sheets": _parsed.attrs.get("skipped_sheets", []),
                        "replaced": _sr.get("replaced", 0)})
                except Exception as _exc2:
                    pending_t.append({"success": False, "file_name": _name,
                        "message": str(_exc2), "stage": "saving"})
                st.session_state.pop(mapping_editor.state_key("traffic", _name), None)
            st.session_state["_up_traffic_results"] = pending_t
            st.session_state.pop("_up_traffic_pending", None)
            _analyse_traffic.clear()
            _analyse_traffic_mapped.clear()
            clear_data_cache()  # new data must show on every page immediately
            st.rerun()

    if "_up_traffic_results" in st.session_state:
        for _tr in st.session_state["_up_traffic_results"]:
            if _tr["success"]:
                upload_status.render_result(True, _tr["file_name"], "",
                    inserted=_tr["inserted"], skipped=_tr["skipped"],
                    extra_lines=[f"**Rows parsed:** {_tr['rows_parsed']:,}"]
                                + ([f"**Replaced:** {_tr['replaced']:,} earlier rows for the same airports and dates"]
                                   if _tr.get("replaced") else []))
                for _msg in _tr.get("skipped_sheets") or []:
                    st.warning(f"⚠️ {_msg}")
            else:
                upload_status.render_result(False, _tr["file_name"], _tr["message"],
                    stage=_tr["stage"], expected_format=upload_status.FORMAT_TRAFFIC)
        if st.button("✖️ Dismiss", key="up_traffic_dismiss"):
            del st.session_state["_up_traffic_results"]
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — Database Stats
# ─────────────────────────────────────────────────────────────────────────────
with tab_db:
    with safe_run("Database stats", error_type="db_error"):
        stats = cached_db.get_db_stats()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Rows", f"{stats['total_rows']:,}")
        m2.metric("Distinct Dates", f"{stats['distinct_dates']:,}")
        m3.metric("Earliest", str(stats["min_date"]) if stats["min_date"] else "—")
        m4.metric("Latest", str(stats["max_date"]) if stats["max_date"] else "—")

    # Saved layouts: files the app learned to read from a confirmed mapping
    with safe_run("Saved layouts", error_type="db_error"):
        st.markdown("##### Saved layouts")
        _layouts = database.list_parse_templates()
        if not _layouts:
            st.caption("None yet. When the app cannot read a file's layout, map its columns "
                       "once under **Teach the app this layout**; ticking *Remember this "
                       "layout* saves it here and the same layout is read automatically "
                       "next time.")
        else:
            st.dataframe(pd.DataFrame([{
                "Name": t["name"], "For": t["kind"].title(),
                "Columns recognised": ", ".join(t["fingerprint"][:8])
                                      + (" …" if len(t["fingerprint"]) > 8 else ""),
                "Created by": t["created_by"] or "", "Created": (t["created_at"] or "")[:10],
                "Used": t["times_used"], "Last used": (t["last_used"] or "")[:10],
            } for t in _layouts]), use_container_width=True, hide_index=True)
            if _is_admin():
                _del = st.selectbox("Delete a saved layout", ["—"] + [
                    f"{t['id']}: {t['name']} ({t['kind']})" for t in _layouts], key="up_tpl_del")
                if _del != "—" and st.button("🗑️ Delete", key="up_tpl_del_btn"):
                    database.delete_parse_template(int(_del.split(":", 1)[0]))
                    st.rerun()
