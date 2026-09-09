"""Araştırma masası — A karşılaştır · B terminal · C sohbet."""

from __future__ import annotations

import streamlit as st

try:
    from utils.advisor_chat import answer, build_context, gemini_configured
    from utils.opportunity_agent import format_opportunity_cards, generate_opportunities
    from utils.portfolio import MANIFESTO, portfolio_frame
    from utils.pp_scan import load_pp_table
    from utils.research_compare import (
        compare_pp_candidates,
        compare_us_names,
        solution_map_frame,
    )
    from utils.risk_engine import compute_risk
    from utils.terminal_desk import run_command
except ImportError:
    from advisor_chat import answer, build_context, gemini_configured
    from opportunity_agent import format_opportunity_cards, generate_opportunities
    from portfolio import MANIFESTO, portfolio_frame
    from pp_scan import load_pp_table
    from research_compare import (
        compare_pp_candidates,
        compare_us_names,
        solution_map_frame,
    )
    from risk_engine import compute_risk
    from terminal_desk import run_command


@st.cache_data(ttl="20m", show_spinner="Araştırma verisi…")
def _bundle(nonce: int = 0):
    _ = nonce
    book, total = portfolio_frame(live=False)
    weights = book.set_index("code")["weight"].to_dict()
    pp = load_pp_table()
    risk = compute_risk(weights, pp_daily_rate=0.001)
    cards = generate_opportunities(
        book, pp, total_tl=total, mstr_vol_pct=risk.mstr_vol_pct, max_cards=3
    )
    pp_cmp = compare_pp_candidates(book, pp, total_tl=total, top_n=8)
    us_cmp = compare_us_names(
        book, mstr_vol_pct=risk.mstr_vol_pct, nvda_mstr_corr=risk.nvda_mstr_corr
    )
    firsat = format_opportunity_cards(cards)
    return book, total, cards, risk, pp_cmp, us_cmp, firsat


def _book_text(book, total: float) -> str:
    lines = [f"Toplam ₺{total:,.0f}".replace(",", ".")]
    for _, r in book.iterrows():
        lines.append(
            f"- {r['code']}: ₺{float(r['value_tl']):,.0f} "
            f"(%{float(r['weight'])*100:.1f})".replace(",", ".")
        )
    return "\n".join(lines)


def _render_compare(pp_cmp, us_cmp) -> None:
    st.caption(
        "Adayları yan yana gör — SaaS karşılaştırma tablosu gibi, ama senin "
        "kitap + manifesto önerisiyle."
    )
    st.markdown("**PP / park adayları**")
    if pp_cmp is None or pp_cmp.empty:
        st.warning("PP karşılaştırma boş.")
    else:
        st.dataframe(
            pp_cmp,
            hide_index=True,
            column_config={
                "1A %": st.column_config.NumberColumn(format="%.2f"),
                "3A %": st.column_config.NumberColumn(format="%.2f"),
                "6A %": st.column_config.NumberColumn(format="%.2f"),
                "Günlük ≈%": st.column_config.NumberColumn(format="%.3f"),
                "Ağırlık %": st.column_config.NumberColumn(format="%.2f"),
                "Max ₺": st.column_config.NumberColumn(format="%.0f"),
            },
        )
        st.download_button(
            "CSV indir",
            pp_cmp.to_csv(index=False).encode("utf-8-sig"),
            file_name="karsilastir_pp.csv",
            mime="text/csv",
            icon=":material/download:",
        )

    st.markdown("**ABD isimleri (kitap riski)**")
    st.dataframe(us_cmp, hide_index=True)

    with st.expander("SaaS haritası (ne biziz / ne değiliz)"):
        st.dataframe(solution_map_frame(), hide_index=True)


