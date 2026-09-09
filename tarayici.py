"""PP park taraması — yeni serbest/TLY avı yok."""

from __future__ import annotations

import pandas as pd
import streamlit as st

try:
    from utils.pp_scan import build_pp_orders, format_pp_emri, load_pp_table
    from utils.portfolio import portfolio_frame
except ImportError:
    from pp_scan import build_pp_orders, format_pp_emri, load_pp_table
    from portfolio import portfolio_frame


@st.cache_data(ttl="30m", show_spinner=False)
def _pp() -> pd.DataFrame:
    return load_pp_table()


def render() -> None:
    st.subheader("PP park taraması", divider="blue")
    st.caption(
        "Sadece para piyasası / katılım PP. Serbest fon avı yok — "
        "amaç park + silah, yeni TLY aramak değil."
    )

    book, _ = portfolio_frame(live=False)
    tp2_rows = book.loc[book["code"] == "TP2", "value_tl"]
    tlv_rows = book.loc[book["code"] == "TLV", "value_tl"]
    tp2_v = float(tp2_rows.iloc[0]) if len(tp2_rows) else 0.0
    tlv_v = float(tlv_rows.iloc[0]) if len(tlv_rows) else 0.0

    try:
        with st.spinner("TEFAS PP…"):
            table = _pp()
    except Exception as exc:  # noqa: BLE001
        st.error(f"PP veri yok: {exc}")
        return

    if table.empty:
        st.warning("PP tablosu boş.")
        return

    orders, meta = build_pp_orders(table, tp2_v, tlv_v)
    st.code(format_pp_emri(orders, meta), language=None)

    c1, c2 = st.columns(2)
    cols = ["fund_code", "return_1m", "return_3m", "daily_pct"]
    show_cols = [c for c in cols if c in table.columns]
    if "daily_pct" not in table.columns and "daily_approx" in table.columns:
        show_cols = ["fund_code", "return_1m", "return_3m", "daily_approx"]

    with c1:
        st.markdown("**Tera dışı konvansiyonel top5**")
        top = meta.get("top_conventional")
        if top is not None and not top.empty:
            st.dataframe(top[show_cols].head(5), hide_index=True)
        else:
            st.caption("Veri yok")
    with c2:
        st.markdown("**Tera dışı katılım top5**")
        topk = meta.get("top_katilim")
        if topk is not None and not topk.empty:
            st.dataframe(topk[show_cols].head(5), hide_index=True)
        else:
            st.caption("Veri yok")

    st.caption(
        "Geçiş kuralı: 1A ≥ +0.25 puan ve 3A teyit. "
        "TLV yalnız katılım ligi. Faiz düşünce tüm PP iner — kilit getiri yok."
    )
