"""Yahoo Finance access: search, daily prices, fundamentals and FX, with a file cache.

Endpoints (query1 only; query2 and the crumb endpoints are not used):
  search        /v1/finance/search             symbol, exchange, sector, industry, other listings
  chart         /v8/finance/chart/{sym}        daily closes, adjusted closes, currency, exchange
  fundamentals  /ws/fundamentals-timeseries    market value, revenue, earnings, equity, shares
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from ..config import DB_DIR

CACHE = DB_DIR / "cache"
BASE = "https://query1.finance.yahoo.com"
FUND_TYPES = ["trailingMarketCap", "trailingTotalRevenue", "trailingNetIncome", "trailingPeRatio",
              "annualTotalRevenue", "annualNetIncome", "annualStockholdersEquity",
              "annualOrdinarySharesNumber", "annualPreferredStockEquity", "quarterlyTotalRevenue"]
TTL = {"search": 30 * 86400, "chart": 20 * 3600, "fund": 7 * 86400, "quote": 6 * 3600}

_S = requests.Session()
_S.headers["User-Agent"] = "Mozilla/5.0 (sfa research tool)"
_lock = threading.Lock()
_last = [0.0]
MIN_GAP = 0.25          # seconds between requests (≈4/s), on top of 429 back-off


def _get(url: str, params: dict | None = None, tries: int = 5):
    wait = 2.0
    for k in range(tries):
        with _lock:
            gap = MIN_GAP - (time.time() - _last[0])
            if gap > 0:
                time.sleep(gap)
            _last[0] = time.time()
        try:
            r = _S.get(url, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(wait); wait *= 2; continue
            if r.status_code in (400, 404):
                return None
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if k == tries - 1:
                return None
            time.sleep(wait); wait *= 2
    return None


def _cache_file(kind: str, key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_.^=" else "_" for c in key)[:120]
    return CACHE / kind / f"{safe}.json"


def _cached(kind: str, key: str, fetch, refresh: bool = False):
    f = _cache_file(kind, key)
    if not refresh and f.exists() and time.time() - f.stat().st_mtime < TTL[kind]:
        return json.loads(f.read_text())
    data = fetch()
    if data is None:
        return json.loads(f.read_text()) if f.exists() else None   # stale beats nothing
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data))
    return data


# ---------------------------------------------------------------- search
def search(query: str, n: int = 12, refresh: bool = False) -> list[dict]:
    def fetch():
        d = _get(f"{BASE}/v1/finance/search", {"q": query, "quotesCount": n, "newsCount": 0,
                                               "enableFuzzyQuery": "false"})
        if d is None:
            return None
        keep = ("symbol", "quoteType", "exchange", "exchDisp", "sector", "industry",
                "longname", "shortname", "typeDisp")
        return [{k: q.get(k) for k in keep} for q in d.get("quotes") or []]
    return _cached("search", f"{query}|{n}", fetch, refresh) or []


# ---------------------------------------------------------------- prices
def chart(symbol: str, start: datetime | int = datetime(2005, 1, 1, tzinfo=timezone.utc),
          refresh: bool = False) -> dict | None:
    """Daily history: {"meta": {...}, "t": [epoch], "close": [...], "adj": [...]}."""
    p1 = int(start.timestamp()) if isinstance(start, datetime) else int(start)

    def fetch():
        d = _get(f"{BASE}/v8/finance/chart/{quote(symbol)}",
                 {"period1": p1, "period2": int(time.time()), "interval": "1d", "events": "split,div"})
        try:
            res = d["chart"]["result"][0]
            q = res["indicators"]
            close = q["quote"][0]["close"]
            adj = (q.get("adjclose") or [{}])[0].get("adjclose") or close
            m = res["meta"]
            return {"meta": {k: m.get(k) for k in ("currency", "exchangeName", "fullExchangeName", "instrumentType",
                                                     "longName", "shortName", "regularMarketPrice",
                                                     "regularMarketTime", "firstTradeDate", "timezone")},
                    "t": res.get("timestamp") or [], "close": close, "adj": adj}
        except (TypeError, KeyError, IndexError):
            return None
    return _cached("chart", f"{symbol}|{p1}", fetch, refresh)


def last_quote(symbol: str, refresh: bool = False) -> dict | None:
    """Latest price and currency from a 5-day chart (cheap, for cross-listing ratios)."""
    def fetch():
        d = _get(f"{BASE}/v8/finance/chart/{quote(symbol)}", {"range": "5d", "interval": "1d"})
        try:
            m = d["chart"]["result"][0]["meta"]
            return {"price": m.get("regularMarketPrice"), "currency": m.get("currency"),
                    "time": m.get("regularMarketTime"), "exchange": m.get("exchangeName"),
                    "longName": m.get("longName"), "shortName": m.get("shortName"),
                    "instrumentType": m.get("instrumentType")}
        except (TypeError, KeyError, IndexError):
            return None
    return _cached("quote", symbol, fetch, refresh)


# ---------------------------------------------------------------- fundamentals
def fundamentals(symbol: str, refresh: bool = False) -> dict[str, list[dict]] | None:
    """{item: [{"date", "value", "ccy"}, ...]} sorted by date."""
    def fetch():
        p1 = int(datetime(2019, 1, 1, tzinfo=timezone.utc).timestamp())
        d = _get(f"{BASE}/ws/fundamentals-timeseries/v1/finance/timeseries/{quote(symbol)}",
                 {"type": ",".join(FUND_TYPES), "period1": p1, "period2": int(time.time())})
        if d is None:
            return None
        out = {}
        for r in (d.get("timeseries") or {}).get("result") or []:
            t = r["meta"]["type"][0]
            pts = [{"date": p["asOfDate"], "value": p["reportedValue"]["raw"], "ccy": p.get("currencyCode")}
                   for p in r.get(t) or [] if p and p.get("reportedValue")]
            if pts:
                out[t] = sorted(pts, key=lambda p: p["date"])
        return out
    return _cached("fund", symbol, fetch, refresh)


# ---------------------------------------------------------------- FX
MINOR = {"GBp": ("GBP", 0.01), "GBX": ("GBP", 0.01), "ZAc": ("ZAR", 0.01), "ILA": ("ILS", 0.01)}


def normalise_ccy(ccy: str | None) -> tuple[str | None, float]:
    """('GBp') -> ('GBP', 0.01): major currency and the factor to convert into it."""
    if ccy in MINOR:
        return MINOR[ccy]
    return (ccy.upper() if ccy else None), 1.0


def fx_to_usd(ccy: str | None, refresh: bool = False) -> float | None:
    """USD per one unit of `ccy` (minor units handled)."""
    major, f = normalise_ccy(ccy)
    if major is None:
        return None
    if major == "USD":
        return f
    q = last_quote(f"{major}USD=X", refresh)
    return q["price"] * f if q and q.get("price") else None


def fx_history_to_usd(ccy: str) -> dict[str, float]:
    """Daily USD-per-unit history keyed by ISO date (for converting price series)."""
    major, f = normalise_ccy(ccy)
    if major == "USD":
        return {}
    c = chart(f"{major}USD=X", datetime(2005, 1, 1, tzinfo=timezone.utc))
    if not c:
        return {}
    return {datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"): v * f
            for t, v in zip(c["t"], c["close"]) if v}
