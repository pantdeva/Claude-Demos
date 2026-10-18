"""Offline tests for the Stage 0 classifiers, feed parser and scheduler.

Run from the "Stock Finder and Analyzer" folder:  python -m pytest tests -q
(or  python tests/test_stage0.py  without pytest).
"""

import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sfa.classify import fundamental as F  # noqa: E402
from sfa.classify import listing as L  # noqa: E402
from sfa.classify import market as M  # noqa: E402
from sfa.classify import sector as S  # noqa: E402
from sfa.config import venues  # noqa: E402
from sfa.data import rss  # noqa: E402
from sfa.db import connect, set_tag  # noqa: E402
from sfa.service import is_due  # noqa: E402


# ---------------------------------------------------------------- names
def test_same_company_matches_legal_forms():
    assert L.same_company("Taiwan Semiconductor Manufacturing Company Limited",
                          "Taiwan Semiconductor Manufacturing Co Ltd")
    assert L.same_company("Samsung Electronics Co., Ltd.", "Samsung Electronics Co Ltd")
    assert L.same_company("Shell plc", "Shell PLC")


def test_same_company_rejects_subsidiaries():
    assert not L.same_company("Enel SpA", "Enel Chile S.A.")
    assert not L.same_company("Saudi Arabian Oil Company", "Saudi Aramco Base Oil Company")
    assert not L.same_company("Toyota Motor Corporation", "Toyota Industries Corporation")
    assert not L.same_company("Reliance Industries Limited", "Reliance, Inc.")
    assert not L.same_company("Compass Group PLC", "Compass, Inc.")
    assert not L.same_company("First Financial Holding Co., Ltd.", "First Financial Bancorp.")
    assert not L.same_company("First Financial Holding Co., Ltd.", "First Financial Corporation")
    assert not L.same_company("NN Group N.V.", "NN, Inc.")
    assert not L.same_company("Acme Ltd", "Acme Inc", "Technology", "Energy")
    assert L.same_company("Alibaba Group Holding Limited", "Alibaba Group Holding Ltd", "Consumer Cyclical", "Consumer Cyclical")


# ---------------------------------------------------------------- share type
def test_share_type_rules():
    assert L.share_type("005935.KS")[0] == "preferred"
    assert L.share_type("005930.KS")[0] == "common"
    assert L.share_type("VOW3.DE")[0] == "preferred"
    assert L.share_type("BAC-PL")[0] == "preferred"
    assert L.share_type("PETR4.SA")[0] == "preferred"
    assert L.share_type("PETR3.SA")[0] == "common"
    assert L.share_type("BRK-B") == ("common", "B", "default")
    assert L.share_type("GOOGL")[1] == "A"
    assert L.share_type("XYZ.L", "Something Preference Shares")[0] == "preferred"


# ---------------------------------------------------------------- venues
def test_venue_resolution():
    V = venues()
    assert V.resolve("2330.TW")["id"] == "TWSE"
    assert V.resolve("TSM", "NYQ")["id"] == "NYSE"
    assert V.resolve("SMSN.IL", "IOB")["id"] == "LSE_IOB"
    assert V.resolve("RY4C.DU", "DUS") is None          # Düsseldorf, not Dubai
    assert V.resolve("ABC.DU") is None
    assert len(V.covered()) >= 20


def _l(sym, venue, role="covered", ccy="USD", country=None, rank=0, st="common"):
    country = country or venues().by_id[venue]["country"]
    return {"symbol": sym, "venue": venue, "venue_role": role, "currency": ccy, "country": country,
            "rank": rank, "share_type": st}


def test_choose_home_foreign_company():
    ls = [_l("TSM", "NYSE"), _l("2330.TW", "TWSE", ccy="TWD", rank=2)]
    assert L.choose_home(ls, "TWD", "TSM")[0]["symbol"] == "2330.TW"


def test_choose_home_german_company_on_xetra():
    ls = [_l("SAP", "NYSE"), _l("SAP.DE", "XETRA", role="secondary", ccy="EUR", rank=1)]
    assert L.choose_home(ls, "EUR", "SAP")[0]["symbol"] == "SAP.DE"
    ls = [_l("NVDA", "NASDAQ"), _l("NVD.DE", "XETRA", role="secondary", ccy="EUR", rank=1)]
    assert L.choose_home(ls, "USD", "NVDA")[0]["symbol"] == "NVDA"


