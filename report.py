"""Sabah raporu metni üret, diske yaz, isteğe bağlı e-posta gönder."""

from __future__ import annotations

import os
import smtplib
import tomllib
from dataclasses import dataclass
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from utils.briefing import build_clean_briefing, build_expert_note
    from utils.orders import decide_positions, orders_to_frame
    from utils.portfolio import portfolio_frame
    from utils.pp_scan import build_pp_orders, format_pp_emri, load_pp_table
    from utils.risk_engine import compute_risk
except ImportError:
    from briefing import build_clean_briefing, build_expert_note
    from orders import decide_positions, orders_to_frame
    from portfolio import portfolio_frame
    from pp_scan import build_pp_orders, format_pp_emri, load_pp_table
    from risk_engine import compute_risk

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SECRETS = ROOT / ".streamlit" / "secrets.toml"


@dataclass
class MailConfig:
    host: str
    port: int
    user: str
    password: str
    mail_from: str
    mail_to: str
    use_tls: bool = True


def load_mail_config() -> MailConfig | None:
    """Önce ortam değişkeni, sonra .streamlit/secrets.toml."""
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    mail_to = os.getenv("MAIL_TO", "").strip()
    mail_from = os.getenv("MAIL_FROM", user).strip()
    port = int(os.getenv("SMTP_PORT", "587") or 587)

    if SECRETS.exists():
        with SECRETS.open("rb") as fh:
            data = tomllib.load(fh)
        smtp = data.get("smtp") or {}
        host = host or str(smtp.get("host", "")).strip()
        user = user or str(smtp.get("user", "")).strip()
        password = password or str(smtp.get("password", "")).strip()
        mail_to = mail_to or str(smtp.get("to", "")).strip()
        mail_from = mail_from or str(smtp.get("from", user)).strip()
        port = int(smtp.get("port", port) or port)

    if not (host and user and password and mail_to):
        return None
    return MailConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        mail_from=mail_from or user,
        mail_to=mail_to,
    )


def generate_morning_report(as_of: date | None = None) -> dict[str, Any]:
    """Canlı veri + emir + Türkçe uzman notu."""
    day = as_of or date.today()
    book, total = portfolio_frame()
    weights = book.set_index("code")["weight"].to_dict()

    pp_table = load_pp_table()
    pp_daily = 0.001
    if not pp_table.empty and "daily_return" in pp_table.columns:
        sub = pp_table[pp_table["fund_code"].isin(["TP2", "TLV"])]
        if not sub.empty and sub["daily_return"].notna().any():
            pp_daily = float(sub["daily_return"].mean())

    tp2_v = float(book.loc[book["code"] == "TP2", "value_tl"].iloc[0])
    tlv_v = float(book.loc[book["code"] == "TLV", "value_tl"].iloc[0])
    pp_orders, meta = build_pp_orders(pp_table, tp2_v, tlv_v) if not pp_table.empty else ([], {})

    preferred = None
    top = meta.get("top_conventional") if meta else None
    if top is not None and not getattr(top, "empty", True):
        preferred = str(top.iloc[0]["fund_code"])

    risk = compute_risk(weights, pp_daily_rate=pp_daily)
    pos = decide_positions(
        book,
        total,
        risk.mstr_vol_pct,
        risk.nvda_mstr_corr,
        preferred_pp=preferred,
    )
    pos_df = orders_to_frame(pos)
    briefing = build_clean_briefing(book, risk, pp_orders, position_orders=pos, as_of=day)
    expert = build_expert_note(book, pos, pp_orders, preferred_pp=preferred)
    pp_text = format_pp_emri(pp_orders, meta) if pp_orders else "PP EMRİ: veri yok"

    alarms = "\n".join(f"- {a}" for a in risk.alarms)
    var_line = ""
    if risk.var95 is not None:
        var_line = (
            f"VaR95 (1 ay): %{risk.var95 * 100:.1f} ≈ ₺{abs(risk.var95) * total:,.0f} | "
            f"CVaR95: %{(risk.cvar95 or 0) * 100:.1f} | "
            f"P(ay≤-5%): %{(risk.p_loss_5pct or 0) * 100:.0f}"
        ).replace(",", ".")

    full = "\n".join(
        [
            briefing["headline"],
            "=" * 48,
            briefing["body"],
            "",
            "UZMAN ÖNERİSİ",
            "-" * 48,
            expert,
            "",
            "PP EMRİ",
            "-" * 48,
            pp_text,
            "",
            "PORTFÖY EMRİ",
            "-" * 48,
            pos_df.to_string(index=False),
            "",
            "ALARM / RİSK",
            "-" * 48,
            alarms or "- Yok",
            var_line,
            "",
            "Bu rapor otomatik üretildi. Emir senin kuralların; uygulama senin.",
        ]
    )

    return {
        "as_of": day,
        "text": full,
        "briefing": briefing,
        "expert": expert,
        "pos_df": pos_df,
        "pp_orders": pp_orders,
        "risk": risk,
        "total": total,
    }


def save_report(report: dict[str, Any]) -> Path:
    DATA.mkdir(exist_ok=True)
    day: date = report["as_of"]
    path = DATA / f"sabah_raporu_{day.isoformat()}.txt"
    path.write_text(report["text"], encoding="utf-8")
    latest = DATA / "sabah_raporu_son.txt"
    latest.write_text(report["text"], encoding="utf-8")
    pos_df: pd.DataFrame = report["pos_df"]
    pos_df.to_csv(DATA / f"portfoy_emri_{day.isoformat()}.csv", index=False)
    return path


def send_email(subject: str, body: str, cfg: MailConfig) -> None:
    msg = MIMEMultipart()
    msg["From"] = cfg.mail_from
    msg["To"] = cfg.mail_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(cfg.host, cfg.port, timeout=45) as server:
        if cfg.use_tls:
            server.starttls()
        server.login(cfg.user, cfg.password)
        server.sendmail(cfg.mail_from, [cfg.mail_to], msg.as_string())
