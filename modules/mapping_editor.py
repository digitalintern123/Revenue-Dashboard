"""
mapping_editor.py — "Teach the app this layout" on the upload screen.

Shown for a revenue or traffic file the app could not read with confidence.
The person picks the sheet and header row, confirms or corrects the
suggested role of every column (layout_learning.propose), and adds a value
for anything the file has no column for (e.g. the location). The confirmed
mapping is kept in session state (small: roles only, no data) and read by
the page; on Save it can be remembered as a saved layout.
"""
from __future__ import annotations

import json
from typing import Optional

import pandas as pd
import streamlit as st

from modules import layout_learning as ll


def state_key(kind: str, file_name: str) -> str:
    return f"_map::{kind}::{file_name}"


def get_state(kind: str, file_name: str) -> Optional[dict]:
    return st.session_state.get(state_key(kind, file_name))


def state_json(state: dict) -> str:
    return json.dumps(state, sort_keys=True, default=str)


def render(kind: str, file_bytes: bytes, file_name: str, key: str,
           default_sheet: Optional[str] = None, expanded: bool = False) -> None:
    """The editor for one file. Writes the confirmed mapping to session state."""
    current = get_state(kind, file_name)
    with st.expander("🧩 Teach the app this layout (map the columns)", expanded=expanded):
        st.caption("The app could not read this layout with confidence. Check the role of each "
                   "column — the app's guess and its confidence are filled in — then press "
                   "**Read with this mapping**. Columns set to *Ignore* are not imported.")
        sheets = ll.sheet_names(file_bytes, file_name)
        sheet = None
        if sheets:
            idx = sheets.index(current["sheet"]) if current and current.get("sheet") in sheets else (
                sheets.index(default_sheet) if default_sheet in sheets else 0)
            sheet = st.selectbox("Sheet", sheets, index=idx, key=f"{key}_sheet")
        try:
            grid = ll.read_grid(file_bytes, file_name, sheet)
        except Exception as exc:
            st.error(f"Could not read the sheet: {exc}")
            return
        guess = ll.guess_header_row(grid)
        hr_default = current["header_row"] if current and current.get("sheet") == sheet else guess
        hr = st.number_input("Row with the column headers (as numbered in Excel)", min_value=1,
                             max_value=max(1, len(grid)), value=int(hr_default) + 1,
                             key=f"{key}_hr") - 1
        headers, data = ll.table_at(grid, hr)
        proposal = ll.propose(headers, data, kind)
        if current and current.get("sheet") == sheet and current.get("header_row") == hr:
            saved = pd.DataFrame(current["mapping"])
            if list(saved["Column"]) == headers:
                proposal["Role"] = saved["Role"].values
                if "Terminal" in proposal and "Terminal" in saved:
                    proposal["Terminal"] = saved["Terminal"].values
        roles = ll.REVENUE_ROLES if kind == "revenue" else ll.TRAFFIC_ROLES
        cfg = {
            "Column": st.column_config.TextColumn("Column", disabled=True),
            "Sample values": st.column_config.TextColumn("Sample values", disabled=True),
            "Role": st.column_config.SelectboxColumn("Role", options=roles, required=True),
            "Confidence": st.column_config.ProgressColumn(
                "App's confidence", min_value=0.0, max_value=1.0, format="%.0f%%"),
        }
        if kind == "traffic":
            cfg["Terminal"] = st.column_config.TextColumn(
                "Terminal (for Traffic columns)",
                help="Columns with the same terminal are added together, "
                     "e.g. Domestic arrivals + Domestic departures.")
        edited = st.data_editor(proposal, column_config=cfg, hide_index=True,
                                use_container_width=True, key=f"{key}_editor_{sheet}_{hr}")

        st.caption("Values for fields the file has no column for (leave blank if it has one):")
        consts = dict((current or {}).get("constants") or {})
        c1, c2, c3 = st.columns(3)
        if kind == "revenue":
            consts["location"] = c1.text_input("Location", consts.get("location", ""), key=f"{key}_loc")
            consts["business"] = c2.text_input("Business (e.g. Lounges, Atithya)",
                                               consts.get("business", ""), key=f"{key}_bus")
            consts["date"] = c3.text_input("Date (DD-MM-YYYY)", consts.get("date", ""), key=f"{key}_date")
        else:
            consts["location"] = c1.text_input("Location", consts.get("location", ""), key=f"{key}_loc")
            consts["granularity"] = c2.selectbox(
                "One row per", ["daily", "monthly"],
                index=1 if consts.get("granularity") == "monthly" else 0, key=f"{key}_gran")

        b1, b2 = st.columns([1, 3])
        if b1.button("Read with this mapping", type="primary", key=f"{key}_apply"):
            st.session_state[state_key(kind, file_name)] = {
                "sheet": sheet, "header_row": int(hr),
                "mapping": edited.to_dict("list"),
                "constants": {k: v for k, v in consts.items() if v not in (None, "")},
            }
            st.rerun()
        if current and b2.button("Forget this mapping", key=f"{key}_reset"):
            st.session_state.pop(state_key(kind, file_name), None)
            st.rerun()


def remember_inputs(kind: str, file_name: str, key: str) -> Optional[str]:
    """'Remember this layout as …' — returns the name, or None if not ticked."""
    c1, c2 = st.columns([1, 2])
    keep = c1.checkbox("Remember this layout", value=True, key=f"{key}_remember")
    default = file_name.rsplit(".", 1)[0][:40]
    name = c2.text_input("Name", value=default, key=f"{key}_tname", label_visibility="collapsed")
    return name.strip() if keep and name.strip() else None
