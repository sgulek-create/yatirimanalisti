"""Kişisel yatırım uzmanı — klasörlü (views/utils) veya düz (kök) GitHub yüklemesi."""

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
for path in (ROOT, ROOT / "utils", ROOT / "views"):
    s = str(path)
    if path.exists() and s not in sys.path:
        sys.path.insert(0, s)

_has_pkg = (ROOT / "views" / "uzman.py").is_file() and (ROOT / "utils" / "portfolio.py").is_file()
_has_flat = (ROOT / "uzman.py").is_file() and (ROOT / "portfolio.py").is_file()

if not _has_pkg and not _has_flat:
    st.error(
        "Ne `views/`+`utils/` klasörleri ne de kökte `uzman.py`+`portfolio.py` var. "
        "GitHub'a yerel `yanaliz` yapısını klasörleriyle yükle (düz dökme)."
    )
    st.write("Repoda görünenler:")
    st.code("\n".join(sorted(p.name for p in ROOT.iterdir())), language=None)
    st.stop()

if _has_pkg:
    from views import tarayici, uzman  # noqa: E402
else:
    import tarayici  # noqa: E402
    import uzman  # noqa: E402

st.title("Kişisel yatırım uzmanı", icon=":material/psychology:")
if _has_flat and not _has_pkg:
    st.caption("Düz yükleme modu — sonraki push'ta views/ ve utils/ klasörlerini kullan.")

mode = st.segmented_control(
    "Modül",
    options=["Uzman emirleri", "PP park taraması"],
    default="Uzman emirleri",
    label_visibility="collapsed",
)

if mode == "PP park taraması":
    tarayici.render()
else:
    uzman.render()
