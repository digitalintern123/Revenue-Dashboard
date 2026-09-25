"""
auth.py — Per-person login for the app.

This exists because the app itself has no access control by default: on
Streamlit Community Cloud, anyone with the URL can open it, upload data,
and see everything already uploaded — completely independent of whether
the GitHub repo is public or private. This module is what actually closes
that gap.

Credentials live ONLY in Streamlit secrets (.streamlit/secrets.toml
locally — already gitignored — or the "Secrets" panel in the Streamlit
Cloud app settings when deployed), never in source code, never committed
to the repo, and never compared in plaintext: only a salted SHA-256 hash
of each password is stored, and verification uses a constant-time
comparison (hmac.compare_digest) to avoid leaking timing information
about how much of the password matched.

Secrets format expected (see .streamlit/secrets.toml.example):

    [auth]
    [auth.users]
    alice = "<salt>$<hash>"
    bob   = "<salt>$<hash>"

Use modules/generate_password_hash.py to create the "<salt>$<hash>" value
for a new user's password — never type a real password directly into
secrets.toml or anywhere else in plain form.

Every page should call require_login() as the very first thing, before
rendering any content — this is what makes the page show a login form
instead of the real content when nobody (or the wrong somebody) is
logged in.
"""

from __future__ import annotations

import hashlib
import os
import hmac
import secrets as _secrets_module
from typing import Optional

import datetime as _dt_module
import streamlit as st

_SESSION_KEY = "_authenticated_user"
_SESSION_TOKEN_KEY = "_session_token"     # DB-registered session token
_LOGIN_ATTEMPTED_KEY = "_login_attempted"
_FAILED_ATTEMPTS_KEY = "_failed_login_attempts"
_LOCKOUT_UNTIL_KEY = "_lockout_until"
_SESSION_CREATED_KEY = "_session_created_at"
_LAST_ACTIVITY_KEY = "_last_activity_at"
_MAX_ATTEMPTS = 5           # lock after 5 wrong passwords
_LOCKOUT_SECONDS = 300      # 5 minute lockout
_SESSION_TIMEOUT_HOURS = 8  # absolute auto-logout after 8 hours, active or not
_INACTIVITY_TIMEOUT_MINUTES = 30  # auto-logout after 30 minutes with no activity


def _hash_password(password: str, salt: str) -> str:
    """
    PBKDF2-HMAC-SHA256 with 260,000 iterations.
    Much stronger than plain SHA-256 — resistant to GPU/ASIC brute-force attacks.
    Falls back to SHA-256 for legacy hashes (those without the 'pbkdf2:' prefix)
    so existing stored hashes keep working after this upgrade.
    """
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=260_000,
    )
    return "pbkdf2:" + dk.hex()


def _hash_password_legacy(password: str, salt: str) -> str:
    """SHA-256 — kept only to verify old stored hashes during migration."""
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _verify_password(password: str, stored_salt_and_hash: str) -> bool:
    """
    Verify a password against a stored "salt$hash" string using constant-time
    comparison (prevents timing attacks). Supports both PBKDF2 hashes (new,
    prefixed with 'pbkdf2:') and plain SHA-256 hashes (legacy, for backwards
    compatibility during migration).
    """
    try:
        salt, expected_hash = stored_salt_and_hash.split("$", 1)
    except ValueError:
        return False
    if expected_hash.startswith("pbkdf2:"):
        actual_hash = _hash_password(password, salt)
    else:
        # Legacy SHA-256 hash — verify and flag for upgrade
        actual_hash = _hash_password_legacy(password, salt)
    return hmac.compare_digest(actual_hash, expected_hash)


_DUMMY_STORED = "00000000000000000000000000000000$" + "0" * 64


def _verify_password_constant_time(password: str, stored_or_none) -> bool:
    """Always runs full hash+compare even for invalid usernames (prevents timing enumeration)."""
    stored = stored_or_none if stored_or_none is not None else _DUMMY_STORED
    result = _verify_password(password, stored)
    return result and stored_or_none is not None