def test_choose_home_us_company_with_cdr():
    ls = [_l("NVDA", "NASDAQ"), _l("NVDA.TO", "TSX", ccy="CAD", rank=1)]
    assert L.choose_home(ls, "USD", "NVDA")[0]["symbol"] == "NVDA"


def test_choose_home_canadian_reporting_usd():
    ls = [_l("SHOP", "NASDAQ"), _l("SHOP.TO", "TSX", ccy="CAD", rank=1)]
    assert L.choose_home(ls, "USD", "SHOP")[0]["symbol"] == "SHOP.TO"


def test_choose_home_skips_preferred_and_override():
    ls = [_l("005935.KS", "KRX", ccy="KRW", st="preferred"), _l("005930.KS", "KRX", ccy="KRW", rank=1)]
    assert L.choose_home(ls, "KRW", "005935.KS")[0]["symbol"] == "005930.KS"
    ls = [_l("SHEL", "NYSE"), _l("SHEL.L", "LSE", ccy="GBp", rank=2)]
    assert L.choose_home(ls, "USD", "SHEL") == (ls[1], "override")


# ---------------------------------------------------------------- structure
def test_listing_structure():
    home = {"symbol": "2330.TW", "country": "TW"}
    assert L.listing_structure(_l("TSM", "NYSE"), home, 30.0, 150.0)[:2] == ("ADR", 5)
    assert L.listing_structure(_l("SMSN.IL", "LSE_IOB", role="secondary"), home, 1, 25)[0] == "GDR"
    assert L.listing_structure(_l("0NRE.IL", "LSE_IOB", role="secondary"), home, 1, 1)[0] == "foreign ordinary"
    assert L.listing_structure(_l("TSMWF", "US_OTC", role="secondary"), home, 1, 1)[0] == "OTC ordinary"
    assert L.listing_structure(_l("TSMCY", "US_OTC", role="secondary"), home, 1, 5)[0] == "OTC ADR"
    ca = {"symbol": "RY.TO", "country": "CA"}
    assert L.listing_structure(_l("RY", "NYSE"), ca, 100, 100)[0] == "foreign ordinary"
    us = {"symbol": "GOOGL", "country": "US"}
    assert L.listing_structure(_l("GOOG.TO", "TSX", ccy="CAD"), us, 300, 33)[0] == "CDR"
    assert L.listing_structure(_l("GOOG", "NASDAQ"), us, 300, 300)[0] == "domestic secondary"
    inf = {"symbol": "INFY.NS", "country": "IN"}
    assert L.listing_structure(_l("INFY.BO", "BSE", ccy="INR"), inf, 1, 1)[0] == "domestic secondary"


def test_company_structure_priority():
    assert L.company_structure(["primary", "foreign ordinary", "ADR"]).startswith("Depositary")
    assert L.company_structure(["primary", "foreign ordinary"]).startswith("Cross-listed")
    assert L.company_structure(["primary", "domestic secondary", "OTC ordinary"]) == "Domestic"
    assert L.company_structure(["primary", "foreign ordinary"], ["covered", "secondary"]) == "Domestic"


def test_nice_ratio():
    assert L.nice_ratio(4.9) == 5
    assert L.nice_ratio(0.102) == 0.1
    assert L.nice_ratio(7.0) == 7.0


# ---------------------------------------------------------------- market class
def test_market_class_current_and_providers():
    assert M.current_class("US") == "DM"
    assert M.current_class("IN") == "EM"
    assert M.current_class("KR", "MSCI") == "EM" and M.current_class("KR", "FTSE") == "DM"
    assert M.current_class("XX") == "SA"
    d = M.detail("KR")
    assert d["agree"] is False and d["watch"]


def test_market_class_on_date():
    assert M.class_on("SA", "2018-01-01")[0] == "SA"          # before MSCI inclusion
    assert M.class_on("SA", "2020-01-01")[0] == "EM"
    assert M.class_on("KR", "2005-01-01", "FTSE")[0] == "EM"
    assert M.class_on("KR", "2015-01-01", "FTSE")[0] == "DM"
    assert M.class_on("US", "2000-01-01") == ("DM", True)     # no history → assumed


