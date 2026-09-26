"""
session.py — Lightweight session-state helpers shared across all pages.

Per the persistence requirements: st.session_state must only ever hold
small references (selected dates, UI toggles) — never DataFrames of revenue
data. Every page re-loads its data from the database on each run via
modules.database, so navigating between pages never loses anything and
switching pages is always consistent with what's actually stored.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import streamlit as st

from . import cached_db, database

_ACTIVE_DATE_KEY   = "active_analysis_date"
_COMPARE_DATE_KEY  = "compare_analysis_date"
_BOOTSTRAPPED_KEY  = "_db_bootstrapped"


@st.cache_resource(show_spinner=False)
def _init_db_once() -> bool:
    """Run the schema check/migrations once per server process. It issues
    a dozen inspection queries, too slow to repeat for every visitor."""
    database.init_db()
    return True


def bootstrap_session() -> None:
    """
    Ensure the database schema exists. Safe to call at the top of every
    page — runs only once per server process (and is skipped entirely
    for sessions that already passed the _BOOTSTRAPPED_KEY guard).
    """
    if not st.session_state.get(_BOOTSTRAPPED_KEY):
        _init_db_once()
        st.session_state[_BOOTSTRAPPED_KEY] = True


def get_active_date() -> Optional[dt.date]:
    """The currently selected 'main' analysis date, or None if unset."""
    return st.session_state.get(_ACTIVE_DATE_KEY)


def set_active_date(value: Optional[dt.date]) -> None:
    st.session_state[_ACTIVE_DATE_KEY] = value


def get_compare_date() -> Optional[dt.date]:
    """The currently selected 'comparison' date (Page 4), or None if unset."""
    return st.session_state.get(_COMPARE_DATE_KEY)


def set_compare_date(value: Optional[dt.date]) -> None:
    st.session_state[_COMPARE_DATE_KEY] = value


def clear_session() -> None:
    """
    Clear the active workspace (selected dates / UI state) without touching
    the database or the authenticated session.

    Keeps the bootstrap flag so we don't re-run init_db needlessly, and
    preserves all auth keys so clearing workspace state never logs the
    user out.
    """
    # Auth keys are defined in auth.py — import their names directly so
    # this list stays in sync with auth.py rather than duplicating strings.
    from modules.auth import (
        _SESSION_KEY,
        _SESSION_TOKEN_KEY,
        _SESSION_CREATED_KEY,
        _FAILED_ATTEMPTS_KEY,
        _LOCKOUT_UNTIL_KEY,
        _LOGIN_ATTEMPTED_KEY,
        _LAST_ACTIVITY_KEY,
    )
    _AUTH_KEYS = {
        _SESSION_KEY,
        _SESSION_TOKEN_KEY,
        _SESSION_CREATED_KEY,
        _FAILED_ATTEMPTS_KEY,
        _LOCKOUT_UNTIL_KEY,
        _LOGIN_ATTEMPTED_KEY,
        _LAST_ACTIVITY_KEY,
        _BOOTSTRAPPED_KEY,
    }
    keys_to_clear = [
        k for k in st.session_state.keys()
        if k not in _AUTH_KEYS
    ]
    for k in keys_to_clear:
        del st.session_state[k]


def default_active_date() -> Optional[dt.date]:
    """
    Fall back to the most recent date in the database if no active date has
    been explicitly selected yet — gives every page a sensible default on
    first load instead of an empty selector.
    """
    current = get_active_date()
    if current is not None:
        return current
    dates = cached_db.get_available_dates()
    return dates[-1] if dates else None
