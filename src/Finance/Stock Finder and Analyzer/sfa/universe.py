"""Build the company universe from seeds: one company row per issuer, one listing row
per place its shares (or receipts) trade, with the home listing chosen.

For each seed: latest quote (name, currency) → Yahoo search by company name → keep
results whose name matches the company → resolve each to a venue → statement currency
from fundamentals → choose the home listing → store. For US companies SEC EDGAR is
asked for the state/country of incorporation when SFA_SEC_USER_AGENT is set.
"""

from __future__ import annotations

from .classify.listing import choose_home, name_key, same_company, share_type
from .config import load, seeds, venues
from .data import sec, yahoo
from .db import now

DR_VENUES_TO_PRICE = {"NASDAQ", "NYSE", "LSE_IOB", "B3"}


def _statement_ccy(fund: dict | None) -> str | None:
    for k in ("annualTotalRevenue", "annualStockholdersEquity", "trailingTotalRevenue"):
        pts = (fund or {}).get(k)
        if pts and pts[-1].get("ccy"):
            return pts[-1]["ccy"]
    return None


def resolve_seed(seed: str) -> dict | None:
    """All listings of the seed's company, or None if the seed is not a live equity."""
    V = venues()
    q = yahoo.last_quote(seed)
    if not q or not q.get("price"):
        return {"drop": "no quote"}
    if q.get("instrumentType") not in (None, "EQUITY"):
        return {"drop": f"not an equity ({q.get('instrumentType')})"}
    name = q.get("longName") or q.get("shortName") or seed
    found = yahoo.search(name)
    key = name_key(name)
    if key and key != name.lower():                 # the short name finds more listings
        have = {r["symbol"] for r in found}
        found += [r for r in yahoo.search(key) if r["symbol"] not in have]
    if not any(r["symbol"] == seed for r in found):
        found = found + yahoo.search(seed, n=5)
    listings, info = {}, {}
    for rank, r in enumerate(found):
        sym = r["symbol"]
        if r.get("quoteType") != "EQUITY":
            continue
        if sym != seed and not same_company(name, r.get("longname") or r.get("shortname")):
            continue
        v = V.resolve(sym, r.get("exchange"))
        if sym == seed and v is None:
            v = V.resolve(sym)
        if v is None:
            continue                       # regional German, Vienna etc.: not tracked
        if r.get("sector") and not info:
            info = {"sector": r["sector"], "industry": r.get("industry")}
        st, cls, _ = share_type(sym, r.get("longname"))
        listings[sym] = {"symbol": sym, "venue": v["id"], "venue_role": v["role"], "country": v["country"],
                         "currency": v.get("currency"), "yahoo_code": r.get("exchange"),
                         "long_name": r.get("longname") or r.get("shortname"), "quote_type": "EQUITY",
                         "share_type": st, "share_class": cls, "rank": rank}
    if seed not in listings:
        v = V.resolve(seed)
        if v is None:
            return {"drop": "seed venue not recognised"}
        st, cls, _ = share_type(seed, name)
        listings[seed] = {"symbol": seed, "venue": v["id"], "venue_role": v["role"], "country": v["country"],
                          "currency": v.get("currency"), "yahoo_code": None, "long_name": name,
                          "quote_type": "EQUITY", "share_type": st, "share_class": cls, "rank": 99}
    listings[seed]["currency"] = q.get("currency") or listings[seed]["currency"]
    fund = yahoo.fundamentals(seed)
    stmt = _statement_ccy(fund)
    home, basis = choose_home(list(listings.values()), stmt, seed)
    if home["symbol"] != seed and stmt is None:
        stmt = _statement_ccy(yahoo.fundamentals(home["symbol"]))
    if not info:
        for r in yahoo.search(home["symbol"], n=3):
            if r["symbol"] == home["symbol"] and r.get("sector"):
                info = {"sector": r["sector"], "industry": r.get("industry")}
    return {"name": name, "listings": listings, "home": home["symbol"], "home_basis": basis,
            "statement_ccy": stmt, **info}


