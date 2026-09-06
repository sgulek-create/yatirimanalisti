"""Pozisyon emirleri — AL / TUT / AZALT / SAT + hedef ağırlık."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from utils.portfolio import RULES, tera_weight


@dataclass
class PositionOrder:
    code: str
    action: str
    target_weight: float
    size_tl: float  # işlem büyüklüğü (+al / -sat)
    confidence: float
    reason: str


def decide_positions(
    book: pd.DataFrame,
    total_tl: float,
    mstr_vol_pct: float | None,
    nvda_mstr_corr: float | None,
    preferred_pp: str | None = None,
) -> list[PositionOrder]:
    """Kullanıcı kuralları + risk sayıları → emir tablosu."""
    w = book.set_index("code")["weight"].to_dict()
    v = book.set_index("code")["value_tl"].to_dict()
    pnl = book.set_index("code")["pnl_pct"].to_dict()
    orders: list[PositionOrder] = []

    tera = tera_weight(book)
    park_dest = preferred_pp or "Tera-dışı PP"

    # --- TLY ---
    tly_w = w.get("TLY", 0)
    if tly_w > RULES["tly_max_weight"]:
        excess = (tly_w - 0.40) * total_tl  # hedef %40
        orders.append(
            PositionOrder(
                "TLY",
                "AZALT",
                0.40,
                -round(excess, 2),
                0.85,
                f"TLY %{tly_w*100:.1f} > %45 tavan — fazla {park_dest}'ye",
            )
        )
    else:
        orders.append(
            PositionOrder(
                "TLY",
                "TUT",
                tly_w,
                0.0,
                0.70,
                f"TLY %{tly_w*100:.1f} tavan altında — senin serbest motorun; TUT",
            )
        )

    # --- Tera toplam ---
    tera_pressure = tera > RULES["tera_max_weight"]

    # --- TLV ---
    tlv_w = w.get("TLV", 0)
    if tera_pressure:
        cut = min(v.get("TLV", 0) * 0.25, total_tl * 0.05)
        orders.append(
            PositionOrder(
                "TLV",
                "AZALT",
                max(0.10, tlv_w * 0.75),
                -round(cut, 2),
                0.78,
                f"Tera toplam %{tera*100:.0f} > %70 — katılım parkı Tera dışına kaydır",
            )
        )
    else:
        orders.append(
            PositionOrder(
                "TLV",
                "TUT",
                tlv_w,
                0.0,
                0.65,
                "Katılım PP tamponu — TUT (kör PRY/PNU geçişi yok)",
            )
        )

    # --- TP2 ---
    tp2_w = w.get("TP2", 0)
    if tera_pressure:
        cut = min(v.get("TP2", 0) * 0.30, total_tl * 0.05)
        orders.append(
            PositionOrder(
                "TP2",
                "AZALT",
                max(0.08, tp2_w * 0.70),
                -round(cut, 2),
                0.80,
                f"Tera yoğunluğu — PP parkını Tera dışına dağıt ({park_dest})",
            )
        )
    else:
        orders.append(
            PositionOrder(
                "TP2",
                "TUT",
                tp2_w,
                0.0,
                0.62,
                "Konvansiyonel PP parkı — TUT; geçiş için 1A+3A kuralına bak",
            )
        )

    # --- GMC ---
    gmc_w = w.get("GMC", 0)
    orders.append(
        PositionOrder(
            "GMC",
            "TUT",
            max(gmc_w, 0.04),
            0.0,
            0.60,
            "Gümüş hedge (SLV vekil) — küçük tutulur; üzerine yığma",
        )
    )

    # --- BOS ---
    bos_pnl = pnl.get("BOS")
    bos_w = w.get("BOS", 0)
    bos_v = v.get("BOS", 0)
    if bos_pnl is not None and bos_pnl < -15:
        orders.append(
            PositionOrder(
                "BOS",
                "SAT",
                0.0,
                -round(bos_v, 2),
                0.82,
                f"BOS %{bos_pnl:.1f} zararda; TLY kopyası değil — ortalama düşürme, SAT",
            )
        )
    else:
        orders.append(
            PositionOrder(
                "BOS",
                "TUT",
                min(bos_w, 0.01),
                0.0,
                0.55,
                "BOS küçük — TUT-küçük; ekleme yok",
            )
        )

    # --- NVDA ---
    nvda_w = w.get("NVDA", 0)
    nvda_pnl = pnl.get("NVDA")
    nvda_v = v.get("NVDA", 0)
    if nvda_pnl is not None and nvda_pnl > 20:
        trim = nvda_v * 0.20
        orders.append(
            PositionOrder(
                "NVDA",
                "AZALT",
                nvda_w * 0.80,
                -round(trim, 2),
                0.68,
                f"NVDA +%{nvda_pnl:.0f} kârda — %20 kısmi realize; AVGO/AMD yığma",
            )
        )
    else:
        orders.append(
            PositionOrder(
                "NVDA",
                "TUT",
                nvda_w,
                0.0,
                0.65,
                "NVDA çekirdek ABD büyüme — TUT",
            )
        )

    # --- MSTR ---
    mstr_w = w.get("MSTR", 0)
    mstr_v = v.get("MSTR", 0)
    mstr_reasons = []
    action = "TUT"
    conf = 0.55
    target = mstr_w
    size = 0.0

    if mstr_vol_pct is not None and mstr_vol_pct > RULES["mstr_vol_annual_pct"]:
        action = "AZALT"
        target = mstr_w * 0.40
        size = -round(mstr_v * 0.60, 2)
        conf = 0.88
        mstr_reasons.append(f"60g yıllık vol %{mstr_vol_pct:.0f} > %100")

    if nvda_mstr_corr is not None and nvda_mstr_corr > RULES["nvda_mstr_corr"]:
        if action == "TUT":
            action = "AZALT"
            target = mstr_w * 0.50
            size = -round(mstr_v * 0.50, 2)
            conf = 0.80
        else:
            target = min(target, mstr_w * 0.35)
            size = -round(mstr_v * 0.65, 2)
            conf = max(conf, 0.90)
        mstr_reasons.append(f"NVDA–MSTR corr {nvda_mstr_corr:.2f} > 0.50 — aynı faktör")

    if not mstr_reasons:
        mstr_reasons.append("Vol/corr eşiği aşılmadı — TUT; BTC beta izle")

    # Zararda + yüksek vol → SAT'a yükselt
    mstr_pnl = pnl.get("MSTR")
    if (
        action == "AZALT"
        and mstr_pnl is not None
        and mstr_pnl < -20
        and mstr_vol_pct
        and mstr_vol_pct > 120
    ):
        action = "SAT"
        target = 0.0
        size = -round(mstr_v, 2)
        conf = 0.84
        mstr_reasons.append("Zarar + aşırı vol — SAT, nakdi PP'ye")

    if action != "TUT":
        mstr_reasons.append(f"nakit → {park_dest}")

    orders.append(
        PositionOrder(
            "MSTR",
            action,
            target,
            size,
            conf,
            "; ".join(mstr_reasons),
        )
    )

    return orders


def orders_to_frame(orders: list[PositionOrder]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Kod": o.code,
                "Emir": o.action,
                "Hedef ağırlık": o.target_weight,
                "İşlem ₺": o.size_tl,
                "Güven": o.confidence,
                "Gerekçe": o.reason,
            }
            for o in orders
        ]
    )
