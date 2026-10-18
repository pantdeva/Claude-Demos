"""Growth predictions: every model fitted on the latest 5 years, forecasting 3 months
and 1 year from the last close; the leaderboard's chosen model gives the headline
prediction (stored as stock tags growth_3m / growth_1y)."""

from __future__ import annotations

import math
from multiprocessing import Pool

import numpy as np
import pandas as pd

from ..config import load
from ..data import rates
from ..db import now, set_tag
from . import leaderboard, zoo
from .walkforward import _jobs, clean_prices

TAG = {"3 months": "growth_3m", "1 year": "growth_1y"}


def predict_job(args):
    cid, symbol, dates, closes, ccy, erp, _ = args
    cfg = load("models")["walk_forward"]
    W = cfg["window_days"]
    px = clean_prices(pd.Series(closes, index=pd.to_datetime(dates)))
    if len(px) < 260:
        return cid, symbol, None, [], "under 1 year of prices"
    r = np.diff(np.log(px.values))[-W:]
    rf_s, rf_src = rates.series(ccy)
    rf0 = float(rf_s[rf_s.index <= px.index[-1]].iloc[-1]) if (rf_s.index <= px.index[-1]).any() else 0.0
    out = []
    for mid in zoo.model_ids():
        try:
            m = zoo.make(mid, erp).fit(r, rf0)
        except Exception:  # noqa: BLE001
            continue
        for hn, h in cfg["horizons"].items():
            f = m.forecast(h, cfg["n_sims"], seed=7)
            if not np.all(np.isfinite(f.samples)):
                continue
            q05, q50, q95 = f.quantiles((0.05, 0.5, 0.95))
            rf_h = rf0 * h / 252
            out.append({"model": mid, "horizon": hn, "exp_return": f.exp_return,
                        "median_return": math.exp(q50) - 1, "q05_return": math.exp(q05) - 1,
                        "q95_return": math.exp(q95) - 1, "p_beat_cash": f.prob_above(rf_h), "rf_h": rf_h})
    note = None if len(r) >= W else f"only {len(r)} days of history (forecast-only)"
    return cid, symbol, {"as_of": str(px.index[-1].date()), "price": float(px.iloc[-1]), "rf": rf0,
                         "rf_source": rf_src}, out, note


def run(con, jobs: int | None = None, log=print) -> dict:
    work = list(_jobs(con))
    for ccy in {w[4] for w in work}:
        rates.series(ccy)
    jobs = jobs or load("models")["walk_forward"]["jobs"]
    con.execute("DELETE FROM model_results WHERE metric IN ('exp_return','median_return','q05_return',"
                "'q95_return','p_beat_cash')")
    n = 0
    with Pool(jobs) as pool:
        for k, (cid, symbol, info, rows, note) in enumerate(pool.imap_unordered(predict_job, work), 1):
            if info is None:
                continue
            for x in rows:
                for metric in ("exp_return", "median_return", "q05_return", "q95_return", "p_beat_cash"):
                    con.execute("INSERT OR REPLACE INTO model_results VALUES (?,?,?,?,?,?)",
                                (cid, x["model"], x["horizon"], metric, x[metric], info["as_of"]))
            for hn, tag in TAG.items():
                mid, basis = leaderboard.choice_for_company(con, cid, hn)
                x = next((y for y in rows if y["model"] == mid and y["horizon"] == hn), None)
                if x is None:
                    continue
                med = np.median([y["exp_return"] for y in rows if y["horizon"] == hn and y["model"] != "bsm"])
                set_tag(con, cid, "growth", tag, round(x["exp_return"], 4),
                        {"model": zoo.name(mid), "model_id": mid, "basis": basis, "symbol": symbol,
                         "as_of": info["as_of"], "price": info["price"], "rf_annual": info["rf"],
                         "rf_source": info["rf_source"], "median_return": x["median_return"],
                         "range_5_95": [x["q05_return"], x["q95_return"]], "p_beat_cash": x["p_beat_cash"],
                         "all_models_median_expected": float(med), "note": note}, now()[:10])
            n += 1
            if k % 100 == 0:
                con.commit()
                log(f"  predictions {k}/{len(work)}")
    con.commit()
    return {"predicted": n, "companies": len(work)}