def _domicile(res: dict) -> tuple[str | None, str]:
    ov = load("overrides").get("domicile") or {}
    for s in res["listings"]:
        if s in ov:
            return ov[s], "override"
    home = res["listings"][res["home"]]
    if home["country"] == "US":
        f = sec.company_facts(res["home"])
        if f and f.get("domicile"):
            return f["domicile"], f"SEC EDGAR (incorporation code {f['incorporation_code']})"
        if f and f.get("foreign_private_issuer"):
            return None, "SEC EDGAR: foreign private issuer, country code unmapped"
    return home["country"], "home exchange"


def store(con, group: str, res: dict) -> int:
    syms = list(res["listings"])
    row = con.execute(f"SELECT company_id FROM listings WHERE symbol IN ({','.join('?' * len(syms))}) "
                      "AND company_id IS NOT NULL LIMIT 1", syms).fetchone()
    key = name_key(res["name"])
    if row is None:
        row = con.execute("SELECT id AS company_id FROM companies WHERE name_key=?", (key,)).fetchone()
    home = res["listings"][res["home"]]
    dom, dom_basis = _domicile(res)
    vals = (res["name"], res["home"], home["venue"], home["country"], dom, dom_basis, res["statement_ccy"],
            res.get("sector"), res.get("industry"), group, f"home: {res['home_basis']}", now())
    if row:
        cid = row["company_id"]
        con.execute("UPDATE companies SET name=?, home_symbol=?, home_venue=?, home_country=?, domicile=?, "
                    "domicile_basis=?, statement_ccy=?, sector=COALESCE(?, sector), industry=COALESCE(?, industry), "
                    "seed_group=COALESCE(seed_group, ?), note=?, updated=?, status='active' WHERE id=?", (*vals, cid))
    else:
        while con.execute("SELECT 1 FROM companies WHERE name_key=?", (key,)).fetchone():
            key += "*"                       # two issuers with the same normalised name
        cur = con.execute("INSERT INTO companies (name, home_symbol, home_venue, home_country, domicile, "
                          "domicile_basis, statement_ccy, sector, industry, seed_group, note, updated, name_key) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (*vals, key))
        cid = cur.lastrowid
    for s, l in res["listings"].items():
        con.execute("INSERT INTO listings (symbol, company_id, venue, venue_role, country, currency, yahoo_code, "
                    "long_name, quote_type, is_home, share_type, share_class, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(symbol) DO UPDATE SET company_id=excluded.company_id, venue=excluded.venue, "
                    "venue_role=excluded.venue_role, country=excluded.country, currency=COALESCE(listings.currency, excluded.currency), "
                    "is_home=excluded.is_home, share_type=excluded.share_type, share_class=excluded.share_class, "
                    "updated=excluded.updated",
                    (s, cid, l["venue"], l["venue_role"], l["country"], l["currency"], l["yahoo_code"], l["long_name"],
                     l["quote_type"], int(s == res["home"]), l["share_type"], l["share_class"], now()))
    con.execute("UPDATE listings SET is_home=0 WHERE company_id=? AND symbol<>?", (cid, res["home"]))
    return cid


def build(con, limit: int | None = None, only: list[str] | None = None, log=print) -> dict:
    stats = {"seeds": 0, "companies": 0, "dropped": 0, "skipped": 0}
    todo = [(g, s) for g, s in seeds() if not only or s in only][:limit]
    for i, (group, seed) in enumerate(todo, 1):
        stats["seeds"] += 1
        known = con.execute("SELECT updated FROM listings WHERE symbol=? AND company_id IS NOT NULL", (seed,)).fetchone()
        if known and not only and known["updated"][:10] == now()[:10]:
            stats["skipped"] += 1
            continue
        res = resolve_seed(seed)
        if res is None or "drop" in res:
            con.execute("INSERT OR REPLACE INTO dropped_seeds VALUES (?,?,?)", (seed, (res or {}).get("drop"), now()))
            stats["dropped"] += 1
            continue
        store(con, group, res)
        stats["companies"] += 1
        if i % 25 == 0:
            con.commit()
            log(f"  universe {i}/{len(todo)}  {seed} → {res['home']} ({len(res['listings'])} listings)")
    con.commit()
    stats["total_companies"] = con.execute("SELECT COUNT(*) FROM companies WHERE status='active'").fetchone()[0]
    return stats
