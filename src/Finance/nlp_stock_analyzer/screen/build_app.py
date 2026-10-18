"""Combine selection.json and results/*.json into the dashboard web app.

Writes app/index.html (data embedded, works offline) and app/data.json.
Serve it with:  python serve.py   →  http://localhost:8000
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

HERE = Path(__file__).parent
APP = HERE / "app"


def r(v, n=4):
    return None if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else round(v, n)


def index_quote(sym):
    f = HERE / "cache" / "chart" / f"{sym}.json"
    if not f.exists():
        return None
    c = json.loads(f.read_text())
    pts = [(t, v) for t, v in zip(c["t"], c["c"]) if v]
    if len(pts) < 2:
        return None
    (t1, v1), (_, v0) = pts[-1], pts[-2]
    y = [v for t, v in pts if t <= t1 - 365 * 86400]
    return {"level": r(v1, 2), "change": r(v1 / v0 - 1), "date": str(datetime.fromtimestamp(t1, timezone.utc).date()),
            "ret_1y": r(v1 / y[-1] - 1) if y else None}


def strat_key(s):
    if s["model"].startswith(("MPT", "Buy")):
        return s["model"] if s["model"].startswith("MPT") else "Buy & hold"
    return f'{s["model"]} · {s["rule"]}'


def summarise_stock(res):
    out = {"days": res.get("days"), "first": res.get("first"), "note": res.get("note"),
           "benchmark": res.get("index_benchmark"), "rf_series": res.get("rf_series")}
    bt = res.get("backtest")
    if bt:
        out["period"] = bt.get("period")
        out["horizons"] = {}
        for h, hz in bt["horizons"].items():
            bh = next(s for s in hz["strategies"] if s["model"] == f"Buy & hold {res['ticker']}")
            strats = []
            for s in hz["strategies"]:
                if s["rule"] == "benchmark":
                    continue
                strats.append({"k": strat_key(s), "sharpe": r(s.get("sharpe"), 3), "cagr": r(s.get("cagr")),
                               "dd": r(s.get("max_drawdown")), "exp": r(s.get("avg_exposure"), 3)})
            eligible = [s for s in strats if not s["k"].startswith("Black-Scholes")
                        and (s["exp"] or 0) > 0.05 and s["sharpe"] is not None]
            eligible.sort(key=lambda s: -s["sharpe"])
            best = eligible[0] if eligible else None
            curves = hz.get("curves", {})
            keep = {}
            for name, cv in curves.items():
                if name.startswith("Buy & hold") and res["ticker"] in name:
                    keep["Buy & hold"] = cv
            if best:
                # curves are stored for the sized rule (and MPT); show the best model's sized curve
                bm = best["k"].split(" · ")[0]
                for n, cv in curves.items():
                    if n == bm or (bm.startswith("MPT") and n.startswith("MPT")):
                        keep[f"{bm} (sized)" if not bm.startswith("MPT") else bm] = cv
            out["horizons"][h] = {
                "bh": {"sharpe": r(bh.get("sharpe"), 3), "cagr": r(bh.get("cagr")), "dd": r(bh.get("max_drawdown"))},
                "strategies": strats,
                "ranked": [s["k"] for s in eligible],
                "best": best,
                "skill": [{"m": s["model"], "hit": r(s["hit_rate"], 3), "cov": r(s["coverage90"], 3),
                           "crps": r(s["crps"], 5), "n": s["n"]} for s in hz["skill"]],
                "curves": keep,
            }
    cur = res.get("current")
    if cur:
        models = []
        for m in cur["models"]:
            models.append({"m": m["model"], "h": {h: {k: r(v, 4) for k, v in hz.items()}
                                                  for h, hz in m["horizons"].items()}})
        cons = {}
        for h in (models[0]["h"] if models else {}):
            vals = [m["h"][h]["median_price"] for m in models if not m["m"].startswith("Black-Scholes")]
            pb = [m["h"][h]["p_beat_cash"] for m in models if not m["m"].startswith("Black-Scholes")]
            cons[h] = {"median_ret": r(median(vals) / cur["price"] - 1) if vals else None,
                       "p_beat_cash": r(median(pb), 3) if pb else None}
        out["current"] = {"as_of": cur["as_of"], "price": r(cur["price"], 4), "rf": r(cur["rf"], 4),
                          "models": models, "consensus": cons,
                          "options": [{k: r(v, 4) if isinstance(v, float) else v for k, v in o.items()}
                                      for o in cur["options"]],
                          "mpt": {k: r(v, 3) for k, v in (cur.get("mpt") or {}).get("weights", {}).items()}}
    return out


def index_league(stocks, h):
    """Average within-stock Sharpe rank of each strategy across an index's stocks."""
    ranks, beat, n = {}, {}, {}
    for s in stocks:
        hz = (s.get("model") or {}).get("horizons", {}).get(h)
        if not hz:
            continue
        for i, k in enumerate(hz["ranked"], 1):
            ranks.setdefault(k, []).append(i)
            n[k] = n.get(k, 0) + 1
            st = next(x for x in hz["strategies"] if x["k"] == k)
            beat[k] = beat.get(k, 0) + (1 if st["sharpe"] > (hz["bh"]["sharpe"] or -9) else 0)
    total = sum(1 for s in stocks if (s.get("model") or {}).get("horizons", {}).get(h))
    rows = [{"k": k, "avg_rank": r(sum(v) / len(v), 2), "stocks": n[k], "beat": beat[k]}
            for k, v in ranks.items() if n[k] >= max(1, math.ceil(0.6 * total))]
    rows.sort(key=lambda x: x["avg_rank"])
    return {"rows": rows, "modelled": total}


