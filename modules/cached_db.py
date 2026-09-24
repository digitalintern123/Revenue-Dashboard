"""
modules/cached_db.py — Streamlit-cached wrappers for the most-frequently
called database read functions.

Every analytics page calls get_available_dates() and load_for_date_range()
on every re-run (every widget interaction). Without caching these hit the
database 10–20 times per page visit. With @st.cache_data(ttl=60) the result
is served from memory for 60 seconds, cutting DB round-trips by ~95%.

Usage — replace direct database calls in pages with:

    from modules.cached_db import get_available_dates, load_for_date_range

The cache is invalidated automatically after `ttl` seconds, so fresh uploads
appear within one minute even without a manual clear.  If an upload just
succeeded and the user navigates immediately, they can call
`clear_data_cache()` to force an immediate refresh.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from . import database


@st.cache_data(ttl=60, show_spinner=False)
def get_available_dates() -> list[dt.date]:
    """Cached: all distinct revenue dates, sorted ascending. Refreshes every 60 s."""
    return database.get_available_dates()


@st.cache_data(ttl=60, show_spinner=False)
def load_for_date_range(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """Cached: revenue rows for [start_date, end_date]. Refreshes every 60 s."""
    return database.load_for_date_range(start_date, end_date)


@st.cache_data(ttl=60, show_spinner=False)
def load_for_date(target_date: dt.date) -> pd.DataFrame:
    """Cached: revenue rows for a single date. Refreshes every 60 s."""
    return database.load_for_date(target_date)


@st.cache_data(ttl=60, show_spinner=False)
def load_aop_targets_for_range(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """Cached: AOP target rows for a date range. Refreshes every 60 s."""
    return database.load_aop_targets_for_range(start_date, end_date)


@st.cache_data(ttl=60, show_spinner=False)
def load_traffic_for_date_range(
    start_date: dt.date,
    end_date: dt.date,
    location: str | None = None,
) -> pd.DataFrame:
    """Cached: airport traffic rows for a date range. Refreshes every 60 s."""
    return database.load_traffic_for_date_range(start_date, end_date, location)


@st.cache_data(ttl=60, show_spinner=False)
def get_available_traffic_dates() -> list[dt.date]:
    """Cached: distinct traffic dates, sorted ascending. Refreshes every 60 s."""
    return database.get_available_traffic_dates()


def clear_data_cache() -> None:
    """
    Force-invalidate all cached DB results immediately.

    Call this right after a successful upload so the user sees fresh data
    without waiting for the 60-second TTL to expire:

        from modules.cached_db import clear_data_cache
        clear_data_cache()
        st.rerun()
    """
    get_available_dates.clear()
    load_for_date_range.clear()
    load_for_date.clear()
    load_aop_targets_for_range.clear()
    load_traffic_for_date_range.clear()
    get_available_traffic_dates.clear()
