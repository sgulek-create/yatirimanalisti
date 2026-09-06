"""60g vol/corr, blok-bootstrap VaR/CVaR, walk-forward overlay."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

from utils.portfolio import RULES, USDTRY


PROXY = {
    "NVDA": "NVDA",
    "MSTR": "MSTR",
    "GMC": "SLV",
    "BOS": "XU100.IS",
    "TLY": "XU100.IS",  # vekil — açıkça işaretlenir
    "BTC": "BTC-USD",
    "QQQ": "QQQ",
    "TRY": "TRY=X",
}

TLY_PROXY_MULT = 1.35
BOS_PROXY_MULT = 1.20


def fetch_closes(tickers: list[str], period: str = "6mo") -> pd.DataFrame:
    raw = yf.download(
        tickers=tickers,
        period=period,
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw is None or raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" in raw.columns.get_level_values(0):
            close = raw["Close"].copy()
        else:
            close = raw.xs("Close", axis=1, level=1)
    else:
        close = raw[["Close"]].rename(columns={"Close": tickers[0]})

    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.dropna(how="all")


def annualized_vol(returns: pd.Series, window: int = 60) -> float | None:
    r = returns.dropna().tail(window)
    if len(r) < max(20, window // 3):
        return None
    return float(r.std() * np.sqrt(252) * 100)


def rolling_corr(a: pd.Series, b: pd.Series, window: int = 60) -> float | None:
    joined = pd.concat([a, b], axis=1).dropna()
    if len(joined) < max(20, window // 3):
        return None
    return float(joined.iloc[:, 0].tail(window).corr(joined.iloc[:, 1].tail(window)))


@dataclass
class RiskSnapshot:
    mstr_vol_pct: float | None
    nvda_vol_pct: float | None
    nvda_mstr_corr: float | None
    var95: float | None
    cvar95: float | None
    p_loss_5pct: float | None
    alarms: list[str]
    tly_is_proxy: bool
    notes: list[str]


def build_proxy_returns(close: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Varlık getirileri; TLY/BOS/GMC vekil işaretli."""
    notes: list[str] = []
    cols: dict[str, pd.Series] = {}

    if "NVDA" in close.columns:
        cols["NVDA"] = close["NVDA"].pct_change()
    if "MSTR" in close.columns:
        cols["MSTR"] = close["MSTR"].pct_change()
    if "SLV" in close.columns:
        cols["GMC"] = close["SLV"].pct_change()
        notes.append("GMC = SLV vekil")
    if "XU100.IS" in close.columns:
        xu = close["XU100.IS"].pct_change()
        cols["BOS"] = xu * BOS_PROXY_MULT
        cols["TLY"] = xu * TLY_PROXY_MULT
        notes.append(
            f"TLY pay yok → {RULES['proxy_tly']} vekil (bu yüzden TLY'ye SAT üretilmez)"
        )
        notes.append(f"BOS = {RULES['proxy_bos']} vekil")

    # PP parkı: düşük vol sabit günlük (~TP2/TLV 1A/21) — dışarıdan set edilebilir
    return pd.DataFrame(cols), notes


def block_bootstrap_monthly(
    port_returns: pd.Series,
    n_sims: int = 5000,
    block: int = 5,
    horizon: int = 21,
    seed: int = 42,
) -> tuple[float, float, float]:
    """1 aylık blok-bootstrap: VaR95, CVaR95, P(ay<=-5%)."""
    r = port_returns.dropna().values
    if len(r) < block * 4:
        return float("nan"), float("nan"), float("nan")

    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(horizon / block))
    outcomes = np.empty(n_sims)
    max_start = len(r) - block
    for i in range(n_sims):
        chunks = []
        for _ in range(n_blocks):
            start = int(rng.integers(0, max_start + 1))
            chunks.append(r[start : start + block])
        path = np.concatenate(chunks)[:horizon]
        outcomes[i] = float(np.prod(1 + path) - 1)

    var95 = float(np.percentile(outcomes, 5))
    tail = outcomes[outcomes <= var95]
    cvar95 = float(tail.mean()) if len(tail) else var95
    p_loss = float((outcomes <= -0.05).mean())
    return var95, cvar95, p_loss


