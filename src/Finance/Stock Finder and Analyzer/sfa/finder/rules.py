"""Rules A–D: one news score per rule per company, recency-weighted FinBERT sentiment.

A  Market sentiment              stories that mention the company
B  Competition & news releases   the company's own releases (+) and its competitors'
                                 news (sign flipped: a rival's good news is a headwind).
                                 Competitors = the largest companies in the same industry.
C  Manufacturing industry        stories about the supply chain its industry depends on
D  Customers                     stories about the customers and end markets it sells to

Each score runs from −1 to +1; an article `half_life_days` old counts half. A rule
needs `min_items_for_signal` stories. The composite re-weights the rules that have a
signal. Results are stored as stock tags (heading "news") and in rule_scores.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone

from ..classify.sector import norm_industry
from ..config import load
from ..db import now, set_tag
from . import init

RULES = {"A": "A_market_sentiment", "B": "B_competition", "C": "C_manufacturing", "D": "D_customers"}
LABEL = {"A": "Market sentiment", "B": "Competition & news releases", "C": "Manufacturing industry", "D": "Customers"}


def recency_weight(published: str | None, ref: datetime, half_life: float) -> float:
    if not published:
        return 0.5
    try:
        d = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return 0.5
    age = max(0.0, (ref - d).total_seconds() / 86400)
    return 0.5 ** (age / half_life)


def weighted(items: list[tuple[float, float, int]]) -> float | None:
    """items: (sentiment, weight, direction) → weighted mean of direction × sentiment."""
    sw = sum(w for _, w, _ in items)
    return sum(s * w * d for s, w, d in items) / sw if sw > 0 else None


def composite(scores: dict[str, tuple[float | None, int]], weights: dict[str, float], min_n: int) -> float | None:
    num = den = 0.0
    for r, key in RULES.items():
        s, n = scores.get(r, (None, 0))
        if s is not None and n >= min_n:
            num += weights[key] * s
            den += weights[key]
    return num / den if den > 0 else None


def verdict(score: float | None) -> str:
    t = load("finder")["rules"]["thresholds"]
    if score is None:
        return "No signal"
    return "Bullish" if score >= t["bullish"] else "Bearish" if score <= t["bearish"] else "Neutral"


def compute(con, log=print) -> dict:
    init(con)
    cfg = load("finder")
    ncfg, rcfg = cfg["news"], cfg["rules"]
    ref = datetime.now(timezone.utc)
    cutoff = (ref.timestamp() - ncfg["lookback_days"] * 86400)
    cut_iso = datetime.fromtimestamp(cutoff, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rel = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, rcfg["release_keywords"])) + r")(?!\w)", re.I)
    items = {r["id"]: dict(r) for r in con.execute(
        """SELECT n.id, n.title, n.published, s.score FROM news_items n JOIN news_sentiment s ON s.news_id=n.id
           WHERE COALESCE(n.published, n.fetched) >= ?""", (cut_iso,))}
    by_target = defaultdict(list)
    for r in con.execute("SELECT news_id, target, rule FROM news_links WHERE rule IN ('A','C','D')"):
        if r["news_id"] in items:
            by_target[(r["target"], r["rule"])].append(r["news_id"])
    comps = {r["id"]: dict(r) for r in con.execute(
        """SELECT c.id, c.name, c.industry,
                  (SELECT CAST(value AS REAL) FROM stock_tags t WHERE t.company_id=c.id AND t.tag='market_cap_usd') mcap
           FROM companies c WHERE status='active'""")}
    by_ind = defaultdict(list)
    for c in comps.values():
        by_ind[norm_industry(c["industry"])].append(c)
    for v in by_ind.values():
        v.sort(key=lambda c: -(c["mcap"] or 0))
    hl = ncfg["half_life_days"]

    def row(nid, d=1):
        it = items[nid]
        return (it["score"], recency_weight(it["published"], ref, hl), d)

    today = now()[:10]
    stats = {"companies": 0, "with_signal": 0}
    for cid, c in comps.items():
        ind = norm_industry(c["industry"])
        own = by_target.get((f"company:{cid}", "A"), [])
        peers = [p["id"] for p in by_ind.get(ind, []) if p["id"] != cid][:rcfg["peers_per_company"]]
        own_set = set(own)
        a = [row(n) for n in own]
        b = [row(n) for n in own if rel.search(items[n]["title"])]
        comp_ids = set()
        for p in peers:
            comp_ids |= {n for n in by_target.get((f"company:{p}", "A"), []) if n not in own_set}
        b += [row(n, rcfg["competitor_direction"]) for n in comp_ids]
        cc = [row(n) for n in by_target.get((f"industry:{ind}", "C"), [])]
        dd = [row(n) for n in by_target.get((f"industry:{ind}", "D"), [])]
        scores = {"A": (weighted(a), len(a)), "B": (weighted(b), len(b)), "C": (weighted(cc), len(cc)),
                  "D": (weighted(dd), len(dd))}
        comp = composite(scores, rcfg["weights"], ncfg["min_items_for_signal"])
        for r, (s, n) in scores.items():
            con.execute("INSERT OR REPLACE INTO rule_scores VALUES (?,?,?,?,?)", (cid, today, r, s, n))
            set_tag(con, cid, "news", f"news_{r}", None if s is None else round(s, 3),
                    {"rule": LABEL[r], "items": n}, today)
        set_tag(con, cid, "news", "news_composite", None if comp is None else round(comp, 3),
                {"verdict": verdict(comp), "items_company": len(own), "items_competitors": len(comp_ids),
                 "items_supply": len(cc), "items_customers": len(dd), "peers": [comps[p]["name"] for p in peers]},
                today)
        set_tag(con, cid, "news", "news_verdict", verdict(comp), {}, today)
        stats["companies"] += 1
        stats["with_signal"] += comp is not None
    con.commit()
    return stats


def evidence(con, cid: int, k: int = 3) -> dict:
    """Most influential recent headlines per rule for a company (for lead reports)."""
    cfg = load("finder")
    ref = datetime.now(timezone.utc)
    ind = norm_industry(con.execute("SELECT industry FROM companies WHERE id=?", (cid,)).fetchone()["industry"])
    out = {}
    for rule, target in (("A", f"company:{cid}"), ("C", f"industry:{ind}"), ("D", f"industry:{ind}")):
        rows = con.execute("""SELECT n.title, n.source, n.published, s.score FROM news_links k
                JOIN news_items n ON n.id=k.news_id JOIN news_sentiment s ON s.news_id=n.id
                WHERE k.target=? AND k.rule=? ORDER BY n.published DESC LIMIT 60""", (target, rule)).fetchall()
        ranked = sorted(rows, key=lambda r: -abs(r["score"]) * recency_weight(r["published"], ref,
                                                                                cfg["news"]["half_life_days"]))
        out[rule] = [{"title": r["title"], "source": r["source"], "date": (r["published"] or "")[:10],
                      "sentiment": round(r["score"], 2)} for r in ranked[:k]]
    return out

