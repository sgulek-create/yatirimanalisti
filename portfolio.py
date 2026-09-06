"""6 Eyl 2026 Midas portföy snapshot — kullanıcı kitabı."""

from __future__ import annotations

from dataclasses import dataclass

USDTRY = 48.42
AS_OF = "2026-09-06"


@dataclass(frozen=True)
class Holding:
    code: str
    name: str
    kind: str  # serbest | pp | katilim_pp | emtia | hisse_serbest | abd_hisse
    value_tl: float
    pnl_pct: float | None = None
    manager: str = ""
    valor: str = "T+1"
    cost_usd: float | None = None
    value_usd: float | None = None


HOLDINGS: list[Holding] = [
    Holding("TLY", "Tera 1. Serbest", "serbest", 66_085.84, 121.87, "Tera", "T+2"),
    Holding("TLV", "Tera katılım PP", "katilim_pp", 21_504.08, 19.47, "Tera", "T+1"),
    Holding("TP2", "Tera PP", "pp", 18_341.17, 22.29, "Tera", "T+1"),
    Holding("GMC", "TEB gümüş", "emtia", 5_202.31, 4.05, "TEB", "T+1"),
    Holding("BOS", "Bulls hisse serbest", "hisse_serbest", 1_666.26, -22.66, "Bulls", "T+2"),
    Holding(
        "NVDA",
        "NVIDIA",
        "abd_hisse",
        295.41 * USDTRY,
        26.61,
        "",
        "T+1 (USD)",
        cost_usd=229.47,
        value_usd=295.41,
    ),
    Holding(
        "MSTR",
        "MicroStrategy",
        "abd_hisse",
        176.97 * USDTRY,
        -24.08,
        "",
        "T+1 (USD)",
        cost_usd=142.57,
        value_usd=176.97,
    ),
]

# PP tarama evreni (kullanıcı + lig)
PP_UNIVERSE: list[str] = [
    "TP2",
    "TLV",
    "PRY",
    "PNU",
    "TI1",
    "GTL",
    "ILH",
    "GJH",
    "DCB",
    "AC4",
    "AAL",
    "PRR",
]

# Katılım PP — yalnızca adında/künyesinde katılım olanlar (PRY/PNU kör hedef değil)
KATILIM_PP: set[str] = {
    "TLV",
    "TI1",
    "ILH",
    "GJH",
    "PRR",  # Inveo katılım PP
}

# Konvansiyonel PP (PRY/PNU buraya — TLV rakibi değiller)
CONVENTIONAL_PP: set[str] = {
    "TP2",
    "GTL",
    "DCB",
    "AC4",
    "AAL",
    "PRY",
    "PNU",
    "BPZ",
    "KIE",
    "PPT",
}

# Serbest / hisse — PP parkına sokma
EXCLUDE_FROM_PP: set[str] = {"PHE", "TLY", "BOS"}

RULES = {
    "tly_max_weight": 0.45,
    "tera_max_weight": 0.70,
    "mstr_vol_annual_pct": 100.0,
    "nvda_mstr_corr": 0.50,
    "pp_switch_1m_pp": 0.25,  # yüzde puan
    "pp_switch_need_3m": True,
    "proxy_tly": "XU100*1.35",
    "proxy_gmc": "SLV",
    "proxy_bos": "XU100*1.2",
}


def portfolio_frame():
    import pandas as pd

    rows = []
    for h in HOLDINGS:
        rows.append(
            {
                "code": h.code,
                "name": h.name,
                "kind": h.kind,
                "value_tl": h.value_tl,
                "pnl_pct": h.pnl_pct,
                "manager": h.manager,
                "valor": h.valor,
                "value_usd": h.value_usd,
                "cost_usd": h.cost_usd,
            }
        )
    df = pd.DataFrame(rows)
    total = float(df["value_tl"].sum())
    df["weight"] = df["value_tl"] / total
    df["as_of"] = AS_OF
    df["usdtry"] = USDTRY
    return df, total


def tera_weight(df) -> float:
    return float(df.loc[df["code"].isin(["TLY", "TP2", "TLV"]), "weight"].sum())
