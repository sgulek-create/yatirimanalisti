"""Kişisel yatırım uzmanı — tek giriş (st.Page yolu yok)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from views import tarayici, uzman

st.set_page_config(
    page_title="Kişisel yatırım uzmanı",
    page_icon=":material/psychology:",
    layout="wide",
)

st.title("Kişisel yatırım uzmanı", icon=":material/psychology:")

mode = st.segmented_control(
    "Modül",
    options=["Uzman emirleri", "Fırsat tarayıcısı"],
    default="Uzman emirleri",
    label_visibility="collapsed",
)

if mode == "Fırsat tarayıcısı":
    tarayici.render()
else:
    uzman.render()