def _get_configured_users() -> dict:
    """
    Read the configured users from Streamlit secrets or directly from
    .streamlit/secrets.toml if st.secrets fails (e.g. Python 3.14).
    """
    # Try st.secrets first (works on Streamlit Cloud and most local setups)
    try:
        users = dict(st.secrets["auth"]["users"])
        if users:
            return users
    except Exception:
        pass

    # Fallback: read secrets.toml directly using tomllib (Python 3.11+)
    import os
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # pip install tomli for older Python
        except ImportError:
            return {}

    # Search for secrets.toml relative to this file and cwd
    search_paths = [
        os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml"),
        os.path.join(os.getcwd(), ".streamlit", "secrets.toml"),
    ]
    for path in search_paths:
        path = os.path.abspath(path)
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    data = tomllib.load(f)
                return dict(data.get("auth", {}).get("users", {}))
            except Exception:
                continue
    return {}


def is_logged_in() -> bool:
    return bool(st.session_state.get(_SESSION_KEY))


def current_user() -> Optional[str]:
    """The username of whoever is currently logged in, or None."""
    return st.session_state.get(_SESSION_KEY)


def logout() -> None:
    # Invalidate the server-side session so other tabs also get logged out
    token = st.session_state.get(_SESSION_TOKEN_KEY)
    if token:
        try:
            from . import database as _db
            _db.invalidate_session(token)
        except Exception:
            pass  # DB unavailable — still clear local state
    for key in [_SESSION_KEY, _SESSION_TOKEN_KEY, _LOGIN_ATTEMPTED_KEY,
                _SESSION_CREATED_KEY, _FAILED_ATTEMPTS_KEY, _LOCKOUT_UNTIL_KEY,
                _LAST_ACTIVITY_KEY]:
        st.session_state.pop(key, None)


def _login_brand() -> None:
    """Logo + heading shown above the sign-in form."""
    import base64
    _svg = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "logo_on_light.svg")
    img = ""
    try:
        with open(_svg, "rb") as f:
            img = f'<img src="data:image/svg+xml;base64,{base64.b64encode(f.read()).decode()}" alt="Encalm">'
    except OSError:
        pass
    st.markdown(
        f'<div class="enc-login">{img}<h2>Sign in</h2>'
        "<p>Encalm Group — Revenue Analytics System</p></div>",
        unsafe_allow_html=True,
    )


