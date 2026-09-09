"""Yatırım sohbeti — manifesto + kitap bağlamı; opsiyonel Gemini."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / ".streamlit" / "secrets.toml"


def _secret_key() -> str | None:
    env = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if env:
        return env.strip()
    if not SECRETS.exists():
        return None
    try:
        import tomllib

        data = tomllib.loads(SECRETS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    for k in ("gemini_api_key", "GEMINI_API_KEY", "google_api_key", "GOOGLE_API_KEY"):
        v = data.get(k)
        if isinstance(v, str) and v.strip() and "your" not in v.lower():
            return v.strip()
    return None


def build_context(
    *,
    book_text: str,
    firsat_text: str,
    compare_hint: str,
) -> str:
    try:
        from utils.portfolio import MANIFESTO, RULES
    except ImportError:
        from portfolio import MANIFESTO, RULES

    return "\n".join(
        [
            "Sen Süleyman’ın kişisel yatırım asistanısın (yanaliz).",
            "Karakter: parkçı / disiplinli. İcra yok — Midas emri basma.",
            f"Manifesto: {MANIFESTO}",
            (
                f"Kurallar: TLY≤%{RULES['tly_max_weight']*100:.0f}, "
                f"Tera≤%{RULES['tera_max_weight']*100:.0f}, "
                f"PP geçiş +{RULES['pp_switch_1m_pp']:.2f}pp+3A, "
                f"ikinci TLY yasak."
            ),
            "",
            "KITAP:",
            book_text[:2500],
            "",
            "FIRSAT KARTLARI:",
            firsat_text[:2000] or "(henüz yok)",
            "",
            "KARŞILAŞTIRMA İPUCU:",
            compare_hint[:1200] or "(yok)",
            "",
            "Cevap Türkçe, kısa, maddeli. Kör hisse/fon önerme.",
        ]
    )


def _rule_answer(question: str, context: str) -> str:
    q = question.casefold()
    lines: list[str] = []

    if any(k in q for k in ("tly", "ikinci", "serbest av", "yeni fon")):
        lines.append(
            "İkinci TLY / yeni serbest avı manifesto dışı. "
            "Park için Tera dışı PP (GEÇ/AL kartı) bak; serbest avlama."
        )
    if any(k in q for k in ("ne al", "ne alınır", "fırsat", "aday")):
        # FIRSAT bloğundan ilk satırları çek
        block = ""
        if "FIRSAT KARTLARI:" in context:
            block = context.split("FIRSAT KARTLARI:", 1)[1].split("KARŞILAŞTIRMA", 1)[0]
        snippet = "\n".join(block.strip().splitlines()[:12]) or "Kart yok — Fırsat ajanını çalıştır."
        lines.append("Güncel fırsat özeti:\n" + snippet)
    if any(k in q for k in ("pp", "park", "geç", "tp2", "tlv", "pnu")):
        lines.append(
            "PP kuralı: 1A ≥ +0.25pp ve 3A teyit olmadan geçme. "
            "TLV yalnız katılım ligi. Terminalde `pp` veya Karşılaştır sekmesi."
        )
    if any(k in q for k in ("mstr", "vol", "risk", "nvda")):
        lines.append(
            "MSTR’de vol eşiği aşılınca KÜÇÜLT; NVDA-MSTR corr yüksekse ekleme. "
            "Tema bozulmasa bile boyut disiplini."
        )
    if any(k in q for k in ("kitap", "portföy", "toplam", "ağırlık")):
        if "KITAP:" in context:
            kitap = context.split("KITAP:", 1)[1].split("FIRSAT", 1)[0].strip()
            lines.append("Kitap özeti:\n" + "\n".join(kitap.splitlines()[:14]))
    if any(k in q for k in ("manifesto", "kural", "neden")):
        lines.append(
            "Amaç katlama değil; PP tamponu ile yaşat, vol’da realize et, "
            "valör için parkı önceden tut. Onay sende."
        )
    if any(k in q for k in ("midas", "otomatik", "emir bas")):
        lines.append("Otomatik Midas emri yok. Kart üret → sen uygula.")

    if not lines:
        lines.append(
            "Kural motoru: kitap / fırsat / PP / risk sor. "
            "Örn. «bugün ne alınır?», «neden TLY yok?», «PNU ne?» "
            "Gemini anahtarı eklersen daha serbest dil."
        )
        # Bağlamdan kısa hatırlatma
        if "FIRSAT KARTLARI:" in context:
            block = context.split("FIRSAT KARTLARI:", 1)[1].split("KARŞILAŞTIRMA", 1)[0]
            first = next((ln for ln in block.splitlines() if ln.strip().startswith("1.")), "")
            if first:
                lines.append("İpucu: " + first.strip())

    lines.append("\n_İcra yok — human-in-the-loop._")
    return "\n\n".join(lines)


def ask_gemini(question: str, context: str, api_key: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"{context}\n\n---\nKullanıcı sorusu:\n{question}\n"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 700},
    }
    r = requests.post(url, json=payload, timeout=45)
    r.raise_for_status()
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Gemini yanıtı parse edilemedi: {json.dumps(data)[:400]}") from exc


def answer(question: str, context: str) -> tuple[str, str]:
    """Returns (text, engine) where engine is 'rules' | 'gemini'."""
    key = _secret_key()
    if key:
        try:
            return ask_gemini(question, context, key), "gemini"
        except Exception as exc:  # noqa: BLE001
            fallback = _rule_answer(question, context)
            return (
                f"(Gemini hata: {exc})\n\nKural motoruna düştüm:\n\n{fallback}",
                "rules",
            )
    return _rule_answer(question, context), "rules"


def gemini_configured() -> bool:
    return _secret_key() is not None
