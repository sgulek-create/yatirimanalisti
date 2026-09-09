"""Aday karşılaştırma masası — fon/hisse yan yana skor kartı."""

from __future__ import annotations

from typing import Any

import pandas as pd

try:
    from utils.portfolio import EXCLUDE_FROM_PP, RULES, TARGET_BUCKETS
    from utils.pp_scan import best_outside_tera, build_pp_orders
except ImportError:
    from portfolio import EXCLUDE_FROM_PP, RULES, TARGET_BUCKETS
    from pp_scan import best_outside_tera, build_pp_orders


def _held_map(book: pd.DataFrame) -> dict[str, float]:
    return {
        str(code).upper(): float(w)
        for code, w in zip(book["code"], book["weight"], strict=False)
    }


def _suggest_pp(
    code: str,
    *,
    held: dict[str, float],
    switch_to: set[str],
    room_tl: float,
) -> tuple[str, float, str]:
    c = code.upper()
    if c in EXCLUDE_FROM_PP or c == "TLY":
        return "GEÇ", 0.0, "Manifesto: ikinci TLY / serbest avı yok"
    if c in switch_to:
        return "GEÇ", room_tl, "PP geçiş sinyali — TP2/TLV’den kaydır"
    if c in held:
        return "TUT", 0.0, f"Kitapta · ağırlık %{held[c]*100:.1f}"
    if room_tl >= 1000:
        return "AL", room_tl, "Tera dışı park adayı · max PP odası"
    return "BEKLE", 0.0, "PP odası dar veya eşik yok"


