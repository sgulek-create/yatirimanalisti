"""PP park taraması — CLI. Çıktı: data/pp_tarama.csv + konsol PP EMRİ."""

from __future__ import annotations

from pathlib import Path

from utils.portfolio import portfolio_frame
from utils.pp_scan import build_pp_orders, format_pp_emri, load_pp_table

OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(exist_ok=True)


def main() -> None:
    book, _ = portfolio_frame()
    tp2_v = float(book.loc[book["code"] == "TP2", "value_tl"].iloc[0])
    tlv_v = float(book.loc[book["code"] == "TLV", "value_tl"].iloc[0])

    table = load_pp_table()
    if table.empty:
        print("PP EMRİ: veri yok — TEFAS erişilemedi. TUT TP2, TUT TLV.")
        return

    table.to_csv(OUT / "pp_tarama.csv", index=False)
    orders, meta = build_pp_orders(table, tp2_v, tlv_v)
    print(format_pp_emri(orders, meta))
    print()
    print("Tera dışı konvansiyonel top3:")
    top = meta["top_conventional"]
    if top is not None and not top.empty:
        print(
            top[["fund_code", "fund_name", "return_1m", "return_3m", "daily_approx"]]
            .head(3)
            .to_string(index=False)
        )
    print("Tera dışı katılım top3:")
    topk = meta["top_katilim"]
    if topk is not None and not topk.empty:
        print(
            topk[["fund_code", "fund_name", "return_1m", "return_3m", "daily_approx"]]
            .head(3)
            .to_string(index=False)
        )


if __name__ == "__main__":
    main()
