"""Stage 0 jobs: refresh prices and fundamentals, then classify every company."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from .classify import fundamental as F
from .classify import listing as L
from .classify import market as M
from .classify import sector as S
from .config import venues
from .data import yahoo
from .db import now, set_tag


def _iso(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- prices
def refresh_prices(con, refresh: bool = False, log=print) -> dict:
    """Daily history since 2005 for every home listing and every benchmark index."""
    syms = [r["symbol"] for r in con.execute("SELECT symbol FROM listings WHERE is_home=1")]
    bench = sorted({v["benchmark"] for v in venues().by_id.values() if v.get("benchmark")})
    ok = 0
    for i, s in enumerate(syms + bench, 1):
        c = yahoo.chart(s, refresh=refresh)
        if not c or not c["t"]:
            continue
        rows = [(s, _iso(t), cl, ad) for t, cl, ad in zip(c["t"], c["close"], c["adj"]) if cl]
        con.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?)", rows)
        if rows:
            con.execute("UPDATE listings SET last_price=?, last_date=?, currency=COALESCE(?, currency) WHERE symbol=?",
                        (rows[-1][2], rows[-1][1], c["meta"].get("currency"), s))
        ok += 1
        if i % 100 == 0:
            con.commit()
            log(f"  prices {i}/{len(syms) + len(bench)}")
    con.commit()
    return {"series": ok, "requested": len(syms) + len(bench)}


def refresh_fundamentals(con, refresh: bool = False, log=print) -> dict:
    rows = con.execute("SELECT symbol FROM listings WHERE is_home=1").fetchall()
    ok = 0
    for i, r in enumerate(rows, 1):
        f = yahoo.fundamentals(r["symbol"], refresh=refresh)
        if not f:
            continue
        for item, pts in f.items():
            con.executemany("INSERT OR REPLACE INTO fundamentals VALUES (?,?,?,?,?)",
                            [(r["symbol"], item, p["date"], p["value"], p["ccy"]) for p in pts])
        ok += 1
        if i % 100 == 0:
            con.commit()
            log(f"  fundamentals {i}/{len(rows)}")
    con.commit()
    return {"with_data": ok, "requested": len(rows)}


# ---------------------------------------------------------------- helpers
def _series(con, symbol: str) -> dict[str, float]:
    return {r["date"]: r["adj_close"] for r in
            con.execute("SELECT date, adj_close FROM prices WHERE symbol=? AND adj_close IS NOT NULL", (symbol,))}


def _fund(con, symbol: str) -> dict[str, list[dict]]:
    out = {}
    for r in con.execute("SELECT item, as_of, value, currency FROM fundamentals WHERE symbol=? ORDER BY as_of", (symbol,)):
        out.setdefault(r["item"], []).append({"date": r["as_of"], "value": r["value"], "ccy": r["currency"]})
    return out


def benchmark_series(con, venue_id: str, cache: dict) -> tuple[dict[str, float], str]:
    """Home index closes; when Yahoo has too little history (e.g. ^TASI.SR) an
    equal-weight index of the universe's home listings on that exchange is built."""
    if venue_id in cache:
        return cache[venue_id]
    v = venues().by_id.get(venue_id) or {}
    sym = v.get("benchmark")
    px = _series(con, sym) if sym else {}
    if len(px) >= 260:
        cache[venue_id] = (px, sym)
        return cache[venue_id]
    members = [r["symbol"] for r in con.execute("SELECT symbol FROM listings WHERE is_home=1 AND venue=?", (venue_id,))]
    rets: dict[str, list[float]] = {}
    for m in members:
        s = _series(con, m)
        ds = sorted(s)
        for a, b in zip(ds, ds[1:]):
            if s[a] and s[b]:
                r = s[b] / s[a] - 1
                if abs(r) < 0.5:
                    rets.setdefault(b, []).append(r)
    level, out = 100.0, {}
    for d in sorted(rets):
        if len(rets[d]) >= max(3, len(members) // 3):
            level *= 1 + sum(rets[d]) / len(rets[d])
            out[d] = level
    cache[venue_id] = (out, f"equal-weight {venue_id} universe ({len(members)} stocks; {sym} too short)")
    return cache[venue_id]


def _price_on(px: dict[str, float], date: str) -> float | None:
    ds = [d for d in px if d <= date]
    return px[max(ds)] if ds else None


def market_value_usd(con, home: dict, fund: dict, px: dict[str, float]) -> tuple[float | None, str]:
    """Latest market value in USD: Yahoo's trailing value rolled forward with the price."""
    mc = fund.get("trailingMarketCap")
    if mc:
        p = mc[-1]
        fx = yahoo.fx_to_usd(p["ccy"] or home["currency"])
        last = max(px) if px else None
        roll = 1.0
        if last and p["date"] < last:
            p0 = _price_on(px, p["date"])
            roll = px[last] / p0 if p0 else 1.0
        if fx:
            return p["value"] * fx * roll, f"Yahoo market value {p['date']} × price change to {last}"
    sh = fund.get("annualOrdinarySharesNumber")
    if sh and home.get("last_price"):
        fx = yahoo.fx_to_usd(home["currency"])
        if fx:
            return sh[-1]["value"] * home["last_price"] * fx, "shares × price"
    return None, "no market value"


# ---------------------------------------------------------------- classify
def classify_all(con, log=print) -> dict:
    today = now()[:10]
    comps = con.execute("SELECT * FROM companies WHERE status='active'").fetchall()
    rows_style, stats = [], {"companies": len(comps)}
    fx_cache: dict[str, float | None] = {}

    def fx(c):
        if c not in fx_cache:
            fx_cache[c] = yahoo.fx_to_usd(c)
        return fx_cache[c]

    india, bench_cache = [], {}
    for c in comps:
        cid = c["id"]
        lst = [dict(r) for r in con.execute("SELECT * FROM listings WHERE company_id=?", (cid,))]
        home = next((l for l in lst if l["is_home"]), None)
        if not home:
            continue
        # 1. market development
        d = M.detail(home["country"])
        set_tag(con, cid, "market", "market_class", M.CLASSES[d["MSCI"]], d, today)
        set_tag(con, cid, "market", "market_class_ftse", M.CLASSES[d["FTSE"]], {}, today)
        set_tag(con, cid, "market", "market_class_spdji", M.CLASSES[d["SPDJI"]], {}, today)
        set_tag(con, cid, "market", "home_exchange", home["venue"], {"symbol": home["symbol"]}, today)
        set_tag(con, cid, "market", "covered", "yes" if home["venue_role"] == "covered" else "no", {}, today)

        # 2. listing structure (price ratio needs home price in USD)
        hp = home.get("last_price") or (yahoo.last_quote(home["symbol"]) or {}).get("price")
        h_usd = hp * fx(home["currency"]) if hp and fx(home["currency"]) else None
        structs = []
        for l in lst:
            p_usd = None
            priced = {"NASDAQ", "NYSE", "LSE_IOB", "B3", "US_OTC", "SGX"} | ({"TSX"} if home["country"] == "US" else set())
            if l["symbol"] != home["symbol"] and l["venue"] in priced:
                q = yahoo.last_quote(l["symbol"])
                if q and q.get("price") and fx(q.get("currency")):
                    p_usd = q["price"] * fx(q["currency"])
            stc, ratio, basis = L.listing_structure(l, home, h_usd, p_usd)
            con.execute("UPDATE listings SET structure=?, dr_ratio=?, structure_basis=? WHERE symbol=?",
                        (stc, ratio, basis, l["symbol"]))
            structs.append(stc)
        label = L.company_structure(structs, [l["venue_role"] for l in lst])
        set_tag(con, cid, "listing", "listing_structure", label,
                {"listings": {l["symbol"]: s for l, s in zip(lst, structs)}}, today)
        set_tag(con, cid, "listing", "domicile", c["domicile"], {"basis": c["domicile_basis"]}, today)
        foreign_dom = c["domicile"] and c["domicile"] != home["country"]
        set_tag(con, cid, "listing", "foreign_domiciled", "yes" if foreign_dom else "no", {}, today)

        # 3. sector
        sm = S.map_sector(c["sector"], c["industry"])
        set_tag(con, cid, "sector", "gics_sector", sm["gics"], {"yahoo": c["sector"], "industry": c["industry"],
                                                                 "basis": sm["basis"]}, today)
        set_tag(con, cid, "sector", "sector_group", sm["group_name"], {}, today)

        # 4. stock level
        px = _series(con, home["symbol"])
        fund = _fund(con, home["symbol"])
        mcap, mbasis = market_value_usd(con, home, fund, px)
        set_tag(con, cid, "stock", "market_cap_usd", None if mcap is None else round(mcap), {"basis": mbasis}, today)
        set_tag(con, cid, "stock", "cap_band", F.usd_band(mcap), {"bands_usd": "Mega ≥200B, Large ≥10B, Mid ≥2B, "
                                                                   "Small ≥300M, Micro"}, today)
        if home["country"] == "IN":
            india.append((cid, mcap))
        bpx, bench = benchmark_series(con, home["venue"], bench_cache)
        beta, nw = F.weekly_beta(px, bpx)
        set_tag(con, cid, "stock", "beta", None if beta is None else round(beta, 3), {"index": bench, "weeks": nw}, today)
        beh, bbasis = S.behaviour(sm.get("super"), c["industry"], beta)
        set_tag(con, cid, "stock", "cyclical_defensive", beh, {"basis": bbasis, "super_sector": sm.get("super")}, today)
        st = home["share_type"] or "common"
        has_pref = any(l["share_type"] == "preferred" for l in lst)
        set_tag(con, cid, "stock", "share_type", st,
                {"preferred_lines": [l["symbol"] for l in lst if l["share_type"] == "preferred"]}, today)
        set_tag(con, cid, "stock", "has_preferred", "yes" if has_pref else "no", {}, today)

        g, gbasis = F.growth_rate(fund)
        sccy = c["statement_ccy"] or home["currency"]
        k = fx(sccy) if sccy else None

        def ratio(item):
            pts = fund.get(item)
            if not pts or not mcap or not k:
                return None
            v = pts[-1]["value"] * (fx(pts[-1]["ccy"]) or k)
            return v / mcap
        ep, sp, bp = ratio("trailingNetIncome"), ratio("trailingTotalRevenue"), ratio("annualStockholdersEquity")
        if sp is not None and sp > 50:          # unit mismatch (e.g. pence vs pounds) → drop
            sp = None
        rows_style.append({"id": cid, "cell": f"{d['MSCI']}|{sm['group']}", "group": sm["group"],
                           "growth": g, "ep": ep, "bp": bp, "sp": sp, "gbasis": gbasis})

    # growth / value needs everyone's numbers
    styles = F.style_scores(rows_style)
    for r in rows_style:
        s = styles[r["id"]]
        set_tag(con, r["id"], "stock", "growth_value", s["label"],
                {**s, "revenue_growth": r["growth"], "growth_basis": r["gbasis"], "earnings_yield": r["ep"],
                 "book_to_price": r["bp"], "sales_to_price": r["sp"]}, today)
    # SEBI-style rank for Indian companies
    india.sort(key=lambda x: -(x[1] or 0))
    for rank, (cid, mc) in enumerate(india, 1):
        set_tag(con, cid, "stock", "cap_band_sebi", F.sebi_band(rank) if mc else None,
                {"rank_in_universe": rank, "note": "approximate: ranked within this universe, not all NSE/BSE stocks"},
                today)
    con.commit()
    stats["styled"] = sum(1 for s in styles.values() if s["label"] != "Unclassified")
    return stats
