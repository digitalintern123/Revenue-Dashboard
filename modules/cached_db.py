"""
modules/cached_db.py — Streamlit-cached wrappers for the database read
functions used while rendering pages.

Streamlit re-runs the whole page on every widget interaction. Without
caching, each run repeats the same 15–30 read queries; on a hosted setup
where every query is a network round trip to the database, that makes each
click take seconds. These wrappers serve repeat reads from memory.

Usage — replace direct database calls in pages with:

    from modules.cached_db import get_available_dates, load_for_date_range

Freshness: every upload/import/reset path calls `clear_data_cache()`, so new
data shows up immediately. The TTL only bounds staleness for changes made
outside this app (e.g. another server process or direct SQL).

Importing this module also routes the traffic joins in `database` through a
cached traffic loader (see database._traffic_totals_loader).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from . import database

_TTL = 600  # seconds


@st.cache_data(ttl=_TTL, show_spinner=False)
def get_available_dates() -> list[dt.date]:
    """Cached: all distinct revenue dates, sorted ascending."""
    return database.get_available_dates()


@st.cache_data(ttl=_TTL, show_spinner=False)
def load_for_date_range(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """Cached: revenue rows for [start_date, end_date]."""
    return database.load_for_date_range(start_date, end_date)


@st.cache_data(ttl=_TTL, show_spinner=False)
def load_for_date(target_date: dt.date) -> pd.DataFrame:
    """Cached: revenue rows for a single date."""
    return database.load_for_date(target_date)


@st.cache_data(ttl=_TTL, show_spinner=False)
def load_aop_targets_for_range(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """Cached: AOP target rows for a date range."""
    return database.load_aop_targets_for_range(start_date, end_date)


@st.cache_data(ttl=_TTL, show_spinner=False)
def load_traffic_for_date_range(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """Cached: airport traffic rows for a date range."""
    return database.load_traffic_for_date_range(start_date, end_date)


@st.cache_data(ttl=_TTL, show_spinner=False)
def get_traffic_total_for_range(
    start_date: dt.date, end_date: dt.date, location: str | None = None
) -> pd.DataFrame:
    """Cached: best-available traffic totals per location/terminal."""
    return database.get_traffic_total_for_range(start_date, end_date, location)


@st.cache_data(ttl=_TTL, show_spinner=False)
def get_available_traffic_dates() -> list[dt.date]:
    """Cached: distinct traffic dates, sorted ascending."""
    return database.get_available_traffic_dates()


@st.cache_data(ttl=_TTL, show_spinner=False)
def get_available_week_starts() -> list[dt.date]:
    return database.get_available_week_starts()


@st.cache_data(ttl=_TTL, show_spinner=False)
def get_available_year_months() -> list[tuple[int, int]]:
    return database.get_available_year_months()


@st.cache_data(ttl=_TTL, show_spinner=False)
def get_available_years() -> list[int]:
    return database.get_available_years()


@st.cache_data(ttl=_TTL, show_spinner=False)
def load_encalm_eats_dsr_for_range(start_date, end_date) -> pd.DataFrame:
    return database.load_encalm_eats_dsr_for_range(start_date, end_date)


@st.cache_data(ttl=_TTL, show_spinner=False)
def get_encalm_eats_dsr_dates() -> list:
    return database.get_encalm_eats_dsr_dates()


@st.cache_data(ttl=_TTL, show_spinner=False)
def get_upload_history() -> pd.DataFrame:
    return database.get_upload_history()


@st.cache_data(ttl=_TTL, show_spinner=False)
def get_dates_summary() -> pd.DataFrame:
    return database.get_dates_summary()


@st.cache_data(ttl=_TTL, show_spinner=False)
def get_db_stats() -> dict:
    return database.get_db_stats()


def _cached_traffic_totals(start_date, end_date, location=None):
    return get_traffic_total_for_range(start_date, end_date, location)


# Route database's traffic joins through the cache (one query per date range
# instead of one per join call and per rerun).
database._traffic_totals_loader = _cached_traffic_totals


_ALL_CACHED = (
    get_available_dates, load_for_date_range, load_for_date,
    load_aop_targets_for_range, load_traffic_for_date_range,
    get_traffic_total_for_range, get_available_traffic_dates,
    get_available_week_starts, get_available_year_months, get_available_years,
    load_encalm_eats_dsr_for_range, get_encalm_eats_dsr_dates,
    get_upload_history, get_dates_summary, get_db_stats,
)


def clear_data_cache() -> None:
    """
    Force-invalidate all cached DB results immediately.

    Call this right after any successful write (upload, import, reset) so
    every page shows fresh data on the next run:

        from modules.cached_db import clear_data_cache
        clear_data_cache()
        st.rerun()
    """
    for fn in _ALL_CACHED:
        fn.clear()
