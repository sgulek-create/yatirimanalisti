"""Portföy — Midas gerçek kitap + isteğe bağlı TEFAS/yfinance işaret."""

from __future__ import annotations

from dataclasses import dataclass

# Şablon (ilk kurulum). Gerçek bakiye: data/midas_kitap.json
USDTRY_DEFAULT = 48.42
AS_OF_DEFAULT = "2026-09-06"


@dataclass(frozen=True)
class Holding:
    code: str
    name: str
    kind: str  # serbest | pp | katilim_pp | emtia | hisse_serbest | abd_hisse | nakit
    value_tl: float
    pnl_pct: float | None = None
    manager: str = ""
    valor: str = "T+1"
    cost_usd: float | None = None
    value_usd: float | None = None


DEFAULT_HOLDINGS: list[Holding] = [
    Holding("TLY", "Tera 1. Serbest", "serbest", 66_085.84, 121.87, "Tera", "T+2"),
    Holding("TLV", "Tera katılım PP", "katilim_pp", 21_504.08, 19.47, "Tera", "T+1"),
    Holding("TP2", "Tera PP", "pp", 18_341.17, 22.29, "Tera", "T+1"),
    Holding("GMC", "TEB gümüş", "emtia", 5_202.31, 4.05, "TEB", "T+1"),
    Holding("BOS", "Bulls hisse serbest", "hisse_serbest", 1_666.26, -22.66, "Bulls", "T+2"),
    Holding(
        "NVDA",
        "NVIDIA",
        "abd_hisse",
        295.41 * USDTRY_DEFAULT,
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
        176.97 * USDTRY_DEFAULT,
        -24.08,
        "",
        "T+1 (USD)",
        cost_usd=142.57,
        value_usd=176.97,
    ),
]

# Geriye uyum
HOLDINGS = DEFAULT_HOLDINGS
USDTRY = USDTRY_DEFAULT
AS_OF = AS_OF_DEFAULT

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

KATILIM_PP: set[str] = {
    "TLV",
    "TI1",
    "ILH",
    "GJH",
    "PRR",
}

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

EXCLUDE_FROM_PP: set[str] = {"PHE", "TLY", "BOS"}

RULES = {
    "tly_max_weight": 0.45,
    "tera_max_weight": 0.70,
    "mstr_vol_annual_pct": 100.0,
    "nvda_mstr_corr": 0.50,
    "pp_switch_1m_pp": 0.25,
    "pp_switch_need_3m": True,
    "proxy_tly": "XU100*1.35",
    "proxy_gmc": "SLV",
    "proxy_bos": "XU100*1.2",
}

TARGET_BUCKETS = {
    "pp": (0.35, 0.40),
    "atak": (0.35, 0.40),
    "global_veya_emtia": (0.15, 0.20),
}

MANIFESTO = (
    "Katlama hedefi yok. TLY benzeri kazancı ikinci kez arama; "
    "PP tamponu ile yaşat, vol yüksekken realize et, valör için parkı önceden tut."
)


def get_holdings() -> list[Holding]:
    try:
        from utils.midas_book import active_holdings
    except ImportError:
        from midas_book import active_holdings

    return active_holdings()


def get_book_as_of() -> str:
    try:
        from utils.midas_book import book_meta
    except ImportError:
        from midas_book import book_meta

    meta = book_meta()
    return str(meta.get("as_of") or AS_OF_DEFAULT)


def get_book_usdtry() -> float:
    try:
        from utils.midas_book import book_meta
    except ImportError:
        from midas_book import book_meta

    meta = book_meta()
    fx = meta.get("usdtry")
    return float(fx) if fx else USDTRY_DEFAULT


def _book_frame(holdings: list[Holding] | None = None):
    import pandas as pd

    rows_h = holdings or get_holdings()
    as_of = get_book_as_of()
    fx = get_book_usdtry()
    rows = []
    for h in rows_h:
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
                "price_source": "midas",
                "mark_date": as_of,
                "mark_note": "Midas gerçek",
            }
        )
    df = pd.DataFrame(rows)
    total = float(df["value_tl"].sum()) if len(df) else 0.0
    df["weight"] = df["value_tl"] / total if total else 0.0
    df["as_of"] = as_of
    df["as_of_book"] = as_of
    df["usdtry"] = fx
    df["usdtry_book"] = fx
    df["live"] = False
    df.attrs["book_total"] = total
    return df, total


def portfolio_frame(live: bool = False, bundle=None):
    """Portföy tablosu.

    live=False (varsayılan): Midas kitabı — ekranda gördüğün gerçek.
    live=True: TEFAS/yfinance tahmini işaret (kitaptan sapabilir).
    """
    import pandas as pd

    holdings = get_holdings()
    as_of = get_book_as_of()
    fx_book = get_book_usdtry()

    if not live:
        return _book_frame(holdings)

    try:
        from utils.live_prices import fetch_live_bundle, revalue_holdings
    except ImportError:
        from live_prices import fetch_live_bundle, revalue_holdings

    if bundle is None:
        bundle = fetch_live_bundle(
            book_as_of=as_of,
            book_usdtry=fx_book,
            holdings=holdings,
        )
    rows = revalue_holdings(holdings, bundle)
    df = pd.DataFrame(rows)
    total = float(df["value_tl"].sum()) if len(df) else 0.0
    df["weight"] = df["value_tl"] / total if total else 0.0
    fx = bundle.usdtry_live if bundle.usdtry_live else fx_book
    live_day = None
    for m in bundle.marks.values():
        if m.live_date and (live_day is None or m.live_date > live_day):
            live_day = m.live_date
    df["as_of"] = live_day.isoformat() if live_day else as_of
    df["as_of_book"] = as_of
    df["usdtry"] = fx
    df["usdtry_book"] = fx_book
    df["live"] = True
    df.attrs["live_bundle"] = bundle
    df.attrs["book_total"] = float(sum(h.value_tl for h in holdings))
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
