"""Leaderboard: which model forecasts best, by group and horizon.

Groups: every company; each home exchange; each sector group; each market class;
each cell (market class × sector group); and all companies together.

For each group, horizon and model: mean CRPS, skill versus the group's baseline
(1 − CRPS_model / CRPS_baseline), direction hit rate, 90% interval coverage, bias.
The baseline comes from config (models.yaml → baseline_rule). A candidate replaces it
only on a clear out-of-sample win: positive skill and a Diebold–Mariano statistic of
at least `promotion.dm_t`. The DM test uses the loss difference averaged over the
group's stocks on each forecast date, a Newey–West variance with lags for
overlapping horizons, and the Harvey–Leybourne–Newbold small-sample correction.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from ..config import load
from ..db import now

SCHEMA = """
CREATE TABLE IF NOT EXISTS leaderboard (
    group_type TEXT, group_key TEXT, horizon TEXT, model TEXT,
    n_forecasts INTEGER, n_origins INTEGER, n_stocks INTEGER,
    crps REAL, skill REAL, dm_t REAL, hit REAL, cover90 REAL, bias REAL,
    is_baseline INTEGER, selected INTEGER, as_of TEXT,
    PRIMARY KEY (group_type, group_key, horizon, model)
);
CREATE TABLE IF NOT EXISTS model_choice (
    group_type TEXT, group_key TEXT, horizon TEXT, baseline TEXT, selected TEXT, basis TEXT,
    best_raw TEXT, n_origins INTEGER, n_stocks INTEGER, as_of TEXT,
    PRIMARY KEY (group_type, group_key, horizon)
);
"""


def baseline_for(horizon: str, market_class: str | None) -> str:
    rule = load("models")["baseline_rule"][horizon]
    return rule.get(market_class or "", rule["default"])


def dm_stat(d: np.ndarray, lag: int) -> float:
    """Diebold–Mariano t-statistic for mean(d) > 0 with Newey–West (Bartlett) variance
    and the Harvey–Leybourne–Newbold correction. d: loss(baseline) − loss(candidate)."""
    d = np.asarray(d, float)
    d = d[np.isfinite(d)]
    T = len(d)
    if T < 3:
        return float("nan")
    m = d.mean()
    e = d - m
    var = e @ e / T
    for k in range(1, min(lag, T - 1) + 1):
        var += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / T
    if var <= 0:
        return float("inf") if m > 0 else float("-inf") if m < 0 else 0.0
    t = m / math.sqrt(var / T)
    h = lag + 1
    corr = (T + 1 - 2 * h + h * (h - 1) / T) / T
    return float(t * math.sqrt(corr)) if corr > 0 else float(t)


def _overlap_lag(h_days: int) -> int:
    step = load("models")["walk_forward"]["step_days"]
    return max(0, math.ceil(h_days / step) - 1)


def evaluate(rows: list[dict], baseline: str, h_days: int) -> tuple[list[dict], dict]:
    """rows: scored forecasts of one group & horizon {company_id, origin, model, crps, hit, cover90, err}.
    Returns per-model stats and the choice."""
    cfg = load("models")["promotion"]
    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r)
    # loss per (origin, company) for each model
    # forecast dates fall on each exchange's first trading day of the month, so they are
    # matched across exchanges by month
    loss = {m: {(r["origin"][:7], r["company_id"]): r["crps"] for r in rs} for m, rs in by_model.items()}
    base = loss.get(baseline, {})
    lag = _overlap_lag(h_days)
    out = []
    for m, rs in by_model.items():
        crps = np.array([r["crps"] for r in rs])
        common = [k for k in loss[m] if k in base]
        skill = dm = float("nan")
        if common and m != baseline:
            b = np.array([base[k] for k in common])
            c = np.array([loss[m][k] for k in common])
            skill = 1 - c.mean() / b.mean() if b.mean() > 0 else float("nan")
            per_origin = defaultdict(list)
            for k, bv, cv in zip(common, b, c):
                per_origin[k[0]].append(bv - cv)
            d = np.array([np.mean(per_origin[o]) for o in sorted(per_origin)])
            dm = dm_stat(d, lag)
        elif m == baseline:
            skill, dm = 0.0, 0.0
        out.append({"model": m, "n_forecasts": len(rs), "n_origins": len({r["origin"][:7] for r in rs}),
                    "n_stocks": len({r["company_id"] for r in rs}), "crps": float(crps.mean()),
                    "skill": skill, "dm_t": dm, "hit": float(np.mean([r["hit"] for r in rs])),
                    "cover90": float(np.mean([r["cover90"] for r in rs])),
                    "bias": float(np.mean([r["err"] for r in rs])), "is_baseline": int(m == baseline)})
    n_orig = len({r["origin"][:7] for r in rows})
    n_stk = len({r["company_id"] for r in rows})
    best_raw = min(out, key=lambda x: x["crps"])["model"] if out else None
    choice = {"baseline": baseline, "selected": baseline, "best_raw": best_raw, "n_origins": n_orig,
              "n_stocks": n_stk, "basis": "baseline (no clear out-of-sample win)"}
    if baseline not in by_model:
        choice["basis"] = "baseline has no forecasts; best raw CRPS used"
        choice["selected"] = best_raw
    elif n_orig < cfg["min_origins"]:
        choice["basis"] = f"baseline (only {n_orig} forecast dates)"
    else:
        wins = [x for x in out if x["model"] != baseline and x["skill"] > 0 and x["dm_t"] >= cfg["dm_t"]]
        if wins:
            w = max(wins, key=lambda x: x["skill"])
            choice["selected"] = w["model"]
            choice["basis"] = f"beats baseline: skill {w['skill']:+.1%}, DM t = {w['dm_t']:.2f}"
    for x in out:
        x["selected"] = int(x["model"] == choice["selected"])
    return out, choice


def build(con, log=print) -> dict:
    con.executescript(SCHEMA)
    H = load("models")["walk_forward"]["horizons"]
    meta = {}
    for r in con.execute("""SELECT c.id, c.home_venue,
               (SELECT value FROM stock_tags t WHERE t.company_id=c.id AND t.tag='market_class') mc,
               (SELECT value FROM stock_tags t WHERE t.company_id=c.id AND t.tag='sector_group') sg
            FROM companies c WHERE c.status='active'"""):
        meta[r["id"]] = dict(r)
    scored = defaultdict(list)          # horizon -> rows
    for r in con.execute("SELECT company_id, origin, model, horizon, crps, hit, cover90, err FROM forecast_scores "
                         "WHERE crps IS NOT NULL"):
        if r["company_id"] in meta:
            scored[r["horizon"]].append(dict(r))
    con.execute("DELETE FROM leaderboard")
    con.execute("DELETE FROM model_choice")
    stamp = now()
    n_groups = 0
    for hn, rows in scored.items():
        groups = defaultdict(list)
        for r in rows:
            m = meta[r["company_id"]]
            for gt, gk in (("all", "All companies"), ("market_class", m["mc"]), ("sector_group", m["sg"]),
                           ("cell", f"{m['mc']} | {m['sg']}"), ("exchange", m["home_venue"]),
                           ("company", str(r["company_id"]))):
                groups[(gt, gk)].append(r)
        for (gt, gk), grows in groups.items():
            if gt in ("cell", "market_class", "exchange", "company"):
                mc = gk.split(" | ")[0] if gt == "cell" else gk if gt == "market_class" else \
                    meta[grows[0]["company_id"]]["mc"]
            else:
                mc = None
            if gt == "cell" and len({r["company_id"] for r in grows}) < load("models")["promotion"]["min_stocks_cell"]:
                continue
            stats, choice = evaluate(grows, baseline_for(hn, mc), H[hn])
            for s in stats:
                con.execute("INSERT INTO leaderboard VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (gt, gk, hn, s["model"], s["n_forecasts"], s["n_origins"], s["n_stocks"], s["crps"],
                             _f(s["skill"]), _f(s["dm_t"]), s["hit"], s["cover90"], s["bias"], s["is_baseline"],
                             s["selected"], stamp))
            con.execute("INSERT INTO model_choice VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (gt, gk, hn, choice["baseline"], choice["selected"], choice["basis"], choice["best_raw"],
                         choice["n_origins"], choice["n_stocks"], stamp))
            n_groups += 1
    con.commit()
    return {"groups": n_groups, "scored_forecasts": sum(len(v) for v in scored.values())}


def _f(v):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else float(v)


def choice_for_company(con, cid: int, horizon: str) -> tuple[str, str]:
    """Model to use for a company's prediction: its own record if it shows a clear win
    over the baseline, otherwise its cell's choice, then its market class's."""
    r = con.execute("SELECT selected, baseline, basis FROM model_choice WHERE group_type='company' AND group_key=? "
                    "AND horizon=?", (str(cid), horizon)).fetchone()
    if r and r["selected"] != r["baseline"]:
        return r["selected"], f"company: {r['basis']}"
    tags = {t["tag"]: t["value"] for t in con.execute(
        "SELECT tag, value FROM stock_tags WHERE company_id=? AND tag IN ('market_class','sector_group')", (cid,))}
    mc, sg = tags.get("market_class"), tags.get("sector_group")
    for gt, gk in (("cell", f"{mc} | {sg}"), ("market_class", mc)):
        r = con.execute("SELECT selected, basis FROM model_choice WHERE group_type=? AND group_key=? AND horizon=?",
                        (gt, gk, horizon)).fetchone()
        if r:
            return r["selected"], f"{gt.replace('_', ' ')} {gk}: {r['basis']}"
    return baseline_for(horizon, mc), "baseline rule (no leaderboard yet)"
