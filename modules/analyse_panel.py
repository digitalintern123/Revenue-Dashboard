"""
analyse_panel.py — the "what is in this file" panel shown after **Analyse**
on every upload point (Daily Revenue, AOP Targets, Traffic, Encalm Eats DSR).

Shows the overall confidence, the sheet-by-sheet identification
(modules/format_registry.py) and the pre-save checks
(modules/upload_checks.py). Nothing here writes to the database.
"""
from __future__ import annotations

import html
from typing import Optional

import pandas as pd
import streamlit as st

from modules.upload_checks import OK, INFO, WARN, Analysis

_ICON = {OK: "✅", INFO: "ℹ️", WARN: "⚠️"}


def confidence_label(conf: Optional[float]) -> str:
    if conf is None:
        return "not scored"
    if conf >= 0.95:
        return f"{conf:.0%} — high"
    if conf >= 0.8:
        return f"{conf:.0%} — good"
    if conf >= 0.55:
        return f"{conf:.0%} — check the mapping"
    return f"{conf:.0%} — low"


def render(file_name: str, ident: pd.DataFrame, analysis: Analysis,
           preview: Optional[pd.DataFrame] = None, key: str = "") -> None:
    """One file's analysis. `key` keeps widget keys unique per file."""
    conf = analysis.confidence
    n_warn = analysis.warnings
    head = (f"**{html.escape(file_name)}** · confidence **{confidence_label(conf)}** · "
            + (f"**{n_warn} thing(s) to check**" if n_warn else "no problems found"))
    if conf is not None and conf < 0.8 or n_warn:
        st.warning(head, icon="🔎")
    else:
        st.success(head, icon="🔎")

    st.markdown("###### What the app found in the file")
    st.dataframe(ident, use_container_width=True, hide_index=True)

    if analysis.checks:
        st.markdown("###### Checks before saving")
    for i, c in enumerate(analysis.checks):
        line = f"{_ICON.get(c.level, '')} **{c.title}**" + (f" — {c.detail}" if c.detail else "")
        if c.table is not None and not c.table.empty:
            more = f" (first {len(c.table)} of {c.count:,})" if c.count > len(c.table) else ""
            with st.expander(line.split(" — ")[0] + more, expanded=c.level == WARN):
                if c.detail:
                    st.caption(c.detail)
                st.dataframe(c.table, use_container_width=True, hide_index=True)
        elif c.level == WARN:
            st.warning(line)
        else:
            st.caption(line)

    if preview is not None and not preview.empty:
        with st.expander(f"Preview — first 200 of {len(preview):,} row(s)"):
            st.dataframe(preview.head(200), use_container_width=True, hide_index=True)
