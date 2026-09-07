"""Canlı fiyat işaretleri — TEFAS fon + yfinance hisse/kur/emtia."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

try:
    from utils.tefas import fetch_fund_price_series
except ImportError:
    from tefas import fetch_fund_price_series

YF_TICKERS = {
    "NVDA": "NVDA",
    "MSTR": "MSTR",
    "GMC_PROXY": "SLV",  # yalnızca GMC TEFAS yoksa
    "USDTRY": "TRY=X",
}

FUND_KINDS = ("serbest", "pp", "katilim_pp", "emtia", "hisse_serbest")
USD_KINDS = ("abd_hisse",)


@dataclass
class Mark:
    code: str
    book_price: float | None
    live_price: float | None
    book_date: date | None
    live_date: date | None
    source: str  # tefas | yfinance | book
    note: str = ""


@dataclass
class LiveBundle:
    as_of_book: date
    fetched_at: datetime
    usdtry_book: float
    usdtry_live: float | None
    usdtry_date: date | None
    marks: dict[str, Mark]
    notes: list[str]


def _as_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _nearest_on_or_before(series: pd.Series, day: date) -> tuple[date | None, float | None]:
    """Index=date, values=price."""
    if series is None or series.empty:
        return None, None
    idx = pd.to_datetime(series.index).tz_localize(None).normalize()
    s = pd.Series(series.to_numpy(dtype=float), index=idx).dropna().sort_index()
    if s.empty:
        return None, None
    target = pd.Timestamp(day)
    prior = s.loc[s.index <= target]
    if prior.empty:
        # kitap tarihinden önce yoksa ilk noktayı al
        row = s.iloc[0]
        return s.index[0].date(), float(row)
    return prior.index[-1].date(), float(prior.iloc[-1])


def _yf_close_series(ticker: str, start: date, end: date) -> pd.Series:
    hist = yf.Ticker(ticker).history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=True,
    )
    if hist.empty or "Close" not in hist.columns:
        return pd.Series(dtype=float)
    close = hist["Close"].dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close


def fetch_live_bundle(
    *,
    book_as_of: str | date,
    book_usdtry: float,
    holdings: list[Any],
    lookback_days: int = 25,
) -> LiveBundle:
    """Kitap tarihine göre birim çıkarıp canlı işaret üretir."""
    as_of = _as_date(book_as_of)
    notes: list[str] = []
    marks: dict[str, Mark] = {}

    fund_codes = [
        h.code.upper()
        for h in holdings
        if getattr(h, "kind", "") in FUND_KINDS
    ]
    fund_hist = pd.DataFrame()
    if fund_codes:
        try:
            # Portföy fonları YAT; BYF eklemek 429 ve süreyi şişirir.
            fund_hist = fetch_fund_price_series(
                fund_codes,
                lookback_days=lookback_days,
                kinds=("YAT",),
            )
        except Exception as exc:  # noqa: BLE001
            notes.append(f"TEFAS hata: {exc}")

    start = as_of - timedelta(days=lookback_days)
    end = date.today()

    usdtry_live: float | None = None
    usdtry_date: date | None = None
    try:
        fx = _yf_close_series(YF_TICKERS["USDTRY"], start, end)
        usdtry_date, usdtry_live = _nearest_on_or_before(fx, end)
        if usdtry_live is None:
            notes.append("USDTRY canlı alınamadı — kitap kuru kullanılacak.")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"USDTRY hata: {exc}")

    yf_cache: dict[str, pd.Series] = {}

    for h in holdings:
        code = h.code.upper()
        kind = getattr(h, "kind", "")

        if kind in FUND_KINDS:
            marks[code] = _mark_fund(code, as_of, fund_hist, notes)
            continue

        if kind in USD_KINDS:
            yf_sym = YF_TICKERS.get(code, code)
            if yf_sym not in yf_cache:
                try:
                    yf_cache[yf_sym] = _yf_close_series(yf_sym, start, end)
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"{code} yfinance hata: {exc}")
                    yf_cache[yf_sym] = pd.Series(dtype=float)
            marks[code] = _mark_yf(code, as_of, yf_cache[yf_sym], "yfinance")
            continue

        marks[code] = Mark(code, None, None, None, None, "book", "canlı kaynak yok")

    return LiveBundle(
        as_of_book=as_of,
        fetched_at=datetime.now().astimezone(),
        usdtry_book=float(book_usdtry),
        usdtry_live=usdtry_live,
        usdtry_date=usdtry_date,
        marks=marks,
        notes=notes,
    )


def _mark_fund(code: str, as_of: date, hist: pd.DataFrame, notes: list[str]) -> Mark:
    if hist is None or hist.empty:
        return Mark(code, None, None, None, None, "book", "TEFAS boş")
    sub = hist[hist["fund_code"] == code].copy()
    if sub.empty:
        notes.append(f"{code}: TEFAS'ta yok — kitap değeri.")
        return Mark(code, None, None, None, None, "book", "TEFAS'ta yok")
    series = sub.set_index("date")["price"].astype(float).sort_index()
    book_d, book_p = _nearest_on_or_before(series, as_of)
    live_d, live_p = _nearest_on_or_before(series, date.today())
    return Mark(code, book_p, live_p, book_d, live_d, "tefas")


def _mark_yf(code: str, as_of: date, series: pd.Series, source: str) -> Mark:
    if series is None or series.empty:
        return Mark(code, None, None, None, None, "book", "fiyat yok")
    book_d, book_p = _nearest_on_or_before(series, as_of)
    live_d, live_p = _nearest_on_or_before(series, date.today())
    return Mark(code, book_p, live_p, book_d, live_d, source)


def revalue_holdings(
    holdings: list[Any],
    bundle: LiveBundle,
) -> list[dict[str, Any]]:
    """Kitap birimini canlı fiyata çarpar. Fon: ₺ fiyat; ABD: USD × kur."""
    fx = bundle.usdtry_live if bundle.usdtry_live else bundle.usdtry_book
    rows: list[dict[str, Any]] = []

    for h in holdings:
        code = h.code.upper()
        mark = bundle.marks.get(code)
        book_tl = float(h.value_tl)
        live_tl = book_tl
        value_usd = h.value_usd
        source = "book"
        mark_date = None
        note = ""
        units = None

        if mark and mark.source == "tefas" and mark.book_price and mark.live_price:
            units = book_tl / mark.book_price
            live_tl = units * mark.live_price
            source = "tefas"
            mark_date = mark.live_date
            note = f"birim {units:.4f} · TEFAS {mark.live_price:.6g}"
        elif (
            mark
            and mark.source == "yfinance"
            and mark.book_price
            and mark.live_price
            and h.value_usd
        ):
            # value_usd = kitaptaki USD piyasa değeri (toplam)
            units = float(h.value_usd) / mark.book_price
            value_usd = units * mark.live_price
            live_tl = value_usd * fx
            source = "yfinance"
            mark_date = mark.live_date
            note = f"{units:.4f} ad · ${mark.live_price:.2f} · kur {fx:.2f}"
        elif mark and mark.note:
            note = mark.note

        delta_pct = (live_tl / book_tl - 1.0) * 100.0 if book_tl else 0.0
        pnl_pct = h.pnl_pct

        rows.append(
            {
                "code": h.code,
                "name": h.name,
                "kind": h.kind,
                "value_tl_book": book_tl,
                "value_tl": live_tl,
                "delta_pct": delta_pct,
                "pnl_pct": pnl_pct,
                "manager": h.manager,
                "valor": h.valor,
                "value_usd": value_usd,
                "cost_usd": h.cost_usd,
                "price_source": source,
                "mark_date": mark_date.isoformat() if mark_date else None,
                "mark_note": note,
                "units": units,
            }
        )
    return rows