def compare_pp_candidates(
    book: pd.DataFrame,
    pp_table: pd.DataFrame,
    *,
    total_tl: float,
    top_n: int = 8,
) -> pd.DataFrame:
    """Konvansiyonel + katılım PP liderlerini yan yana tabloya dök."""
    if pp_table.empty:
        return pd.DataFrame()

    held = _held_map(book)
    tp2_v = float(book.loc[book["code"] == "TP2", "value_tl"].sum())
    tlv_v = float(book.loc[book["code"] == "TLV", "value_tl"].sum())
    orders, _meta = build_pp_orders(pp_table, tp2_v, tlv_v)
    switch_to = {str(o.to_code).upper() for o in orders if o.action == "GEÇ" and o.to_code}

    pp_w = float(book.loc[book["kind"].isin(["pp", "katilim_pp"]), "weight"].sum())
    room = max(0.0, TARGET_BUCKETS["pp"][1] - pp_w) * float(total_tl)

    conv = best_outside_tera(pp_table, katilim=False, n=top_n)
    kat = best_outside_tera(pp_table, katilim=True, n=max(3, top_n // 2))
    held_codes = set(held)
    book_pp = pp_table[pp_table["fund_code"].isin(held_codes)].copy()

    frames = [f for f in (conv, kat, book_pp) if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    uni = pd.concat(frames, ignore_index=True).drop_duplicates("fund_code")

    rows: list[dict[str, Any]] = []
    for _, r in uni.iterrows():
        code = str(r["fund_code"]).upper()
        action, max_tl, note = _suggest_pp(
            code, held=held, switch_to=switch_to, room_tl=room
        )
        rows.append(
            {
                "Kod": code,
                "Lig": "Katılım" if bool(r.get("is_katilim")) else "Konvansiyonel",
                "Kitapta": "Evet" if code in held else "Hayır",
                "Ağırlık %": round(held.get(code, 0.0) * 100, 2),
                "1A %": round(float(r["return_1m"]), 2) if pd.notna(r.get("return_1m")) else None,
                "3A %": round(float(r["return_3m"]), 2) if pd.notna(r.get("return_3m")) else None,
                "6A %": round(float(r["return_6m"]), 2) if pd.notna(r.get("return_6m")) else None,
                "Günlük ≈%": round(float(r["daily_pct"]), 3)
                if pd.notna(r.get("daily_pct"))
                else None,
                "Öneri": action,
                "Max ₺": round(max_tl, 0),
                "Not": note,
            }
        )

    out = pd.DataFrame(rows)
    order = {"GEÇ": 0, "AL": 1, "TUT": 2, "BEKLE": 3, "KÜÇÜLT": 0}
    out["_ord"] = out["Öneri"].map(lambda x: order.get(x, 9))
    out = out.sort_values(["_ord", "1A %"], ascending=[True, False]).drop(columns="_ord")
    return out.reset_index(drop=True)


def compare_us_names(
    book: pd.DataFrame,
    *,
    mstr_vol_pct: float | None,
    nvda_mstr_corr: float | None,
) -> pd.DataFrame:
    """Kitaptaki ABD isimleri + manifesto risk satırları."""
    held = _held_map(book)
    rows = []
    for code in ("NVDA", "MSTR"):
        w = held.get(code, 0.0)
        if code == "MSTR" and mstr_vol_pct is not None and mstr_vol_pct > RULES["mstr_vol_annual_pct"]:
            oneri, note = "KÜÇÜLT", f"Vol %{mstr_vol_pct:.0f} > eşik %{RULES['mstr_vol_annual_pct']:.0f}"
        elif code == "MSTR" and nvda_mstr_corr is not None and nvda_mstr_corr > RULES["nvda_mstr_corr"]:
            oneri, note = "BEKLE", f"NVDA-MSTR corr {nvda_mstr_corr:.2f} yüksek — boyut ekleme"
        elif w > 0:
            oneri, note = "TUT", "Eşik içinde; üstüne ekleme yok (parkçı)"
        else:
            oneri, note = "GEÇ", "Kitapta yok — kör tema avı yok"
        rows.append(
            {
                "Kod": code,
                "Lig": "ABD hisse",
                "Kitapta": "Evet" if w > 0 else "Hayır",
                "Ağırlık %": round(w * 100, 2),
                "Vol %": round(mstr_vol_pct, 0) if code == "MSTR" and mstr_vol_pct else None,
                "Corr NVDA-MSTR": round(nvda_mstr_corr, 2) if nvda_mstr_corr is not None else None,
                "Öneri": oneri,
                "Max ₺": 0.0,
                "Not": note,
            }
        )
    return pd.DataFrame(rows)


def solution_map_frame() -> pd.DataFrame:
    """Referans: SaaS listesine karşı senin masanın kapsamı (eğitim/benchmark)."""
    return pd.DataFrame(
        [
            {
                "Çözüm": "yanaliz (bu app)",
                "Dağıtım": "Yerel / Streamlit Cloud",
                "Ücretsiz": "Evet",
                "Odak": "Kitap doktoru + PP fırsat + karar kartı",
                "Senin için": "Ana motor",
            },
            {
                "Çözüm": "OpenBB tarzı terminal (bu sekme)",
                "Dağıtım": "Yerel",
                "Ücretsiz": "Evet",
                "Odak": "Piyasa / PP ligi / quote",
                "Senin için": "Veri tezgâhı",
            },
            {
                "Çözüm": "Sohbet katmanı (bu sekme)",
                "Dağıtım": "Yerel (+ opsiyonel Gemini)",
                "Ücretsiz": "Evet",
                "Odak": "Manifesto + kitap soruları",
                "Senin için": "Açıklama / eğitim",
            },
            {
                "Çözüm": "AlphaSense / PitchBook",
                "Dağıtım": "Kurumsal bulut",
                "Ücretsiz": "Hayır",
                "Odak": "Transcript / VC / muhasebe",
                "Senin için": "Kapsam dışı",
            },
            {
                "Çözüm": "TradingView",
                "Dağıtım": "Bulut",
                "Ücretsiz": "Kısmi",
                "Odak": "Grafik",
                "Senin için": "İstersen dışarıdan bak",
            },
        ]
    )
