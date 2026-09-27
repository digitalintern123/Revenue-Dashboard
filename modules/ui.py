"""
ui.py — Shared presentation helpers: brand colours, global CSS, page
headers and section titles.

Presentation only — nothing here touches the database or business logic.
`inject_css()` is called once from Home.py; because Home.py runs on every
rerun under st.navigation, the styles apply to every page.
"""

from __future__ import annotations

import base64
import functools
import html
import os

import streamlit as st

# Encalm brand colours, sampled from the official logo (assets/encalm_logo.png).
COLORS = {
    "navy": "#142248",        # ENCALM wordmark
    "navy_dark": "#0C1530",
    "gold": "#CBA578",        # petal mark — lines, bars, accents only
    "gold_text": "#8C6A3F",   # darker gold for text on white (readable contrast)
    "gold_tint": "#F3ECE1",   # subtotal rows, highlights
    "growth": "#0B7A57",
    "decline": "#B91C1C",
    "neutral": "#5F6677",
    "compare": "#B9B2A6",     # compare-period bars (warm grey)
    "border": "#E7E1D7",
    "surface": "#F6F3EE",
}

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
LOGO_STACKED = os.path.join(_ASSETS, "encalm_logo.png")                  # light backgrounds
LOGO_SIDEBAR = os.path.join(_ASSETS, "encalm_logo_horizontal_light.png")  # navy sidebar
LOGO_MARK = os.path.join(_ASSETS, "encalm_mark.png")                      # icon / favicon
_ICONS = os.path.join(_ASSETS, "icons")  # Lucide SVGs (lucide.dev, ISC licence)


def logo_path() -> str:
    return LOGO_SIDEBAR


def logo_icon_path() -> str:
    """Small mark shown in the top bar when the sidebar is collapsed."""
    return LOGO_MARK


_BRAND_FONT = "'Montserrat', 'Segoe UI', sans-serif"

