"""
Home.py - Encalm Revenue Analytics

Navigation (st.navigation / st.Page):

    Home (Upload)
    Previous Uploads
    EHPL
    Encalm Eats
    Sky Plates

No icon parameters are used anywhere in this file. Old analytical pages
are not registered here and never appear in the sidebar.
"""
from __future__ import annotations
import streamlit as st
from startup_checks import check_production_readiness

st.set_page_config(
    page_title="Encalm Revenue Analytics",
    layout="wide",
)

check_production_readiness()

st.markdown(
    '<meta http-equiv="X-Content-Type-Options" content="nosniff">'
    '<meta http-equiv="X-Frame-Options" content="DENY">'
    '<meta name="robots" content="noindex, nofollow">',
    unsafe_allow_html=True,
)

home    = st.Page("pages/Uploads.py",          title="Home",            default=True)
prev_up = st.Page("pages/Previous_Uploads.py", title="Previous Uploads")
ehpl    = st.Page("pages/EHPL.py",             title="EHPL")
eats    = st.Page("pages/Encalm_Eats.py",      title="Encalm Eats")
sky     = st.Page("pages/Sky_Plates.py",       title="Sky Plates")

pg = st.navigation([home, prev_up, ehpl, eats, sky])
pg.run()
