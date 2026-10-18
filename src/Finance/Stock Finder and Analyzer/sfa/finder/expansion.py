"""Exchange expansion from news: which markets outside the 14 covered exchanges show a
growing industry in the news, so they can be added to config/exchanges.yaml.

For each candidate market (config/finder.yaml → expansion.markets) count recent stories
that name the market, the share of them that also use a growth word, their mean
FinBERT sentiment and the sector groups they touch. A market with at least `min_items`
stories and sentiment ≥ `min_score` is suggested.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from ..classify.sector import map_sector
from ..config import load
from ..db import now
from . import init
from .linking import Linker


def scan(con, log=print) -> dict:
    init(con)
    cfg = load("finder")
    ex = cfg["expansion"]
    cut = (datetime.now(timezone.utc) - timedelta(days=cfg["news"]["lookback_days"] * 2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = con.execute("""SELECT n.title, n.summary, s.score FROM news_items n JOIN news_sentiment s ON s.news_id=n.id
                          WHERE COALESCE(n.published, n.fetched) >= ?""", (cut,)).fetchall()
    grow = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, ex["growth_words"])) + r")(?!\w)", re.I)
    lk = Linker(con)
    sec_of = {}
    for r in con.execute("SELECT DISTINCT sector, industry FROM companies"):
        from ..classify.sector import norm_industry
        sec_of[norm_industry(r["industry"])] = map_sector(r["sector"], r["industry"]).get("group_name")
    today = now()[:10]
    out = {}
    for ctry, m in ex["markets"].items():
        rx = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, m["names"])) + r")(?!\w)")
        hits = [r for r in rows if rx.search(f"{r['title']} {r['summary'] or ''}")]
        if not hits:
            continue
        g = [r for r in hits if grow.search(r["title"])]
        sent = sum(r["score"] for r in hits) / len(hits)
        groups = Counter(sec_of.get(ind) for r in hits for ind, _ in lk.industries_in(r["title"]) if sec_of.get(ind))
        suggest = int(len(hits) >= ex["min_items"] and sent >= ex["min_score"] and len(g) >= 2)
        heads = [r["title"] for r in sorted(hits, key=lambda r: -r["score"])[:5]]
        con.execute("INSERT OR REPLACE INTO expansion_signals VALUES (?,?,?,?,?,?,?,?,?)",
                    (ctry, today, m["exchange"], len(hits), sent, len(g), json.dumps(groups.most_common(3)),
                     json.dumps(heads), suggest))
        out[ctry] = {"items": len(hits), "sentiment": round(sent, 3), "suggest": bool(suggest)}
    con.commit()
    return {"markets_mentioned": len(out), "suggested": sum(v["suggest"] for v in out.values())}