# ---------------------------------------------------------------- sector
def test_sector_mapping():
    assert S.map_sector("Technology", "Semiconductors")["group_name"] == "IT & Software"
    assert S.map_sector("Communication Services", "Internet Content & Information")["group"] == "IT"
    assert S.map_sector("Consumer Defensive", "Beverages")["group_name"] == "Consumer Discretionary & Staples"
    assert S.map_sector("Basic Materials", "Steel")["group"] == "EMU"
    assert S.map_sector("Real Estate", "REIT - Industrial")["group"] == "IRE"
    assert S.map_sector(None, None)["group_name"] == "Unclassified"


def test_behaviour():
    assert S.behaviour("Defensive", "Packaged Foods", 0.5)[0] == "Defensive"
    assert S.behaviour("Sensitive", "Semiconductors", 1.8)[0] == "Cyclical"
    assert S.behaviour("Cyclical", "Banks - Diversified", 0.4)[0] == "Defensive"   # beta overrides
    assert S.behaviour("Defensive", "Medical Devices", 1.5)[0] == "Cyclical"
    assert S.behaviour(None, None, None)[0] == "Unclassified"
    assert S.behaviour("Defensive", "Utilities—Regulated Electric", 1.2) == ("Defensive", "industry")
    assert S.norm_industry("Banks—Regional") == "Banks - Regional"
    assert S.norm_industry("Beverages—Non-Alcoholic") == "Beverages - Non-Alcoholic"


# ---------------------------------------------------------------- stock level
def test_cap_bands():
    assert F.usd_band(5e12) == "Mega" and F.usd_band(50e9) == "Large"
    assert F.usd_band(5e9) == "Mid" and F.usd_band(1e9) == "Small" and F.usd_band(1e8) == "Micro"
    assert F.sebi_band(1) == "Large" and F.sebi_band(101) == "Mid" and F.sebi_band(251) == "Small"


def test_style_scores_rank_growth_and_value():
    rng = np.random.default_rng(0)
    rows = []
    for i in range(30):
        rows.append({"id": i, "cell": "DM|IT", "group": "IT", "growth": float(rng.normal(0.1, 0.05)),
                     "ep": float(rng.normal(0.04, 0.01)), "bp": float(rng.normal(0.3, 0.1)),
                     "sp": float(rng.normal(0.3, 0.1))})
    rows.append({"id": 99, "cell": "DM|IT", "group": "IT", "growth": 0.6, "ep": 0.005, "bp": 0.02, "sp": 0.03})
    rows.append({"id": 98, "cell": "DM|IT", "group": "IT", "growth": -0.1, "ep": 0.15, "bp": 1.5, "sp": 2.0})
    s = F.style_scores(rows)
    assert s[99]["label"] == "Growth" and s[98]["label"] == "Value"
    assert s[0]["basis"] == "market class × sector group"


def test_weekly_beta_recovers_known_beta():
    rng = np.random.default_rng(1)
    start = datetime.now() - timedelta(days=3 * 365)
    m, a, px, bx = 100.0, 100.0, {}, {}
    for k in range(1100):
        d = (start + timedelta(days=k))
        if d.weekday() >= 5:
            continue
        rm = rng.normal(0, 0.01)
        m *= math.exp(rm)
        a *= math.exp(1.5 * rm + rng.normal(0, 0.004))
        px[d.strftime("%Y-%m-%d")], bx[d.strftime("%Y-%m-%d")] = a, m
    beta, n = F.weekly_beta(px, bx)
    assert n > 100 and abs(beta - 1.5) < 0.15


def test_growth_rate_falls_back_on_broken_year():
    f = {"annualTotalRevenue": [{"value": 100}, {"value": 110}, {"value": 1000}]}
    g, basis = F.growth_rate(f)
    assert basis.startswith("2-year") and abs(g - (10 ** 0.5 - 1)) < 1e-9
    assert F.growth_rate({"annualTotalRevenue": [{"value": 100}, {"value": 120}]})[0] == 0.2 or \
        abs(F.growth_rate({"annualTotalRevenue": [{"value": 100}, {"value": 120}]})[0] - 0.2) < 1e-9


