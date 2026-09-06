"""Kişisel yatırım uzmanı — Streamlit Cloud uyumlu giriş."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Kişisel yatırım uzmanı",
    page_icon=":material/psychology:",
    layout="wide",
)

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_missing = [
    name
    for name in ("views", "utils")
    if not (ROOT / name).is_dir() or not (ROOT / name / "__init__.py").exists()
]
if _missing:
    st.error(
        "GitHub reposunda eksik klasör: "
        + ", ".join(_missing)
        + ". `views/` ve `utils/` kök dizine yükleyip Cloud'dan Redeploy et."
    )
    st.write("Şu an repoda görünenler:")
    st.code("\n".join(sorted(p.name for p in ROOT.iterdir())), language=None)
    st.stop()

from views import tarayici, uzman  # noqa: E402

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
