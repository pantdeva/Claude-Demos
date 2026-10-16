"""Compare the quant models on a stock with a walk-forward backtest.

  python quant_run.py --download                       # NVDA + S&P 500 from Stooq, T-bill rate from FRED
  python quant_run.py --stock nvda.csv --market spx.csv --rf dtb3.csv
  python quant_run.py --download --step 63              # quicker run (quarterly origins)

Writes results/quant_<TICKER>.json and results/quant_<TICKER>.html (the dashboard).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from stock_analyzer.quant.backtest import Backtest, load_fred, load_stooq
from stock_analyzer.quant.report import render_dashboard

ROOT = Path(__file__).parent
STOOQ = "https://stooq.com/q/d/l/?s={sym}&i=d"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"


def fetch(url: str) -> str:
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    if "<html" in r.text[:200].lower():
        raise RuntimeError(f"{url} returned a web page instead of CSV data")
    return r.text


YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=0&period2=9999999999&interval=1d&events=split"


def fetch_yahoo(sym: str) -> pd.Series:
    """Split- and dividend-adjusted daily closes from Yahoo Finance's chart API."""
    r = requests.get(YAHOO.format(sym=requests.utils.quote(sym)), timeout=60,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts = pd.to_datetime(res["timestamp"], unit="s").normalize()
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or res["indicators"]["quote"][0]["close"]
    s = pd.Series(adj, index=ts, dtype=float).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def download_prices(stooq_sym: str, yahoo_sym: str) -> tuple[pd.Series, str]:
    try:
        return load_stooq(fetch(STOOQ.format(sym=stooq_sym))), "Stooq"
    except Exception as exc:  # fall back to Yahoo Finance
        print(f"  Stooq unavailable ({exc.__class__.__name__}); trying Yahoo Finance")
        return fetch_yahoo(yahoo_sym), "Yahoo Finance"


def to_jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, pd.Series):          # equity curves -> month-end points
        s = obj.dropna().resample("ME").last()
        return {"dates": [d.strftime("%Y-%m") for d in s.index], "values": [round(float(v), 5) for v in s]}
    if isinstance(obj, (np.floating, float)):
        return None if math.isnan(float(obj)) or math.isinf(float(obj)) else float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


def pick_best(strategies: list[dict]) -> dict:
    cands = [s for s in strategies if s.get("rule") != "benchmark" and s.get("sharpe") is not None
             and not math.isnan(s["sharpe"]) and s.get("avg_exposure", 0) > 0.05]
    by_sharpe = max(cands, key=lambda s: s["sharpe"])
    by_cagr = max(cands, key=lambda s: s["cagr"])
    return {"best_risk_adjusted": by_sharpe, "best_growth": by_cagr}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticker", default="NVDA")
    ap.add_argument("--stooq-symbol", default="nvda.us")
    ap.add_argument("--market-symbol", default="^spx")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--stock"), ap.add_argument("--market"), ap.add_argument("--rf")
    ap.add_argument("--window", type=int, default=1260, help="daily returns per fit (default 5 years)")
    ap.add_argument("--step", type=int, default=21, help="days between forecast origins (default monthly)")
    ap.add_argument("--gamma", type=float, default=2.0, help="risk aversion for position sizing")
    ap.add_argument("--sentiment", help="optional run.py JSON for the same ticker, shown as context")
    ap.add_argument("--out", default=str(ROOT / "results"))
    args = ap.parse_args(argv)

    source = "local CSV files"
    if args.download:
        stock, source = download_prices(args.stooq_symbol, args.ticker)
        market, _ = download_prices(args.market_symbol, "^GSPC")
        rf = load_fred(fetch(FRED.format(series="DTB3")))
    else:
        if not args.stock:
            sys.exit("Pass --download or --stock CSV (plus --market and --rf)")
        stock = load_stooq(args.stock)
        market = load_stooq(args.market) if args.market else None
        rf = load_fred(args.rf) if args.rf else None

    bt = Backtest(stock, market, rf, window=args.window, step=args.step, gamma=args.gamma)
    t0 = time.time()
    n_orig = len(bt.origins())
    print(f"{args.ticker}: {len(bt.px)} trading days {bt.px.index[0].date()} → {bt.px.index[-1].date()}, "
          f"{n_orig} forecast origins")

    def progress(k, n):
        if k % 10 == 0 or k == n:
            print(f"  {k}/{n} origins ({time.time() - t0:.0f}s)", flush=True)

    summary = bt.run(progress)
    current = bt.current_forecasts()
    for hname, h in summary["horizons"].items():
        h["best"] = pick_best(h["strategies"])

    result = {
        "ticker": args.ticker,
        "data": {"first": str(bt.px.index[0].date()), "last": str(bt.px.index[-1].date()),
                 "days": int(len(bt.px)), "origins": n_orig, "source": source, "window": args.window, "step": args.step,
                 "gamma": args.gamma},
        "backtest": summary,
        "current": current,
    }
    if args.sentiment and Path(args.sentiment).exists():
        result["sentiment"] = json.loads(Path(args.sentiment).read_text())
    result = to_jsonable(result)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"quant_{args.ticker}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    (out / f"quant_{args.ticker}.html").write_text(render_dashboard(result), encoding="utf-8")
    for hname, h in result["backtest"]["horizons"].items():
        b = h["best"]
        print(f"\n{hname}: best risk-adjusted = {b['best_risk_adjusted']['model']} ({b['best_risk_adjusted']['rule']}), "
              f"best growth = {b['best_growth']['model']} ({b['best_growth']['rule']})")
    print(f"\nDone in {time.time() - t0:.0f}s → {out}/quant_{args.ticker}.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