# ---------------------------------------------------------------- feeds
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>TSMC lifts capex &amp; guidance - Reuters</title><link>https://x/1</link>
<pubDate>Sun, 18 Oct 2026 09:00:00 GMT</pubDate><description>&lt;p&gt;Chip demand&lt;/p&gt;</description></item>
<item><title>Infosys wins deal</title><link>https://x/2</link><pubDate>Sat, 17 Oct 2026 10:00:00 +0530</pubDate></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>SEC</title>
<entry><title>S-1 - Example Corp</title><link href="https://sec/1"/><updated>2026-10-16T12:00:00-04:00</updated>
<summary>Registration statement</summary></entry></feed>"""


def test_parse_rss_and_atom():
    items = rss.parse_feed(RSS)
    assert len(items) == 2 and items[0]["title"] == "TSMC lifts capex & guidance - Reuters"
    assert items[0]["summary"] == "Chip demand" and items[0]["published"] == "2026-10-18T09:00:00Z"
    assert items[1]["published"] == "2026-10-17T04:30:00Z"
    a = rss.parse_feed(ATOM)
    assert a[0]["link"] == "https://sec/1" and a[0]["published"] == "2026-10-16T16:00:00Z"


def test_title_key_dedupes_syndication():
    assert rss.title_key("TSMC lifts capex - Reuters") == rss.title_key("TSMC lifts capex | Mint")
    assert rss.title_key("TSMC lifts capex") != rss.title_key("TSMC cuts capex")


def test_every_listed_news_site_configured():
    from sfa.config import load
    ids = {s["id"] for s in load("news_sources")["sources"]}
    assert {"bloomberg", "ft", "wsj", "reuters", "yahoo_finance", "marketwatch", "economist", "economic_times",
            "mint", "moneycontrol", "pulse_zerodha", "investing_in"} <= ids
    for s in load("news_sources")["sources"]:
        assert rss.feed_urls(s, "INFY.NS") and "{" not in rss.fallback_url(s)


def test_poll_falls_back_to_google_news():
    class R:
        def __init__(self, ok, body=b""):
            self.ok, self.content = ok, body

        def raise_for_status(self):
            if not self.ok:
                import requests
                raise requests.HTTPError("403")

    class Sess:
        headers = {}
        calls = []

        def get(self, url, timeout=None):
            self.calls.append(url)
            return R("news.google.com" in url, RSS)

    con = connect(":memory:")
    s = Sess()
    for _ in range(3):
        rss.poll(con, ["ft"], session=s)
    assert any("site:ft.com" in u for u in s.calls)
    assert con.execute("SELECT COUNT(*) FROM news_items WHERE source='ft'").fetchone()[0] == 2


# ---------------------------------------------------------------- db + scheduler
def test_tag_history_only_on_change():
    con = connect(":memory:")
    con.execute("INSERT INTO companies (id, name, name_key) VALUES (1, 'X', 'x')")
    set_tag(con, 1, "stock", "cap_band", "Large", as_of="2026-01-01")
    set_tag(con, 1, "stock", "cap_band", "Large", as_of="2026-02-01")
    set_tag(con, 1, "stock", "cap_band", "Mega", as_of="2026-03-01")
    h = con.execute("SELECT value, as_of FROM stock_tag_history ORDER BY as_of").fetchall()
    assert [tuple(r) for r in h] == [("Large", "2026-01-01"), ("Mega", "2026-03-01")]


def test_is_due():
    utc = datetime(2026, 10, 18, 3, 0)            # 08:30 IST
    local = utc + timedelta(hours=5, minutes=30)
    assert is_due({"every_hours": 24}, None, utc, local)
    assert not is_due({"every_hours": 24}, utc - timedelta(hours=2), utc, local)
    assert is_due({"every_hours": 1}, utc - timedelta(hours=2), utc, local)
    # daily 07:00 local job last ran yesterday 07:05 local → due
    assert is_due({"at": "07:00"}, utc - timedelta(days=1, hours=1, minutes=25), utc, local)
    # ran today at 07:05 local → not due
    assert not is_due({"at": "07:00"}, utc - timedelta(hours=1, minutes=25), utc, local)


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
