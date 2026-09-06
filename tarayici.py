"""Fırsat tarayıcısı sayfası."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
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
)
PCT_COLUMN = st.column_config.NumberColumn(format="percent", step=0.0001)
TREND_COLUMN = st.column_config.LineChartColumn("Trend", width="medium", color="auto")

st.title("Fırsat tarayıcısı", icon=":material/query_stats:")
st.caption("TEFAS + yfinance momentum taraması — uzman emirleri için diğer sekmeye bak.")

with st.sidebar:
    st.subheader("Tarama ayarları")
    risk_score = st.slider("Risk skoru", 1, 10, 5)
    st.caption(
        f"{risk_profile_label(risk_score)} · KIID "
        f"{kiid_band(risk_score)[0]}–{kiid_band(risk_score)[1]}"
    )
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
    stock_text = st.text_area("Hisse evreni", value=", ".join(DEFAULT_STOCKS), height=120)
    portfolio_fund_text = st.text_input(
        "Portföy fonları", value=", ".join(DEFAULT_PORTFOLIO_FUNDS)
    )
    portfolio_stock_text = st.text_input(
        "Portföy hisseleri", value=", ".join(DEFAULT_PORTFOLIO_STOCKS)
    )
    if st.button("Verileri yenile", icon=":material/refresh:"):
        st.cache_data.clear()
        st.rerun()

tickers = tuple(parse_codes(stock_text))
portfolio_funds = parse_codes(portfolio_fund_text)
portfolio_stocks = parse_codes(portfolio_stock_text)

fund_error = None
stock_error = None
fund_history = pd.DataFrame()
funds = pd.DataFrame()
stocks = pd.DataFrame()

if not kind_codes:
    fund_error = "En az bir fon tipi seç."
else:
    try:
        with st.spinner("TEFAS…"):
            fund_snapshot = load_fund_snapshot(kind_codes)
            fund_history = load_fund_history(kind_codes)
        funds = build_fund_table(fund_history, fund_snapshot, risk_score)
    except (TefasError, OSError, ValueError) as exc:
        fund_error = str(exc)

if tickers:
    try:
        with st.spinner("Hisseler…"):
            stock_history = load_stock_history(tickers)
        stocks = build_stock_table(stock_history, risk_score)
    except (OSError, ValueError) as exc:
        stock_error = str(exc)

as_of = _as_of(fund_history) or date.today()
briefing = build_briefing(
    funds, stocks, risk_score, portfolio_funds, portfolio_stocks, as_of=as_of
)
top_funds = top_n(funds, TOP_N)
top_stocks = top_n(stocks, TOP_N)

with st.container(border=True):
    st.subheader("Sabah brifingi", icon=":material/wb_sunny:")
    st.markdown(f"**{briefing['headline']}**")
    st.markdown(briefing["body"])

fund_col, stock_col = st.columns(2)
with fund_col:
    with st.container(border=True):
        st.subheader("İlk 5 fon")
        if fund_error:
            st.warning(fund_error)
        elif top_funds.empty:
            st.info("Sonuç yok.")
        else:
            st.dataframe(
                _fund_display(top_funds),
                hide_index=True,
                column_config={
                    "Puan": SCORE_COLUMN,
                    "Günlük getiri": PCT_COLUMN,
                    "Hacim değişimi": PCT_COLUMN,
                    "Momentum (5g)": PCT_COLUMN,
                    "Trend": TREND_COLUMN,
                },
            )
with stock_col:
    with st.container(border=True):
        st.subheader("İlk 5 hisse")
        if stock_error:
            st.warning(stock_error)
        elif top_stocks.empty:
            st.info("Sonuç yok.")
        else:
            st.dataframe(
                _stock_display(top_stocks),
                hide_index=True,
                column_config={
                    "Puan": SCORE_COLUMN,
                    "Günlük getiri": PCT_COLUMN,
                    "Hacim değişimi": PCT_COLUMN,
                    "Momentum (5g)": PCT_COLUMN,
                    "Trend": TREND_COLUMN,
                },
            )
