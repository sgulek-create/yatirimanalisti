"""Risk iştahına göre fırsat puanı."""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from utils.metrics import metrics_from_long_prices, vol_to_risk_score
    from utils.universe import RISK_BANDS
except ImportError:
    from metrics import metrics_from_long_prices, vol_to_risk_score
    from universe import RISK_BANDS


def _zscore(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.notna().sum() >= 8:
        low, high = values.quantile(0.02), values.quantile(0.98)
        values = values.clip(lower=low, upper=high)
    std = values.std(ddof=0)
    if std == 0 or pd.isna(std):
        return pd.Series(0.0, index=values.index)
    return (values - values.mean()) / std


def _clip_score(raw: pd.Series) -> pd.Series:
    """Z-skor karışımını 0–100 aralığına sıkıştırır."""
    scaled = 50 + 12 * raw
    return scaled.clip(lower=0, upper=100)


def kiid_band(user_risk: int) -> tuple[int, int]:
    return RISK_BANDS.get(int(user_risk), (3, 5))


def stock_risk_band(user_risk: int) -> tuple[int, int]:
    """Hisse risk skoru 1–10; kullanıcı skorunun ±2 bandı."""
    lo = max(1, int(user_risk) - 2)
    hi = min(10, int(user_risk) + 2)
    return lo, hi


def score_universe(metrics: pd.DataFrame, user_risk: int) -> pd.DataFrame:
    """Günlük getiri, hacim ve momentumu risk iştahına göre puanlar."""
    if metrics.empty:
        return metrics.copy()

    out = metrics.copy()
    appetite = (int(user_risk) - 1) / 9  # 0 = temkinli, 1 = agresif

    daily = _zscore(out.get("daily_return", pd.Series(dtype=float)))
    volume = _zscore(out.get("volume_change", pd.Series(dtype=float)))
    mom5 = _zscore(out.get("momentum_5d", pd.Series(dtype=float)))
    mom20 = _zscore(out.get("momentum_20d", pd.Series(dtype=float)))
    vol = _zscore(out.get("volatility", pd.Series(dtype=float)))

    opportunity = (
        0.28 * daily.fillna(0)
        + 0.22 * volume.fillna(0)
        + 0.25 * mom5.fillna(0)
        + 0.15 * mom20.fillna(0)
    )
    # Düşük risk oynaklığı cezalandırır; yüksek risk momentum için kabul eder.
    risk_term = (1 - appetite) * (-vol.fillna(0)) + appetite * (0.35 * vol.fillna(0))
    out["score"] = _clip_score(opportunity + 0.20 * risk_term)
    return out.sort_values("score", ascending=False).reset_index(drop=True)


def build_fund_table(
    history: pd.DataFrame,
    snapshot: pd.DataFrame,
    user_risk: int,
    min_aum: float = 10_000_000,
) -> pd.DataFrame:
    metrics = metrics_from_long_prices(
        history,
        id_col="fund_code",
        price_col="price",
        volume_col="portfolio_size",
    )
    if metrics.empty and snapshot.empty:
        return pd.DataFrame()

    if metrics.empty:
        table = snapshot.copy()
        table["daily_return"] = np.nan
        table["volume_change"] = np.nan
        table["momentum_5d"] = pd.to_numeric(table.get("return_1m"), errors="coerce") / 100
        table["momentum_20d"] = pd.to_numeric(table.get("return_3m"), errors="coerce") / 100
        table["volatility"] = np.nan
        table["spark"] = [[] for _ in range(len(table))]
        table["last_price"] = np.nan
    else:
        table = metrics.copy()
        if not snapshot.empty:
            table = table.merge(snapshot, on="fund_code", how="left")
        latest = history.sort_values("date").groupby("fund_code").tail(1)
        extra_cols = [
            col
            for col in ("fund_name", "portfolio_size", "kind")
            if col in latest.columns
        ]
        if extra_cols:
            table = table.merge(
                latest[["fund_code", *extra_cols]],
                on="fund_code",
                how="left",
                suffixes=("", "_hist"),
            )
            if "fund_name_hist" in table.columns:
                table["fund_name"] = table.get("fund_name", pd.Series(index=table.index)).fillna(
                    table["fund_name_hist"]
                )
            if "kind_hist" in table.columns:
                table["kind"] = table.get("kind", pd.Series(index=table.index)).fillna(
                    table["kind_hist"]
                )
            if "portfolio_size_hist" in table.columns:
                if "portfolio_size" in table.columns:
                    table["portfolio_size"] = table["portfolio_size"].fillna(
                        table["portfolio_size_hist"]
                    )
                else:
                    table["portfolio_size"] = table["portfolio_size_hist"]

    if "portfolio_size" in table.columns:
        table = table[table["portfolio_size"].fillna(0).ge(min_aum)]

    if "observations" in table.columns:
        table = table[table["observations"].fillna(0).ge(5)]

    lo, hi = kiid_band(user_risk)
    if "kiid_risk" in table.columns:
        kiid = pd.to_numeric(table["kiid_risk"], errors="coerce")
        matched = table[kiid.between(lo, hi)]
        if not matched.empty:
            table = matched

    scored = score_universe(table, user_risk)
    return scored


def build_stock_table(history: pd.DataFrame, user_risk: int) -> pd.DataFrame:
    metrics = metrics_from_long_prices(
        history,
        id_col="ticker",
        price_col="close",
        volume_col="volume",
    )
    if metrics.empty:
        return metrics
    metrics["risk_score"] = metrics["annual_vol"].map(vol_to_risk_score)
    lo, hi = stock_risk_band(user_risk)
    matched = metrics[metrics["risk_score"].between(lo, hi) | metrics["risk_score"].isna()]
    if not matched.empty:
        metrics = matched
    return score_universe(metrics, user_risk)


def top_n(table: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    if table.empty:
        return table
    return table.head(n).copy()
