"""MPT versus the 1/N benchmark inside each cell (market class × sector group).

Every quarter (from the walk-forward start date) the cell's largest stocks with five
years of history are taken; MPT sets long-only mean-variance weights from the past
five years of daily US-dollar returns (rest in US T-bills), 1/N holds them equally.
Both are held for the next quarter. Results: annual return, volatility, Sharpe, worst
quarter, and the Jobson–Korkie test (Memmel correction) of the Sharpe difference.

Caveat: the universe is today's largest companies, so every strategy benefits from
survivorship; the comparison between MPT and 1/N is affected far less than the levels.
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import load
from ..data import rates, yahoo
from ..db import now

_QUANT = Path(__file__).resolve().parents[3] / "nlp_stock_analyzer"
if str(_QUANT) not in sys.path:
    sys.path.insert(0, str(_QUANT))
from stock_analyzer.quant.portfolio import mean_variance_weights  # noqa: E402

from .walkforward import clean_prices, origin_grid  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio_tests (
    cell TEXT, strategy TEXT, quarters INTEGER, avg_assets REAL, cagr REAL, vol REAL, sharpe REAL,
    worst_quarter REAL, sharpe_diff_z REAL, as_of TEXT, PRIMARY KEY (cell, strategy)
);
"""


def memmel_z(a: np.ndarray, b: np.ndarray) -> float:
    """Jobson–Korkie z for SR(a) − SR(b) with Memmel's correction (excess returns)."""
    T = len(a)
    if T < 8:
        return float("nan")
    sa, sb = a.std(ddof=1), b.std(ddof=1)
    if sa == 0 or sb == 0:
        return float("nan")
    ra, rb = a.mean() / sa, b.mean() / sb
    rho = np.corrcoef(a, b)[0, 1]
    theta = (2 - 2 * rho + 0.5 * (ra ** 2 + rb ** 2 - 2 * ra * rb * rho ** 2)) / T
    return float((ra - rb) / math.sqrt(theta)) if theta > 0 else float("nan")


def _usd_prices(con, symbol: str, ccy: str) -> pd.Series:
    px = pd.Series(dict(con.execute("SELECT date, adj_close FROM prices WHERE symbol=? AND adj_close IS NOT NULL",
                                    (symbol,)).fetchall()), dtype=float)
    if px.empty:
        return px
    px.index = pd.to_datetime(px.index)
    px = clean_prices(px.sort_index())
    major, _ = yahoo.normalise_ccy(ccy)
    if major != "USD":
        fx = pd.Series(yahoo.fx_history_to_usd(ccy), dtype=float)
        if fx.empty:
            return pd.Series(dtype=float)
        fx.index = pd.to_datetime(fx.index)
        fx = fx.reindex(px.index.union(fx.index)).sort_index().ffill().reindex(px.index)
        px = px * fx
    return px.dropna()


def run(con, log=print) -> dict:
    con.executescript(SCHEMA)
    cfg, wf = load("models")["portfolio"], load("models")["walk_forward"]
    W, hold = wf["window_days"], cfg["rebalance_days"]
    cells = defaultdict(list)
    for r in con.execute("""SELECT c.id, l.symbol, l.currency,
              (SELECT value FROM stock_tags t WHERE t.company_id=c.id AND t.tag='market_class') mc,
              (SELECT value FROM stock_tags t WHERE t.company_id=c.id AND t.tag='sector_group') sg,
              (SELECT CAST(value AS REAL) FROM stock_tags t WHERE t.company_id=c.id AND t.tag='market_cap_usd') mcap
            FROM companies c JOIN listings l ON l.company_id=c.id AND l.is_home=1 WHERE c.status='active'"""):
        cells[f"{r['mc']} | {r['sg']}"].append(dict(r))
    usd_rf, _ = rates.series("USD")
    con.execute("DELETE FROM portfolio_tests")
    out = {}
    for cell, members in sorted(cells.items()):
        members = sorted(members, key=lambda m: -(m["mcap"] or 0))[:cfg["max_assets"]]
        px = pd.DataFrame({m["symbol"]: _usd_prices(con, m["symbol"], m["currency"]) for m in members})
        px = px.sort_index()
        px = px[px.index.dayofweek < 5].ffill(limit=5)
        if len(px) < W + hold:
            continue
        rets = px.pct_change(fill_method=None)
        rf = usd_rf.reindex(px.index.union(usd_rf.index)).sort_index().ffill().reindex(px.index).fillna(0.0)
        q = {"MPT (mean-variance)": [], "1/N equal weight": []}
        rf_q, n_assets = [], []
        for i in origin_grid(px.index, str(wf["first_origin"]), hold):
            if i < W or i + hold >= len(px):
                continue
            win = rets.iloc[i - W + 1:i + 1]
            ok = [c for c in px.columns if win[c].notna().mean() > 0.95 and np.isfinite(px[c].iloc[i])
                  and np.isfinite(px[c].iloc[i + hold])]
            if len(ok) < 3:
                continue
            X = win[ok].fillna(0.0).values
            rf_h = float(rf.iloc[i]) * hold / 252
            w = mean_variance_weights(X.mean(axis=0) * hold, np.cov(X.T) * hold, rf_h, cfg["gamma"])
            fwd = (px[ok].iloc[i + hold] / px[ok].iloc[i] - 1).values
            q["MPT (mean-variance)"].append(float(w @ fwd + (1 - w.sum()) * rf_h))
            q["1/N equal weight"].append(float(fwd.mean()))
            rf_q.append(rf_h)
            n_assets.append(len(ok))
        if len(rf_q) < 8:
            continue
        rf_q = np.array(rf_q)
        ex = {k: np.array(v) - rf_q for k, v in q.items()}
        z = memmel_z(ex["MPT (mean-variance)"], ex["1/N equal weight"])
        per_year = 252 / hold
        for k, v in q.items():
            v = np.array(v)
            cagr = float(np.prod(1 + v) ** (per_year / len(v)) - 1)
            vol = float(v.std(ddof=1) * math.sqrt(per_year))
            sh = float(ex[k].mean() / ex[k].std(ddof=1) * math.sqrt(per_year)) if ex[k].std(ddof=1) > 0 else None
            con.execute("INSERT INTO portfolio_tests VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (cell, k, len(v), float(np.mean(n_assets)), cagr, vol, sh, float(v.min()),
                         z if k.startswith("MPT") and math.isfinite(z) else None, now()))
        out[cell] = round(z, 2) if math.isfinite(z) else None
        log(f"  portfolio {cell}: {len(rf_q)} quarters, MPT vs 1/N Sharpe z = {out[cell]}")
    con.commit()
    return {"cells": len(out)}
