import streamlit as st
st.set_page_config(page_title="EHPL", page_icon="🏨", layout="wide")
from modules.business_dashboard import render_ehpl_page
render_ehpl_page(page_key="ehpl")