def _render_terminal(firsat: str) -> None:
    st.caption(
        "OpenBB-lite: komut yaz → quote / pp / book / chart / rules. "
        "Veri TEFAS + yfinance."
    )
    if "term_hist" not in st.session_state:
        st.session_state.term_hist = []

    c1, c2 = st.columns([4, 1])
    with c1:
        cmd = st.text_input(
            "Komut",
            placeholder="pp 10 | quote PNU | chart NVDA 90 | book | rules | help",
            label_visibility="collapsed",
            key="term_cmd",
        )
    with c2:
        go = st.button("Çalıştır", type="primary", icon=":material/terminal:")

    b1, b2, b3, b4, b5 = st.columns(5)
    if b1.button("pp", key="chip_pp"):
        st.session_state.term_run = "pp 10"
    if b2.button("book", key="chip_book"):
        st.session_state.term_run = "book"
    if b3.button("quote NVDA", key="chip_nvda"):
        st.session_state.term_run = "quote NVDA"
    if b4.button("rules", key="chip_rules"):
        st.session_state.term_run = "rules"
    if b5.button("help", key="chip_help"):
        st.session_state.term_run = "help"

    pending = st.session_state.pop("term_run", None)
    if go and cmd:
        pending = cmd

    if pending:
        with st.spinner(f"$ {pending}"):
            result = run_command(pending, firsat_text=firsat)
        st.session_state.term_hist.insert(
            0, {"cmd": pending, "title": result.title, "result": result}
        )
        st.session_state.term_hist = st.session_state.term_hist[:8]

    if not st.session_state.term_hist:
        st.info("Örnek: `pp 10` veya `quote TP2`")
        return

    for item in st.session_state.term_hist:
        r = item["result"]
        st.markdown(f"`$ {item['cmd']}` · **{r.title}**")
        if r.kind == "text" and r.text:
            st.code(r.text, language=None)
        if r.kind == "table" and r.table is not None:
            st.dataframe(r.table, hide_index=True)
        if r.kind == "chart" and r.chart is not None and not r.chart.empty:
            st.line_chart(r.chart)
            st.caption(r.title)


def _render_chat(book, total: float, firsat: str, pp_cmp) -> None:
    st.caption(
        "C: karar chatbot — manifesto kilitli. Anahtar yoksa kural motoru; "
        "`.streamlit/secrets.toml` içine `gemini_api_key` eklersen Gemini."
    )
    engine = "gemini" if gemini_configured() else "rules"
    st.badge(f"Motor: {engine}", icon=":material/smart_toy:")

    if "chat_msgs" not in st.session_state:
        st.session_state.chat_msgs = [
            {
                "role": "assistant",
                "content": (
                    "Merhaba Süleyman. Kitap, PP geçiş, fırsat kartı veya "
                    "«neden ikinci TLY yok?» diye sor. Emir basmam."
                ),
            }
        ]

    for msg in st.session_state.chat_msgs:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    hint = ""
    if pp_cmp is not None and not pp_cmp.empty:
        top = pp_cmp.head(3)
        hint = "; ".join(
            f"{r.Kod}→{r.Öneri}" for r in top.itertuples(index=False)
        )

    ctx = build_context(
        book_text=_book_text(book, total),
        firsat_text=firsat,
        compare_hint=hint,
    )

    prompt = st.chat_input("Sorunu yaz…")
    if prompt:
        st.session_state.chat_msgs.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Düşünüyor…"):
                text, used = answer(prompt, ctx)
            st.markdown(text)
            st.caption(f"kaynak: {used}")
        st.session_state.chat_msgs.append({"role": "assistant", "content": text})

    if st.button("Sohbeti temizle", icon=":material/delete:"):
        st.session_state.chat_msgs = []
        st.rerun()


def render() -> None:
    st.subheader("Araştırma masası", divider="blue")
    st.info(MANIFESTO)

    if "ar_nonce" not in st.session_state:
        st.session_state.ar_nonce = 0
    if st.button("Veriyi yenile", icon=":material/refresh:"):
        st.session_state.ar_nonce += 1
        _bundle.clear()

    try:
        book, total, _cards, risk, pp_cmp, us_cmp, firsat = _bundle(
            st.session_state.ar_nonce
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Araştırma verisi alınamadı: {exc}")
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Kitap", f"₺{total:,.0f}".replace(",", "."))
    m2.metric(
        "MSTR vol",
        f"%{risk.mstr_vol_pct:.0f}" if risk.mstr_vol_pct is not None else "—",
    )
    m3.metric("PP satır", str(0 if pp_cmp is None else len(pp_cmp)))

    tab_a, tab_b, tab_c = st.tabs(
        ["A · Karşılaştır", "B · Terminal", "C · Sohbet"]
    )
    with tab_a:
        _render_compare(pp_cmp, us_cmp)
    with tab_b:
        _render_terminal(firsat)
    with tab_c:
        _render_chat(book, total, firsat, pp_cmp)
