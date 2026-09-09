"""Kişisel uzman görünümü — PP EMRİ → PORTFÖY EMRİ → Alarm/VaR → Walk-forward."""

from __future__ import annotations

import pandas as pd
import streamlit as st

try:
    from utils.briefing import build_clean_briefing, build_expert_note
    from utils.live_prices import fetch_live_bundle
    from utils.midas_book import (
        book_meta,
        editor_frame_to_book,
        holdings_to_editor_frame,
        save_book,
    )
    from utils.orders import decide_positions, orders_to_frame
    from utils.portfolio import (
        AS_OF_DEFAULT,
        MANIFESTO,
        TARGET_BUCKETS,
        USDTRY_DEFAULT,
        bucket_weights,
        get_book_as_of,
        get_book_usdtry,
        get_holdings,
        portfolio_frame,
        tera_weight,
    )
    from utils.pp_scan import build_pp_orders, format_pp_emri, load_pp_table
    from utils.report import (
        generate_morning_report,
        load_mail_config,
        mail_status,
        save_report,
        send_email,
    )
    from utils.risk_engine import (
        build_proxy_returns,
        compute_risk,
        fetch_closes,
        performance_stats,
        walk_forward,
    )
except ImportError:
    from briefing import build_clean_briefing, build_expert_note
    from live_prices import fetch_live_bundle
    from midas_book import (
        book_meta,
        editor_frame_to_book,
        holdings_to_editor_frame,
        save_book,
    )
    from orders import decide_positions, orders_to_frame
    from portfolio import (
        AS_OF_DEFAULT,
        MANIFESTO,
        TARGET_BUCKETS,
        USDTRY_DEFAULT,
        bucket_weights,
        get_book_as_of,
        get_book_usdtry,
        get_holdings,
        portfolio_frame,
        tera_weight,
    )
    from pp_scan import build_pp_orders, format_pp_emri, load_pp_table
    from report import (
        generate_morning_report,
        load_mail_config,
        mail_status,
        save_report,
        send_email,
    )
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


@st.cache_data(ttl="15m", show_spinner="Tahmini işaret güncelleniyor…")
def _estimate_book(nonce: int = 0):
    """TEFAS/yfinance tahmini — ana toplam değil."""
    _ = nonce
    holdings = get_holdings()
    as_of = get_book_as_of()
    fx = get_book_usdtry()
    bundle = fetch_live_bundle(
        book_as_of=as_of,
        book_usdtry=fx,
        holdings=holdings,
    )
    book, total = portfolio_frame(live=True, bundle=bundle)
    return book, total, list(bundle.notes)


def _render_morning_report_panel() -> None:
    """İsteğe bağlı: şimdi üret / üret + e-posta."""
    with st.expander("Sabah raporu", expanded=False):
        ms = mail_status()
        if ms["ready"]:
            st.caption(f"E-posta hazır → {ms['to']}")
        elif ms["to"]:
            st.caption(
                f"Alıcı: {ms['to']} — Gmail uygulama şifresini "
                "`.streamlit/secrets.toml` → `password` satırına yaz."
            )
        else:
            st.caption("E-posta yoksa rapor yine dosyaya yazılır.")

        c1, c2 = st.columns(2)
        do_make = c1.button(
            "Raporu şimdi üret",
            key="btn_sabah_rapor",
            icon=":material/description:",
            width="stretch",
        )
        do_mail = c2.button(
            "Üret + e-posta",
            key="btn_sabah_mail",
            icon=":material/mail:",
            width="stretch",
            disabled=not ms["ready"],
        )

        if do_make or do_mail:
            with st.spinner("Sabah raporu üretiliyor…"):
                try:
                    report = generate_morning_report()
                    path = save_report(report)
                    st.session_state["sabah_rapor_text"] = report["text"]
                    st.session_state["sabah_rapor_path"] = str(path)
                    if do_mail:
                        cfg = load_mail_config()
                        if cfg is None:
                            st.error("E-posta ayarı eksik veya şifre placeholder.")
                        else:
                            send_email(
                                f"Sabah raporu {report['as_of'].isoformat()}",
                                report["text"],
                                cfg,
                            )
                            st.success(f"Gönderildi → {cfg.mail_to}")
                    else:
                        st.success(f"Kaydedildi: `{path.name}`")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Rapor hatası: {exc}")

        text = st.session_state.get("sabah_rapor_text")
        if text:
            st.download_button(
                "İndir (.txt)",
                data=text,
                file_name="sabah_raporu_son.txt",
                mime="text/plain",
                key="dl_sabah_rapor",
            )
            st.code(text, language=None)

        st.markdown(
            "Zamanlayıcı 08:00: `.\\kur_sabah_gorevi.ps1` · "
            "mail ile: `-WithEmail` · dosya: `data/sabah_raporu_son.txt`"
        )


