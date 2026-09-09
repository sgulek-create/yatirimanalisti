"""OpenBB-lite terminal — quote, PP ligi, kitap, basit komutlar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf

try:
    from utils.portfolio import portfolio_frame
    from utils.pp_scan import load_pp_table
    from utils.tefas import fetch_fund_snapshot
except ImportError:
    from portfolio import portfolio_frame
    from pp_scan import load_pp_table
    from tefas import fetch_fund_snapshot


HELP = """Komutlar:
  help                 — bu liste
  book                 — Midas kitabı özeti
  pp [n]               — PP ligi top-n (varsayılan 10)
  quote <KOD>          — TEFAS fon veya yfinance hisse (NVDA, MSTR, TRY=X)
  chart <KOD> [gün]    — kapanış serisi (varsayılan 90 gün)
  firsat               — fırsat ajanı kısa özet (son hesap)
  rules                — manifesto / tavanlar
"""


@dataclass
class TerminalResult:
    kind: str  # text | table | chart
    title: str
    text: str = ""
    table: pd.DataFrame | None = None
    chart: pd.Series | None = None


def _quote_fund(code: str) -> TerminalResult:
    snap = fetch_fund_snapshot(("YAT",))
    row = snap[snap["fund_code"] == code.upper()]
    if row.empty:
        return TerminalResult("text", code, text=f"{code}: TEFAS’ta bulunamadı.")
    r = row.iloc[0]
    lines = [
        f"{code.upper()} — {r.get('fund_name', '')}",
        f"Kategori: {r.get('category', '—')}",
        f"1A %{_f(r.get('return_1m'))} | 3A %{_f(r.get('return_3m'))} | "
        f"6A %{_f(r.get('return_6m'))} | YTD %{_f(r.get('return_ytd'))}",
    ]
    price = r.get("price")
    if price is not None and pd.notna(price):
        lines.append(f"Fiyat: {float(price):.6g}")
    return TerminalResult("text", f"QUOTE {code.upper()}", text="\n".join(lines))


def _f(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{float(v):.2f}"


def _quote_yf(ticker: str) -> TerminalResult:
    t = yf.Ticker(ticker)
    hist = t.history(period="5d", auto_adjust=True)
    last = float(hist["Close"].iloc[-1]) if not hist.empty else None
    prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else None
    chg = ((last / prev) - 1) * 100 if last and prev else None
    name = ticker
    try:
        meta = t.info or {}
        name = meta.get("shortName") or ticker
    except Exception:  # noqa: BLE001
        pass
    lines = [
        f"{ticker} — {name}",
        f"Son: {last:.4f}" if last is not None else "Son: —",
        f"Günlük Δ: %{chg:.2f}" if chg is not None else "Günlük Δ: —",
        "Kaynak: yfinance",
    ]
    return TerminalResult("text", f"QUOTE {ticker}", text="\n".join(lines))


def quote(symbol: str) -> TerminalResult:
    sym = symbol.strip().upper()
    if not sym:
        return TerminalResult("text", "QUOTE", text="Kullanım: quote <KOD>")
    # TR fon kodları genelde 3 harf
    if len(sym) <= 4 and sym.isalpha() and sym not in {"NVDA", "MSTR", "AAPL", "MSFT", "TSLA"}:
        try:
            return _quote_fund(sym)
        except Exception as exc:  # noqa: BLE001
            return TerminalResult("text", sym, text=f"TEFAS hata: {exc}")
    yf_map = {"USDTRY": "TRY=X", "TRY": "TRY=X", "SILVER": "SLV", "GMC": "SLV"}
    return _quote_yf(yf_map.get(sym, sym))


def pp_league(n: int = 10) -> TerminalResult:
    table = load_pp_table()
    if table.empty:
        return TerminalResult("text", "PP", text="PP tablosu boş.")
    cols = [c for c in ("fund_code", "return_1m", "return_3m", "return_6m", "daily_pct", "is_katilim") if c in table.columns]
    show = table[cols].head(max(1, n)).copy()
    show = show.rename(
        columns={
            "fund_code": "Kod",
            "return_1m": "1A %",
            "return_3m": "3A %",
            "return_6m": "6A %",
            "daily_pct": "Günlük ≈%",
            "is_katilim": "Katılım",
        }
    )
    return TerminalResult("table", f"PP ligi top-{len(show)}", table=show)


def book_summary() -> TerminalResult:
    book, total = portfolio_frame(live=False)
    show = book[["code", "name", "kind", "value_tl", "weight"]].copy()
    show["weight"] = (show["weight"] * 100).round(2)
    show = show.rename(
        columns={
            "code": "Kod",
            "name": "Ad",
            "kind": "Tür",
            "value_tl": "Değer ₺",
            "weight": "Ağırlık %",
        }
    )
    return TerminalResult(
        "table",
        f"Kitap · ₺{total:,.0f}".replace(",", "."),
        table=show,
        text=f"Toplam ₺{total:,.0f}".replace(",", "."),
    )


def chart_series(symbol: str, days: int = 90) -> TerminalResult:
    sym = symbol.strip().upper()
    days = max(20, min(int(days), 365))
    yf_map = {"USDTRY": "TRY=X", "TRY": "TRY=X", "GMC": "SLV", "SILVER": "SLV"}
    use_yf = sym in yf_map or sym in {"NVDA", "MSTR", "AAPL", "MSFT", "TSLA", "SLV"} or len(sym) > 4
    if use_yf:
        ticker = yf_map.get(sym, sym)
        hist = yf.Ticker(ticker).history(period=f"{days}d", auto_adjust=True)
        if hist.empty:
            return TerminalResult("text", ticker, text=f"{ticker}: yfinance boş.")
        s = hist["Close"].copy()
        s.name = ticker
        return TerminalResult("chart", f"CHART {ticker} ({days}g)", chart=s)

    try:
        from utils.tefas import fetch_fund_price_series
    except ImportError:
        from tefas import fetch_fund_price_series

    df = fetch_fund_price_series([sym], lookback_days=days)
    if df is None or df.empty:
        return TerminalResult("text", sym, text=f"{sym}: TEFAS grafik verisi yok.")
    sub = df[df["fund_code"] == sym].sort_values("date")
    if sub.empty or "price" not in sub.columns:
        return TerminalResult("text", sym, text=f"{sym}: fiyat satırı yok.")
    s = pd.Series(
        sub["price"].astype(float).to_numpy(),
        index=pd.to_datetime(sub["date"]),
        name=sym,
    )
    return TerminalResult("chart", f"CHART {sym} ({days}g)", chart=s)


def run_command(raw: str, *, firsat_text: str | None = None) -> TerminalResult:
    line = (raw or "").strip()
    if not line:
        return TerminalResult("text", "?", text=HELP)
    parts = line.split()
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in {"help", "?", "h"}:
        return TerminalResult("text", "HELP", text=HELP)
    if cmd in {"book", "kitap"}:
        return book_summary()
    if cmd == "pp":
        n = int(args[0]) if args and args[0].isdigit() else 10
        return pp_league(n)
    if cmd in {"quote", "q", "fiyat"}:
        return quote(args[0] if args else "")
    if cmd in {"chart", "grafik"}:
        sym = args[0] if args else ""
        days = int(args[1]) if len(args) > 1 and args[1].isdigit() else 90
        if not sym:
            return TerminalResult("text", "CHART", text="Kullanım: chart <KOD> [gün]")
        return chart_series(sym, days)
    if cmd in {"firsat", "opp"}:
        return TerminalResult(
            "text",
            "FIRSAT",
            text=firsat_text or "Önce Fırsat ajanı sekmesinden tara; veya burada quote/pp kullan.",
        )
    if cmd in {"rules", "manifesto", "kural"}:
        try:
            from utils.portfolio import MANIFESTO, RULES
        except ImportError:
            from portfolio import MANIFESTO, RULES
        text = (
            f"{MANIFESTO}\n\n"
            f"TLY tavan %{RULES['tly_max_weight']*100:.0f} · "
            f"Tera tavan %{RULES['tera_max_weight']*100:.0f} · "
            f"PP geçiş +{RULES['pp_switch_1m_pp']:.2f}pp (3A teyit) · "
            f"MSTR vol eşik %{RULES['mstr_vol_annual_pct']:.0f}"
        )
        return TerminalResult("text", "RULES", text=text)

    return TerminalResult(
        "text",
        "?",
        text=f"Bilinmeyen komut: {cmd}\n\n{HELP}",
    )