def main():
    sel = json.loads((HERE / "selection.json").read_text())
    res_dir = HERE / "results"
    cache = {}
    data = {"built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "indexes": []}
    for sym, ix in sel.items():
        stocks = []
        for c in ix["companies"]:
            t = c["ticker"]
            if t not in cache:
                f = res_dir / f"{t}.json"
                cache[t] = summarise_stock(json.loads(f.read_text())) if f.exists() else None
            stocks.append({
                "rank": c["rank"], "t": t, "name": c["name"], "ccy": c.get("currency"),
                "mcap": r(c.get("mcap_usd"), 0), "rev": r(c.get("revenue_usd"), 0),
                "growth": r(c.get("rev_growth")), "margin": r(c.get("net_margin")), "pe": r(c.get("pe"), 2),
                "growth_basis": c.get("growth_basis"), "score": r(c.get("score"), 4),
                "pct": {k: r(c.get(f"pct_{k}"), 3) for k in ("mcap_usd", "revenue_usd", "rev_growth", "net_margin")},
            })
        data["indexes"].append({
            "sym": sym, "name": ix["name"], "region": ix["region"], "ccy": ix["ccy"],
            "pool": ix["pool_size"], "pool_complete": ix["pool_complete"], "quote": index_quote(sym),
            "stocks": stocks,
            "league": {h: index_league(stocks, h) for h in ("3 months", "1 year")},
        })
    # each stock's model results are stored once, even if it is in several indexes
    data["models"] = {t: m for t, m in cache.items() if m}
    APP.mkdir(exist_ok=True)
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    (APP / "data.json").write_text(blob, encoding="utf-8")
    tpl = (HERE / "app_template.html").read_text(encoding="utf-8")
    (APP / "index.html").write_text(tpl.replace("__DATA__", blob.replace("</", "<\\/")), encoding="utf-8")
    # phone copy: growth curves thinned to quarterly points
    lite = json.loads(blob)
    for m in lite["models"].values():
        for hz in (m.get("horizons") or {}).values():
            for name, cv in hz["curves"].items():
                keep = [i for i in range(len(cv["d"])) if i % 3 == 0 or i == len(cv["d"]) - 1]
                hz["curves"][name] = {"d": [cv["d"][i] for i in keep], "v": [cv["v"][i] for i in keep]}
    lblob = json.dumps(lite, separators=(",", ":"), ensure_ascii=False)
    (APP / "dashboard_mobile.html").write_text(tpl.replace("__DATA__", lblob.replace("</", "<\\/")), encoding="utf-8")
    print(f"app/dashboard_mobile.html written: {len(lblob) / 1e6:.1f} MB of data")
    n_mod = sum(1 for v in cache.values() if v and v.get("horizons"))
    print(f"app/index.html written: {len(data['indexes'])} indexes, {len(cache)} stocks "
          f"({n_mod} backtested), {len(blob) / 1e6:.1f} MB of data")


if __name__ == "__main__":
    main()