def portfolio_daily_returns(
    asset_returns: pd.DataFrame,
    weights: dict[str, float],
    pp_daily: float = 0.001,
) -> pd.Series:
    """Ağırlıklı günlük getiri; PP nakit getiri sabit."""
    w = weights.copy()
    # PP ağırlığı (TP2+TLV) nakit gibi
    pp_w = w.pop("TP2", 0) + w.pop("TLV", 0)
    frame = asset_returns.copy()
    for col in list(w):
        if col not in frame.columns:
            w.pop(col, None)
    if not w and pp_w <= 0:
        return pd.Series(dtype=float)

    # normalize remaining risky weights
    risky = sum(w.values())
    total = risky + pp_w
    if total <= 0:
        return pd.Series(dtype=float)
    w = {k: v / total for k, v in w.items()}
    pp_w = pp_w / total

    port = pd.Series(0.0, index=frame.index)
    for k, wt in w.items():
        port = port.add(frame[k].fillna(0) * wt, fill_value=0)
    port = port + pp_w * pp_daily
    return port.dropna()


def compute_risk(
    book_weights: dict[str, float],
    pp_daily_rate: float = 0.001,
) -> RiskSnapshot:
    tickers = ["NVDA", "MSTR", "SLV", "XU100.IS", "BTC-USD", "QQQ"]
    close = fetch_closes(tickers)
    asset_r, notes = build_proxy_returns(close)

    mstr_vol = (
        annualized_vol(asset_r["MSTR"]) if "MSTR" in asset_r.columns else None
    )
    nvda_vol = (
        annualized_vol(asset_r["NVDA"]) if "NVDA" in asset_r.columns else None
    )
    corr = None
    if "NVDA" in asset_r.columns and "MSTR" in asset_r.columns:
        corr = rolling_corr(asset_r["NVDA"], asset_r["MSTR"])

    port_r = portfolio_daily_returns(asset_r, book_weights, pp_daily=pp_daily_rate)
    var95, cvar95, p_loss = block_bootstrap_monthly(port_r)

    alarms: list[str] = []
    if mstr_vol is not None and mstr_vol > RULES["mstr_vol_annual_pct"]:
        alarms.append(
            f"MSTR 60g vol %{mstr_vol:.0f} > %100 — bu yüzden MSTR küçült, PP'ye kaydır"
        )
    if corr is not None and corr > RULES["nvda_mstr_corr"]:
        alarms.append(
            f"NVDA–MSTR corr {corr:.2f} > 0.50 — aynı faktör; MSTR'yi küçült"
        )
    if book_weights.get("TLY", 0) > RULES["tly_max_weight"]:
        alarms.append(
            f"TLY ağırlık %{book_weights['TLY']*100:.1f} > %45 — fazla PP'ye (Tera dışı tercih)"
        )
    tera = sum(book_weights.get(c, 0) for c in ("TLY", "TP2", "TLV"))
    if tera > RULES["tera_max_weight"]:
        alarms.append(
            f"Tera toplam %{tera*100:.0f} > %70 — parkı Tera dışına kaydır"
        )
    if not alarms:
        alarms.append("Kritik eşik yok — mevcut emirleri uygula, izlemeye devam")

    return RiskSnapshot(
        mstr_vol_pct=mstr_vol,
        nvda_vol_pct=nvda_vol,
        nvda_mstr_corr=corr,
        var95=var95 if var95 == var95 else None,
        cvar95=cvar95 if cvar95 == cvar95 else None,
        p_loss_5pct=p_loss if p_loss == p_loss else None,
        alarms=alarms,
        tly_is_proxy=True,
        notes=notes,
    )


