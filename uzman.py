"""Kişisel uzman görünümü — PP EMRİ → PORTFÖY EMRİ → Alarm/VaR → Walk-forward."""

from __future__ import annotations

import pandas as pd
import streamlit as st

try:
    from utils.briefing import build_clean_briefing, build_expert_note
    from utils.orders import decide_positions, orders_to_frame
    from utils.portfolio import (
        AS_OF,
        MANIFESTO,
        TARGET_BUCKETS,
        USDTRY,
        bucket_weights,
        portfolio_frame,
        tera_weight,
    )
    from utils.pp_scan import build_pp_orders, format_pp_emri, load_pp_table
    from utils.risk_engine import (
        build_proxy_returns,
        compute_risk,
        fetch_closes,
        performance_stats,
        walk_forward,
    )
except ImportError:
    from briefing import build_clean_briefing, build_expert_note
    from orders import decide_positions, orders_to_frame
    from portfolio import (
        AS_OF,
        MANIFESTO,
        TARGET_BUCKETS,
        USDTRY,
        bucket_weights,
        portfolio_frame,
        tera_weight,
    )
    from pp_scan import build_pp_orders, format_pp_emri, load_pp_table
    from risk_engine import (
        build_proxy_returns,
        compute_risk,
        fetch_closes,
        performance_stats,
        walk_forward,
    )


@st.cache_data(ttl="30m", show_spinner=False)
def _pp_table() -> pd.DataFrame:
    return load_pp_table()


@st.cache_data(ttl="15m", show_spinner=False)
def _risk(weights_items: tuple, pp_daily: float):
    return compute_risk(dict(weights_items), pp_daily_rate=pp_daily)


