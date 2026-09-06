"""Varsayılan hisse evreni ve portföy izleme listesi."""

from __future__ import annotations

DEFAULT_STOCKS: list[str] = [
    # Küresel
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AVGO",
    "JPM",
    "LLY",
    "V",
    "XOM",
    "WMT",
    "ASML",
    "TSM",
    "BABA",
    "SAP",
    # BIST
    "THYAO.IS",
    "GARAN.IS",
    "AKBNK.IS",
    "EREGL.IS",
    "BIMAS.IS",
    "KCHOL.IS",
    "TUPRS.IS",
    "ASELS.IS",
    "FROTO.IS",
    "SISE.IS",
]

DEFAULT_PORTFOLIO_FUNDS: list[str] = [
    "TTE",
    "YAS",
    "AAL",
    "MAC",
    "IPB",
]

DEFAULT_PORTFOLIO_STOCKS: list[str] = [
    "NVDA",
    "AAPL",
    "THYAO.IS",
    "GARAN.IS",
]

FUND_KIND_LABELS: dict[str, str] = {
    "YAT": "Yatırım fonları",
    "BYF": "Borsa yatırım fonları",
    "EMK": "Emeklilik fonları",
}

RISK_BANDS: dict[int, tuple[int, int]] = {
    1: (1, 2),
    2: (1, 3),
    3: (1, 3),
    4: (2, 4),
    5: (3, 5),
    6: (3, 5),
    7: (4, 6),
    8: (5, 7),
    9: (5, 7),
    10: (6, 7),
}


def risk_profile_label(score: int) -> str:
    if score <= 3:
        return "Düşük risk"
    if score <= 7:
        return "Dengeli"
    return "Yüksek risk"


def parse_codes(raw: str) -> list[str]:
    """Virgül, boşluk veya satır sonu ile ayrılmış kodları temizler."""
    tokens = raw.replace("\n", ",").replace(";", ",").split(",")
    seen: set[str] = set()
    codes: list[str] = []
    for token in tokens:
        code = token.strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes
