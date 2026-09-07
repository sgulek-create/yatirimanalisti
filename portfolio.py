"""6 Eyl 2026 Midas portföy snapshot — kullanıcı kitabı + canlı işaret."""

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

# Hedef kovalar — "yeni TLY avı" yok; PP ile yaşat
TARGET_BUCKETS = {
    "pp": (0.35, 0.40),  # park + silah (Tera dışı tercih)
    "atak": (0.35, 0.40),  # mevcut tema / TLY tavanlı; kopya avı değil
    "global_veya_emtia": (0.15, 0.20),  # NVDA veya GMC — ikisi birden zorlama
}

MANIFESTO = (
    "Katlama hedefi yok. TLY benzeri kazancı ikinci kez arama; "
    "PP tamponu ile yaşat, vol yüksekken realize et, valör için parkı önceden tut."
)


def _book_frame():
    import pandas as pd

    rows = []
    for h in HOLDINGS:
        rows.append(
            {
                "code": h.code,
                "name": h.name,
                "kind": h.kind,
                "value_tl": h.value_tl,
                "value_tl_book": h.value_tl,
                "delta_pct": 0.0,
                "pnl_pct": h.pnl_pct,
                "manager": h.manager,
                "valor": h.valor,
                "value_usd": h.value_usd,
                "cost_usd": h.cost_usd,
                "price_source": "book",
                "mark_date": AS_OF,
                "mark_note": "kitap",
            }
        )
    df = pd.DataFrame(rows)
    total = float(df["value_tl"].sum())
    df["weight"] = df["value_tl"] / total if total else 0.0
    df["as_of"] = AS_OF
    df["usdtry"] = USDTRY
    df["live"] = False
    return df, total


def portfolio_frame(live: bool = True, bundle=None):
    """Portföy tablosu. live=True ise TEFAS/yfinance ile yeniden değerler."""
    import pandas as pd

    if not live:
        return _book_frame()

    try:
        from utils.live_prices import fetch_live_bundle, revalue_holdings
    except ImportError:
        from live_prices import fetch_live_bundle, revalue_holdings

    if bundle is None:
        bundle = fetch_live_bundle(
            book_as_of=AS_OF,
            book_usdtry=USDTRY,
            holdings=HOLDINGS,
        )
    rows = revalue_holdings(HOLDINGS, bundle)
    df = pd.DataFrame(rows)
    total = float(df["value_tl"].sum())
    df["weight"] = df["value_tl"] / total if total else 0.0
    fx = bundle.usdtry_live if bundle.usdtry_live else USDTRY
    live_day = None
    for m in bundle.marks.values():
        if m.live_date and (live_day is None or m.live_date > live_day):
            live_day = m.live_date
    df["as_of"] = live_day.isoformat() if live_day else AS_OF
    df["as_of_book"] = AS_OF
    df["usdtry"] = fx
    df["usdtry_book"] = USDTRY
    df["live"] = True
    df.attrs["live_bundle"] = bundle
    df.attrs["book_total"] = float(sum(h.value_tl for h in HOLDINGS))
    return df, total


def tera_weight(df) -> float:
    return float(df.loc[df["code"].isin(["TLY", "TP2", "TLV"]), "weight"].sum())


def bucket_weights(df) -> dict[str, float]:
    """Atak / PP / global / emtia ağırlıkları."""
    w = df.set_index("code")["weight"]
    kind = df.set_index("code")["kind"]
    gmc = float(w.get("GMC", 0.0) if "GMC" in w.index else 0.0)
    nvda = float(w.get("NVDA", 0.0) if "NVDA" in w.index else 0.0)
    pp = float(w[kind.isin(["pp", "katilim_pp"])].sum())
    atak_core = float(
        (w.get("TLY", 0.0) if "TLY" in w.index else 0.0)
        + (w.get("BOS", 0.0) if "BOS" in w.index else 0.0)
        + (w.get("MSTR", 0.0) if "MSTR" in w.index else 0.0)
    )
    return {
        "pp": pp,
        "atak": atak_core + nvda,
        "emtia": gmc,
        "nvda": nvda,
        "tly": float(w.get("TLY", 0.0) if "TLY" in w.index else 0.0),
    }
