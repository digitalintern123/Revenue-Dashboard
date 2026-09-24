"""
startup_checks.py — Production readiness checks run at app startup.

Call check_production_readiness() at the top of Home.py (before any
page rendering) to catch misconfiguration early and refuse to start
rather than silently run in a broken/insecure state.
"""
from __future__ import annotations
import os
import sys


def check_production_readiness() -> None:
    """
    Validate critical configuration. Logs warnings for optional items,
    raises SystemExit for items that would cause data loss or security holes.
    
    Critical (app refuses to start):
      - No auth users configured (anyone could access the app)
    
    Warnings (app starts but logs a warning):
      - DATABASE_URL not set (using ephemeral SQLite — data lost on restart)
      - GitHub backup not configured (no persistence on Streamlit Cloud)
    """
    import streamlit as st

    warnings = []
    errors = []

    # ── 1. Auth users must be configured ────────────────────────────────────
    try:
        users = dict(st.secrets.get("auth", {}).get("users", {}))
    except Exception:
        users = {}

    if not users:
        # Try reading directly from file as fallback
        import tomllib, pathlib
        secrets_path = pathlib.Path(".streamlit/secrets.toml")
        if secrets_path.exists():
            try:
                with open(secrets_path, "rb") as f:
                    data = tomllib.load(f)
                users = data.get("auth", {}).get("users", {})
            except Exception:
                pass

    if not users:
        errors.append(
            "CRITICAL: No auth users configured. "
            "Add credentials to .streamlit/secrets.toml before deploying. "
            "Run: python create_secrets.py"
        )

    # ── 2. Database persistence warning (Streamlit Cloud only) ─────────────
    # Only warn about missing DATABASE_URL when running on Streamlit Cloud.
    # Locally, SQLite persists data just fine between restarts.
    _on_cloud = (
        os.path.exists("/mount/src")
        or os.environ.get("STREAMLIT_SHARING_MODE", "") != ""
        or os.environ.get("HOME", "") == "/home/adminuser"
    )

    db_url = ""
    try:
        db_url = st.secrets.get("DATABASE_URL", "")
    except Exception:
        pass
    if not db_url:
        db_url = os.environ.get("DATABASE_URL", "")

    if not db_url and _on_cloud:
        warnings.append(
            "DATABASE_URL is not set. Using ephemeral SQLite — "
            "all uploaded data will be lost on every app restart. "
            "Set DATABASE_URL in Streamlit Secrets for persistence."
        )

    # ── 3. GitHub backup warning (Streamlit Cloud only) ──────────────────────
    github_token = ""
    try:
        github_token = st.secrets.get("GITHUB_TOKEN", "")
    except Exception:
        pass
    if not github_token:
        github_token = os.environ.get("GITHUB_TOKEN", "")

    if not github_token and not db_url and _on_cloud:
        warnings.append(
            "Neither DATABASE_URL nor GITHUB_TOKEN is configured. "
            "Data will not persist across restarts on Streamlit Cloud."
        )

    # ── 4. Log warnings ──────────────────────────────────────────────────────
    import logging
    _log = logging.getLogger("encalm_startup")
    for w in warnings:
        _log.warning(w)

    # ── 5. Fail hard on critical errors ─────────────────────────────────────
    if errors:
        for e in errors:
            st.error(f"🚫 {e}")
        st.stop()
