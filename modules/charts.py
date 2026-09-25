"""
charts.py — Plotly charts for the dashboard pages (EHPL, Encalm Eats,
Sky Plates). Presentation only: callers pass already-filtered DataFrames.

Colour encoding: current period = brand navy, compare period = muted grey
(context). Every chart has a legend and hover tooltips, and the full
numbers are always in the tables below the charts.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.formatting import format_money
from modules.ui import COLORS

_FONT = dict(family="sans-serif", size=12, color="#1F2937")
_CONFIG = {"displayModeBar": False, "responsive": True}


def _short_inr(v: float) -> str:
    """Axis-friendly rupees: ₹1.25 Cr / ₹8.4 L / ₹56K."""
    v = float(v)
    a = abs(v)
    if a >= 1e7:
        return f"₹{v / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"₹{v / 1e5:.1f} L"
    if a >= 1e3:
        return f"₹{v / 1e3:.0f}K"
    return f"₹{v:.0f}"


def _axis_ticks(max_val: float, n: int = 4) -> tuple[list[float], list[str]]:
    if max_val <= 0:
        return [0], ["₹0"]
    step = max_val / n
    vals = [step * i for i in range(n + 1)]
    return vals, [_short_inr(v) for v in vals]


def _layout(fig: go.Figure, title: str, height: int) -> None:
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15, color=COLORS["navy"])),
        height=height,
        margin=dict(l=8, r=16, t=48, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_FONT,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1,
                    font=dict(size=11)),
        hoverlabel=dict(bgcolor="white", bordercolor=COLORS["border"], font=_FONT),
    )


def revenue_by_group_bar(
    cur_df: pd.DataFrame,
    cmp_df: pd.DataFrame | None,
    by: str,
    cur_label: str,
    cmp_label: str,
    title: str,
    top_n: int = 10,
) -> None:
    """Horizontal bars: revenue per `by` (location/outlet), current vs compare."""
    if cur_df is None or cur_df.empty or by not in cur_df.columns:
        return
    cur = cur_df.groupby(cur_df[by].astype(str).str.strip())["revenue"].sum()
    cmp = (
        cmp_df.groupby(cmp_df[by].astype(str).str.strip())["revenue"].sum()
        if cmp_df is not None and not cmp_df.empty and by in cmp_df.columns
        else pd.Series(dtype=float)
    )
    cur = cur.sort_values(ascending=False).head(top_n)
    cats = list(cur.index)[::-1]  # largest at the top
    cmp = cmp.reindex(cats).fillna(0)
    cur = cur.reindex(cats)

    fig = go.Figure()
    if cmp.sum() > 0:
        fig.add_bar(
            y=cats, x=cmp.values, name=cmp_label, orientation="h",
            marker=dict(color=COLORS["compare"], cornerradius=4),
            customdata=[format_money(v) for v in cmp.values],
            hovertemplate="%{y}<br>" + cmp_label + ": %{customdata}<extra></extra>",
        )
    fig.add_bar(
        y=cats, x=cur.values, name=cur_label, orientation="h",
        marker=dict(color=COLORS["navy"], cornerradius=4),
        customdata=[format_money(v) for v in cur.values],
        hovertemplate="%{y}<br>" + cur_label + ": %{customdata}<extra></extra>",
    )
    tv, tt = _axis_ticks(max(cur.max(), cmp.max() if len(cmp) else 0))
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.12)
    fig.update_xaxes(tickvals=tv, ticktext=tt, showgrid=True, gridcolor="#EEF1F5",
                     zeroline=False)
    fig.update_yaxes(showgrid=False, automargin=True)
    _layout(fig, title, height=max(320, 70 + 42 * len(cats)))
    st.plotly_chart(fig, use_container_width=True, config=_CONFIG)


def revenue_trend_line(daily: pd.DataFrame, title: str, highlight_date=None) -> None:
    """Daily revenue line. `daily` needs columns date, revenue (one row per date)."""
    if daily is None or daily.empty:
        return
    daily = daily.sort_values("date")
    fig = go.Figure()
    fig.add_scatter(
        x=daily["date"], y=daily["revenue"], mode="lines", name="Revenue",
        line=dict(color=COLORS["navy"], width=2),
        fill="tozeroy", fillcolor="rgba(30,58,95,0.08)",
        customdata=[format_money(v) for v in daily["revenue"]],
        hovertemplate="%{x|%d %b %Y}<br>%{customdata}<extra></extra>",
        showlegend=False,
    )
    if highlight_date is not None:
        hit = daily[daily["date"] == pd.Timestamp(highlight_date)]
        if not hit.empty:
            fig.add_scatter(
                x=hit["date"], y=hit["revenue"], mode="markers", name="Report date",
                marker=dict(size=10, color=COLORS["gold"],
                            line=dict(color="white", width=2)),
                hoverinfo="skip", showlegend=False,
            )
    tv, tt = _axis_ticks(float(daily["revenue"].max()))
    fig.update_yaxes(tickvals=tv, ticktext=tt, showgrid=True, gridcolor="#EEF1F5",
                     zeroline=False, rangemode="tozero")
    fig.update_xaxes(showgrid=False, tickformat="%d %b")
    fig.update_layout(hovermode="x unified", showlegend=False)
    _layout(fig, title, height=320)
    st.plotly_chart(fig, use_container_width=True, config=_CONFIG)
