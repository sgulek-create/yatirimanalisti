"""Risk alarm + VaR/CVaR + walk-forward. Çıktı: data/*.csv."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from utils.orders import decide_positions, orders_to_frame
from utils.portfolio import portfolio_frame
from utils.pp_scan import build_pp_orders, load_pp_table
from utils.risk_engine import (
    build_proxy_returns,
    compute_risk,
    fetch_closes,
    performance_stats,
    walk_forward,
)

OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(exist_ok=True)


def main() -> None:
    book, total = portfolio_frame()
    weights = book.set_index("code")["weight"].to_dict()

    # PP günlük oran ≈ 1A/21
    pp_daily = 0.001
    try:
        pp_table = load_pp_table()
        if not pp_table.empty:
            sub = pp_table[pp_table["fund_code"].isin(["TP2", "TLV"])]
            if not sub.empty and sub["daily_approx"].notna().any():
                pp_daily = float(sub["daily_approx"].mean() / 100.0)
    except Exception as exc:  # noqa: BLE001
        print(f"PP oran fallback: {exc}")

    risk = compute_risk(weights, pp_daily_rate=pp_daily)

    # preferred PP for trims
    preferred = None
    try:
        if not pp_table.empty:
            orders_pp, meta = build_pp_orders(
                pp_table,
                float(book.loc[book["code"] == "TP2", "value_tl"].iloc[0]),
                float(book.loc[book["code"] == "TLV", "value_tl"].iloc[0]),
            )
            top = meta.get("top_conventional")
            if top is not None and not top.empty:
                preferred = str(top.iloc[0]["fund_code"])
    except Exception:
        preferred = None

    pos = decide_positions(
        book,
        total,
        risk.mstr_vol_pct,
        risk.nvda_mstr_corr,
        preferred_pp=preferred,
    )
    pos_df = orders_to_frame(pos)
    pos_df.to_csv(OUT / "portfoy_emri.csv", index=False)

    print("PORTFÖY EMRİ:")
    print(pos_df.to_string(index=False))
    print()
    print("ALARM:")
    for a in risk.alarms:
        print(f"- {a}")
    print()
    if risk.var95 is not None:
        var_tl = abs(risk.var95) * total
        cvar_tl = abs(risk.cvar95 or 0) * total
        print(
            f"VaR95 (1ay): {risk.var95*100:.1f}% ≈ -₺{var_tl:,.0f} | "
            f"CVaR95: {(risk.cvar95 or 0)*100:.1f}% ≈ -₺{cvar_tl:,.0f} | "
            f"P(ay≤-5%): {(risk.p_loss_5pct or 0)*100:.0f}%"
        )
    print("Notlar:", "; ".join(risk.notes))

    # Walk-forward
    close = fetch_closes(["NVDA", "MSTR", "SLV", "XU100.IS"], period="1y")
    asset_r, _ = build_proxy_returns(close)
    # inject PP columns as zeros (cash yield applied inside)
    for code in ("TP2", "TLV"):
        if code not in asset_r.columns:
            asset_r[code] = 0.0

    curves = walk_forward(asset_r, weights, pp_daily=pp_daily, valor_lag=2)
    if not curves.empty:
        curves.to_csv(OUT / "walk_forward_curves.csv")
        rows = []
        for col in curves.columns:
            stats = performance_stats(curves[col])
            stats["strategy"] = col
            rows.append(stats)
        stats_df = pd.DataFrame(rows)
        stats_df.to_csv(OUT / "walk_forward_stats.csv", index=False)
        print()
        print("WALK-FORWARD (vekil TLY açık):")
        print(stats_df.to_string(index=False))
        print(
            "Yorum: Overlay'i TLY vekilinin başarısızlığı diye yorma; "
            "A vs B farkı kuralın valörlü etkisidir."
        )

    # risk dump
    pd.DataFrame(
        [
            {
                "mstr_vol_pct": risk.mstr_vol_pct,
                "nvda_vol_pct": risk.nvda_vol_pct,
                "nvda_mstr_corr": risk.nvda_mstr_corr,
                "var95": risk.var95,
                "cvar95": risk.cvar95,
                "p_loss_5pct": risk.p_loss_5pct,
                "pp_daily": pp_daily,
                "total_tl": total,
            }
        ]
    ).to_csv(OUT / "risk_snapshot.csv", index=False)


if __name__ == "__main__":
    main()
