"""Offline tests for Milestone 3 (Stage 1 company finder).

Run from the "Stock Finder and Analyzer" folder:  python tests/test_finder.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sfa.db import connect, set_tag  # noqa: E402
from sfa.finder import init, ipo, leads, linking, routes, rules  # noqa: E402
from sfa.finder.linking import Linker, short_names  # noqa: E402


def _iso(days_ago=0.0):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def fixture():
    con = connect(":memory:")
    init(con)
    comps = [
        (1, "Infosys Limited", "Technology", "Information Technology Services", "INFY.NS", "NSE", "IN", 50e9),
        (2, "Wipro Limited", "Technology", "Information Technology Services", "WIPRO.NS", "NSE", "IN", 30e9),
        (3, "Toyota Motor Corporation", "Consumer Cyclical", "Auto Manufacturers", "7203.T", "JPX", "JP", 230e9),
        (4, "Kweichow Moutai Co., Ltd.", "Consumer Defensive", "Beverages—Wineries & Distilleries", "600519.SS", "SSE",
         "CN", 250e9),
        (5, "NVIDIA Corporation", "Technology", "Semiconductors", "NVDA", "NASDAQ", "US", 5e12),
    ]
    for cid, name, sec, ind, sym, venue, ctry, mcap in comps:
        con.execute("INSERT INTO companies (id, name, name_key, home_symbol, home_venue, home_country, sector, industry) "
                    "VALUES (?,?,?,?,?,?,?,?)", (cid, name, name.lower(), sym, venue, ctry, sec, ind))
        con.execute("INSERT INTO listings (symbol, company_id, venue, country, is_home, structure, share_type) "
                    "VALUES (?,?,?,?,1,'primary','common')", (sym, cid, venue, ctry))
        set_tag(con, cid, "stock", "market_cap_usd", mcap)
        set_tag(con, cid, "sector", "sector_group", {"Technology": "IT & Software"}.get(sec, "Consumer Discretionary & Staples"))
        set_tag(con, cid, "market", "market_class", "Developed" if ctry in ("JP", "US") else "Emerging")
    for sym, cid, venue, ctry, st in (("INFY", 1, "NYSE", "US", "ADR"), ("INFY.BO", 1, "BSE", "IN", "domestic secondary"),
                                      ("TM", 3, "NYSE", "US", "ADR")):
        con.execute("INSERT INTO listings (symbol, company_id, venue, country, is_home, structure, share_type) "
                    "VALUES (?,?,?,?,0,?,'common')", (sym, cid, venue, ctry, st))
    con.commit()
    return con


def add_news(con, title, score, days_ago=1.0, source="test"):
    cur = con.execute("INSERT INTO news_items (url, source, published, title, summary, fetched) VALUES (?,?,?,?,?,?)",
                      (f"u:{title}", source, _iso(days_ago), title, "", _iso()))
    con.execute("INSERT INTO news_sentiment VALUES (?,?,?,?,?,?,?)", (cur.lastrowid, 0, 0, 0, score, "test", _iso()))
    return cur.lastrowid


# ---------------------------------------------------------------- linking
def test_short_names():
    assert short_names("Infosys Limited")[0] == "Infosys"
    assert short_names("Toyota Motor Corporation")[0] == "Toyota Motor"


def test_linker_names_tickers_and_ambiguity():
    con = fixture()
    lk = Linker(con)
    assert set(lk.companies_in("Infosys wins $1.5 billion deal")) == {1}
    assert set(lk.companies_in("Why Nvidia's Rally Isn't Over")) == {5}
    assert set(lk.companies_in("Taiwan chip stock rises (NVDA) on demand")) == {5}
    assert set(lk.companies_in("Toyota recalls 500,000 cars")) == {3}
    assert lk.companies_in("Toyota Industries shares jump") == {}
    assert set(lk.companies_in("Markets", ["ticker:TM"])) == {3}


def test_industry_terms():
    con = fixture()
    lk = Linker(con)
    hits = lk.industries_in("Chip shortage hits automakers as car sales slow")
    assert ("Auto Manufacturers", "C") in hits and ("Auto Manufacturers", "D") in hits


# ---------------------------------------------------------------- rules
def test_recency_and_composite():
    ref = datetime.now(timezone.utc)
    assert abs(rules.recency_weight(_iso(3), ref, 3) - 0.5) < 0.01
    assert rules.weighted([(1.0, 1.0, 1), (-1.0, 1.0, -1)]) == 1.0
    w = {"A_market_sentiment": 0.3, "B_competition": 0.25, "C_manufacturing": 0.2, "D_customers": 0.25}
    c = rules.composite({"A": (0.5, 5), "B": (None, 0), "C": (-0.5, 1), "D": (0.1, 3)}, w, 2)
    assert abs(c - (0.3 * 0.5 + 0.25 * 0.1) / 0.55) < 1e-9          # C has too few items, B none


def test_rules_end_to_end_with_competitor_flip():
    con = fixture()
    add_news(con, "Infosys wins $1.5 billion deal from European bank", 0.8)
    add_news(con, "Infosys announces quarterly results ahead of estimates", 0.6)
    add_news(con, "Infosys shares slip on visa worries", -0.4)
    add_news(con, "Wipro wins large contract from US retailer", 0.7)            # rival's good news → B negative
    add_news(con, "IT spending by enterprises rebounds, survey says", 0.5)       # customers of IT services
    add_news(con, "Enterprise spending outlook improves for 2027", 0.4)
    linking.link_pending(con)
    rules.compute(con)
    t = {r["tag"]: r["value"] for r in con.execute("SELECT tag, value FROM stock_tags WHERE company_id=1")}
    assert float(t["news_A"]) > 0.2
    b = json.loads(con.execute("SELECT detail FROM stock_tags WHERE company_id=1 AND tag='news_composite'").fetchone()[0])
    assert b["items_competitors"] == 1 and "Wipro Limited" in b["peers"]
    assert float(t["news_D"]) > 0.3 and t["news_verdict"] in ("Bullish", "Neutral")
    w = {r["tag"]: r["value"] for r in con.execute("SELECT tag, value FROM stock_tags WHERE company_id=2")}
    assert float(w["news_B"]) < 0                                           # Infosys good news is a headwind for Wipro


# ---------------------------------------------------------------- IPO
def test_ipo_extraction():
    cases = {"Lenskart files DRHP with SEBI for ₹8,000 crore IPO": ("Lenskart", "filed"),
             "SoftBank-backed PayPay plans US IPO as early as March": ("PayPay", "planning"),
             "Meesho shares debut at 40% premium on NSE": ("Meesho", "listed"),
             "S-1 - Cerebras Systems Inc. (0002021728) (Filer)": ("Cerebras Systems Inc.", "filed"),
             "National Stock Exchange of India Sets Price Band for IPO": ("National Stock Exchange of India", "priced")}
    for t, want in cases.items():
        assert ipo.extract(t) == [want], (t, ipo.extract(t))
    for t in ("Why the IPO market is booming", "WuXi Biologics Passes Another FDA GMP Inspection",
              "Album Makes Exclusive Debut on NetEase Cloud Music", "Swiggy share price today"):
        assert ipo.extract(t) == [], t
    assert ipo.hints("Lenskart files DRHP with SEBI")[1] == "IN"
    assert ipo.hints("Klarna stock lists on NYSE")[1] == "US"


def test_ipo_pipeline_lead():
    con = fixture()
    for t, s in (("Lenskart files DRHP with SEBI for IPO", 0.3), ("Lenskart IPO opens for subscription on NSE", 0.5)):
        add_news(con, t, s)
    ipo.scan(con)
    leads.build(con)
    d = leads.top(con, "ipo_pipeline", 5)
    assert d and d[0]["name"] == "Lenskart" and d[0]["stage"] == "priced" and d[0]["country"] == "IN"
    assert d[0]["routes"][0]["route"] == "Apply in the IPO"


# ---------------------------------------------------------------- routes
def _L(sym, venue, country, structure="primary", home=1):
    return {"symbol": sym, "venue": venue, "country": country, "structure": structure, "share_type": "common",
            "is_home": home}


def test_routes_india_first():
    lst = [_L("INFY.NS", "NSE", "IN"), _L("INFY", "NYSE", "US", "ADR", 0)]
    r = routes.for_listed(lst, lst[0], "IT & Software")
    assert r[0]["route"].startswith("Buy directly on NSE") and r[1]["route"].startswith("ADR under LRS")
    assert any(x["route"].startswith("Avoid: NSE IFSC") for x in r)


def test_routes_china_a_share():
    lst = [_L("600519.SS", "SSE", "CN")]
    r = routes.for_listed(lst, lst[0], None)
    a = next(x for x in r if "Stock Connect" in x["route"])
    assert a["ok"] is True
    star = [_L("688981.SS", "SSE", "CN")]
    assert next(x for x in routes.for_listed(star, star[0], None) if "Stock Connect" in x["route"])["ok"] is False


def test_routes_limited_market_falls_to_etf():
    lst = [_L("2222.SR", "TADAWUL", "SA")]
    r = routes.for_listed(lst, lst[0], None)
    assert r[0]["ok"] is not True and "KSA" in routes.best(r)


def test_routes_unlisted_warnings():
    r = routes.for_unlisted("PayPay", "planning", "JP", "Financials & Banking")
    assert r[0]["route"].startswith("Wait for the listing")
    pre = next(x for x in r if x["route"].startswith("Pre-IPO"))
    assert pre["ok"] is False and "SEBI" in pre["notes"] and "ODI" in pre["notes"]


# ---------------------------------------------------------------- lead scoring
def test_model_signal_and_blend():
    s, info = leads.model_signal({"range_5_95": [-0.3, 0.6], "rf_annual": 0.05, "model": "GBM"}, 0.15)
    assert 0 < s < 1 and info["model"] == "GBM"
    s2, _ = leads.model_signal({"range_5_95": [-0.3, 0.6], "rf_annual": 0.05}, -0.05)
    assert s2 < 0
    assert leads.blend(0.4, None) == 0.4 and abs(leads.blend(0.4, -0.2) - 0.1) < 1e-12


def test_listed_lead_end_to_end():
    con = fixture()
    for k in range(4):
        add_news(con, f"Toyota sales rise in month {k}", 0.6, days_ago=k)
    linking.link_pending(con)
    rules.compute(con)
    set_tag(con, 3, "growth", "growth_1y", 0.12, {"range_5_95": [-0.2, 0.5], "rf_annual": 0.01,
                                                  "model": "EWMA vol + shrunk drift", "basis": "test"})
    leads.build(con)
    d = leads.top(con, "listed", 3)
    assert d and d[0]["name"].startswith("Toyota") and d[0]["model_score"] > 0
    assert any(x["route"].startswith("ADR under LRS") for x in d[0]["routes"])


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
