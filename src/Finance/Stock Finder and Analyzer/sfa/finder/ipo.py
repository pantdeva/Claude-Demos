"""IPO pipeline: companies that are planning, filing for, pricing or have just made a
stock-market listing, found in news headlines and filing feeds.

Stage patterns are in config/finder.yaml (ipo.stages). The company name is the run of
capitalised words just before the stage phrase ("Lenskart files DRHP" → Lenskart) or
just before "IPO" ("PhonePe IPO opens" → PhonePe). SEC EDGAR S-1/F-1 feed titles
("S-1 - Example Corp (0001234567) (Filer)") are parsed directly. Each name is then
looked up on Yahoo Finance: a match whose first trade is within `recently_listed_days`
is a new listing (modelled with the peer proxy); a match inside the universe is an
existing company (often a subsidiary listing or follow-on offer).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..classify.listing import name_key
from ..config import load, venues
from ..data import yahoo
from ..db import now
from . import init

EXCHANGES = {"NSE": "IN", "BSE": "IN", "SME": "IN", "Nasdaq": "US", "NASDAQ": "US", "NYSE": "US", "HKEX": "HK",
             "Hong Kong": "HK", "SGX": "SG", "LSE": "GB", "London": "GB", "Tokyo": "JP", "TSE": "JP",
             "Shanghai": "CN", "Shenzhen": "CN", "STAR Market": "CN", "Tadawul": "SA", "Saudi": "SA",
             "Euronext": "FR", "Amsterdam": "NL", "Frankfurt": "DE", "ASX": "AU", "TSX": "CA", "Toronto": "CA",
             "KOSPI": "KR", "KOSDAQ": "KR", "Taiwan": "TW", "Dubai": "AE", "Abu Dhabi": "AE", "SEBI": "IN",
             "DRHP": "IN", "SEC": "US", "₹": "IN", "crore": "IN", "lakh": "IN", "Rs": "IN"}
LEAD_VERBS = {"files", "filed", "file", "submits", "submitted", "gets", "got", "receives", "received", "plans",
              "planned", "set", "sets", "makes", "made", "to", "will", "may", "could", "set to"}
NAME_STOP = set("""the a an its this that these why how what who when stock stocks shares share market markets ipo ipos
exclusive breaking update report reports sources source analysis watch live here new top big biggest largest india's
india indian us china chinese japan japanese hong kong saudi global world asia asian europe european company firm
startup start-up unicorn fintech edtech billionaire backed govt government state-run state-owned sebi sec nse bse
week today tomorrow monday tuesday wednesday thursday friday saturday sunday upcoming""".split())
CAP = r"[A-Z0-9][\w&.'’\-]*"
SEC_TITLE = re.compile(r"^(S-1|F-1|S-1/A|F-1/A|424B4)\s+-\s+(.+?)\s+\(\d{6,10}\)", re.I)


def _compile():
    st = load("finder")["ipo"]["stages"]
    return {k: re.compile("|".join(f"(?:{p})" for p in v), re.I) for k, v in st.items()}


def _clean_name(words: list[str]) -> str | None:
    while words and (words[0].lower().strip(":") in NAME_STOP or words[0].endswith(":")):
        words = words[1:]
    words = [w for w in words if not w.lower().endswith(("-backed", "-based", "-owned", "-led"))]
    if not words:
        return None
    name = " ".join(words).strip(" ,.:;'’")
    name = re.sub(r"(’s|'s)$", "", name)
    if len(name) < 2 or len(name) > 60 or name.lower() in NAME_STOP or not re.search(r"[A-Za-z]", name):
        return None
    return name


def extract(title: str, pats=None) -> list[tuple[str, str]]:
    """[(company name, stage)] found in one headline."""
    pats = pats or _compile()
    m = SEC_TITLE.match(title)
    if m:
        return [(m.group(2).strip(), "filed")]
    out = []
    for stage in ("listed", "priced", "filed", "planning"):          # strongest stage first
        mm = pats[stage].search(title)
        if not mm:
            continue
        before = title[:mm.start()].strip().rstrip(":;,-–—").strip()
        before = re.sub(r"\b(IPO|IPOs|initial public offering|shares?|stock)\s*$", "", before, flags=re.I).strip()
        toks = before.replace(",", " ").split()
        while toks and toks[-1].lower() in LEAD_VERBS:              # "Lenskart files DRHP"
            toks = toks[:-1]
        if toks and toks[-1].upper() in ("IPO", "IPO:"):
            toks = toks[:-1]
        run = []
        for t in reversed(toks):
            if re.fullmatch(CAP, t) or t in ("&", "and", "of") and run:
                run.insert(0, t)
                if len(run) >= 6:
                    break
            else:
                break
        while run and run[0] in ("&", "and", "of"):
            run = run[1:]
        name = _clean_name(run)
        if not name:                                                     # "IPO of X opens", "X's IPO"
            m2 = re.search(r"IPO of (" + CAP + r"(?:\s+" + CAP + r"){0,4})", title)
            name = _clean_name(m2.group(1).split()) if m2 else None
        if name:
            out.append((name, stage))
            break
    return out


def hints(title: str) -> tuple[str | None, str | None]:
    for k, c in EXCHANGES.items():
        pat = re.escape(k) if not k[0].isalnum() else r"(?<!\w)" + re.escape(k) + r"(?!\w)"
        if re.search(pat, title):
            return k, c
    return None, None


def scan(con, log=print) -> dict:
    """Extract IPO events from news items not yet scanned."""
    init(con)
    pats = _compile()
    last = con.execute("SELECT value FROM finder_state WHERE key='ipo:last_id'").fetchone()
    last_id = int(last["value"]) if last else 0
    rows = con.execute("SELECT id, title, source, published FROM news_items WHERE id > ? ORDER BY id", (last_id,)).fetchall()
    n = 0
    for r in rows:
        for name, stage in extract(r["title"], pats):
            ex, ctry = hints(r["title"])
            if r["source"].startswith("sec_"):
                ex, ctry = "SEC", "US"
            con.execute("INSERT OR IGNORE INTO ipo_events (name, name_key, stage, event_date, news_id, title, source, "
                        "exchange_hint, country_hint, found) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (name, name_key(name), stage, (r["published"] or now())[:10], r["id"], r["title"], r["source"],
                         ex, ctry, now()))
            n += 1
        last_id = r["id"]
    con.execute("INSERT OR REPLACE INTO finder_state VALUES ('ipo:last_id', ?)", (str(last_id),))
    con.commit()
    return {"scanned": len(rows), "events": n}


def resolve(con, log=print) -> dict:
    """Match IPO names to universe companies or Yahoo listings (first trade date)."""
    init(con)
    days = load("finder")["ipo"]["recently_listed_days"]
    V = venues()
    keys = con.execute("SELECT name_key, MAX(name) name, MAX(stage='listed' OR stage='priced') late FROM ipo_events "
                       "WHERE symbol IS NULL AND company_id IS NULL GROUP BY name_key").fetchall()
    n = 0
    for k in keys:
        cid = con.execute("SELECT id FROM companies WHERE name_key=? OR name_key LIKE ? LIMIT 1",
                          (k["name_key"], k["name_key"] + " %")).fetchone()
        if cid:
            con.execute("UPDATE ipo_events SET company_id=? WHERE name_key=?", (cid["id"], k["name_key"]))
            n += 1
            continue
        if not k["late"]:
            continue                                   # not trading yet: nothing to look up
        for q in yahoo.search(k["name"], n=6):
            if q.get("quoteType") != "EQUITY" or name_key(q.get("longname") or q.get("shortname")).split()[:1] != \
                    k["name_key"].split()[:1]:
                continue
            v = V.resolve(q["symbol"], q.get("exchange"))
            if v is None or v["role"] == "secondary":
                continue
            c = yahoo.chart(q["symbol"], start=int(datetime.now(timezone.utc).timestamp()) - 400 * 86400)
            if not c or not c["t"]:
                continue
            first = datetime.fromtimestamp((c["meta"].get("firstTradeDate") or c["t"][0]), timezone.utc)
            if (datetime.now(timezone.utc) - first).days > days:
                continue
            con.execute("UPDATE ipo_events SET symbol=?, first_trade=? WHERE name_key=?",
                        (q["symbol"], first.strftime("%Y-%m-%d"), k["name_key"]))
            n += 1
            break
    con.commit()
    return {"names": len(keys), "resolved": n}
