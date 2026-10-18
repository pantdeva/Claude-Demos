"""RSS/Atom reader for the news sources in config/news_sources.yaml.

- Parses RSS 2.0 and Atom with the standard library (no feedparser needed).
- Tracks each feed's health; after 3 consecutive failures a feed is marked broken and
  the site is read through Google News RSS limited to its domain instead.
- De-duplicates syndicated items (aggregators such as Pulse re-publish other outlets)
  by normalised title.
Items are stored in the news_items table; scoring with FinBERT on rules A–D is
Milestone 3.
"""

from __future__ import annotations

import email.utils
import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests

from ..config import load
from ..db import now

HEALTH_SQL = """CREATE TABLE IF NOT EXISTS feed_health (
    url TEXT PRIMARY KEY, source TEXT, ok INTEGER, fails INTEGER, last_ok TEXT, last_error TEXT,
    items_last INTEGER, checked TEXT)"""
ATOM = "{http://www.w3.org/2005/Atom}"


def _text(el, *names):
    for n in names:
        x = el.find(n)
        if x is not None:
            if x.text and x.text.strip():
                return x.text.strip()
            if x.get("href"):
                return x.get("href")
    return None


def _date(s: str | None) -> str | None:
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(html: str | None) -> str:
    if not html:
        return ""
    s = re.sub(r"<[^>]+>", " ", html)
    s = re.sub(r"&nbsp;|&#160;", " ", s).replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    return re.sub(r"\s+", " ", s).strip()


def parse_feed(xml: bytes | str) -> list[dict]:
    """Items as {title, link, published, summary}."""
    root = ET.fromstring(xml)
    items = []
    for it in root.iter("item"):                                   # RSS 2.0
        items.append({"title": _clean(_text(it, "title")), "link": _text(it, "link", "guid"),
                      "published": _date(_text(it, "pubDate", "{http://purl.org/dc/elements/1.1/}date")),
                      "summary": _clean(_text(it, "description"))[:1000]})
    for it in root.iter(f"{ATOM}entry"):                           # Atom
        link = it.find(f"{ATOM}link")
        items.append({"title": _clean(_text(it, f"{ATOM}title")),
                      "link": link.get("href") if link is not None else None,
                      "published": _date(_text(it, f"{ATOM}updated", f"{ATOM}published")),
                      "summary": _clean(_text(it, f"{ATOM}summary", f"{ATOM}content"))[:1000]})
    return [i for i in items if i["title"]]


def title_key(title: str) -> str:
    t = re.sub(r"\s[-|–]\s[^-|–]{2,40}$", "", title)              # strip " - Reuters" suffixes
    t = re.sub(r"[^a-z0-9 ]", "", t.lower())
    return hashlib.sha1(" ".join(t.split()).encode()).hexdigest()[:16]


def feed_urls(source: dict, ticker: str | None = None) -> list[tuple[str, dict]]:
    d = load("news_sources")["defaults"]
    out = []
    for f in source["feeds"]:
        if f["kind"] == "rss":
            out.append((f["url"], f))
        elif f["kind"] == "google_news":
            out.append((d["fallback"].format(domain=source["domain"], q=quote_plus(f["q"])), f))
        elif f["kind"] == "per_ticker" and ticker:
            out.append((f["url"].format(ticker=quote_plus(ticker)), f))
    return out


def fallback_url(source: dict) -> str:
    d = load("news_sources")["defaults"]
    return d["fallback"].format(domain=source["domain"], q=quote_plus(d["fallback_q"]))


def _store(con, source: dict, topic: str, items: list[dict], seen: set) -> int:
    n = 0
    for i in items:
        k = title_key(i["title"])
        if k in seen:
            continue
        seen.add(k)
        cur = con.execute("INSERT OR IGNORE INTO news_items (url, source, published, title, summary, rule, fetched)"
                          " VALUES (?,?,?,?,?,?,?)",
                          (i["link"] or f"nolink:{k}", source["id"], i["published"], i["title"], i["summary"],
                           f"topic:{topic}", now()))
        n += cur.rowcount
    return n


def poll(con, sources: list[str] | None = None, session: requests.Session | None = None) -> dict:
    """Fetch every enabled feed once. Returns {source_id: new_items}."""
    cfg = load("news_sources")
    d = cfg["defaults"]
    con.execute(HEALTH_SQL)
    s = session or requests.Session()
    s.headers["User-Agent"] = d["user_agent"]
    seen = {title_key(r["title"]) for r in con.execute(
        "SELECT title FROM news_items WHERE fetched > datetime('now','-3 day')")}
    result = {}
    for src in cfg["sources"]:
        if sources and src["id"] not in sources:
            continue
        new, broken = 0, 0
        urls = feed_urls(src)
        for url, f in urls:
            h = con.execute("SELECT fails FROM feed_health WHERE url=?", (url,)).fetchone()
            if h and h["fails"] >= 3:
                broken += 1
                continue
            try:
                r = s.get(url, timeout=d["timeout_s"])
                r.raise_for_status()
                items = parse_feed(r.content)
                new += _store(con, src, f.get("topic", "general"), items, seen)
                con.execute("INSERT OR REPLACE INTO feed_health VALUES (?,?,1,0,?,NULL,?,?)",
                            (url, src["id"], now(), len(items), now()))
            except (requests.RequestException, ET.ParseError) as e:
                fails = (h["fails"] if h else 0) + 1
                con.execute("INSERT OR REPLACE INTO feed_health VALUES (?,?,0,?,NULL,?,0,?)",
                            (url, src["id"], fails, str(e)[:200], now()))
                broken += fails >= 3
        if urls and broken == len(urls):                           # whole site broken → Google News
            url = fallback_url(src)
            try:
                r = s.get(url, timeout=d["timeout_s"])
                r.raise_for_status()
                new += _store(con, src, "fallback", parse_feed(r.content), seen)
            except (requests.RequestException, ET.ParseError):
                pass
        result[src["id"]] = new
    con.commit()
    return result


def health(con) -> list[dict]:
    con.execute(HEALTH_SQL)
    return [dict(r) for r in con.execute("SELECT * FROM feed_health ORDER BY source, url")]
