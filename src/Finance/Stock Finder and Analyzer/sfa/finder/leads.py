"""Lead scoring for Stage 1.

Three kinds of lead:
  listed        universe companies: score = news composite (rules A–D) blended with
                the quant-model signal of the model the Milestone 2 leaderboard chose
                (tanh of expected excess return over one 1-year standard deviation × scale)
  new_listing   IPOs that have started trading in the last year: IPO-news sentiment
                blended with a peer-proxy forecast from the same models
  ipo_pipeline  companies planning, filing for or pricing an IPO: IPO-news sentiment,
                weighted up by how many separate stories mention them
Every lead carries its investment routes for an Indian resident and the evidence.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict

from ..classify import market as M
from ..classify.sector import map_sector
from ..config import load, venues
from ..data import yahoo
from ..db import now
from . import init, peers, routes, rules
from .linking import Linker


def model_signal(growth_detail: dict | None, growth_value) -> tuple[float | None, dict]:
    """(−1…+1, info) from the stored growth_1y prediction."""
    if not growth_detail or growth_value is None:
        return None, {}
    cfg = load("finder")["leads"]
    try:
        exp = float(growth_value)
        lo, hi = growth_detail["range_5_95"]
        sd = (math.log(1 + hi) - math.log(1 + max(lo, -0.99))) / 3.29
    except (KeyError, TypeError, ValueError):
        return None, {}
    rf = growth_detail.get("rf_annual") or 0.0
    if not math.isfinite(sd) or sd <= 0:
        return None, {}
    sd = max(sd, cfg.get("min_sd_1y", 0.10))
    sig = math.tanh((exp - rf) / (cfg["model_scale"] * sd))
    return sig, {"model": growth_detail.get("model"), "expected_1y": exp, "rf": rf, "sd_1y": sd,
                 "p_beat_cash": growth_detail.get("p_beat_cash"), "basis": growth_detail.get("basis")}


def blend(news: float | None, model: float | None) -> float | None:
    w = load("finder")["leads"]["weights"]
    parts = [(w["news"], news), (w["model"], model)]
    den = sum(a for a, v in parts if v is not None)
    return sum(a * v for a, v in parts if v is not None) / den if den else None


def _tags(con, cid):
    return {r["tag"]: (r["value"], json.loads(r["detail"] or "{}")) for r in
            con.execute("SELECT tag, value, detail FROM stock_tags WHERE company_id=?", (cid,))}


def _listings(con, cid):
    return [dict(r) for r in con.execute("SELECT symbol, venue, country, structure, share_type, is_home FROM listings "
                                         "WHERE company_id=?", (cid,))]


def build(con, log=print) -> dict:
    init(con)
    cfg = load("finder")
    stamp = now()
    seen = {r["lead_key"]: r["first_seen"] for r in con.execute("SELECT lead_key, first_seen FROM finder_leads")}
    con.execute("UPDATE finder_leads SET status='stale'")
    n = Counter()

    def put(key, **v):
        con.execute("INSERT OR REPLACE INTO finder_leads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (key, v["kind"], v.get("company_id"), v["name"], v.get("symbol"), v.get("exchange"),
                     v.get("country"), v.get("market_class"), v.get("sector_group"), v.get("stage"), v.get("score"),
                     v.get("news_score"), v.get("model_score"), v.get("n_news", 0), json.dumps(v.get("rules") or {}),
                     json.dumps(v.get("model") or {}), json.dumps(v.get("routes") or []),
                     json.dumps(v.get("evidence") or {}), seen.get(key, stamp), stamp, "active"))
        n[v["kind"]] += 1

    # ---- listed companies
    for c in con.execute("SELECT id, name, home_symbol, home_venue, home_country FROM companies WHERE status='active'"):
        t = _tags(con, c["id"])
        comp = t.get("news_composite")
        if not comp:
            continue
        det = comp[1]
        n_news = det.get("items_company", 0) + det.get("items_competitors", 0)
        if n_news < cfg["leads"]["min_news_items"]:
            continue
        news = float(comp[0]) if comp[0] not in (None, "None") else None
        g = t.get("growth_1y")
        msig, minfo = model_signal(g[1] if g else None, g[0] if g else None)
        score = blend(news, msig)
        if score is None:
            continue
        lst = _listings(con, c["id"])
        home = next(l for l in lst if l["is_home"])
        sg = (t.get("sector_group") or (None,))[0]
        rts = routes.for_listed(lst, home, sg)
        put(f"listed:{c['id']}", kind="listed", company_id=c["id"], name=c["name"], symbol=c["home_symbol"],
            exchange=c["home_venue"], country=c["home_country"], market_class=(t.get("market_class") or (None,))[0],
            sector_group=sg, stage="listed", score=score, news_score=news, model_score=msig, n_news=n_news,
            rules={r: (t.get(f"news_{r}") or (None, {}))[0] for r in "ABCD"} | {"verdict": det.get("verdict"),
                                                                                  "peers": det.get("peers")},
            model=minfo, routes=rts, evidence=rules.evidence(con, c["id"]))

    # ---- IPO pipeline and new listings
    lk = Linker(con)
    ev = defaultdict(list)
    for r in con.execute("""SELECT e.*, s.score FROM ipo_events e LEFT JOIN news_sentiment s ON s.news_id=e.news_id
                            WHERE e.company_id IS NULL"""):
        ev[r["name_key"]].append(dict(r))
    order = {"planning": 0, "filed": 1, "priced": 2, "listed": 3}
    for key, es in ev.items():
        es.sort(key=lambda e: (e["event_date"] or "", order[e["stage"]]))
        last = max(es, key=lambda e: (order[e["stage"]], e["event_date"] or ""))
        sents = [e["score"] for e in es if e["score"] is not None]
        news = sum(sents) / len(sents) if sents else None
        stories = len({e["title"].lower() for e in es})
        conf = 1 - 0.5 ** stories                         # more separate stories → more weight
        inds = Counter(ind for e in es for ind, _ in lk.industries_in(e["title"]))
        sg = None
        if inds:
            ind = inds.most_common(1)[0][0]
            sec = con.execute("SELECT sector FROM companies WHERE industry LIKE ? LIMIT 1",
                              (ind.replace(" - ", "%"),)).fetchone()
            sg = map_sector(sec["sector"] if sec else None, ind).get("group_name") if sec else None
        country = next((e["country_hint"] for e in es if e["country_hint"]), None)
        if not country and " India" in f" {last['name']}":
            country = "IN"
        evidence = {"IPO": [{"title": e["title"], "source": e["source"], "date": e["event_date"], "stage": e["stage"],
                             "sentiment": None if e["score"] is None else round(e["score"], 2)} for e in es[-5:]]}
        sym = next((e["symbol"] for e in es if e["symbol"]), None)
        if sym:
            info = next((q for q in yahoo.search(sym, n=3) if q["symbol"] == sym), {})
            v = venues().resolve(sym, info.get("exchange")) or {}
            country = v.get("country") or country
            mc = M.CLASSES[M.current_class(country)] if country else None
            sm = map_sector(info.get("sector"), info.get("industry"))
            sg = sm.get("group_name") if sm.get("group") else sg
            fc = peers.forecast(con, sym, info.get("industry"), info.get("sector"), mc, country, v.get("currency"))
            msig, minfo = None, {}
            if fc:
                h = fc["horizons"].get("1 year", {})
                msig, minfo = model_signal({"range_5_95": h.get("range_5_95"), "rf_annual": 0.0,
                                            "model": h.get("model"), "basis": fc["basis"],
                                            "p_beat_cash": h.get("p_beat_cash")}, h.get("exp_return"))
                minfo["peers"] = fc["peers"]
                minfo["horizons"] = fc["horizons"]
            lst = [{"symbol": sym, "venue": v.get("id"), "country": country, "structure": "primary",
                    "share_type": "common", "is_home": 1}]
            put(f"new:{key}", kind="new_listing", name=last["name"], symbol=sym, exchange=v.get("id"), country=country,
                market_class=mc, sector_group=sg, stage="listed",
                score=blend(news * conf if news is not None else None, msig), news_score=news, model_score=msig,
                n_news=stories, model=minfo, routes=routes.for_listed(lst, lst[0], sg) if v else [],
                evidence=evidence)
        else:
            put(f"ipo:{key}", kind="ipo_pipeline", name=last["name"], country=country, sector_group=sg,
                stage=last["stage"], score=None if news is None else news * conf, news_score=news, n_news=stories,
                routes=routes.for_unlisted(last["name"], last["stage"], country, sg), evidence=evidence)
    con.commit()
    return dict(n)


def top(con, kind: str, k: int) -> list[dict]:
    cond = "" if kind == "ipo_pipeline" else " AND score IS NOT NULL"     # unscored IPO names are still leads
    rows = con.execute(f"SELECT * FROM finder_leads WHERE status='active' AND kind=?{cond} "
                       "ORDER BY score IS NULL, score DESC LIMIT ?", (kind, k)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for f in ("rules", "model", "routes", "evidence"):
            d[f] = json.loads(d[f] or "null")
        out.append(d)
    return out
