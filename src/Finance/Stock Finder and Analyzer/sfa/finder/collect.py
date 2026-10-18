"""News collection for the finder.

- RSS feeds of the 12 news sites plus regulator / exchange filing feeds (data/rss.py)
- Yahoo Finance news per company: rotates through the universe, a batch per run;
  Yahoo tags each story with related tickers, which link it straight to companies
- NewsAPI deep dives on the best leads (needs NEWSAPI_KEY; free plan 100 requests/day)
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import load
from ..data import rss, yahoo
from ..db import now
from . import init

_QUANT = Path(__file__).resolve().parents[3] / "nlp_stock_analyzer"
if str(_QUANT) not in sys.path:
    sys.path.insert(0, str(_QUANT))


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def yahoo_news_query(symbol: str, n: int = 10) -> list[dict]:
    """Yahoo Finance search endpoint, news part: title, publisher, link, time, related tickers."""
    d = yahoo._get(f"{yahoo.BASE}/v1/finance/search", {"q": symbol, "quotesCount": 0, "newsCount": n})
    out = []
    for x in (d or {}).get("news") or []:
        if not x.get("title") or not x.get("link"):
            continue
        out.append({"title": x["title"], "link": x["link"], "publisher": x.get("publisher") or "",
                    "published": _iso(x["providerPublishTime"]) if x.get("providerPublishTime") else None,
                    "tickers": x.get("relatedTickers") or []})
    return out


def _store(con, source: str, items: list[dict], topic: str) -> list[int]:
    ids = []
    for i in items:
        cur = con.execute("INSERT OR IGNORE INTO news_items (url, source, published, title, summary, rule, fetched) "
                          "VALUES (?,?,?,?,?,?,?)", (i["link"], source, i.get("published"), i["title"],
                                                     i.get("summary", ""), f"topic:{topic}", now()))
        row = con.execute("SELECT id FROM news_items WHERE url=?", (i["link"],)).fetchone()
        if row:
            ids.append(row["id"])
            for t in i.get("tickers", []):
                con.execute("INSERT OR IGNORE INTO news_links VALUES (?,?,?,?,?)",
                            (row["id"], f"ticker:{t}", "tag", 0, "Yahoo related ticker"))
    return ids


def yahoo_batch(con, log=print) -> dict:
    """Yahoo Finance news for the next batch of companies (oldest-fetched first)."""
    init(con)
    cfg = load("finder")["news"]
    rows = con.execute("""SELECT c.id, c.home_symbol,
              (SELECT l.symbol FROM listings l WHERE l.company_id=c.id AND l.venue IN ('NYSE','NASDAQ')
               ORDER BY l.is_home DESC LIMIT 1) us_symbol,
              COALESCE((SELECT value FROM finder_state WHERE key='yahoo:' || c.id), '') last
            FROM companies c WHERE c.status='active' ORDER BY last, c.id LIMIT ?""", (cfg["yahoo_batch"],)).fetchall()
    n_items = 0
    for r in rows:
        q = r["us_symbol"] or r["home_symbol"]
        items = yahoo_news_query(q, cfg["yahoo_news_per_query"])
        if not r["us_symbol"] and len(items) < 3:                      # non-US tickers return little: try the name
            from .linking import short_names
            name = con.execute("SELECT name FROM companies WHERE id=?", (r["id"],)).fetchone()["name"]
            have = {i["link"] for i in items}
            items += [i for i in yahoo_news_query(short_names(name)[0], cfg["yahoo_news_per_query"])
                      if i["link"] not in have]
        for i in items:
            i["summary"] = ""
            _store(con, f"yahoo_finance:{i['publisher']}"[:80], [i], "company")
        n_items += len(items)
        con.execute("INSERT OR REPLACE INTO finder_state VALUES (?,?)", (f"yahoo:{r['id']}", now()))
    con.commit()
    return {"companies": len(rows), "items": n_items}


def rss_all(con, log=print) -> dict:
    init(con)
    return rss.poll(con)


# ---------------------------------------------------------------- NewsAPI deep dives
def newsapi_budget_left(con) -> int:
    cfg = load("news_sources").get("newsapi") or {}
    day = now()[:10]
    used = con.execute("SELECT value FROM finder_state WHERE key=?", (f"newsapi:{day}",)).fetchone()
    return int(cfg.get("daily_budget", 90)) - int(used["value"] if used else 0)


def newsapi_deep_dive(con, names: list[tuple[int, str]], log=print) -> dict:
    """[(company_id, search phrase)] → NewsAPI articles of the last 14 days, stored and tagged."""
    cfg = load("news_sources").get("newsapi") or {}
    key = os.environ.get(cfg.get("env_key", "NEWSAPI_KEY"))
    if not cfg.get("enabled") or not key:
        return {"skipped": "NEWSAPI_KEY not set"}
    from stock_analyzer.news import NewsAPIClient, NewsAPIError
    client = NewsAPIClient(api_key=key, cache_dir=Path(__file__).resolve().parents[2] / "db" / "cache" / "newsapi")
    end = datetime.now(timezone.utc) - timedelta(hours=1)
    start = end - timedelta(days=14)
    done, items = 0, 0
    for cid, phrase in names:
        if newsapi_budget_left(con) <= 0:
            break
        try:
            arts = client.search(f'"{phrase}"', "en", start, end, page_size=50)
        except NewsAPIError as e:
            log(f"  NewsAPI: {e}")
            break
        day = now()[:10]
        used = con.execute("SELECT value FROM finder_state WHERE key=?", (f"newsapi:{day}",)).fetchone()
        con.execute("INSERT OR REPLACE INTO finder_state VALUES (?,?)", (f"newsapi:{day}", int(used["value"] if used else 0) + 1))
        ids = _store(con, "newsapi", [{"title": a.title, "link": a.url, "summary": a.description,
                                       "published": a.published_at.strftime("%Y-%m-%dT%H:%M:%SZ")} for a in arts],
                     "deep_dive")
        for i in ids:
            con.execute("INSERT OR IGNORE INTO news_links VALUES (?,?,?,?,?)", (i, f"company:{cid}", "query", 0,
                                                                                "NewsAPI deep dive"))
        done += 1
        items += len(arts)
        time.sleep(0.2)
    con.commit()
    return {"queries": done, "items": items}
