import streamlit as st
st.set_page_config(page_title="Sky Plates", page_icon="🛩️", layout="wide")
from modules.business_dashboard import render_subsidiary_page
render_subsidiary_page(segment="Sky Plates", page_key="sp", icon="🛩️")
