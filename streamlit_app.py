"""Giriş — kişisel uzman + fırsat tarayıcısı."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(
    page_title="Kişisel yatırım uzmanı",
    page_icon=":material/psychology:",
    layout="wide",
)

page = st.navigation(
    [
        st.Page("app_pages/uzman.py", title="Uzman emirleri", icon=":material/gavel:"),
        st.Page(
            "app_pages/tarayici.py",
            title="Fırsat tarayıcısı",
            icon=":material/query_stats:",
        ),
    ],
    position="top",
)
page.run()