def walk_forward(
    asset_returns: pd.DataFrame,
    base_weights: dict[str, float],
    pp_daily: float = 0.001,
    valor_lag: int = 2,
) -> pd.DataFrame:
    """
    A: al-tut (sabit ağırlık)
    B: overlay (TLY>%45 / MSTR vol / corr kuralları, T+2 valör)
    C: sadece PP park
    """
    if asset_returns.empty:
        return pd.DataFrame()

    idx = asset_returns.dropna(how="all").index
    rets = asset_returns.reindex(idx).fillna(0)

    # Precompute rolling signals
    mstr_vol = rets["MSTR"].rolling(60).std() * np.sqrt(252) if "MSTR" in rets else None
    corr = (
        rets["NVDA"].rolling(60).corr(rets["MSTR"])
        if {"NVDA", "MSTR"} <= set(rets.columns)
        else None
    )

    curves = {"A_buyhold": [], "B_overlay": [], "C_pp_only": []}
    dates = []
    wealth = {k: 1.0 for k in curves}

    # Pending overlay adjustments (valor)
    pending_cut_mstr = 0.0
    pending_cut_tly = 0.0
    queue: list[tuple[pd.Timestamp, str, float]] = []

    w_b = base_weights.copy()

    for i, dt in enumerate(idx):
        # apply due valor actions
        due = [q for q in queue if q[0] <= dt]
        queue = [q for q in queue if q[0] > dt]
        for _, kind, amt in due:
            if kind == "mstr":
                w_b["MSTR"] = max(0.0, w_b.get("MSTR", 0) - amt)
                w_b["TP2"] = w_b.get("TP2", 0) + amt
            elif kind == "tly":
                w_b["TLY"] = max(0.0, w_b.get("TLY", 0) - amt)
                w_b["TP2"] = w_b.get("TP2", 0) + amt

        # signal → schedule T+valor
        if i >= 60:
            # mstr_vol yıllık (ondalık): 1.0 = %100
            if mstr_vol is not None and mstr_vol.iloc[i] > 1.0 and w_b.get("MSTR", 0) > 0.01:
                cut = w_b["MSTR"] * 0.5
                queue.append((idx[min(i + valor_lag, len(idx) - 1)], "mstr", cut))
            if w_b.get("TLY", 0) > 0.45:
                cut = w_b["TLY"] - 0.40
                queue.append((idx[min(i + valor_lag, len(idx) - 1)], "tly", cut))
            if corr is not None and corr.iloc[i] > 0.50 and w_b.get("MSTR", 0) > 0.01:
                cut = w_b["MSTR"] * 0.3
                queue.append((idx[min(i + valor_lag, len(idx) - 1)], "mstr", cut))

        # normalize B
        s = sum(w_b.values()) or 1.0
        w_bn = {k: v / s for k, v in w_b.items()}

        day = {c: float(rets.loc[dt, c]) if c in rets.columns else 0.0 for c in rets.columns}

        def port_ret(weights: dict[str, float]) -> float:
            pp = weights.get("TP2", 0) + weights.get("TLV", 0)
            r = pp * pp_daily
            for k, wt in weights.items():
                if k in ("TP2", "TLV"):
                    continue
                r += wt * day.get(k, 0.0)
            return r

        wealth["A_buyhold"] *= 1 + port_ret(base_weights)
        wealth["B_overlay"] *= 1 + port_ret(w_bn)
        wealth["C_pp_only"] *= 1 + pp_daily

        dates.append(dt)
        for k in curves:
            curves[k].append(wealth[k])

    out = pd.DataFrame(curves, index=dates)
    out.index.name = "date"
    return out


def performance_stats(curve: pd.Series) -> dict[str, float]:
    if curve.empty or len(curve) < 5:
        return {}
    rets = curve.pct_change().dropna()
    total = float(curve.iloc[-1] / curve.iloc[0] - 1)
    years = len(curve) / 252
    cagr = float((curve.iloc[-1] / curve.iloc[0]) ** (1 / max(years, 1e-6)) - 1)
    vol = float(rets.std() * np.sqrt(252))
    peak = curve.cummax()
    dd = float(((curve / peak) - 1).min())
    return {
        "total_return": total,
        "cagr": cagr,
        "vol": vol,
        "max_dd": dd,
    }
