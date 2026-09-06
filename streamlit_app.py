"""Quant portföy ve fırsat tarayıcısı."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.briefing import build_briefing
from utils.scoring import build_fund_table, build_stock_table, kiid_band, top_n
from utils.stocks import fetch_stock_history
from utils.tefas import TefasError, fetch_fund_history, fetch_fund_snapshot
from utils.universe import (
    DEFAULT_PORTFOLIO_FUNDS,
    DEFAULT_PORTFOLIO_STOCKS,
    DEFAULT_STOCKS,
    FUND_KIND_LABELS,
    parse_codes,
    risk_profile_label,
)

st.set_page_config(
    page_title="Quant portföy ve fırsat tarayıcısı",
    page_icon=":material/query_stats:",
    layout="wide",
)

TOP_N = 5


@st.cache_data(ttl="1h", show_spinner=False)
def load_fund_snapshot(kinds: tuple[str, ...]) -> pd.DataFrame:
    return fetch_fund_snapshot(kinds)


@st.cache_data(ttl="1h", show_spinner=False)
def load_fund_history(kinds: tuple[str, ...]) -> pd.DataFrame:
    return fetch_fund_history(kinds)


@st.cache_data(ttl="15m", show_spinner=False)
def load_stock_history(tickers: tuple[str, ...]) -> pd.DataFrame:
    return fetch_stock_history(list(tickers))


def _as_of(history: pd.DataFrame) -> date | None:
    if history.empty or "date" not in history.columns:
        return None
    last = pd.to_datetime(history["date"], errors="coerce").max()
    if pd.isna(last):
        return None
    return last.date()


def _fund_display(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return table
    cols = {
        "fund_code": "Kod",
        "fund_name": "Fon",
        "score": "Puan",
        "daily_return": "Günlük getiri",
        "volume_change": "Hacim değişimi",
        "momentum_5d": "Momentum (5g)",
        "kiid_risk": "KIID risk",
        "spark": "Trend",
    }
    keep = [c for c in cols if c in table.columns]
    return table[keep].rename(columns=cols)


def _stock_display(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return table
    cols = {
        "ticker": "Sembol",
        "score": "Puan",
        "daily_return": "Günlük getiri",
        "volume_change": "Hacim değişimi",
        "momentum_5d": "Momentum (5g)",
        "risk_score": "Risk skoru",
        "spark": "Trend",
    }
    keep = [c for c in cols if c in table.columns]
    return table[keep].rename(columns=cols)


SCORE_COLUMN = st.column_config.ProgressColumn(
    "Puan",
    min_value=0,
    max_value=100,
    format="%.0f",
    help="Risk iştahına göre günlük getiri, hacim ve momentum karışımı.",
)
PCT_COLUMN = st.column_config.NumberColumn(format="percent", step=0.0001)
TREND_COLUMN = st.column_config.LineChartColumn("Trend", width="medium", color="auto")


"""
# :material/query_stats: Quant portföy ve fırsat tarayıcısı
"""
st.caption(
    "TEFAS fonları ve yfinance hisseleri için günlük getiri, hacim değişimi "
    "ve momentum taraması. Yatırım tavsiyesi değildir."
)

with st.sidebar:
    st.subheader("Tarama ayarları")
    risk_score = st.slider(
        "Risk skoru",
        min_value=1,
        max_value=10,
        value=5,
        help="Düşük skor temkinli fon/hisse arar, yüksek skor momentumu ödüllendirir.",
    )
    st.caption(f"{risk_profile_label(risk_score)} · KIID bandı {kiid_band(risk_score)[0]}–{kiid_band(risk_score)[1]}")

    kind_labels = list(FUND_KIND_LABELS.values())
    selected_kinds = st.pills(
        "Fon tipi",
        options=kind_labels,
        default=["Yatırım fonları", "Borsa yatırım fonları"],
        selection_mode="multi",
    )
    kind_codes = tuple(
        code for code, label in FUND_KIND_LABELS.items() if label in (selected_kinds or [])
    )

    stock_text = st.text_area(
        "Hisse evreni",
        value=", ".join(DEFAULT_STOCKS),
        height=120,
        help="Virgülle ayır. BIST için THYAO.IS formatını kullan.",
    )
    portfolio_fund_text = st.text_input(
        "Portföy fonları",
        value=", ".join(DEFAULT_PORTFOLIO_FUNDS),
        help="Sabah brifinginde önceliklendirilir.",
    )
    portfolio_stock_text = st.text_input(
        "Portföy hisseleri",
        value=", ".join(DEFAULT_PORTFOLIO_STOCKS),
    )

    if st.button("Verileri yenile", icon=":material/refresh:"):
        st.cache_data.clear()
        st.rerun()

tickers = tuple(parse_codes(stock_text))
portfolio_funds = parse_codes(portfolio_fund_text)
portfolio_stocks = parse_codes(portfolio_stock_text)

fund_error: str | None = None
stock_error: str | None = None
fund_history = pd.DataFrame()
fund_snapshot = pd.DataFrame()
stock_history = pd.DataFrame()
funds = pd.DataFrame()
stocks = pd.DataFrame()

if not kind_codes:
    fund_error = "En az bir fon tipi seç."
else:
    try:
        with st.spinner("TEFAS fon verileri çekiliyor…"):
            fund_snapshot = load_fund_snapshot(kind_codes)
            fund_history = load_fund_history(kind_codes)
        funds = build_fund_table(fund_history, fund_snapshot, risk_score)
    except (TefasError, OSError, ValueError) as exc:
        fund_error = f"TEFAS verisi alınamadı: {exc}"

if not tickers:
    stock_error = "En az bir hisse sembolü gir."
else:
    try:
        with st.spinner("Hisse verileri çekiliyor…"):
            stock_history = load_stock_history(tickers)
        stocks = build_stock_table(stock_history, risk_score)
    except (OSError, ValueError) as exc:
        stock_error = f"Hisse verisi alınamadı: {exc}"

as_of = _as_of(fund_history) or _as_of(stock_history) or date.today()
briefing = build_briefing(
    funds,
    stocks,
    risk_score,
    portfolio_funds,
    portfolio_stocks,
    as_of=as_of,
)
top_funds = top_n(funds, TOP_N)
top_stocks = top_n(stocks, TOP_N)

with st.container(border=True):
    st.subheader(":material/wb_sunny: Sabah brifingi")
    st.markdown(f"**{briefing['headline']}**")
    st.markdown(briefing["body"])

st.space("small")

with st.container(horizontal=True):
    st.metric("Taranan fon", f"{len(funds):,}".replace(",", "."), border=True)
    st.metric("Taranan hisse", f"{len(stocks):,}".replace(",", "."), border=True)
    st.metric("Risk profili", risk_profile_label(risk_score), border=True)
    best = None
    if not top_funds.empty:
        best = float(top_funds.iloc[0]["score"])
    elif not top_stocks.empty:
        best = float(top_stocks.iloc[0]["score"])
    st.metric(
        "En yüksek puan",
        f"{best:.0f}" if best is not None else "—",
        border=True,
    )

st.space("small")

fund_col, stock_col = st.columns(2)
with fund_col:
    with st.container(border=True):
        st.subheader("İlk 5 fon")
        if fund_error:
            st.warning(fund_error)
        elif top_funds.empty:
            st.info("Bu risk skoruna uyan fon bulunamadı.")
        else:
            st.dataframe(
                _fund_display(top_funds),
                hide_index=True,
                column_config={
                    "Puan": SCORE_COLUMN,
                    "Günlük getiri": PCT_COLUMN,
                    "Hacim değişimi": PCT_COLUMN,
                    "Momentum (5g)": PCT_COLUMN,
                    "KIID risk": st.column_config.NumberColumn(format="%.0f"),
                    "Trend": TREND_COLUMN,
                },
            )

with stock_col:
    with st.container(border=True):
        st.subheader("İlk 5 hisse")
        if stock_error:
            st.warning(stock_error)
        elif top_stocks.empty:
            st.info("Bu risk skoruna uyan hisse bulunamadı.")
        else:
            st.dataframe(
                _stock_display(top_stocks),
                hide_index=True,
                column_config={
                    "Puan": SCORE_COLUMN,
                    "Günlük getiri": PCT_COLUMN,
                    "Hacim değişimi": PCT_COLUMN,
                    "Momentum (5g)": PCT_COLUMN,
                    "Risk skoru": st.column_config.NumberColumn(format="%.0f"),
                    "Trend": TREND_COLUMN,
                },
            )

with st.expander("Puan nasıl hesaplanıyor?"):
    st.markdown(
        """
- **Günlük getiri:** son iş günü fiyat değişimi.
- **Hacim değişimi:** hissede son gün hacminin 20 günlük ortalamaya oranı;
  fonlarda portföy büyüklüğü (AUM) aynı şekilde vekil olarak kullanılır.
- **Momentum:** 5 ve 20 iş günlük kümülatif getiri.
- **Risk filtresi:** senin 1–10 skorun TEFAS KIID (1–7) ve hisse oynaklık
  skoruna eşlenir; bant dışındakiler elenir.
- **Puan:** evren içinde z-skorlanan bu sinyallerin ağırlıklı toplamı.
  Düşük risk oynaklığı keser, yüksek risk momentumu ödüllendirir.
        """
    )
