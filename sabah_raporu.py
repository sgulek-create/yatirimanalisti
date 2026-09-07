"""Sabah raporu CLI — dosyaya yazar, --email ile SMTP gönderir.

Örnek:
  .\\.venv\\Scripts\\python.exe sabah_raporu.py
  .\\.venv\\Scripts\\python.exe sabah_raporu.py --email
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.report import generate_morning_report, load_mail_config, save_report, send_email


def main() -> int:
    parser = argparse.ArgumentParser(description="Sabah brifingi + emir raporu")
    parser.add_argument(
        "--email",
        action="store_true",
        help="SMTP ayarlıysa e-posta gönder",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="do_print",
        help="Raporu konsola yaz",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    print("Sabah raporu üretiliyor…")
    report = generate_morning_report()
    path = save_report(report)
    print(f"Kaydedildi: {path}")

    if args.do_print:
        print()
        print(report["text"])
        print()
        print("3 MADDELİK AKSİYON:")
        for i, line in enumerate(report.get("actions") or [], 1):
            print(f"  {i}. {line}")

    if args.email:
        cfg = load_mail_config()
        if cfg is None:
            print(
                "E-posta ayarı yok. .streamlit/secrets.toml içine [smtp] ekle "
                "veya SMTP_HOST / SMTP_USER / SMTP_PASSWORD / MAIL_TO ortam değişkenlerini set et."
            )
            return 2
        subject = report["briefing"]["headline"]
        send_email(subject, report["text"], cfg)
        print(f"E-posta gönderildi → {cfg.mail_to}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
