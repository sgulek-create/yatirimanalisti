"""yfinance üzerinden global ve BIST hisse verisi."""

from __future__ import annotations

import pandas as pd
import yfinance as yf


def fetch_stock_history(tickers: list[str], period: str = "3mo") -> pd.DataFrame:
    """Kapanış ve hacim serilerini uzun formda döndürür."""
    if not tickers:
        return pd.DataFrame(columns=["date", "ticker", "close", "volume"])

    raw = yf.download(
        tickers=tickers,
        period=period,
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "ticker", "close", "volume"])

    frames: list[pd.DataFrame] = []
    if isinstance(raw.columns, pd.MultiIndex):
        close = _pick_field(raw, "Close")
        volume = _pick_field(raw, "Volume")
        if close is None:
            return pd.DataFrame(columns=["date", "ticker", "close", "volume"])
        close = close.copy()
        close.index = pd.to_datetime(close.index).tz_localize(None)
        long_close = (
            close.reset_index()
            .rename(columns={close.index.name or "Date": "date", "index": "date"})
            .melt(id_vars="date", var_name="ticker", value_name="close")
        )
        if volume is not None:
            volume = volume.copy()
            volume.index = pd.to_datetime(volume.index).tz_localize(None)
            long_volume = (
                volume.reset_index()
                .rename(columns={volume.index.name or "Date": "date", "index": "date"})
                .melt(id_vars="date", var_name="ticker", value_name="volume")
            )
            merged = long_close.merge(long_volume, on=["date", "ticker"], how="left")
        else:
            merged = long_close
            merged["volume"] = pd.NA
        frames.append(merged)
    else:
        frame = raw.copy()
        frame.index = pd.to_datetime(frame.index).tz_localize(None)
        frame = frame.reset_index().rename(columns={"Date": "date", "index": "date"})
        close_col = "Close" if "Close" in frame.columns else frame.columns[1]
        out = pd.DataFrame(
            {
                "date": frame["date"],
                "ticker": tickers[0].upper(),
                "close": frame[close_col],
                "volume": frame["Volume"] if "Volume" in frame.columns else pd.NA,
            }
        )
        frames.append(out)

    data = pd.concat(frames, ignore_index=True)
    data["ticker"] = data["ticker"].astype(str).str.upper()
    data = data.dropna(subset=["close"])
    return data.sort_values(["ticker", "date"]).reset_index(drop=True)


def _pick_field(raw: pd.DataFrame, field: str) -> pd.DataFrame | None:
    level0 = raw.columns.get_level_values(0)
    level1 = raw.columns.get_level_values(1)
    if field in set(level0):
        return raw[field]
    if field in set(level1):
        return raw.xs(field, axis=1, level=1)
    return None
