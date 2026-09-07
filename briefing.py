"""Sabah brifingi — Rejim / Kitap / Emir. Gürültüsüz, kitaba kilitli."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

try:
    from utils.portfolio import RULES
except ImportError:
    from portfolio import RULES


def _tl(amount: float) -> str:
    return f"₺{abs(amount):,.0f}".replace(",", ".")


def build_action_trio(
    book: pd.DataFrame,
    risk_snapshot: Any,
    pp_orders: list,
    position_orders: list | None = None,
    book_total: float | None = None,
) -> list[str]:
    """Uyuyan ajan çıktısı: en fazla 3 net aksiyon (veya dokunma)."""
    position_orders = position_orders or []
    actions: list[tuple[int, str]] = []  # priority, text

    for o in position_orders:
        action = getattr(o, "action", "")
        if action not in {"SAT", "AZALT"}:
            continue
        code = getattr(o, "code", "?")
        size = abs(getattr(o, "size_tl", 0) or 0)
        reason = getattr(o, "reason", "")
        pri = 10 if action == "SAT" else 20
        verb = "SAT" if action == "SAT" else "KÜÇÜLT"
        actions.append((pri, f"{verb} {code} · {_tl(size)} · {reason}"))

    for o in pp_orders:
        if getattr(o, "action", "") != "GEÇ":
            continue
        frm = getattr(o, "from_code", "?")
        to = getattr(o, "to_code", "?")
        amt = getattr(o, "amount_tl", 0) or 0
        reason = getattr(o, "reason", "")
        actions.append((30, f"GEÇ {frm} → {to} · {_tl(amt)} · {reason}"))

    mstr_vol = getattr(risk_snapshot, "mstr_vol_pct", None)
    if mstr_vol is not None and mstr_vol > RULES["mstr_vol_annual_pct"]:
        actions.append(
            (
                15,
                f"RİSK MSTR · yıllık oynaklık %{mstr_vol:.0f} > eşik "
                f"%{RULES['mstr_vol_annual_pct']:.0f} — küçült / realize et",
            )
        )

    total_now = float(book["value_tl"].sum())
    if book_total and book_total > 0:
        delta = (total_now / book_total - 1.0) * 100.0
        if abs(delta) >= 1.0:
            actions.append(
                (
                    40,
                    f"İŞARET · canlı kitap farkı %{delta:+.2f} "
                    f"({_tl(total_now)} vs {_tl(book_total)}) — Midas bakiyeyi doğrula",
                )
            )

    actions.sort(key=lambda x: x[0])
    lines = [t for _, t in actions[:3]]
    if not lines:
        lines = [
            "DOKUNMA · Eşik aşılmadı. Bugün yeni alım yok; TLY avı yasak.",
            "PARK · PP tamponunu koru; valör için nakdi önceden tut.",
            "İZLE · MSTR vol ve Tera yoğunluğu; alarm yoksa beklemeye devam.",
        ]
    return lines


def build_clean_briefing(
    book: pd.DataFrame,
    risk_snapshot: Any,
    pp_orders: list,
    position_orders: list | None = None,
    as_of: date | None = None,
) -> dict[str, str]:
    """Üç blok: Rejim · Kitap · Emir (veya dokunma)."""
    day = as_of or date.today()
    position_orders = position_orders or []

    mstr_vol = getattr(risk_snapshot, "mstr_vol_pct", None)
    corr = getattr(risk_snapshot, "nvda_mstr_corr", None)
    if mstr_vol is None:
        vol_bit = "MSTR oynaklığı ölçülemedi"
        regime = "Belirsiz"
    elif mstr_vol > RULES["mstr_vol_annual_pct"]:
        vol_bit = f"MSTR oynaklığı %{mstr_vol:.0f} — eşik üstünde"
        regime = "Sıkı / riskli"
    else:
        vol_bit = f"MSTR oynaklığı %{mstr_vol:.0f} — eşik altında"
        regime = "Nötr"
    corr_bit = (
        f". NVDA ile MSTR korelasyonu {corr:.2f}."
        if corr is not None
        else "."
    )
    regime_line = f"Rejim: {regime}. {vol_bit}{corr_bit}"

    total_val = float(book["value_tl"].sum())
    weights = book.set_index("code")["weight"].to_dict()
    tly_w = weights.get("TLY", 0) * 100
    tera_w = sum(weights.get(c, 0) for c in ("TLY", "TP2", "TLV")) * 100
    tly_cap = RULES["tly_max_weight"] * 100
    tera_cap = RULES["tera_max_weight"] * 100
    book_line = (
        f"Kitap: Toplam {_tl(total_val)}. "
        f"TLY payı %{tly_w:.1f} (tavan %{tly_cap:.0f}). "
        f"Tera yoğunluğu %{tera_w:.0f} (tavan %{tera_cap:.0f})."
    )

    emir_bits: list[str] = []
    for o in position_orders:
        action = getattr(o, "action", "")
        if action not in {"SAT", "AZALT"}:
            continue
        code = getattr(o, "code", "?")
        size = abs(getattr(o, "size_tl", 0) or 0)
        reason = getattr(o, "reason", "")
        verb = "Sat" if action == "SAT" else "Küçült"
        emir_bits.append(f"{verb} {code} ({_tl(size)}): {reason}")

    for o in pp_orders:
        if getattr(o, "action", "") != "GEÇ":
            continue
        frm = getattr(o, "from_code", "?")
        to = getattr(o, "to_code", "?")
        amt = getattr(o, "amount_tl", 0) or 0
        reason = getattr(o, "reason", "")
        emir_bits.append(f"Geç {frm} → {to} ({_tl(amt)}): {reason}")

    if emir_bits:
        shown = emir_bits[:3]
        more = len(emir_bits) - len(shown)
        emir_line = "Emir:\n- " + "\n- ".join(shown)
        if more > 0:
            emir_line += f"\n- (Ayrıca {more} kalem daha; ayrıntı aşağıda.)"
    else:
        emir_line = "Emir: Yok. Eşik aşılmadı — bugün dokunma, tut."

    return {
        "headline": f"{day.strftime('%d.%m.%Y')} sabah brifingi",
        "body": f"{regime_line}\n\n{book_line}\n\n{emir_line}",
        "has_orders": bool(emir_bits),
    }


def build_expert_note(
    book: pd.DataFrame,
    position_orders: list,
    pp_orders: list,
    preferred_pp: str | None = None,
) -> str:
    """Uzman önerisi — düzgün Türkçe, okunabilir metin."""
    weights = book.set_index("code")["weight"].to_dict()
    park = preferred_pp or "Tera dışı para piyasası"

    cash = 0.0
    lines_now: list[str] = []
    lines_hold: list[str] = []

    for o in position_orders:
        action = getattr(o, "action", "")
        code = getattr(o, "code", "")
        size = abs(getattr(o, "size_tl", 0) or 0)
        reason = getattr(o, "reason", "")
        if action == "SAT":
            cash += size
            lines_now.append(
                f"• {code} pozisyonunu tamamen kapat ({_tl(size)}). {reason}."
            )
        elif action == "AZALT":
            cash += size
            target = getattr(o, "target_weight", 0) * 100
            lines_now.append(
                f"• {code} küçült ({_tl(size)}); hedef ağırlık yaklaşık %{target:.0f}. "
                f"{reason}."
            )
        elif action == "TUT":
            lines_hold.append(f"• {code}: tut. {reason}.")

    trimmed = {
        getattr(o, "code", "")
        for o in position_orders
        if getattr(o, "action", "") in {"SAT", "AZALT"}
    }

    for o in pp_orders:
        action = getattr(o, "action", "")
        if action == "GEÇ":
            amt = getattr(o, "amount_tl", 0) or 0
            lines_now.append(
                f"• {o.from_code} fonundan {o.to_code} fonuna geç ({_tl(amt)}). "
                f"{o.reason}."
            )
        elif action == "TUT":
            code = getattr(o, "from_code", "")
            if code in trimmed:
                lines_hold.append(
                    f"• {code}: getiri için başka PP’ye geçme ({o.reason}). "
                    f"Küçültme varsa nedeni Tera yoğunluğunu dağıtmak."
                )
            else:
                lines_hold.append(
                    f"• {code} para piyasasında kal: {o.reason}."
                )

    park_block = ""
    if cash >= 1000:
        a, b, c = cash * 0.50, cash * 0.25, cash * 0.25
        park_block = (
            f"Serbest kalan yaklaşık {_tl(cash)} şöyle park edilir:\n"
            f"• Yarısı ({_tl(a)}) → {park} (veya aynı ligde en iyi Tera dışı PP)\n"
            f"• Çeyreği ({_tl(b)}) → ikinci yönetici (ör. BPZ / PRY)\n"
            f"• Çeyreği ({_tl(c)}) → en likit PP’de fırsat mermisi olarak beklet"
        )

    tly = weights.get("TLY", 0) * 100
    intro = (
        "Bugünkü yaklaşım: yeni fırsat avlamak değil, kitabı toparlamak. "
        "Önce sat / küçült, sonra parkı doldur; şimdilik yeni alım yok.\n"
    )
    now = "Bu hafta yapılacaklar:\n" + (
        "\n".join(lines_now) if lines_now else "• Acil işlem yok."
    )
    hold = "Dokunulmayanlar:\n" + (
        "\n".join(lines_hold) if lines_hold else "• —"
    )
    later = (
        "Sonrası:\n"
        "• Üç ay boyunca yeni serbest fon arama.\n"
        f"• TLY’yi yaşat; tavanı (yaklaşık %45) aşırma (şu an %{tly:.1f}).\n"
        "• Yeniden alım ancak park doluyken ve gerçek bir düzeltmede; "
        "bildiğin temaya dön, yabancı ‘yeni TLY’ arama."
    )
    avoid = (
        "Yapılmayacaklar:\n"
        "• BOS’a ortalama düşürme\n"
        "• NVDA üstüne yeni hisse yığma\n"
        "• Tera’yı bu yoğunlukta bırakma\n"
        "• ‘Bu yıl birkaç kat’ diye pozisyon şişirme"
    )

    parts = [intro, now, "", hold]
    if park_block:
        parts.extend(["", park_block])
    parts.extend(["", later, "", avoid])
    return "\n".join(parts)


def build_briefing(*args, **kwargs) -> dict[str, object]:
    return {
        "headline": "Eski brifing devre dışı",
        "body": "Uzman sekmesindeki sabah kartını kullan.",
        "fund_hits": pd.DataFrame(),
        "stock_hits": pd.DataFrame(),
    }
