"""Combine several quant_run.py results into one cross-stock comparison.

  python quant_basket.py results/            # reads results/quant_*.json, writes results/quant_basket.{json,html}

For each horizon it ranks every strategy (model + sizing rule) within each stock,
then reports per strategy: average rank, how often it beat buy & hold on Sharpe,
and its median Sharpe / growth / worst-drop difference versus holding the stock.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from stock_analyzer.quant.report import render_basket

LABELS = {"INTC": "Intel", "C": "Citigroup", "CSCO": "Cisco", "MU": "Micron", "XOM": "ExxonMobil",
          "PG": "Procter & Gamble", "KO": "Coca-Cola", "TATASTEEL.NS": "Tata Steel",
          "INFY.NS": "Infosys", "^GSPC": "S&P 500 index", "NVDA": "NVIDIA"}
GROUPS = {"NVDA": "Big winner", "INTC": "Fell or stalled", "C": "Fell or stalled", "CSCO": "Fell or stalled",
          "MU": "Boom and bust", "XOM": "Boom and bust", "TATASTEEL.NS": "Boom and bust",
          "PG": "Steady", "KO": "Steady", "INFY.NS": "Indian IT", "^GSPC": "Market index"}


def strategy_key(s):
    return s["model"] if s["rule"] in ("sized", "benchmark") and s["model"].startswith(("MPT", "Buy")) \
        else f'{s["model"]} · {s["rule"]}'


def main(folder: str) -> int:
    folder = Path(folder)
    runs = {}
    for f in sorted(folder.glob("quant_*.json")):
        if f.stem == "quant_basket":
            continue
        d = json.loads(f.read_text())
        runs[d["ticker"]] = d
    if not runs:
        sys.exit(f"No quant_*.json files in {folder}")

    out = {"stocks": [], "horizons": {}}
    for t, d in runs.items():
        out["stocks"].append({"ticker": t, "name": LABELS.get(t, t), "group": GROUPS.get(t, ""),
                              "first": d["data"]["first"], "last": d["data"]["last"],
                              "period": d["backtest"]["period"], "market": d.get("market_name"),
                              "rf_source": d["data"].get("rf_source", "US 3-month T-bill")})

    horizons = list(next(iter(runs.values()))["backtest"]["horizons"])
    for h in horizons:
        rows, skill_rows, per_stock = [], [], []
        for t, d in runs.items():
            hz = d["backtest"]["horizons"][h]
            bh = next(s for s in hz["strategies"] if s["model"] == f"Buy & hold {t}")
            strats = [s for s in hz["strategies"] if s["rule"] != "benchmark"
                      and s.get("avg_exposure", 0) > 0.05 and s.get("sharpe") is not None]
            ranked = sorted(strats, key=lambda s: -s["sharpe"])
            for rank, s in enumerate(ranked, 1):
                rows.append({"ticker": t, "strategy": strategy_key(s), "rank": rank, "n": len(ranked),
                             "sharpe": s["sharpe"], "cagr": s["cagr"], "max_drawdown": s["max_drawdown"],
                             "d_sharpe": s["sharpe"] - bh["sharpe"], "d_cagr": s["cagr"] - bh["cagr"],
                             "d_dd": s["max_drawdown"] - bh["max_drawdown"],
                             "exposure": s.get("avg_exposure")})
            sk = sorted(hz["skill"], key=lambda s: s["crps"])
            for rank, s in enumerate(sk, 1):
                skill_rows.append({"ticker": t, "model": s["model"], "crps_rank": rank,
                                   "hit_rate": s["hit_rate"], "coverage90": s["coverage90"]})
            best = ranked[0] if ranked else None
            per_stock.append({"ticker": t, "name": LABELS.get(t, t), "group": GROUPS.get(t, ""),
                              "bh_cagr": bh["cagr"], "bh_sharpe": bh["sharpe"], "bh_dd": bh["max_drawdown"],
                              "best": strategy_key(best) if best else None,
                              "best_sharpe": best["sharpe"] if best else None,
                              "best_cagr": best["cagr"] if best else None,
                              "best_dd": best["max_drawdown"] if best else None,
                              "beat_bh": bool(best and best["sharpe"] > bh["sharpe"]),
                              "best_forecaster": sk[0]["model"]})
        df = pd.DataFrame(rows)
        agg = (df.groupby("strategy")
                 .agg(avg_rank=("rank", "mean"), stocks=("ticker", "nunique"),
                      beat_bh=("d_sharpe", lambda x: int((x > 0).sum())),
                      med_d_sharpe=("d_sharpe", "median"), med_d_cagr=("d_cagr", "median"),
                      med_d_dd=("d_dd", "median"), avg_exposure=("exposure", "mean"),
                      top3=("rank", lambda x: int((x <= 3).sum())))
                 .reset_index().sort_values("avg_rank"))
        # only strategies that were genuinely invested on most stocks; near-cash ones can show
        # a high Sharpe on tiny returns (Black-Scholes-Merton never expects to beat cash)
        min_stocks = int(np.ceil(0.75 * len(runs)))
        excluded = sorted(agg.loc[agg.stocks < min_stocks, "strategy"])
        agg = agg[agg.stocks >= min_stocks]
        sdf = pd.DataFrame(skill_rows)
        sagg = (sdf.groupby("model").agg(avg_crps_rank=("crps_rank", "mean"),
                                         wins=("crps_rank", lambda x: int((x == 1).sum())),
                                         hit_rate=("hit_rate", "mean"), coverage90=("coverage90", "mean"))
                   .reset_index().sort_values("avg_crps_rank"))
        grid = df.pivot_table(index="strategy", columns="ticker", values="d_sharpe").reindex(agg.strategy)
        out["horizons"][h] = {
            "ranking": agg.to_dict("records"),
            "excluded": excluded,
            "skill": sagg.to_dict("records"),
            "per_stock": per_stock,
            "grid": {"strategies": list(grid.index), "tickers": list(grid.columns),
                     "values": [[None if pd.isna(v) else float(v) for v in row] for row in grid.values]},
        }
    notes_file = folder / "basket_notes.json"
    if notes_file.exists():
        out["notes"] = json.loads(notes_file.read_text())
    (folder / "quant_basket.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    (folder / "quant_basket.html").write_text(render_basket(out), encoding="utf-8")
    for h in horizons:
        top = out["horizons"][h]["ranking"][0]
        print(f"{h}: top strategy by average rank = {top['strategy']} (avg rank {top['avg_rank']:.1f}, "
              f"beat buy & hold on {top['beat_bh']}/{top['stocks']} stocks)")
    print(f"→ {folder}/quant_basket.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "results")))