def _render_midas_editor() -> None:
    """Midas bakiyesini elle güncelle — tek gerçek kaynak."""
    meta = book_meta()
    with st.expander("Midas bakiyesini güncelle (gerçek toplam)", expanded=not meta["exists"]):
        st.caption(
            "Midas uygulamasındaki satır tutarlarını buraya yaz. "
            "API yok; sen yazınca toplam bire bir olur. "
            f"Dosya: `data/midas_kitap.json`"
        )
        c1, c2 = st.columns(2)
        as_of = c1.text_input(
            "Kitap tarihi (YYYY-MM-DD)",
            value=meta.get("as_of") or get_book_as_of() or AS_OF_DEFAULT,
            key="midas_as_of",
        )
        fx_default = meta.get("usdtry") or get_book_usdtry() or USDTRY_DEFAULT
        usdtry = c2.number_input(
            "USDTRY (Midas kuru)",
            min_value=1.0,
            value=float(fx_default),
            step=0.01,
            format="%.4f",
            key="midas_usdtry",
        )
        edited = st.data_editor(
            holdings_to_editor_frame(),
            num_rows="dynamic",
            hide_index=True,
            key="midas_editor",
            column_config={
                "value_tl": st.column_config.NumberColumn("Değer ₺", format="%.2f"),
                "pnl_pct": st.column_config.NumberColumn("PnL %", format="%+.2f"),
                "value_usd": st.column_config.NumberColumn("USD değer", format="%.2f"),
                "cost_usd": st.column_config.NumberColumn("USD maliyet", format="%.2f"),
            },
        )
        preview = float(pd.to_numeric(edited["value_tl"], errors="coerce").fillna(0).sum())
        st.caption(f"Önizleme toplam: ₺{preview:,.2f}".replace(",", "."))
        if st.button("Midas kitabını kaydet", type="primary", icon=":material/save:"):
            payload = editor_frame_to_book(
                edited,
                as_of=as_of.strip() or AS_OF_DEFAULT,
                usdtry=float(usdtry),
                note="Midas uygulamasından elle",
            )
            path = save_book(payload)
            _estimate_book.clear()
            st.success(f"Kaydedildi: `{path.name}` · Toplam ₺{preview:,.0f}".replace(",", "."))
            st.rerun()


def render() -> None:
    st.subheader("Kişisel yatırım uzmanı", divider="blue")
    st.info(MANIFESTO)

    if "est_nonce" not in st.session_state:
        st.session_state.est_nonce = 0

    _render_midas_editor()

    book, total = portfolio_frame(live=False)
    meta = book_meta()
    fx = get_book_usdtry()
    as_of = get_book_as_of()

    if not meta["exists"]:
        st.warning(
            "Henüz Midas kitabı kaydedilmedi. Yukarıdan bugünkü bakiyeleri yazıp kaydet — "
            "yoksa şablon (eski) tutarlar görünür."
        )

    st.caption(
        f"Kaynak: Midas kitabı {as_of} · USDTRY {fx:.2f} · "
        "Toplam Midas’taki gibi senin girdiğin bakiyedir (TEFAS tahmini değil)."
    )

    weights = book.set_index("code")["weight"].to_dict()
    buckets = bucket_weights(book)

    with st.container(horizontal=True):
        st.metric(
            "Toplam (Midas)",
            f"₺{total:,.0f}".replace(",", "."),
            border=True,
        )
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

    with st.expander("Pozisyonlar (Midas)", expanded=True):
        show = book[
            ["code", "name", "kind", "value_tl", "weight", "pnl_pct", "valor"]
        ].copy()
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

    with st.expander("Tahmini işaret (TEFAS / yfinance) — referans", expanded=False):
        st.caption(
            "Bu Midas değildir. Kitaptaki birimleri dış fiyatla çarpar; "
            f"₺{total:,.0f} ile bire bir örtüşmeyebilir.".replace(",", ".")
        )
        if st.button("Tahmini yenile", icon=":material/refresh:", key="btn_est"):
            st.session_state.est_nonce += 1
            _estimate_book.clear()
        try:
            est_book, est_total, notes = _estimate_book(st.session_state.est_nonce)
            delta = est_total - total
            st.metric(
                "Tahmini toplam",
                f"₺{est_total:,.0f}".replace(",", "."),
                f"Midas’a göre ₺{delta:+,.0f}".replace(",", "."),
            )
            if notes:
                st.caption(" · ".join(str(n) for n in notes[:3]))
            est_show = est_book[
                ["code", "value_tl_book", "value_tl", "delta_pct", "price_source", "mark_date"]
            ].copy()
            st.dataframe(
                est_show.rename(
                    columns={
                        "code": "Kod",
                        "value_tl_book": "Midas ₺",
                        "value_tl": "Tahmini ₺",
                        "delta_pct": "Δ %",
                        "price_source": "Kaynak",
                        "mark_date": "İşaret",
                    }
                ),
                hide_index=True,
                column_config={
                    "Midas ₺": st.column_config.NumberColumn(format="%.2f"),
                    "Tahmini ₺": st.column_config.NumberColumn(format="%.2f"),
                    "Δ %": st.column_config.NumberColumn(format="%+.2f"),
                },
            )
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Tahmini işaret alınamadı: {exc}")

    _render_morning_report_panel()

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
