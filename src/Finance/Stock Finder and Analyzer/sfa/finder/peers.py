"""Peer-proxy forecasts for companies too new to model on their own prices.

A new listing has too little history for the walk-forward models, so its return
history is stood in for by its peers: the equal-weight daily log return of the largest
universe companies in the same industry (else sector group) and market class. When
the stock has at least `min_history_days_own` of its own trading, the proxy is
rescaled to the stock's own volatility. The model chosen by the Milestone 2
leaderboard for that market class × sector group then forecasts 3 months and 1 year.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..classify.sector import map_sector, norm_industry
from ..config import load
from ..data import rates, yahoo
from ..models import leaderboard, zoo
from ..models.walkforward import clean_prices


def peers_for(con, industry: str | None, sector: str | None, market_class: str | None, k: int = 8) -> list[dict]:
    rows = con.execute("""SELECT c.id, c.name, c.industry, c.sector, l.symbol,
              (SELECT value FROM stock_tags t WHERE t.company_id=c.id AND t.tag='market_class') mc,
              (SELECT CAST(value AS REAL) FROM stock_tags t WHERE t.company_id=c.id AND t.tag='market_cap_usd') mcap
            FROM companies c JOIN listings l ON l.company_id=c.id AND l.is_home=1 WHERE c.status='active'""").fetchall()
    ind = norm_industry(industry)
    grp = map_sector(sector, industry).get("group")
    same_ind = [dict(r) for r in rows if norm_industry(r["industry"]) == ind]
    pick = [r for r in same_ind if r["mc"] == market_class] or same_ind
    if len(pick) < 3:
        pick = [dict(r) for r in rows if map_sector(r["sector"], r["industry"]).get("group") == grp
                and (r["mc"] == market_class or market_class is None)]
    return sorted(pick, key=lambda r: -(r["mcap"] or 0))[:k]


def proxy_returns(con, peers: list[dict], days: int = 1260) -> pd.Series:
    cols = {}
    for p in peers:
        px = pd.Series(dict(con.execute("SELECT date, adj_close FROM prices WHERE symbol=? AND adj_close IS NOT NULL",
                                        (p["symbol"],)).fetchall()), dtype=float)
        if len(px) > 260:
            px.index = pd.to_datetime(px.index)
            cols[p["symbol"]] = np.log(clean_prices(px.sort_index())).diff()
    if not cols:
        return pd.Series(dtype=float)
    df = pd.DataFrame(cols).dropna(how="all")
    return df.mean(axis=1, skipna=True).dropna().iloc[-days:]


def forecast(con, symbol: str, industry: str | None, sector: str | None, market_class: str | None,
             country: str | None, currency: str | None) -> dict | None:
    cfg = load("finder")["ipo"]
    peers = peers_for(con, industry, sector, market_class)
    r = proxy_returns(con, peers)
    if len(r) < 500:
        return None
    own = yahoo.chart(symbol, start=0) if symbol else None
    own_r = None
    if own and own["t"]:
        s = pd.Series(own["adj"], index=pd.to_datetime(own["t"], unit="s"), dtype=float).dropna()
        own_r = np.log(clean_prices(s)).diff().dropna()
    basis = f"equal-weight proxy of {len(peers)} peers"
    rv = r.values.copy()
    if own_r is not None and len(own_r) >= cfg["min_history_days_own"]:
        scale = own_r.std() / rv.std() if rv.std() > 0 else 1.0
        rv = (rv - rv.mean()) * scale + rv.mean()
        basis += f", rescaled to the stock's own volatility ({len(own_r)} days)"
    sg = map_sector(sector, industry).get("group_name")
    erp, _ = zoo.erp_for(country, market_class)
    rf_s, _ = rates.series(currency)
    rf0 = float(rf_s.iloc[-1]) if len(rf_s) else 0.0
    out = {"basis": basis, "peers": [p["name"] for p in peers], "horizons": {}}
    for hn, h in load("models")["walk_forward"]["horizons"].items():
        mid, why = _cell_choice(con, market_class, sg, hn)
        m = zoo.make(mid, erp).fit(rv, rf0)
        f = m.forecast(h, 2000, seed=11)
        q05, q50, q95 = f.quantiles((0.05, 0.5, 0.95))
        out["horizons"][hn] = {"model": zoo.name(mid), "why": why, "exp_return": f.exp_return,
                               "median_return": math.exp(q50) - 1, "range_5_95": [math.exp(q05) - 1, math.exp(q95) - 1],
                               "p_beat_cash": f.prob_above(rf0 * h / 252)}
    return out


def _cell_choice(con, market_class, sector_group, horizon):
    for gt, gk in (("cell", f"{market_class} | {sector_group}"), ("market_class", market_class)):
        r = con.execute("SELECT selected, basis FROM model_choice WHERE group_type=? AND group_key=? AND horizon=?",
                        (gt, gk, horizon)).fetchone() if con.execute(
            "SELECT name FROM sqlite_master WHERE name='model_choice'").fetchone() else None
        if r:
            return r["selected"], f"{gt.replace('_', ' ')} {gk}: {r['basis']}"
    return leaderboard.baseline_for(horizon, market_class), "baseline rule"
