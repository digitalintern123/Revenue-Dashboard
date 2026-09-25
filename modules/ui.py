"""
ui.py — Shared presentation helpers: brand colours, global CSS, page
headers and section titles.

Presentation only — nothing here touches the database or business logic.
`inject_css()` is called once from Home.py; because Home.py runs on every
rerun under st.navigation, the styles apply to every page.
"""

from __future__ import annotations

import html
import os

import streamlit as st

COLORS = {
    "navy": "#1E3A5F",
    "navy_dark": "#0F2744",
    "gold": "#C9A227",
    "growth": "#0B7A57",
    "decline": "#B91C1C",
    "neutral": "#64748B",
    "compare": "#AAB4C3",
    "border": "#E3E8EF",
    "surface": "#F4F6FA",
}

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
# A real logo dropped into assets/ (see assets/README.md) wins over the wordmark.
_CUSTOM_LOGO = os.path.join(_ASSETS, "encalm_logo.png")
_WORDMARK = os.path.join(_ASSETS, "logo.svg")
_ICON = os.path.join(_ASSETS, "logo_icon.svg")


def logo_path() -> str:
    return _CUSTOM_LOGO if os.path.exists(_CUSTOM_LOGO) else _WORDMARK


def logo_icon_path() -> str:
    """Small mark shown in the top bar when the sidebar is collapsed."""
    return _CUSTOM_LOGO if os.path.exists(_CUSTOM_LOGO) else _ICON


_CSS = f"""
<style>
/* ── Layout ─────────────────────────────────────────────────────────── */
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1500px; }}
h1, h2, h3, h4 {{ color: {COLORS["navy"]}; letter-spacing: -0.01em; }}

/* ── Sidebar ────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {{ background: {COLORS["navy"]}; }}
section[data-testid="stSidebar"] * {{ color: #E6ECF5; }}
section[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] {{
    color: {COLORS["gold"]} !important; font-weight: 700; letter-spacing: .08em;
    text-transform: uppercase; font-size: .72rem;
}}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:hover {{
    background: rgba(255,255,255,.08);
}}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: rgba(201,162,39,.18); border-left: 3px solid {COLORS["gold"]};
}}
section[data-testid="stSidebar"] button[data-testid^="stBaseButton-secondary"] {{
    background: transparent; border: 1px solid rgba(255,255,255,.35);
}}
section[data-testid="stSidebar"] button[data-testid^="stBaseButton-secondary"]:hover {{
    border-color: {COLORS["gold"]}; color: {COLORS["gold"]};
}}
section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.15); }}

/* ── Page header ────────────────────────────────────────────────────── */
.enc-header {{ margin: 0 0 1.1rem 0; }}
.enc-header h1 {{ font-size: 2rem; font-weight: 700; margin: 0; padding: 0; }}
.enc-header .enc-accent {{ width: 56px; height: 4px; background: {COLORS["gold"]};
    border-radius: 2px; margin: .45rem 0 .55rem 0; }}
.enc-header p {{ color: {COLORS["neutral"]}; margin: 0; font-size: .92rem; }}

.enc-section {{ display: flex; align-items: center; gap: .6rem;
    margin: 1.6rem 0 .6rem 0; }}
.enc-section span.bar {{ width: 4px; height: 1.3rem; background: {COLORS["gold"]};
    border-radius: 2px; }}
.enc-section h3 {{ margin: 0; padding: 0; font-size: 1.25rem; }}

.enc-summary {{ color: {COLORS["neutral"]}; font-size: .88rem; margin: .2rem 0 .4rem 0; }}
.enc-summary b {{ color: {COLORS["navy"]}; }}
.enc-label {{ font-size: .78rem; font-weight: 600; color: {COLORS["neutral"]};
    text-transform: uppercase; letter-spacing: .05em; margin-bottom: -.35rem; }}

/* ── KPI cards (st.metric) ──────────────────────────────────────────── */
div[data-testid="stMetric"] {{
    background: #FFFFFF; border: 1px solid {COLORS["border"]}; border-radius: 12px;
    padding: .9rem 1.1rem; box-shadow: 0 1px 3px rgba(15,39,68,.06);
    border-top: 3px solid {COLORS["navy"]};
}}
div[data-testid="stMetricLabel"] p {{ color: {COLORS["neutral"]}; font-weight: 600; }}
div[data-testid="stMetricValue"] {{ color: {COLORS["navy"]}; font-weight: 700; font-size: 1.65rem; }}

/* ── Bordered containers (filter bar, charts) ───────────────────────── */
div[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 12px; }}

/* ── Tabs ───────────────────────────────────────────────────────────── */
button[data-baseweb="tab"] p {{ font-weight: 600; }}

/* ── Sign-in ────────────────────────────────────────────────────────── */
.enc-login {{ text-align: center; margin: 3rem 0 1.2rem 0; }}
.enc-login img {{ height: 44px; margin-bottom: 1rem; }}
.enc-login h2 {{ margin: 0; font-size: 1.5rem; }}
.enc-login p {{ color: {COLORS["neutral"]}; margin: .3rem 0 0 0; font-size: .9rem; }}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    sub = f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f'<div class="enc-header"><h1>{html.escape(title)}</h1>'
        f'<div class="enc-accent"></div>{sub}</div>',
        unsafe_allow_html=True,
    )


def section(title: str) -> None:
    st.markdown(
        f'<div class="enc-section"><span class="bar"></span>'
        f"<h3>{html.escape(title)}</h3></div>",
        unsafe_allow_html=True,
    )


def field_label(text: str) -> None:
    st.markdown(f'<div class="enc-label">{html.escape(text)}</div>', unsafe_allow_html=True)


def summary_line(current: str, compare: str, location: str) -> None:
    st.markdown(
        f'<div class="enc-summary">Showing <b>{html.escape(current)}</b> vs '
        f"<b>{html.escape(compare)}</b> · {html.escape(location)}</div>",
        unsafe_allow_html=True,
    )
