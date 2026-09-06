"""Günlük getiri, hacim değişimi, momentum ve oynaklık."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _safe_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current / previous) - 1.0


def summarize_price_series(
    prices: pd.Series,
    volumes: pd.Series | None = None,
    spark_window: int = 20,
) -> dict[str, object]:
    """Tek bir varlık için metrik sözlüğü üretir."""
    clean = prices.dropna().astype(float)
    if len(clean) < 3:
        return {}

    returns = clean.pct_change().dropna()
    daily_return = float(returns.iloc[-1]) if not returns.empty else None

    momentum_5d = _safe_pct(float(clean.iloc[-1]), float(clean.iloc[-6])) if len(clean) >= 6 else None
    momentum_20d = (
        _safe_pct(float(clean.iloc[-1]), float(clean.iloc[-21])) if len(clean) >= 21 else None
    )
    if momentum_20d is None and len(clean) >= 6:
        momentum_20d = _safe_pct(float(clean.iloc[-1]), float(clean.iloc[0]))

    vol_window = min(20, len(returns))
    volatility = float(returns.tail(vol_window).std()) if vol_window >= 5 else None
    annual_vol = float(volatility * np.sqrt(TRADING_DAYS)) if volatility is not None else None

    volume_change = None
    if volumes is not None:
        vol = volumes.reindex(clean.index).astype(float)
        last = vol.iloc[-1]
        baseline = vol.iloc[-21:-1].mean() if len(vol) >= 21 else vol.iloc[:-1].mean()
        if pd.notna(last) and pd.notna(baseline) and baseline not in (0, 0.0):
            volume_change = float((last / baseline) - 1.0)

    spark = [float(x) for x in clean.tail(spark_window).tolist()]
    return {
        "last_price": float(clean.iloc[-1]),
        "daily_return": daily_return,
        "momentum_5d": momentum_5d,
        "momentum_20d": momentum_20d,
        "volatility": volatility,
        "annual_vol": annual_vol,
        "volume_change": volume_change,
        "spark": spark,
        "as_of": clean.index[-1],
        "observations": int(len(clean)),
    }


def metrics_from_long_prices(
    history: pd.DataFrame,
    id_col: str,
    price_col: str,
    volume_col: str | None = None,
    date_col: str = "date",
) -> pd.DataFrame:
    """Uzun form fiyat tablosunu varlık bazında metriğe çevirir."""
    if history.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    grouped = history.sort_values(date_col).groupby(id_col, sort=False)
    for asset_id, group in grouped:
        series = group.set_index(date_col)[price_col]
        volumes = group.set_index(date_col)[volume_col] if volume_col else None
        stats = summarize_price_series(series, volumes)
        if not stats:
            continue
        stats[id_col] = asset_id
        rows.append(stats)
    return pd.DataFrame(rows)


def vol_to_risk_score(annual_vol: float | None) -> int | None:
    """Yıllık oynaklığı 1–10 hisse risk skoruna eşler."""
    if annual_vol is None or np.isnan(annual_vol):
        return None
    pct = annual_vol * 100
    if pct < 12:
        return 2
    if pct < 18:
        return 3
    if pct < 24:
        return 4
    if pct < 30:
        return 5
    if pct < 38:
        return 6
    if pct < 48:
        return 7
    if pct < 60:
        return 8
    if pct < 80:
        return 9
    return 10
