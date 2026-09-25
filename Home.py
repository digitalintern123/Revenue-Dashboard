"""
Home.py - Encalm Revenue Analytics

Navigation (st.navigation / st.Page):

    Home (Upload)
    Previous Uploads
    EHPL
    Encalm Eats
    Sky Plates

Pages are grouped into "Data" and "Dashboards" sections in the sidebar.
Old analytical pages are not registered here and never appear in the sidebar.
"""
from __future__ import annotations
import streamlit as st
from startup_checks import check_production_readiness
from modules import ui

st.set_page_config(
    page_title="Encalm Revenue Analytics",
    layout="wide",
)

# Home.py runs on every rerun under st.navigation, so global styling and the
# sidebar logo only need to be set here to apply to every page.
ui.inject_css()
st.logo(ui.logo_path(), size="large", icon_image=ui.logo_icon_path())

check_production_readiness()

st.markdown(
    '<meta http-equiv="X-Content-Type-Options" content="nosniff">'
    '<meta http-equiv="X-Frame-Options" content="DENY">'
    '<meta name="robots" content="noindex, nofollow">',
    unsafe_allow_html=True,
)

home    = st.Page("pages/Uploads.py",          title="Upload Data",      icon=":material/upload_file:", default=True)
prev_up = st.Page("pages/Previous_Uploads.py", title="Previous Uploads", icon=":material/history:")
ehpl    = st.Page("pages/EHPL.py",             title="EHPL",             icon=":material/flight_takeoff:")
eats    = st.Page("pages/Encalm_Eats.py",      title="Encalm Eats",      icon=":material/restaurant:")
sky     = st.Page("pages/Sky_Plates.py",       title="Sky Plates",       icon=":material/room_service:")

pg = st.navigation({"Data": [home, prev_up], "Dashboards": [ehpl, eats, sky]})
pg.run()
