"""Sabah brifingi metni — portföyle uyumlu hareketler."""

from __future__ import annotations

from datetime import date

import pandas as pd

try:
    from utils.universe import risk_profile_label
except ImportError:
    from universe import risk_profile_label


def _fmt_pct(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value) * 100:+.2f}%"


def _activity_reason(row: pd.Series) -> str:
    parts: list[str] = []
    daily = row.get("daily_return")
    volume = row.get("volume_change")
    mom = row.get("momentum_5d")
    if daily is not None and pd.notna(daily) and abs(float(daily)) >= 0.008:
        parts.append(f"günlük getiri {_fmt_pct(daily)}")
    if volume is not None and pd.notna(volume) and abs(float(volume)) >= 0.15:
        parts.append(f"hacim/AUM değişimi {_fmt_pct(volume)}")
    if mom is not None and pd.notna(mom) and abs(float(mom)) >= 0.02:
        parts.append(f"5 günlük momentum {_fmt_pct(mom)}")
    if not parts:
        parts.append(f"fırsat puanı {float(row.get('score', 0)):.0f}")
    return ", ".join(parts)


def build_briefing(
    funds: pd.DataFrame,
    stocks: pd.DataFrame,
    user_risk: int,
    portfolio_funds: list[str],
    portfolio_stocks: list[str],
    as_of: date | None = None,
) -> dict[str, object]:
    """Portföy uyumlu hareketler için kısa sabah özeti."""
    day = as_of or date.today()
    profile = risk_profile_label(user_risk)
    owned_funds = {code.upper() for code in portfolio_funds}
    owned_stocks = {code.upper() for code in portfolio_stocks}

    fund_hits = pd.DataFrame()
    if not funds.empty and "fund_code" in funds.columns:
        in_portfolio = funds[funds["fund_code"].isin(owned_funds)]
        movers = funds.head(5)
        fund_hits = pd.concat([in_portfolio, movers]).drop_duplicates("fund_code")
        fund_hits = fund_hits.head(5)

    stock_hits = pd.DataFrame()
    if not stocks.empty and "ticker" in stocks.columns:
        in_portfolio = stocks[stocks["ticker"].isin(owned_stocks)]
        movers = stocks.head(5)
        stock_hits = pd.concat([in_portfolio, movers]).drop_duplicates("ticker")
        stock_hits = stock_hits.head(5)

    lines: list[str] = []
    if not fund_hits.empty:
        names = []
        for _, row in fund_hits.iterrows():
            code = row["fund_code"]
            mark = "portföyünde" if code in owned_funds else "risk profiline uyumlu"
            names.append(f"**{code}** ({mark}: {_activity_reason(row)})")
        lines.append(
            f"Bugün portföyüne uyumlu şu fonlarda hareketlilik var: {'; '.join(names)}."
        )
    else:
        lines.append(
            "Bugün risk profiline uyan fon taramasında öne çıkan bir hareket bulunamadı."
        )

    if not stock_hits.empty:
        names = []
        for _, row in stock_hits.iterrows():
            ticker = row["ticker"]
            mark = "portföyünde" if ticker in owned_stocks else "risk profiline uyumlu"
            names.append(f"**{ticker}** ({mark}: {_activity_reason(row)})")
        lines.append(f"Hisse tarafında dikkat çekenler: {'; '.join(names)}.")

    headline = (
        f"{day.strftime('%d.%m.%Y')} sabah brifingi — {profile.lower()} "
        f"(risk skoru {user_risk}/10)."
    )
    return {
        "headline": headline,
        "body": " ".join(lines),
        "fund_hits": fund_hits,
        "stock_hits": stock_hits,
    }
