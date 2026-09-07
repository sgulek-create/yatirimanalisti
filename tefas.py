"""TEFAS public JSON API istemcisi (2026 Next.js uç noktaları)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import requests

TEFAS_ROOT = "https://www.tefas.gov.tr"
RETURNS_ENDPOINT = "/api/funds/fonGetiriBazliBilgiGetir"
HISTORY_ENDPOINT = "/api/funds/fonGnlBlgSiraliGetir"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": TEFAS_ROOT,
    "Referer": f"{TEFAS_ROOT}/tr/fon-verileri",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

INFO_FIELDS = {
    "fonKodu": "fund_code",
    "fonUnvan": "fund_name",
    "tarih": "date",
    "fiyat": "price",
    "tedPaySayisi": "shares_outstanding",
    "kisiSayisi": "investor_count",
    "portfoyBuyukluk": "portfolio_size",
}

RETURN_FIELDS = {
    "fonKodu": "fund_code",
    "fonUnvan": "fund_name",
    "fonTurAciklama": "category",
    "getiri1a": "return_1m",
    "getiri3a": "return_3m",
    "getiri6a": "return_6m",
    "getiri1y": "return_1y",
    "getiriyb": "return_ytd",
    "getiri3y": "return_3y",
    "getiri5y": "return_5y",
    "riskDegeri": "kiid_risk",
}

_EMPTY_MARKERS = ("out of bounds", "veri bulunamadı", "sistem hatası")


class TefasError(RuntimeError):
    """TEFAS isteği başarısız olduğunda yükseltilir."""


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _post(session: requests.Session, endpoint: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            response = session.post(
                f"{TEFAS_ROOT}{endpoint}",
                json=payload,
                timeout=45,
            )
            if response.status_code == 429:
                import time

                time.sleep(1.5 * (attempt + 1))
                last_exc = TefasError("TEFAS 429 Too Many Requests")
                continue
            response.raise_for_status()
            body = response.json()
            err_msg = (body.get("errorMessage") or "").strip()
            err_code = body.get("errorCode")
            is_empty = any(marker in err_msg.lower() for marker in _EMPTY_MARKERS)
            if (err_code or err_msg) and not is_empty:
                raise TefasError(err_msg or f"TEFAS hata kodu: {err_code}")
            if is_empty:
                return []
            return body.get("resultList") or []
        except requests.RequestException as exc:
            last_exc = exc
            import time

            time.sleep(1.0 * (attempt + 1))
    if last_exc:
        raise TefasError(str(last_exc)) from last_exc
    return []


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text[:10] if fmt != "%Y%m%d" else text[:8], fmt).date()
        except ValueError:
            continue
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def fetch_fund_snapshot(kinds: tuple[str, ...] = ("YAT", "BYF")) -> pd.DataFrame:
    """Tüm fonların dönem getirilerini ve KIID risk skorunu çeker."""
    session = _session()
    frames: list[pd.DataFrame] = []
    for kind in kinds:
        payload = {
            "dil": "TR",
            "fonTipi": kind,
            "kurucuKodu": None,
            "sfonTurKod": None,
            "fonTurAciklama": None,
            "islem": 1,
            "fonTurKod": None,
            "fonGrubu": None,
            "donemGetiri1a": "1",
            "donemGetiri3a": "1",
            "donemGetiri6a": "1",
            "donemGetiri1y": "1",
            "donemGetiriyb": "1",
            "donemGetiri3y": "1",
            "donemGetiri5y": "1",
            "basTarih": None,
            "bitTarih": None,
            "calismaTipi": 2,
            "getiriOrani": "1",
        }
        rows = _post(session, RETURNS_ENDPOINT, payload)
        if not rows:
            continue
        records = []
        for row in rows:
            rec = {"kind": kind}
            for src, dest in RETURN_FIELDS.items():
                value = row.get(src)
                if dest == "kiid_risk":
                    rec[dest] = _to_float(value)
                elif dest.startswith("return_"):
                    rec[dest] = _to_float(value)
                else:
                    rec[dest] = value
            if rec.get("fund_code"):
                records.append(rec)
        if records:
            frames.append(pd.DataFrame(records))

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["fund_code"] = out["fund_code"].astype(str).str.upper()
    return out.drop_duplicates(subset=["fund_code"], keep="first")


def _history_records(
    session: requests.Session,
    *,
    kind: str,
    lookback_days: int,
    fund_code: str | None = None,
) -> list[dict[str, Any]]:
    today = date.today()
    code = (fund_code or "").strip().upper() or None
    rows: list[dict[str, Any]] = []
    # Hafta sonu / tatilde boş dönebilir; birkaç gün geriye kaydır.
    for shift in range(0, 5):
        end = today - timedelta(days=shift)
        start = end - timedelta(days=lookback_days)
        payload = {
            "fonTipi": kind,
            "fonKodu": code,
            "aramaMetni": None,
            "fonTurKod": None,
            "fonGrubu": None,
            "sfonTurKod": None,
            "fonTurAciklama": None,
            "kurucuKod": None,
            "basTarih": start.strftime("%Y%m%d"),
            "bitTarih": end.strftime("%Y%m%d"),
            "basSira": 1,
            "bitSira": 100000 if code is None else 5000,
            "dil": "TR",
            "sFonTurKod": "",
            "fonKod": code or "",
            "fonGrup": "",
            "fonUnvanTip": "",
        }
        rows = _post(session, HISTORY_ENDPOINT, payload)
        if rows:
            break
    if not rows:
        return []

    records = []
    for row in rows:
        rec: dict[str, Any] = {"kind": kind}
        for src, dest in INFO_FIELDS.items():
            value = row.get(src)
            if dest == "date":
                rec[dest] = _parse_date(value)
            elif dest in {"price", "shares_outstanding", "investor_count", "portfolio_size"}:
                rec[dest] = _to_float(value)
            else:
                rec[dest] = value
        if rec.get("fund_code") and rec.get("date") and rec.get("price"):
            rec["fund_code"] = str(rec["fund_code"]).upper()
            if code and rec["fund_code"] != code:
                continue
            records.append(rec)
    return records


def fetch_fund_history(
    kinds: tuple[str, ...] = ("YAT", "BYF"),
    lookback_days: int = 25,
) -> pd.DataFrame:
    """Son iş günlerine ait fiyat, AUM ve yatırımcı sayısını çeker."""
    session = _session()
    frames: list[pd.DataFrame] = []

    for kind in kinds:
        records = _history_records(session, kind=kind, lookback_days=lookback_days)
        if records:
            frames.append(pd.DataFrame(records))

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["date", "fund_code"], keep="last")
    return out.sort_values(["fund_code", "date"]).reset_index(drop=True)


def fetch_fund_price_series(
    codes: list[str],
    lookback_days: int = 20,
    kinds: tuple[str, ...] = ("YAT", "BYF"),
) -> pd.DataFrame:
    """Seçili fon kodları için fiyat serisi.

    Birden fazla kodda tek/toplu tarih çekimi kullanır (429 riskini düşürür).
    Tek kodda fonKodu filtresiyle hızlı gider.
    """
    wanted = [c.strip().upper() for c in codes if c and str(c).strip()]
    if not wanted:
        return pd.DataFrame()

    # Çoklu kod: 1–2 istek (tür başına). Tek kod: filtreli.
    if len(wanted) == 1:
        session = _session()
        frames: list[pd.DataFrame] = []
        code = wanted[0]
        for kind in kinds:
            records = _history_records(
                session,
                kind=kind,
                lookback_days=lookback_days,
                fund_code=code,
            )
            if records:
                frames.append(pd.DataFrame(records))
                break
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)
    else:
        out = fetch_fund_history(kinds=kinds, lookback_days=lookback_days)
        if out.empty:
            return out
        out = out[out["fund_code"].isin(wanted)].copy()

    out = out.drop_duplicates(subset=["date", "fund_code"], keep="last")
    return out.sort_values(["fund_code", "date"]).reset_index(drop=True)
