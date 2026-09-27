import streamlit as st
from modules import ui as _ui
st.set_page_config(page_title="Sky Plates · Encalm", page_icon=_ui.LOGO_MARK, layout="wide")
from modules.business_dashboard import render_subsidiary_page
render_subsidiary_page(segment="Sky Plates", page_key="sp", icon="🛩️")