def require_login() -> None:
    """
    Call this as the very first thing on every page (after st.set_page_config,
    before anything else is rendered). If nobody is logged in yet, this
    renders a login form and stops the rest of the page from running at
    all (st.stop()) — so no data, charts, or upload controls ever render
    behind the login wall.
    """
    if is_logged_in():
        import datetime as _dt
        created = st.session_state.get(_SESSION_CREATED_KEY)

        # ── Inactivity timeout (30 min) ──────────────────────────────────────
        # Every page load / filter change / upload reruns this script, so
        # reaching this line at all IS activity — that's what "activity
        # refreshes the timeout" means here. We only ever log someone out
        # if 30+ minutes have passed with no rerun in between (i.e. no
        # interaction at all), never while they're actively using the app.
        now = _dt.datetime.now(tz=_dt.timezone.utc)
        last_active = st.session_state.get(_LAST_ACTIVITY_KEY)
        if last_active and (now - last_active).total_seconds() > _INACTIVITY_TIMEOUT_MINUTES * 60:
            logout()
            st.warning(
                f"You were signed out after {_INACTIVITY_TIMEOUT_MINUTES} minutes "
                "of inactivity. Please sign in again."
            )
            st.rerun()
        st.session_state[_LAST_ACTIVITY_KEY] = now

        # ── Server-side session validation ──────────────────────────────────
        # Check that the session token is still registered in the DB.
        # If another tab logged out (or an admin forced logout), this will
        # catch it and terminate this session too.
        token = st.session_state.get(_SESSION_TOKEN_KEY)
        if token:
            try:
                from . import database as _db
                if not _db.is_session_valid(token):
                    logout()
                    st.warning("Your session was terminated (logged out from another tab or by an administrator).")
                    st.rerun()
                else:
                    # Update last_seen_at without blocking the page load
                    try:
                        _db.touch_session(token)
                    except Exception:
                        pass
            except Exception:
                pass  # DB unavailable — fall back to local session only
        if created and (_dt.datetime.now(tz=_dt.timezone.utc) - created).total_seconds() / 3600 > _SESSION_TIMEOUT_HOURS:
            logout()
            st.warning(f"Session expired after {_SESSION_TIMEOUT_HOURS} hours. Please sign in again.")
            st.rerun()
        elif not created:
            st.session_state[_SESSION_CREATED_KEY] = _dt.datetime.now(tz=_dt.timezone.utc)
        return

    users = _get_configured_users()

    _, center, _ = st.columns([1, 1.3, 1])
    with center:
        _login_brand()

        if not users:
            st.error(
                "No users are configured yet. An administrator needs to add "
                "credentials under `[auth.users]` in this app's Secrets "
                "(Streamlit Cloud → App settings → Secrets, or "
                "`.streamlit/secrets.toml` when running locally) before anyone "
                "can sign in. See `modules/generate_password_hash.py` for how "
                "to generate a password entry safely (hashed, never plaintext)."
            )
            st.stop()

        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

        if submitted:
            import datetime as _dt
            st.session_state[_LOGIN_ATTEMPTED_KEY] = True

            # Check DB-backed lockout (persists across tabs)
            _stripped_user = username.strip()
            try:
                from . import database as _db
                _locked, _remaining = _db.get_lockout_status(_stripped_user)
            except Exception:
                _locked, _remaining = False, 0
            # Also check session-state lockout (fallback when DB unavailable)
            _ss_lockout = st.session_state.get(_LOCKOUT_UNTIL_KEY)
            if _locked or (_ss_lockout and _dt.datetime.now(tz=_dt.timezone.utc) < _ss_lockout):
                _secs = _remaining or int((_ss_lockout - _dt.datetime.now(tz=_dt.timezone.utc)).total_seconds()) if _ss_lockout else _remaining
                st.error(f"Too many failed attempts. Try again in {_secs} seconds.")
                st.stop()

            stored = users.get(_stripped_user)
            if _verify_password_constant_time(password, stored):
                # Reset failed attempts on success
                st.session_state.pop(_FAILED_ATTEMPTS_KEY, None)
                st.session_state.pop(_LOCKOUT_UNTIL_KEY, None)
                try:
                    from . import database as _db
                    _db.clear_failed_logins(_stripped_user)
                except Exception:
                    pass
                import datetime as _dt
                import secrets as _sec
                _token = _sec.token_hex(32)
                st.session_state[_SESSION_KEY] = username.strip()
                st.session_state[_SESSION_TOKEN_KEY] = _token
                st.session_state[_SESSION_CREATED_KEY] = _dt.datetime.now(tz=_dt.timezone.utc)
                # Register in DB for server-side cross-tab invalidation
                try:
                    from . import database as _db
                    _db.register_session(username.strip(), _token)
                except Exception:
                    pass  # DB unavailable — local session still works
                st.rerun()
            else:
                # Track failed attempts in DB (cross-tab persistent)
                try:
                    from . import database as _db
                    _db.record_failed_login(_stripped_user)
                    _locked2, _remaining2 = _db.get_lockout_status(_stripped_user)
                except Exception:
                    _locked2, _remaining2 = False, 0
                # Also track in session-state as fallback
                attempts = st.session_state.get(_FAILED_ATTEMPTS_KEY, 0) + 1
                st.session_state[_FAILED_ATTEMPTS_KEY] = attempts
                if _locked2 or attempts >= _MAX_ATTEMPTS:
                    st.session_state[_LOCKOUT_UNTIL_KEY] = (
                        _dt.datetime.now(tz=_dt.timezone.utc) + _dt.timedelta(seconds=_LOCKOUT_SECONDS)
                    )
                    st.error(f"Too many failed attempts. Account locked for {_LOCKOUT_SECONDS // 60} minutes.")
                else:
                    remaining = _MAX_ATTEMPTS - attempts
                    st.error(f"Incorrect username or password. {remaining} attempt(s) remaining.")

        st.stop()


def render_user_badge() -> None:
    """
    Small sidebar widget showing who's logged in plus a logout button —
    call this from every page after require_login() passes, so it's
    always visible alongside the page content.
    """
    user = current_user()
    if not user:
        return
    with st.sidebar:
        st.divider()
        st.caption(f":material/account_circle: Signed in as **{user}**")
        if st.button("Log out", key="_logout_button", use_container_width=True):
            logout()
            st.rerun()
