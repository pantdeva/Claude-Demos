"""Run the seven-model backtest on every stock in selection.json (cached per stock).

Each stock: daily prices since 2011, models fitted on a 5-year window, quarterly
forecast dates, 3-month and 1-year horizons, plus today's forecasts. MPT uses the
stock's own index; cash is the local short-term rate for the stock's currency.

  python run_models.py            # all selected stocks, 2 at a time
  python run_models.py --jobs 4
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
from multiprocessing import Pool
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from stock_analyzer.quant.backtest import Backtest  # noqa: E402

CACHE = HERE / "cache"
OUT = HERE / "results"
RATE_FOR = {"USD": "USD", "HKD": "USD", "GBP": "GBP", "GBp": "GBP", "EUR": "EUR", "JPY": "JPY",
            "KRW": "KRW", "AUD": "AUD", "INR": "INR"}
WINDOW, STEP, MIN_BACKTEST = 1260, 63, 1260 + 252 + 63


def series(sym: str) -> pd.Series:
    c = json.loads((CACHE / "chart" / f"{sym}.json").read_text())
    s = pd.Series(c["c"], index=pd.to_datetime(c["t"], unit="s").normalize(), dtype=float).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def rate(ccy: str) -> pd.Series:
    key = RATE_FOR.get(ccy, "USD")
    df = pd.read_csv(CACHE / "rates" / f"{key}.csv")
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce") / 100.0
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna().sort_index()


def clean(px: pd.Series) -> pd.Series:
    """Drop one-day spikes that reverse the next day (bad ticks)."""
    for _ in range(3):
        lr = np.log(px).diff()
        bad = (lr.abs() > 0.5) & ((lr + lr.shift(-1)).abs() < 0.1)
        if not bad.any():
            break
        px = px[~bad]
    return px


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, pd.Series):
        s = o.dropna().resample("ME").last()
        return {"d": [d.strftime("%Y-%m") for d in s.index], "v": [round(float(v), 4) for v in s]}
    if isinstance(o, (float, np.floating)):
        return None if math.isnan(float(o)) or math.isinf(float(o)) else round(float(o), 6)
    if isinstance(o, np.integer):
        return int(o)
    return o


def run_one(job):
    sym, index_sym, ccy = job
    out = OUT / f"{sym}.json"
    if out.exists():
        return sym, "cached"
    t0 = time.time()
    try:
        px = clean(series(sym))
        mkt = series(index_sym)
        rf = rate(ccy)
        res = {"ticker": sym, "index_benchmark": index_sym, "currency": ccy,
               "rf_series": RATE_FOR.get(ccy, "USD"), "days": int(len(px)),
               "first": str(px.index[0].date()), "last": str(px.index[-1].date())}
        if len(px) >= MIN_BACKTEST:
            bt = Backtest(px, mkt, rf, window=WINDOW, step=STEP, n_sims=2000, name=sym, market_name=index_sym)
            res["backtest"] = bt.run()
            res["origins"] = len(bt.origins())
            res["current"] = bt.current_forecasts()
        elif len(px) >= 300:
            win = len(px) - 2
            bt = Backtest(px, mkt, rf, window=win, step=STEP, n_sims=2000, name=sym, market_name=index_sym)
            res["current"] = bt.current_forecasts()
            res["note"] = f"Only {len(px)} trading days of history: too short to backtest; forecasts use all of it."
        else:
            res["note"] = f"Only {len(px)} trading days of history: too short to model."
        res["seconds"] = round(time.time() - t0, 1)
        out.write_text(json.dumps(jsonable(res)))
        return sym, f"ok {res['seconds']}s"
    except Exception as exc:  # keep going; record the failure
        (OUT / f"{sym}.error.txt").write_text(traceback.format_exc())
        return sym, f"error {exc.__class__.__name__}: {exc}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args(argv)
    OUT.mkdir(exist_ok=True)
    sel = json.loads((HERE / "selection.json").read_text())
    # each stock runs once, benchmarked against the first index it was selected for;
    # US stocks use the S&P 500 so the four US indexes share one benchmark
    jobs, seen = [], set()
    order = ["^GSPC", "^DJI", "^IXIC", "^NYA"] + [k for k in sel if not k.startswith(("^GSPC", "^DJI", "^IXIC", "^NYA"))]
    for idx in order:
        for c in sel[idx]["companies"]:
            if c["ticker"] in seen:
                continue
            seen.add(c["ticker"])
            bench = "^GSPC" if idx in ("^DJI", "^IXIC", "^NYA") else idx
            jobs.append((c["ticker"], bench, c.get("currency") or sel[idx]["ccy"]))
    print(f"{len(jobs)} stocks to model", flush=True)
    t0, done = time.time(), 0
    with Pool(args.jobs) as pool:
        for sym, status in pool.imap_unordered(run_one, jobs):
            done += 1
            if not status.startswith("ok") or done % 10 == 0 or done == len(jobs):
                print(f"[{done}/{len(jobs)} {time.time() - t0:.0f}s] {sym}: {status}", flush=True)


if __name__ == "__main__":
    main()