def render() -> None:
    st.subheader("Kişisel yatırım uzmanı", divider="blue")
    st.info(MANIFESTO)
    st.caption(
        f"Kitap {AS_OF} · USDTRY {USDTRY} · TLY senin keşfin — "
        "uzman ağırlık, park ve vol ile realize eder; ikinci TLY avlamaz."
    )

    book, total = portfolio_frame()
    weights = book.set_index("code")["weight"].to_dict()
    buckets = bucket_weights(book)

    with st.container(horizontal=True):
        st.metric("Toplam", f"₺{total:,.0f}".replace(",", "."), border=True)
        st.metric("Tera payı", f"%{tera_weight(book)*100:.0f}", border=True)
        st.metric("TLY", f"%{weights.get('TLY', 0)*100:.1f}", border=True)
        st.metric("PP park", f"%{buckets['pp']*100:.0f}", border=True)

    lo_pp, hi_pp = TARGET_BUCKETS["pp"]
    lo_at, hi_at = TARGET_BUCKETS["atak"]
    st.caption(
        f"Hedef kova: PP %{lo_pp*100:.0f}–{hi_pp*100:.0f} · "
        f"Atak %{lo_at*100:.0f}–{hi_at*100:.0f} · "
        f"Global veya emtia %15–20 (NVDA ile GMC aynı kova değil). "
        f"Şu an: PP %{buckets['pp']*100:.0f} · Atak %{buckets['atak']*100:.0f} · "
        f"GMC %{buckets['emtia']*100:.0f}."
    )

    with st.expander("Kitap (Midas)", expanded=False):
        show = book[["code", "name", "kind", "value_tl", "weight", "pnl_pct", "valor"]].copy()
        show["weight"] = show["weight"] * 100
        st.dataframe(
            show.rename(
                columns={
                    "code": "Kod",
                    "name": "Ad",
                    "kind": "Tür",
                    "value_tl": "Değer ₺",
                    "weight": "Ağırlık %",
                    "pnl_pct": "PnL %",
                    "valor": "Valör",
                }
            ),
            hide_index=True,
            column_config={
                "Değer ₺": st.column_config.NumberColumn(format="%.2f"),
                "Ağırlık %": st.column_config.NumberColumn(format="%.1f"),
                "PnL %": st.column_config.NumberColumn(format="%+.2f"),
            },
        )

    run = st.button("Emirleri üret", type="primary", icon=":material/play_arrow:")

    if not (run or st.session_state.get("uzman_ready")):
        st.info("Emirleri üret — PP, pozisyon, VaR ve walk-forward sırayla dolar.")
        return

    st.session_state.uzman_ready = True

    with st.spinner("TEFAS PP + Yahoo risk hesaplanıyor…"):
        try:
            pp_table = _pp_table()
        except Exception as exc:  # noqa: BLE001
            pp_table = pd.DataFrame()
            st.error(f"PP tarama hatası: {exc}")

        pp_daily = 0.001
        if not pp_table.empty and "daily_return" in pp_table.columns:
            sub = pp_table[pp_table["fund_code"].isin(["TP2", "TLV"])]
            if not sub.empty and sub["daily_return"].notna().any():
                # daily_return zaten ondalık (örn. 0.00194 ≈ %0.194/gün)
                pp_daily = float(sub["daily_return"].mean())
        elif not pp_table.empty:
            sub = pp_table[pp_table["fund_code"].isin(["TP2", "TLV"])]
            if not sub.empty and sub["daily_approx"].notna().any():
                pp_daily = float(sub["daily_approx"].mean() / 100.0)

        risk = _risk(tuple(sorted(weights.items())), pp_daily)

        preferred = None
        pp_orders: list = []
        meta: dict = {}
        if not pp_table.empty:
            tp2_v = float(book.loc[book["code"] == "TP2", "value_tl"].iloc[0])
            tlv_v = float(book.loc[book["code"] == "TLV", "value_tl"].iloc[0])
            pp_orders, meta = build_pp_orders(pp_table, tp2_v, tlv_v)
            top = meta.get("top_conventional")
            if top is not None and not top.empty:
                preferred = str(top.iloc[0]["fund_code"])

        pos = decide_positions(
            book,
            total,
            risk.mstr_vol_pct,
            risk.nvda_mstr_corr,
            preferred_pp=preferred,
        )
        pos_df = orders_to_frame(pos)

    briefing = build_clean_briefing(book, risk, pp_orders, position_orders=pos)
    expert = build_expert_note(book, pos, pp_orders, preferred_pp=preferred)

    with st.container(border=True):
        st.subheader(briefing["headline"], icon=":material/wb_sunny:")
        st.text(briefing["body"])
        if briefing.get("has_orders"):
            st.caption("Kısa özet. Ayrıntılı Türkçe öneri hemen altta.")
        else:
            st.success("Bugün işlem yok — dokunma.")

    with st.container(border=True):
        st.subheader("Uzman önerisi", icon=":material/person:")
        st.markdown(expert.replace("\n", "  \n"))

    st.subheader("1) PP EMRİ")
    if pp_orders:
        st.code(format_pp_emri(pp_orders, meta), language=None)
    else:
        st.code(
            "PP EMRİ:\n- TUT TP2 | %50 | veri yok\n- TUT TLV | %50 | veri yok",
            language=None,
        )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Tera dışı konvansiyonel top3**")
        top = meta.get("top_conventional")
        if top is not None and not top.empty:
            st.dataframe(
                top[["fund_code", "return_1m", "return_3m", "daily_approx"]].head(3),
                hide_index=True,
            )
        else:
            st.caption("Veri yok")
    with c2:
        st.markdown("**Tera dışı katılım top3**")
        topk = meta.get("top_katilim")
        if topk is not None and not topk.empty:
            st.dataframe(
                topk[["fund_code", "return_1m", "return_3m", "daily_approx"]].head(3),
                hide_index=True,
            )
        else:
            st.caption("Veri yok")

    st.subheader("2) PORTFÖY EMRİ")
    st.dataframe(
        pos_df,
        hide_index=True,
        column_config={
            "Hedef ağırlık": st.column_config.NumberColumn(format="%.1%"),
            "İşlem ₺": st.column_config.NumberColumn(format="%+.0f"),
            "Güven": st.column_config.ProgressColumn(
                min_value=0, max_value=1, format="%.0f%%"
            ),
        },
    )

    st.subheader("3) Alarm + VaR")
    for a in risk.alarms:
        st.warning(a)

    with st.container(horizontal=True):
        if risk.mstr_vol_pct is not None:
            st.metric("MSTR 60g vol", f"%{risk.mstr_vol_pct:.0f}", border=True)
        if risk.nvda_mstr_corr is not None:
            st.metric("NVDA–MSTR corr", f"{risk.nvda_mstr_corr:.2f}", border=True)
        if risk.var95 is not None:
            st.metric(
                "VaR95 (1ay)",
                f"₺{abs(risk.var95)*total:,.0f}".replace(",", "."),
                f"{risk.var95*100:.1f}%",
                border=True,
            )
        if risk.cvar95 is not None:
            st.metric(
                "CVaR95",
                f"₺{abs(risk.cvar95)*total:,.0f}".replace(",", "."),
                f"{risk.cvar95*100:.1f}%",
                border=True,
            )
        if risk.p_loss_5pct is not None:
            st.metric("P(ay≤-5%)", f"%{risk.p_loss_5pct*100:.0f}", border=True)

    if risk.notes:
        st.caption(" · ".join(risk.notes))

    st.subheader("4) Walk-forward")
    with st.spinner("Walk-forward (T+2 valör)…"):
        close = fetch_closes(["NVDA", "MSTR", "SLV", "XU100.IS"], period="1y")
        asset_r, _ = build_proxy_returns(close)
        # PP kolonları 0: getiri port_ret içinde pp_daily ile eklenir (çift sayma yok)
        for code in ("TP2", "TLV"):
            if code not in asset_r.columns:
                asset_r[code] = 0.0
        curves = walk_forward(asset_r, weights, pp_daily=pp_daily, valor_lag=2)

    if curves.empty:
        st.info("Walk-forward için yeterli seri yok.")
    else:
        st.line_chart(curves)
        rows = []
        for col in curves.columns:
            stats = performance_stats(curves[col])
            stats["Strateji"] = col
            rows.append(stats)
        sdf = pd.DataFrame(rows)
        st.dataframe(
            sdf.rename(
                columns={
                    "total_return": "Toplam",
                    "cagr": "CAGR",
                    "vol": "Vol",
                    "max_dd": "Max DD",
                }
            ),
            hide_index=True,
            column_config={
                "Toplam": st.column_config.NumberColumn(format="%.1%"),
                "CAGR": st.column_config.NumberColumn(format="%.1%"),
                "Vol": st.column_config.NumberColumn(format="%.1%"),
                "Max DD": st.column_config.NumberColumn(format="%.1%"),
            },
        )
        st.caption(
            "A=al-tut · B=overlay (TLY/MSTR kuralları, T+2) · C=sadece PP. "
            "TLY XU100×1.35 vekil — overlay'i TLY'nin başarısızlığı diye yorma."
        )

    st.caption("Kişisel kural motoru · karar senin, emir senin kuralların.")
