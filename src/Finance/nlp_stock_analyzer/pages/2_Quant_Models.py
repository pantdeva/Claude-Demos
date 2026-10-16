"""Streamlit page: the quant model comparison dashboard.

Shows results/quant_<TICKER>.html produced by:  python quant_run.py --download
"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

RESULTS = Path(__file__).resolve().parents[1] / "results"

st.set_page_config(page_title="Quant Models", page_icon="📊", layout="wide")
st.title("Quant model comparison")

reports = sorted(RESULTS.glob("quant_*.html"))
if not reports:
    st.info("No results yet. Run `python quant_run.py --download` in the project folder, then refresh.")
    st.stop()

choice = st.selectbox("Report", reports, format_func=lambda p: p.stem.replace("quant_", ""))
components.html(choice.read_text(encoding="utf-8"), height=3400, scrolling=True)
