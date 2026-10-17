import streamlit as st
from modules import ui as _ui
st.set_page_config(page_title="EHPL · Encalm", page_icon=_ui.LOGO_MARK, layout="wide")
from modules.business_dashboard import render_ehpl_page
render_ehpl_page(page_key="ehpl")
