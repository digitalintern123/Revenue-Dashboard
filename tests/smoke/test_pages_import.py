"""
tests/smoke/test_pages_import.py — Smoke tests: import every module without error.

These verify that no import-time crash (syntax error, circular import, missing
dependency) exists in any module. They run fast, require no database, and
catch the most common post-refactor regressions.
"""
import sys
import os
import types
import importlib
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# ── Mock Streamlit so we can import modules that call st.* at module level ───

_st_mock = mock.MagicMock()
_st_mock.secrets = {}
_st_mock.session_state = {}

sys.modules.setdefault("streamlit", _st_mock)
sys.modules.setdefault("plotly", mock.MagicMock())
sys.modules.setdefault("plotly.express", mock.MagicMock())
sys.modules.setdefault("plotly.graph_objects", mock.MagicMock())
sys.modules.setdefault("pdfplumber", mock.MagicMock())
sys.modules.setdefault("rapidfuzz", mock.MagicMock())
sys.modules.setdefault("rapidfuzz.fuzz", mock.MagicMock())
sys.modules.setdefault("PIL", mock.MagicMock())
sys.modules.setdefault("PIL.Image", mock.MagicMock())
sys.modules.setdefault("bs4", mock.MagicMock())
sys.modules.setdefault("extract_msg", mock.MagicMock())

# Patch environment so database.py picks up SQLite (no real DB needed)
os.environ.setdefault("DATABASE_URL", "")


MODULES = [
    "modules.auth",
    "modules.app_logger",
    "modules.date_utils",
    "modules.formatting",
    "modules.session",
    "modules.comparison_widget",
    "modules.date_picker",
    "modules.outlet_groups",
    "modules.terminal_mapping",
    "modules.revenue_analysis",
    "modules.insights",
    "modules.table_style",
    "modules.segment_tree_view",
    "modules.upload_status",
    "modules.generate_password_hash",
]


@pytest.mark.parametrize("module_path", MODULES)
def test_module_imports_without_error(module_path):
    """Each module must be importable without raising any exception."""
    try:
        mod = importlib.import_module(module_path)
        assert mod is not None
    except ImportError as exc:
        # Allow ImportError only for optional heavy deps (psycopg2, etc.)
        optional_deps = {"psycopg2", "pytesseract", "tomllib"}
        missing = str(exc).split("'")[1] if "'" in str(exc) else str(exc)
        if any(dep in missing for dep in optional_deps):
            pytest.skip(f"Optional dependency not installed: {exc}")
        else:
            pytest.fail(f"ImportError in {module_path}: {exc}")


def test_data_processor_imports():
    import modules.data_processor as dp
    assert hasattr(dp, "process_uploaded_file")
    assert hasattr(dp, "_validate_upload")
    assert hasattr(dp, "ProcessResult")


def test_database_module_imports():
    import modules.database as db
    assert hasattr(db, "init_db")
    assert hasattr(db, "save_dataframe")
    assert hasattr(db, "load_for_date_range")
    assert hasattr(db, "check_upload_rate_limit")
    assert hasattr(db, "reset_db")
    assert hasattr(db, "_RESET_ALLOWED_TABLES")


def test_auth_module_exports():
    import modules.auth as auth
    assert hasattr(auth, "require_login")
    assert hasattr(auth, "is_logged_in")
    assert hasattr(auth, "current_user")
    assert hasattr(auth, "logout")
    assert hasattr(auth, "_verify_password")
    assert hasattr(auth, "_verify_password_constant_time")


def test_all_allowed_extensions_covered():
    """Ensure _ALL_ALLOWED_EXTENSIONS includes every type from the uploader."""
    from modules.data_processor import _ALL_ALLOWED_EXTENSIONS
    uploader_types = {
        ".pdf", ".xlsx", ".xls", ".xlsm", ".csv", ".tsv", ".txt",
        ".docx", ".html", ".htm", ".xml", ".json",
        ".png", ".jpg", ".jpeg", ".tiff", ".tif",
        ".msg",
    }
    for ext in uploader_types:
        assert ext in _ALL_ALLOWED_EXTENSIONS, (
            f"Extension {ext!r} is offered in the file uploader but not in "
            f"_ALL_ALLOWED_EXTENSIONS — users will get a confusing rejection."
        )


def test_reset_allowlist_covers_all_tables():
    """_RESET_ALLOWED_TABLES must include every table reset_db iterates over."""
    from modules.database import _RESET_ALLOWED_TABLES
    expected = {"revenue_master", "airport_traffic", "aop_target",
                "aop_target_daily", "upload_history"}
    assert expected.issubset(_RESET_ALLOWED_TABLES)


def test_bug001_mgmt_message_key_consistent():
    """BUG-001 regression: read key must match write key (no leading dot)."""
    src = open(
        os.path.join(os.path.dirname(__file__), "..", "..", "Home.py"),
        encoding="utf-8",
    ).read()
    # The dotted key must NOT appear in any 'if ... in st.session_state' check
    assert '"._last_mgmt_message" in st.session_state' not in src, (
        "BUG-001 regression: the dotted key '._last_mgmt_message' was found in an "
        "'if ... in st.session_state' check. The correct key is '_last_mgmt_message' "
        "(no leading dot)."
    )


def test_bug003_vacuum_guarded():
    """BUG-003 regression: VACUUM must be inside 'if not _IS_POSTGRES' guard."""
    src = open(
        os.path.join(os.path.dirname(__file__), "..", "..", "modules", "database.py"),
        encoding="utf-8",
    ).read()
    # Find VACUUM and assert it's inside the guard
    vac_idx = src.find('text("VACUUM")')
    assert vac_idx != -1, "VACUUM call not found — may have been removed entirely"
    # The guard must appear before VACUUM in the same block
    guard_idx = src.rfind("if not _IS_POSTGRES", 0, vac_idx)
    assert guard_idx != -1, (
        "BUG-003 regression: VACUUM is not guarded by 'if not _IS_POSTGRES'. "
        "This will raise an exception in PostgreSQL production."
    )
