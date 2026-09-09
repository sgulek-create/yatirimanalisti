"""Pozisyon birimleri + canlı fiyat (TEFAS / yfinance).

Midas da aynı kaynaklara bakar. Biz birimi sabitleriz, fiyatı anlık çekeriz.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BOOK_PATH = ROOT / "data" / "midas_kitap.json"

# Şablon — ilk kurulum; birimler ilk canlı çekimde kilitlenir
SEED = [
    {
        "code": "TLY",
        "name": "Tera 1. Serbest",
        "kind": "serbest",
        "value_tl": 66_085.84,
        "pnl_pct": 121.87,
        "manager": "Tera",
        "valor": "T+2",
        "units": None,
        "value_usd": None,
        "cost_usd": None,
    },
    {
        "code": "TLV",
        "name": "Tera katılım PP",
        "kind": "katilim_pp",
        "value_tl": 21_504.08,
        "pnl_pct": 19.47,
        "manager": "Tera",
        "valor": "T+1",
        "units": None,
        "value_usd": None,
        "cost_usd": None,
    },
    {
        "code": "TP2",
        "name": "Tera PP",
        "kind": "pp",
        "value_tl": 18_341.17,
        "pnl_pct": 22.29,
        "manager": "Tera",
        "valor": "T+1",
        "units": None,
        "value_usd": None,
        "cost_usd": None,
    },
    {
        "code": "GMC",
        "name": "TEB gümüş",
        "kind": "emtia",
        "value_tl": 5_202.31,
        "pnl_pct": 4.05,
        "manager": "TEB",
        "valor": "T+1",
        "units": None,
        "value_usd": None,
        "cost_usd": None,
    },
    {
        "code": "BOS",
        "name": "Bulls hisse serbest",
        "kind": "hisse_serbest",
        "value_tl": 1_666.26,
        "pnl_pct": -22.66,
        "manager": "Bulls",
        "valor": "T+2",
        "units": None,
        "value_usd": None,
        "cost_usd": None,
    },
    {
        "code": "NVDA",
        "name": "NVIDIA",
        "kind": "abd_hisse",
        "value_tl": 295.41 * 48.42,
        "pnl_pct": 26.61,
        "manager": "",
        "valor": "T+1 (USD)",
        "units": None,
        "value_usd": 295.41,
        "cost_usd": 229.47,
    },
    {
        "code": "MSTR",
        "name": "MicroStrategy",
        "kind": "abd_hisse",
        "value_tl": 176.97 * 48.42,
        "pnl_pct": -24.08,
        "manager": "",
        "valor": "T+1 (USD)",
        "units": None,
        "value_usd": 176.97,
        "cost_usd": 142.57,
    },
]


@dataclass(frozen=True)
class Holding:
    code: str
    name: str
    kind: str
    value_tl: float
    pnl_pct: float | None = None
    manager: str = ""
    valor: str = "T+1"
    cost_usd: float | None = None
    value_usd: float | None = None
    units: float | None = None


def _row_to_holding(raw: dict[str, Any]) -> Holding:
    return Holding(
        code=str(raw["code"]).upper(),
        name=str(raw.get("name") or raw["code"]),
        kind=str(raw.get("kind") or "serbest"),
        value_tl=float(raw.get("value_tl") or 0),
        pnl_pct=float(raw["pnl_pct"]) if raw.get("pnl_pct") is not None else None,
        manager=str(raw.get("manager") or ""),
        valor=str(raw.get("valor") or "T+1"),
        cost_usd=float(raw["cost_usd"]) if raw.get("cost_usd") is not None else None,
        value_usd=float(raw["value_usd"]) if raw.get("value_usd") is not None else None,
        units=float(raw["units"]) if raw.get("units") is not None else None,
    )


def load_raw() -> dict[str, Any]:
    if not BOOK_PATH.exists():
        return {
            "as_of": date.today().isoformat(),
            "usdtry": None,
            "source": "tefas_yfinance",
            "note": "Birim × canlı fiyat",
            "holdings": [dict(r) for r in SEED],
        }
    try:
        raw = json.loads(BOOK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "as_of": date.today().isoformat(),
            "usdtry": None,
            "source": "tefas_yfinance",
            "note": "Birim × canlı fiyat",
            "holdings": [dict(r) for r in SEED],
        }
    if not raw.get("holdings"):
        raw["holdings"] = [dict(r) for r in SEED]
    return raw


def save_raw(data: dict[str, Any]) -> Path:
    BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOOK_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return BOOK_PATH


def book_exists() -> bool:
    return BOOK_PATH.exists()


def active_holdings() -> list[Holding]:
    rows = load_raw().get("holdings") or []
    out: list[Holding] = []
    for row in rows:
        try:
            h = _row_to_holding(row)
        except (KeyError, TypeError, ValueError):
            continue
        if h.value_tl <= 0 and (h.units is None or h.units <= 0) and h.code != "CASH":
            continue
        out.append(h)
    if out:
        return out
    return [_row_to_holding(r) for r in SEED]


def book_meta() -> dict[str, Any]:
    data = load_raw()
    holdings = active_holdings()
    return {
        "as_of": str(data.get("as_of") or ""),
        "usdtry": data.get("usdtry"),
        "source": data.get("source") or "tefas_yfinance",
        "path": str(BOOK_PATH),
        "exists": book_exists(),
        "total": float(sum(h.value_tl for h in holdings)),
        "note": data.get("note") or "",
        "units_locked": all(
            h.units is not None or h.kind == "nakit" or h.code == "CASH"
            for h in holdings
        ),
    }


def lock_units_from_marks(holdings: list[Holding], marks: dict[str, Any], fx: float) -> list[Holding]:
    """Fiyat biliniyorsa birimi kilitle (bir kez)."""
    locked: list[Holding] = []
    for h in holdings:
        if h.units is not None and h.units > 0:
            locked.append(h)
            continue
        if h.code == "CASH" or h.kind == "nakit":
            locked.append(
                Holding(
                    h.code, h.name, "nakit", h.value_tl, h.pnl_pct,
                    h.manager, h.valor, h.cost_usd, h.value_usd, units=h.value_tl,
                )
            )
            continue
        mark = marks.get(h.code.upper())
        live_p = getattr(mark, "live_price", None) or getattr(mark, "book_price", None)
        if not live_p or live_p <= 0:
            locked.append(h)
            continue
        if h.kind == "abd_hisse":
            # value_usd toplam USD ise adet = usd / fiyat
            if h.value_usd and h.value_usd > 0:
                units = float(h.value_usd) / float(live_p)
            else:
                units = float(h.value_tl) / (float(live_p) * fx)
        else:
            # Fon / emtia: TL değer / TEFAS fiyat
            book_p = getattr(mark, "book_price", None) or live_p
            units = float(h.value_tl) / float(book_p)
        locked.append(
            Holding(
                h.code, h.name, h.kind, h.value_tl, h.pnl_pct,
                h.manager, h.valor, h.cost_usd, h.value_usd, units=units,
            )
        )
    return locked


def persist_holdings(
    holdings: list[Holding],
    *,
    as_of: str | None = None,
    usdtry: float | None = None,
    note: str = "Birim kilitli — fiyat canlı",
) -> Path:
    data = load_raw()
    data["as_of"] = as_of or date.today().isoformat()
    if usdtry is not None:
        data["usdtry"] = usdtry
    data["source"] = "tefas_yfinance"
    data["note"] = note
    data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    data["holdings"] = [
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
            "units": h.units,
        }
        for h in holdings
    ]
    return save_raw(data)


def holdings_to_editor_frame(holdings: list[Holding] | None = None):
    import pandas as pd

    rows = holdings or active_holdings()
    return pd.DataFrame(
        [
            {
                "code": h.code,
                "name": h.name,
                "kind": h.kind,
                "units": h.units,
                "value_tl": h.value_tl,
                "pnl_pct": h.pnl_pct,
                "manager": h.manager,
                "valor": h.valor,
                "value_usd": h.value_usd,
                "cost_usd": h.cost_usd,
            }
            for h in rows
        ]
    )


def editor_frame_to_holdings(df) -> list[Holding]:
    out: list[Holding] = []
    for _, row in df.iterrows():
        code = str(row.get("code") or "").strip().upper()
        if not code:
            continue

        def _num(key: str) -> float | None:
            v = row.get(key)
            if v is None or (isinstance(v, float) and v != v):
                return None
            return float(v)

        units = _num("units")
        value_tl = _num("value_tl") or 0.0
        out.append(
            Holding(
                code=code,
                name=str(row.get("name") or code),
                kind=str(row.get("kind") or "serbest"),
                value_tl=value_tl,
                pnl_pct=_num("pnl_pct"),
                manager=str(row.get("manager") or ""),
                valor=str(row.get("valor") or "T+1"),
                value_usd=_num("value_usd"),
                cost_usd=_num("cost_usd"),
                units=units,
            )
        )
    return out


# Geriye uyum alias
DEFAULT_HOLDINGS = [_row_to_holding(r) for r in SEED]
save_book = persist_holdings  # type: ignore[assignment]
