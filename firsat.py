"""Fırsat ajanı görünümü — kitap dışı 1–3 karar kartı."""

from __future__ import annotations

import streamlit as st

try:
    from utils.opportunity_agent import (
        format_opportunity_cards,
        generate_opportunities,
        opportunities_frame,
    )
    from utils.portfolio import MANIFESTO, portfolio_frame
    from utils.pp_scan import load_pp_table
    from utils.risk_engine import compute_risk
except ImportError:
    from opportunity_agent import (
        format_opportunity_cards,
        generate_opportunities,
        opportunities_frame,
    )
    from portfolio import MANIFESTO, portfolio_frame
    from pp_scan import load_pp_table
    from risk_engine import compute_risk


@st.cache_data(ttl="20m", show_spinner="Fırsat taranıyor…")
def _scan(nonce: int = 0):
    _ = nonce
    book, total = portfolio_frame(live=False)
    weights = book.set_index("code")["weight"].to_dict()
    pp = load_pp_table()
    risk = compute_risk(weights, pp_daily_rate=0.001)
    cards = generate_opportunities(
        book,
        pp,
        total_tl=total,
        mstr_vol_pct=risk.mstr_vol_pct,
        max_cards=3,
    )
    return book, total, cards, risk


def render() -> None:
    st.subheader("Fırsat ajanı", divider="blue")
    st.info(MANIFESTO)
    st.caption(
        "Yatırımcı modu: kitap dışı aday ara. İkinci TLY yok. "
        "Kart üretir — Midas emri basmaz; onay sende."
    )

    if "firsat_nonce" not in st.session_state:
        st.session_state.firsat_nonce = 0

    if st.button("Fırsatları tara", type="primary", icon=":material/travel_explore:"):
        st.session_state.firsat_nonce += 1
        _scan.clear()

    try:
        book, total, cards, risk = _scan(st.session_state.firsat_nonce)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Tarama hatası: {exc}")
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Kitap toplam", f"₺{total:,.0f}".replace(",", "."))
    vol = risk.mstr_vol_pct
    m2.metric("MSTR vol", f"%{vol:.0f}" if vol is not None else "—")
    m3.metric("Kart", str(len(cards)))

    st.code(format_opportunity_cards(cards), language=None)

    st.dataframe(
        opportunities_frame(cards),
        hide_index=True,
        column_config={
            "Max ₺": st.column_config.NumberColumn(format="%.0f"),
            "Güven": st.column_config.NumberColumn(format="%d"),
        },
    )

    with st.expander("Kitap özeti"):
        show = book[["code", "name", "value_tl", "weight"]].copy()
        show["weight"] = show["weight"] * 100
        st.dataframe(
            show.rename(
                columns={
                    "code": "Kod",
                    "name": "Ad",
                    "value_tl": "Değer ₺",
                    "weight": "Ağırlık %",
                }
            ),
            hide_index=True,
            column_config={
                "Değer ₺": st.column_config.NumberColumn(format="%.2f"),
                "Ağırlık %": st.column_config.NumberColumn(format="%.1f"),
            },
        )

    st.caption(
        "Karakter: parkçı / disiplinli. Agresif tema avcısı değil. "
        "Sabah görevi aynı kartları `sabah_raporu` içine de yazar."
    )