_CSS = f"""
<style>
/* Montserrat: closest free match to the ENCALM wordmark. Used for headings,
   KPI values, navigation and labels; tables keep the default font. */
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800&display=swap');
/* ── Layout ─────────────────────────────────────────────────────────── */
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1500px; }}
h1, h2, h3, h4, h5 {{ color: {COLORS["navy"]}; font-family: {_BRAND_FONT} !important;
    font-weight: 700; letter-spacing: 0; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] span:not([data-testid="stIconMaterial"]),
[data-testid="stTab"] p {{ font-family: {_BRAND_FONT}; }}

/* ── Sidebar ────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {{ background: {COLORS["navy"]}; }}
section[data-testid="stSidebar"] * {{ color: #E6ECF5; }}
section[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] {{
    color: {COLORS["gold"]} !important; font-family: {_BRAND_FONT}; font-weight: 700; letter-spacing: .14em;
    text-transform: uppercase; font-size: .72rem;
}}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:hover {{
    background: rgba(255,255,255,.08);
}}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: rgba(203,165,120,.20); border-left: 3px solid {COLORS["gold"]};
}}
section[data-testid="stSidebar"] button[data-testid^="stBaseButton-secondary"] {{
    background: transparent; border: 1px solid rgba(255,255,255,.35);
}}
section[data-testid="stSidebar"] button[data-testid^="stBaseButton-secondary"]:hover {{
    border-color: {COLORS["gold"]}; color: {COLORS["gold"]};
}}
section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.15); }}

/* ── Page header ────────────────────────────────────────────────────── */
/* ── Lucide icons (drawn as CSS masks so they take the text colour) ──── */
.enc-icon, .enc-ico::before {{
    display: inline-block; width: 1.05em; height: 1.05em; flex: none;
    background-color: currentColor; vertical-align: -0.16em;
    -webkit-mask: var(--icon) center / contain no-repeat; mask: var(--icon) center / contain no-repeat;
}}
.enc-header h1 .enc-icon {{ color: {COLORS["gold"]}; width: .9em; height: .9em;
    margin-right: .45em; vertical-align: -0.08em; }}

.enc-user {{ font-size: .85rem; opacity: .85; margin-bottom: .5rem; }}
.enc-user .enc-icon {{ margin-right: .35em; color: {COLORS["gold"]}; }}

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
.enc-label {{ font-family: {_BRAND_FONT}; font-size: .74rem; font-weight: 600; color: {COLORS["neutral"]};
    text-transform: uppercase; letter-spacing: .05em; margin-bottom: -.35rem; }}

/* ── KPI cards (st.metric) ──────────────────────────────────────────── */
div[data-testid="stMetric"] {{
    background: #FFFFFF; border: 1px solid {COLORS["border"]}; border-radius: 12px;
    padding: .9rem 1.1rem; box-shadow: 0 1px 3px rgba(15,39,68,.06);
    border-top: 3px solid {COLORS["gold"]};
}}
div[data-testid="stMetricLabel"] p {{ color: {COLORS["neutral"]}; font-weight: 600; }}
div[data-testid="stMetricValue"] {{ color: {COLORS["navy"]}; font-family: {_BRAND_FONT};
    font-weight: 700; font-size: 1.55rem; }}

/* ── Bordered containers (filter bar, charts) ───────────────────────── */
div[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 12px; }}

/* ── Tabs ───────────────────────────────────────────────────────────── */
[data-testid="stTab"] p {{ font-weight: 600; }}

/* ── Sign-in ────────────────────────────────────────────────────────── */
.enc-login {{ text-align: center; margin: 3rem 0 1.2rem 0; }}
.enc-login img {{ height: 120px; margin-bottom: 1.4rem; }}
.enc-login h2 {{ margin: 0; font-size: 1.5rem; }}
.enc-login p {{ color: {COLORS["neutral"]}; margin: .3rem 0 0 0; font-size: .9rem; }}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


@functools.lru_cache(maxsize=None)
def lucide(name: str) -> str:
    """CSS url() for a bundled Lucide icon (assets/icons/<name>.svg)."""
    with open(os.path.join(_ICONS, f"{name}.svg"), "rb") as f:
        return f"url('data:image/svg+xml;base64,{base64.b64encode(f.read()).decode()}')"


def icon_html(name: str) -> str:
    """Inline Lucide icon in the surrounding text colour."""
    return f'<span class="enc-icon" style="--icon: {lucide(name)}"></span>'


def _icon_rule(selector: str, name: str) -> str:
    return (
        f"{selector}::before {{ content: ''; display: inline-block; flex: none; width: 1.05em;"
        f" height: 1.05em; margin-right: .5em; vertical-align: -0.16em; background-color: currentColor;"
        f" -webkit-mask: {lucide(name)} center / contain no-repeat;"
        f" mask: {lucide(name)} center / contain no-repeat; }}"
    )


def sidebar_nav_icons(icons: dict[str, str]) -> None:
    """Lucide icons for the sidebar page links. `icons` maps each page's
    url_path to an icon name; "" is the default (root) page."""
    # The link is a flex row, so its ::before sits beside the label.
    rules = [
        _icon_rule(
            f'section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][href$="/{url_path}"]',
            name,
        )
        for url_path, name in icons.items()
    ]
    st.markdown(f"<style>{''.join(rules)}</style>", unsafe_allow_html=True)


def tab_icons(key: str, icons: list[str]) -> None:
    """Lucide icons for the tabs of `st.tabs(..., key=key)`, in tab order."""
    rules = [
        _icon_rule(
            f'.st-key-{key} > div > [role="tablist"] > [data-testid="stTab"]:nth-of-type({i}) p',
            name,
        )
        for i, name in enumerate(icons, start=1)
    ]
    st.markdown(f"<style>{''.join(rules)}</style>", unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", icon: str | None = None) -> None:
    ico = icon_html(icon) if icon else ""
    sub = f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f'<div class="enc-header"><h1>{ico}{html.escape(title)}</h1>'
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
