"""Para piyasası / katılım PP fırsat taraması — emir üretir."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from utils.portfolio import (
    CONVENTIONAL_PP,
    EXCLUDE_FROM_PP,
    KATILIM_PP,
    PP_UNIVERSE,
    RULES,
)
from utils.tefas import fetch_fund_snapshot


@dataclass
class PPOrder:
    action: str  # TUT | GEÇ
    from_code: str
    to_code: str | None
    amount_tl: float
    confidence: float
    reason: str


def _is_pp_category(category: str | None) -> bool:
    if not category:
        return False
    c = category.casefold()
    keys = ("para piyasası", "para piyasa", "katılım para", "kısa vadeli")
    return any(k in c for k in keys)


def load_pp_table(extra_codes: list[str] | None = None) -> pd.DataFrame:
    """TEFAS dönem getirilerinden PP/katılım PP evreni."""
    snap = fetch_fund_snapshot(("YAT",))
    if snap.empty:
        return snap

    codes = {c.upper() for c in PP_UNIVERSE}
    if extra_codes:
        codes |= {c.upper() for c in extra_codes}

    # Evren kodları + kategori filtresi
    by_code = snap[snap["fund_code"].isin(codes)].copy()
    by_cat = snap[snap["category"].map(_is_pp_category)].copy()
    table = pd.concat([by_code, by_cat], ignore_index=True)
    table = table.drop_duplicates(subset=["fund_code"], keep="first")
    table = table[~table["fund_code"].isin(EXCLUDE_FROM_PP)]

    for col in ("return_1m", "return_3m", "return_6m", "return_1y", "return_ytd"):
        if col in table.columns:
            table[col] = pd.to_numeric(table[col], errors="coerce")

    table["daily_approx"] = table["return_1m"] / 21.0  # iş günü yaklaşık (% puan)
    name = table["fund_name"].fillna("")
    cat = table["category"].fillna("")
    table["is_katilim"] = (
        table["fund_code"].isin(KATILIM_PP)
        | name.str.casefold().str.contains("katılım")
        | cat.str.casefold().str.contains("katılım")
    )
    # PRY/PNU açıkça konvansiyonel kabul (kör TLV geçişini kes)
    table.loc[table["fund_code"].isin(CONVENTIONAL_PP), "is_katilim"] = False
    table.loc[table["fund_code"].isin(KATILIM_PP), "is_katilim"] = True
    table["manager"] = name.str.split().str[0]
    return table.sort_values("return_1m", ascending=False).reset_index(drop=True)


def bp_gap(a: float | None, b: float | None) -> float | None:
    """1A getiri farkı baz puan (yüzde puan * 100)."""
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return None
    return (float(a) - float(b)) * 100.0


def best_outside_tera(
    table: pd.DataFrame,
    katilim: bool,
    tera_codes: set[str] | None = None,
    n: int = 3,
) -> pd.DataFrame:
    tera_codes = tera_codes or {"TLY", "TP2", "TLV"}
    pool = table[~table["fund_code"].isin(tera_codes)].copy()
    if katilim:
        pool = pool[pool["is_katilim"]]
    else:
        # Konvansiyonel: katılım olmayan PP
        pool = pool[~pool["is_katilim"]]
    return pool.sort_values("return_1m", ascending=False).head(n)


def decide_pp_switch(
    held_code: str,
    held_1m: float | None,
    held_3m: float | None,
    candidate: pd.Series,
) -> PPOrder | None:
    """1A +0.25 puan VE 3A teyidi yoksa TUT."""
    thr = RULES["pp_switch_1m_pp"]
    c1 = candidate.get("return_1m")
    c3 = candidate.get("return_3m")
    if held_1m is None or c1 is None or pd.isna(c1):
        return PPOrder("TUT", held_code, None, 0.0, 0.55, "Rakip 1A eksik — TUT")

    gap_pp = float(c1) - float(held_1m)
    if gap_pp < thr:
        return PPOrder(
            "TUT",
            held_code,
            None,
            0.0,
            0.70,
            f"{candidate['fund_code']} 1A sadece +{gap_pp:.2f}pp "
            f"(eşik {thr:.2f}pp) — TUT",
        )

    if RULES["pp_switch_need_3m"]:
        if held_3m is None or c3 is None or pd.isna(c3) or pd.isna(held_3m):
            return PPOrder(
                "TUT",
                held_code,
                None,
                0.0,
                0.60,
                f"{candidate['fund_code']} 1A önde ama 3A teyidi yok — TUT",
            )
        if float(c3) <= float(held_3m):
            return PPOrder(
                "TUT",
                held_code,
                None,
                0.0,
                0.72,
                f"{candidate['fund_code']} 1A +{gap_pp:.2f}pp ama 3A geride — TUT",
            )

    return PPOrder(
        "GEÇ",
        held_code,
        str(candidate["fund_code"]),
        0.0,  # tutar çağıran doldurur
        0.75,
        f"1A +{gap_pp:.2f}pp ve 3A teyit — {held_code}→{candidate['fund_code']}",
    )


def build_pp_orders(
    table: pd.DataFrame,
    tp2_value: float,
    tlv_value: float,
) -> tuple[list[PPOrder], dict]:
    """TP2/TLV için emir + Tera dışı top3."""
    by = table.set_index("fund_code") if not table.empty else pd.DataFrame()

    def row(code: str) -> dict:
        if code not in by.index:
            return {}
        r = by.loc[code]
        if isinstance(r, pd.DataFrame):
            r = r.iloc[0]
        return r.to_dict()

    tp2 = row("TP2")
    tlv = row("TLV")

    # Tera dışı en iyi 3 — ayrı ligler
    top_conv = best_outside_tera(table, katilim=False)
    top_kat = best_outside_tera(table, katilim=True)

    orders: list[PPOrder] = []

    # TP2 → konvansiyonel rakip
    if not top_conv.empty and tp2:
        cand = top_conv.iloc[0]
        od = decide_pp_switch(
            "TP2",
            tp2.get("return_1m"),
            tp2.get("return_3m"),
            cand,
        )
        if od and od.action == "GEÇ":
            od.amount_tl = round(tp2_value * 0.40, 2)  # parkın %40'ını kaydır
        if od:
            orders.append(od)
    else:
        orders.append(PPOrder("TUT", "TP2", None, 0.0, 0.50, "TP2 veya rakip veri yok — TUT"))

    # TLV → sadece katılım PP
    if not top_kat.empty and tlv:
        # PRY/PNU kör geçişi engelle: aynı lig + kural
        cand = top_kat.iloc[0]
        od = decide_pp_switch(
            "TLV",
            tlv.get("return_1m"),
            tlv.get("return_3m"),
            cand,
        )
        if od and od.action == "GEÇ":
            od.amount_tl = round(tlv_value * 0.35, 2)
        if od:
            orders.append(od)
    else:
        orders.append(PPOrder("TUT", "TLV", None, 0.0, 0.50, "TLV veya katılım rakip yok — TUT"))

    meta = {
        "tp2_1m": tp2.get("return_1m"),
        "tlv_1m": tlv.get("return_1m"),
        "tp2_daily": (tp2.get("return_1m") / 21) if tp2.get("return_1m") is not None else None,
        "tlv_daily": (tlv.get("return_1m") / 21) if tlv.get("return_1m") is not None else None,
        "top_conventional": top_conv,
        "top_katilim": top_kat,
        "bp_tp2_vs_best": (
            bp_gap(top_conv.iloc[0]["return_1m"], tp2.get("return_1m"))
            if not top_conv.empty and tp2
            else None
        ),
        "bp_tlv_vs_best": (
            bp_gap(top_kat.iloc[0]["return_1m"], tlv.get("return_1m"))
            if not top_kat.empty and tlv
            else None
        ),
    }
    return orders, meta


def format_pp_emri(orders: list[PPOrder], meta: dict) -> str:
    lines = ["PP EMRİ:"]
    for od in orders:
        conf = f"%{od.confidence*100:.0f}"
        if od.action == "GEÇ" and od.to_code:
            lines.append(
                f"- {od.action} {od.from_code} → {od.to_code} "
                f"| ₺{od.amount_tl:,.0f} | {conf} | {od.reason}"
            )
        else:
            lines.append(f"- {od.action} {od.from_code} | {conf} | {od.reason}")

    if meta.get("bp_tp2_vs_best") is not None:
        lines.append(
            f"- TP2 vs Tera-dışı en iyi: {meta['bp_tp2_vs_best']:+.0f} bp (1A)"
        )
    if meta.get("bp_tlv_vs_best") is not None:
        lines.append(
            f"- TLV vs Tera-dışı katılım en iyi: {meta['bp_tlv_vs_best']:+.0f} bp (1A)"
        )
    lines.append(
        "- Not: faiz düşüşünde tüm PP ezilir; yıllık kilit getiri iddiası yok."
    )
    return "\n".join(lines)
