"""Walk-forward forecasts for every company's home listing, scored out of sample.

At each forecast date (a shared calendar grid, so stocks can be compared date by
date) every model is fitted on the previous `window_days` daily log returns only and
forecasts the 3-month and 1-year log return. When the outcome is known each forecast
is scored:

  crps     continuous ranked probability score of the whole forecast distribution
           (lower is better; the leaderboard's main loss)
  hit      did the forecast get the sign of the excess return over cash right
  cover90  did the outcome fall inside the forecast's 5–95% range
  err      forecast mean log return minus outcome (bias)

Runs are incremental: dates already scored are skipped; dates whose outcome was not
yet known are recomputed once it is (seeds are fixed, so forecasts repeat exactly).
"""

from __future__ import annotations

import math
import os
from datetime import datetime
from multiprocessing import Pool

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ..config import load  # noqa: E402
from ..data import rates  # noqa: E402
from ..db import connect, now  # noqa: E402
from . import zoo  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS forecast_scores (
    company_id INTEGER, symbol TEXT, origin TEXT, model TEXT, horizon TEXT, h INTEGER,
    exp_return REAL, mean_log REAL, q05 REAL, q50 REAL, q95 REAL, p_beat_cash REAL, rf_h REAL,
    realized_log REAL, crps REAL, hit INTEGER, cover90 INTEGER, err REAL, fitted TEXT,
    PRIMARY KEY (company_id, origin, model, horizon)
);
CREATE INDEX IF NOT EXISTS ix_fs_model ON forecast_scores(model, horizon);
"""


def crps_samples(x: np.ndarray, y: float) -> float:
    """CRPS of a sample forecast: E|X − y| − ½E|X − X′| (sorted-sample formula)."""
    x = np.sort(np.asarray(x, float))
    n = len(x)
    term1 = np.mean(np.abs(x - y))
    term2 = (2.0 / (n * n)) * np.sum((2 * np.arange(1, n + 1) - n - 1) * x)
    return float(term1 - 0.5 * term2)


def clean_prices(px: pd.Series) -> pd.Series:
    """Drop non-positive prices and one-day spikes that reverse the next day."""
    px = px[px > 0].dropna()
    for _ in range(3):
        lr = np.log(px).diff()
        bad = (lr.abs() > 0.4) & ((lr + lr.shift(-1)).abs() < 0.1)
        if not bad.any():
            break
        px = px[~bad]
    return px


def origin_grid(index: pd.DatetimeIndex, start: str, step_days: int) -> list[int]:
    """Positions of the first trading day on/after each grid date (every step/21 months)."""
    months = max(1, round(step_days / 21))
    first = pd.Timestamp(start)
    grid = pd.date_range(first, index[-1], freq=f"{months}MS")
    pos = index.searchsorted(grid)
    return sorted({int(p) for p in pos if p < len(index)})


def stock_job(args) -> tuple[int, list[tuple], str | None]:
    """Fit and score one company. Runs in a worker process; returns rows to insert."""
    cid, symbol, dates, closes, ccy, erp, done = args
    cfg = load("models")["walk_forward"]
    W, H = cfg["window_days"], cfg["horizons"]
    try:
        px = clean_prices(pd.Series(closes, index=pd.to_datetime(dates)))
        if len(px) < cfg["min_history_days"]:
            return cid, [], "history too short"
        rf_s, _ = rates.series(ccy)
        rf = rf_s.reindex(px.index.union(rf_s.index)).sort_index().ffill().reindex(px.index).fillna(0.0)
        logr = np.log(px.values)
        r_all = np.diff(logr, prepend=np.nan)
        origins = [i for i in origin_grid(px.index, str(cfg["first_origin"]), cfg["step_days"]) if i >= W]
        rows, warm = [], {}
        for k, i in enumerate(origins):
            o = str(px.index[i].date())
            need = [hn for hn, h in H.items() if done.get((o, hn)) != "final"]
            if not need:
                continue
            r = r_all[i - W + 1:i + 1]
            rf0 = float(rf.iloc[i])
            seed = int(px.index[i].strftime("%Y%m%d"))
            for mid in zoo.model_ids():
                m = zoo.make(mid, erp)
                try:
                    if mid in zoo.WARM_START and mid in warm:
                        m.fit(r, rf0, x0=warm[mid])
                    else:
                        m.fit(r, rf0)
                    if mid in zoo.WARM_START:
                        warm[mid] = m.x
                except Exception:  # noqa: BLE001 - one bad fit must not stop the stock
                    continue
                for hn in need:
                    h = H[hn]
                    f = m.forecast(h, cfg["n_sims"], seed=seed)
                    if not np.all(np.isfinite(f.samples)):
                        continue
                    rf_h = rf0 * h / 252
                    real = float(logr[i + h] - logr[i]) if i + h < len(px) else None
                    q05, q50, q95 = (float(v) for v in f.quantiles((0.05, 0.5, 0.95)))
                    exp_r = f.exp_return
                    row = [cid, symbol, o, mid, hn, h, exp_r, f.mean_log, q05, q50, q95,
                           f.prob_above(rf_h), rf_h, real, None, None, None, None, now()]
                    if real is not None:
                        row[14] = crps_samples(f.samples, real)
                        row[15] = int((exp_r - rf_h > 0) == (math.exp(real) - 1 - rf_h > 0))
                        row[16] = int(q05 <= real <= q95)
                        row[17] = f.mean_log - real
                    rows.append(tuple(row))
        return cid, rows, None
    except Exception as e:  # noqa: BLE001
        return cid, [], f"error: {e!r}"[:200]


def _jobs(con, only: list[int] | None = None):
    from ..classify.market import CLASSES  # noqa: F401  (keeps import order simple)
    rows = con.execute("""SELECT c.id, c.home_country, l.symbol, l.currency,
                                 (SELECT value FROM stock_tags t WHERE t.company_id=c.id AND t.tag='market_class') AS mc
                          FROM companies c JOIN listings l ON l.company_id=c.id AND l.is_home=1
                          WHERE c.status='active'""").fetchall()
    for r in rows:
        if only and r["id"] not in only:
            continue
        px = con.execute("SELECT date, adj_close FROM prices WHERE symbol=? AND adj_close IS NOT NULL ORDER BY date",
                         (r["symbol"],)).fetchall()
        done = {}
        for d in con.execute("SELECT origin, horizon, MIN(realized_log IS NOT NULL) AS fin FROM forecast_scores "
                             "WHERE company_id=? GROUP BY origin, horizon", (r["id"],)):
            done[(d["origin"], d["horizon"])] = "final" if d["fin"] else "open"
        erp, _ = zoo.erp_for(r["home_country"], r["mc"])
        yield (r["id"], r["symbol"], [p["date"] for p in px], [p["adj_close"] for p in px],
               r["currency"], erp, done)


def run(con, jobs: int | None = None, only: list[int] | None = None, log=print) -> dict:
    con.executescript(SCHEMA)
    cfg = load("models")["walk_forward"]
    jobs = jobs or cfg["jobs"]
    work = list(_jobs(con, only))
    for ccy in {w[4] for w in work}:          # warm the rate cache once, not in every worker
        rates.series(ccy)
    stats = {"companies": len(work), "rows": 0, "skipped": 0, "errors": 0}
    t0 = datetime.now()
    with Pool(jobs) as pool:
        for k, (cid, rows, note) in enumerate(pool.imap_unordered(stock_job, work), 1):
            if rows:
                con.executemany("INSERT OR REPLACE INTO forecast_scores VALUES "
                                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                stats["rows"] += len(rows)
            if note:
                stats["errors" if note.startswith("error") else "skipped"] += 1
            if k % 20 == 0 or k == len(work):
                con.commit()
                el = (datetime.now() - t0).total_seconds()
                log(f"  walk-forward {k}/{len(work)}  {stats['rows']} rows  "
                    f"{el / 60:.0f} min elapsed, ~{el / k * (len(work) - k) / 60:.0f} min left")
    con.commit()
    return stats
