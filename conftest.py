"""
conftest.py — Shared pytest fixtures and mock setup.

Patches Streamlit and heavy optional dependencies at session scope so that
unit tests that import modules using `import streamlit as st` don't fail
just because Streamlit isn't running.
"""
import sys
import os
import unittest.mock as mock

import pytest


@pytest.fixture(scope="session", autouse=True)
def mock_streamlit():
    """Provide a MagicMock for streamlit so module-level st.* calls don't fail."""
    st_mock = mock.MagicMock()
    st_mock.secrets = {}
    st_mock.session_state = {}
    st_mock.cache_data = lambda *args, **kwargs: (lambda f: f)  # passthrough decorator
    st_mock.cache_resource = lambda *args, **kwargs: (lambda f: f)
    sys.modules.setdefault("streamlit", st_mock)
    yield st_mock


@pytest.fixture(scope="session", autouse=True)
def mock_optional_deps():
    """Stub out heavy optional dependencies not needed for unit/integration tests."""
    stubs = [
        "plotly", "plotly.express", "plotly.graph_objects",
        "pdfplumber", "rapidfuzz", "rapidfuzz.fuzz",
        "PIL", "PIL.Image", "bs4", "extract_msg",
    ]
    for mod in stubs:
        sys.modules.setdefault(mod, mock.MagicMock())
    yield
