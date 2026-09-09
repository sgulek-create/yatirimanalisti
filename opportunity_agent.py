"""Fırsat ajanı — kitap dışı 1–3 aday. Yatırımcı kartı, doktor değil.

Manifesto kilitli:
- İkinci TLY / yeni serbest fon avı YOK
- Tek isim ve Tera tavanı RULES'tan
- Human-in-the-loop: sadece karar kartı
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

try:
    from utils.portfolio import EXCLUDE_FROM_PP, RULES, TARGET_BUCKETS, tera_weight
    from utils.pp_scan import build_pp_orders
except ImportError:
    from portfolio import EXCLUDE_FROM_PP, RULES, TARGET_BUCKETS, tera_weight
    from pp_scan import build_pp_orders


@dataclass
class Opportunity:
    action: str  # AL | GEÇ | BEKLE | KÜÇÜLT
    code: str
    from_code: str | None
    thesis: str
    max_tl: float
    exit_rule: str
    confidence: float
    lane: str  # pp | park | tema | risk | rejim


def _tl(amount: float) -> str:
    return f"₺{abs(amount):,.0f}".replace(",", ".")


def _held_codes(book: pd.DataFrame) -> set[str]:
    return {str(c).upper() for c in book["code"].tolist()}


def _value(book: pd.DataFrame, code: str) -> float:
    rows = book.loc[book["code"] == code, "value_tl"]
    return float(rows.iloc[0]) if len(rows) else 0.0


def _weight(book: pd.DataFrame, code: str) -> float:
    rows = book.loc[book["code"] == code, "weight"]
    return float(rows.iloc[0]) if len(rows) else 0.0


def generate_opportunities(
    book: pd.DataFrame,
    pp_table: pd.DataFrame,
    *,
    total_tl: float | None = None,
    mstr_vol_pct: float | None = None,
    max_cards: int = 3,
) -> list[Opportunity]:
    """En fazla 3 fırsat kartı. Öncelik: risk → PP geç → park adayı → bekle."""
    total = float(total_tl if total_tl is not None else book["value_tl"].sum())
    held = _held_codes(book)
    cards: list[Opportunity] = []

    # --- 1) Risk / rejim (mevcut tema — yeni av değil) ---
    mstr_w = _weight(book, "MSTR")
    if mstr_vol_pct is not None and mstr_vol_pct > RULES["mstr_vol_annual_pct"] and mstr_w > 0.03:
        cut = _value(book, "MSTR") * 0.25
        cards.append(
            Opportunity(
                action="KÜÇÜLT",
                code="MSTR",
                from_code=None,
                thesis=(
                    f"MSTR yıllık oynaklık %{mstr_vol_pct:.0f} > eşik "
                    f"%{RULES['mstr_vol_annual_pct']:.0f}. Tema bozulmadı; boyut küçült."
                ),
                max_tl=round(cut, 2),
                exit_rule="Vol eşik altına inince yeniden boyuta bak; üstüne ekleme.",
                confidence=0.78,
                lane="risk",
            )
        )

    tera = tera_weight(book)
    if tera > RULES["tera_max_weight"]:
        # Parkı Tera dışına — fırsat = dış PP
        spare = (tera - 0.65) * total
        cards.append(
            Opportunity(
                action="KÜÇÜLT",
                code="Tera",
                from_code="TLY/TP2/TLV",
                thesis=(
                    f"Tera yoğunluğu %{tera*100:.0f} > %{RULES['tera_max_weight']*100:.0f}. "
                    "Yeni serbest avı yok; parkı Tera dışı PP'ye kaydır."
                ),
                max_tl=round(max(spare, 0), 2),
                exit_rule="Tera ≤ %65 olunca dur; ikinci TLY alma.",
                confidence=0.82,
                lane="rejim",
            )
        )

    # --- 2) PP geçiş / kitap dışı park adayı ---
    tp2_v = _value(book, "TP2")
    tlv_v = _value(book, "TLV")
    if not pp_table.empty:
        pp_orders, meta = build_pp_orders(pp_table, tp2_v, tlv_v)
        for od in pp_orders:
            if od.action != "GEÇ" or not od.to_code:
                continue
            if od.to_code.upper() in held and od.to_code.upper() in {"TP2", "TLV"}:
                continue
            cards.append(
                Opportunity(
                    action="GEÇ",
                    code=str(od.to_code).upper(),
                    from_code=od.from_code,
                    thesis=od.reason,
                    max_tl=float(od.amount_tl or 0),
                    exit_rule=(
                        "1A farkı eşiğin altına inerse geri dönme; "
                        "3A bozulursa parkı yeniden seç."
                    ),
                    confidence=float(od.confidence),
                    lane="pp",
                )
            )

                # Kitapta olmayan en iyi konvansiyonel PP — nakit/park için AL adayı
        top_conv = meta.get("top_conventional")
        if top_conv is not None and not getattr(top_conv, "empty", True):
            best = top_conv.iloc[0]
            code = str(best["fund_code"]).upper()
            already_gec = any(
                c.code == code and c.action == "GEÇ" for c in cards
            )
            if (
                code not in held
                and code not in EXCLUDE_FROM_PP
                and not already_gec
            ):
                # Max boyut: PP kova üstü - mevcut pp
                pp_now = float(
                    book.loc[book["kind"].isin(["pp", "katilim_pp"]), "weight"].sum()
                )
                room = max(0.0, TARGET_BUCKETS["pp"][1] - pp_now)
                max_tl = round(room * total, 2)
                # Küçük oda olsa bile fırsat olarak göster (bilgi)
                r1 = best.get("return_1m")
                r3 = best.get("return_3m")
                cards.append(
                    Opportunity(
                        action="AL" if max_tl >= 1000 else "BEKLE",
                        code=code,
                        from_code=None,
                        thesis=(
                            f"Tera dışı PP lideri {code}: 1A %{float(r1 or 0):.2f}, "
                            f"3A %{float(r3 or 0):.2f}. "
                            "Yeni serbest/TLY değil — park silahı."
                        ),
                        max_tl=max_tl if max_tl >= 1000 else 0.0,
                        exit_rule=(
                            f"1A, eldeki TP2'den {RULES['pp_switch_1m_pp']:.2f}pp "
                            "geri kalırsa çık / geç."
                        ),
                        confidence=0.68 if max_tl >= 1000 else 0.55,
                        lane="park",
                    )
                )

        top_kat = meta.get("top_katilim")
        if top_kat is not None and not getattr(top_kat, "empty", True):
            bestk = top_kat.iloc[0]
            codek = str(bestk["fund_code"]).upper()
            already = any(c.code == codek for c in cards)
            if codek not in held and not already and codek not in EXCLUDE_FROM_PP:
                cards.append(
                    Opportunity(
                        action="BEKLE",
                        code=codek,
                        from_code=None,
                        thesis=(
                            f"Katılım PP izleme listesi: {codek} "
                            f"(1A %{float(bestk.get('return_1m') or 0):.2f}). "
                            "TLV geçiş eşiği yoksa alma; ligi izle."
                        ),
                        max_tl=0.0,
                        exit_rule="TLV→aday GEÇ sinyali gelince harekete geç.",
                        confidence=0.58,
                        lane="park",
                    )
                )

    # --- 3) Dolgu: BEKLE kartı ---
    # Öncelik sırala
    lane_pri = {"risk": 0, "rejim": 1, "pp": 2, "park": 3, "tema": 4}
    action_pri = {"KÜÇÜLT": 0, "GEÇ": 1, "AL": 2, "BEKLE": 3}
    cards.sort(key=lambda c: (lane_pri.get(c.lane, 9), action_pri.get(c.action, 9), -c.confidence))

    # Tekrarlayan kodları budama
    seen: set[str] = set()
    uniq: list[Opportunity] = []
    for c in cards:
        key = f"{c.action}:{c.code}:{c.from_code}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)

    out = uniq[:max_cards]
    if not out:
        out = [
            Opportunity(
                action="BEKLE",
                code="—",
                from_code=None,
                thesis=(
                    "Eşik aşılmadı. Bugün av yok: ikinci TLY yasak, "
                    "PP farkı yetersiz, risk alarmı yok."
                ),
                max_tl=0.0,
                exit_rule="Yarın aynı tarama; sabah kartına bak.",
                confidence=0.70,
                lane="rejim",
            )
        ]
    return out


def format_opportunity_cards(cards: list[Opportunity], *, as_of: date | None = None) -> str:
    day = (as_of or date.today()).strftime("%d.%m.%Y")
    lines = [
        f"FIRSAT AJANI — {day}",
        "=" * 48,
        "Manifesto: ikinci TLY yok · park PP · onay sende",
        "",
    ]
    for i, c in enumerate(cards, 1):
        route = f"{c.from_code} → {c.code}" if c.from_code else c.code
        lines.extend(
            [
                f"{i}. [{c.action}] {route}  ({c.lane})",
                f"   Tez: {c.thesis}",
                f"   Max boyut: {_tl(c.max_tl)}" if c.max_tl else "   Max boyut: — (şimdilik izle)",
                f"   Çıkış: {c.exit_rule}",
                f"   Güven: %{c.confidence*100:.0f}",
                "",
            ]
        )
    lines.append("İcra yok — kartı oku, Midas'ta sen uygula.")
    return "\n".join(lines)


def opportunities_frame(cards: list[Opportunity]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Emir": c.action,
                "Kod": c.code,
                "Kaynak": c.from_code or "—",
                "Lig": c.lane,
                "Max ₺": c.max_tl,
                "Güven": round(c.confidence * 100),
                "Tez": c.thesis,
                "Çıkış": c.exit_rule,
            }
            for c in cards
        ]
    )
