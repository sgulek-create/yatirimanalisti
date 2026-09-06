"""Sabah brifingi — Rejim / Kitap / Emir. Gürültüsüz, kitaba kilitli."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

try:
    from utils.portfolio import RULES
except ImportError:
    from portfolio import RULES


def build_clean_briefing(
    book: pd.DataFrame,
    risk_snapshot: Any,
    pp_orders: list,
    position_orders: list | None = None,
    as_of: date | None = None,
) -> dict[str, str]:
    """
    Üç satır:
    Rejim · Kitap · Emir (veya YOK / DOKUNMA)
    Yeni TLY avlamaz; yalnız eldeki kurallar.
    """
    day = as_of or date.today()
    position_orders = position_orders or []

    # --- Rejim ---
    mstr_vol = getattr(risk_snapshot, "mstr_vol_pct", None)
    corr = getattr(risk_snapshot, "nvda_mstr_corr", None)
    if mstr_vol is None:
        vol_bit = "MSTR vol: veri yok"
        regime = "Belirsiz"
    elif mstr_vol > RULES["mstr_vol_annual_pct"]:
        vol_bit = f"MSTR vol %{mstr_vol:.0f} (eşik üstü)"
        regime = "Sıkı / riskli"
    else:
        vol_bit = f"MSTR vol %{mstr_vol:.0f} (eşik altı)"
        regime = "Nötr"
    corr_bit = f" · NVDA–MSTR corr {corr:.2f}" if corr is not None else ""
    regime_line = f"Rejim: {regime} · {vol_bit}{corr_bit}"

    # --- Kitap ---
    total_val = float(book["value_tl"].sum())
    weights = book.set_index("code")["weight"].to_dict()
    tly_w = weights.get("TLY", 0) * 100
    tera_w = sum(weights.get(c, 0) for c in ("TLY", "TP2", "TLV")) * 100
    tly_cap = RULES["tly_max_weight"] * 100
    tera_cap = RULES["tera_max_weight"] * 100
    book_line = (
        f"Kitap: ₺{total_val:,.0f} · "
        f"TLY %{tly_w:.1f} (tavan %{tly_cap:.0f}) · "
        f"Tera %{tera_w:.0f} (tavan %{tera_cap:.0f})"
    )

    # --- Emir (öncelik: SAT > AZALT > PP GEÇ > YOK) ---
    emir_bits: list[str] = []

    for o in position_orders:
        action = getattr(o, "action", "")
        if action in {"SAT", "AZALT"}:
            code = getattr(o, "code", "?")
            size = getattr(o, "size_tl", 0) or 0
            reason = getattr(o, "reason", "")
            size_txt = f" ₺{size:,.0f}" if size else ""
            emir_bits.append(f"{action} {code}{size_txt} — {reason}")

    for o in pp_orders:
        action = getattr(o, "action", "")
        if action == "GEÇ":
            frm = getattr(o, "from_code", "?")
            to = getattr(o, "to_code", "?")
            amt = getattr(o, "amount_tl", 0) or 0
            reason = getattr(o, "reason", "")
            emir_bits.append(f"GEÇ {frm}→{to} ₺{amt:,.0f} — {reason}")

    if emir_bits:
        # En fazla 3 satır — sabah kartı kısa kalsın
        shown = emir_bits[:3]
        more = len(emir_bits) - len(shown)
        emir_line = "Emir: " + " | ".join(shown)
        if more > 0:
            emir_line += f" | (+{more} ayrıntı altta)"
    else:
        emir_line = "Emir: YOK — eşik aşılmadı. Bugün: DOKUNMA / TUT."

    headline = f"{day.strftime('%d.%m.%Y')} sabah brifingi"
    body = f"{regime_line}\n\n{book_line}\n\n{emir_line}"

    return {
        "headline": headline,
        "body": body,
        "has_orders": bool(emir_bits),
    }


# Eski tarayıcı uyumu (kullanılmıyorsa zararsız)
def build_briefing(*args, **kwargs) -> dict[str, object]:
    return {
        "headline": "Eski brifing devre dışı",
        "body": "Uzman sekmesindeki sabah kartını kullan.",
        "fund_hits": pd.DataFrame(),
        "stock_hits": pd.DataFrame(),
    }
