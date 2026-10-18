"""Download prices and fundamentals for every candidate in pools.json (cached).

Prices: Yahoo chart API (adjusted daily closes since 2011, plus exchange/currency).
Fundamentals: Yahoo fundamentals-timeseries (market cap, trailing 12-month revenue
and net income, annual revenue/net income, P/E). FX: Yahoo "<CCY>USD=X" closes.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).parent
CACHE = HERE / "cache"
CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}"
         "&interval=1d&events=split%2Cdiv")
TS = ("https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{sym}"
      "?type={types}&period1={p1}&period2={p2}")
TYPES = ["trailingMarketCap", "trailingTotalRevenue", "trailingNetIncome", "annualTotalRevenue",
         "annualNetIncome", "trailingPeRatio", "quarterlyTotalRevenue", "quarterlyNetIncome"]
START = int(datetime(2011, 1, 1, tzinfo=timezone.utc).timestamp())

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"


def get_json(url: str, tries: int = 5):
    wait = 2.0
    for k in range(tries):
        try:
            r = S.get(url, timeout=30)
            if r.status_code == 429:
                time.sleep(wait); wait *= 2; continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if k == tries - 1:
                return None
            time.sleep(wait); wait *= 2
    return None


def fetch_chart(sym: str) -> dict | None:
    f = CACHE / "chart" / f"{sym}.json"
    if f.exists():
        return json.loads(f.read_text())
    d = get_json(CHART.format(sym=requests.utils.quote(sym), p1=START, p2=int(time.time())))
    try:
        res = d["chart"]["result"][0]
        q = res["indicators"]
        adj = (q.get("adjclose") or [{}])[0].get("adjclose") or q["quote"][0]["close"]
        out = {"meta": {k: res["meta"].get(k) for k in ("currency", "exchangeName", "fullExchangeName",
                                                         "instrumentType", "longName", "shortName",
                                                         "regularMarketPrice", "regularMarketTime")},
               "t": res["timestamp"], "c": adj}
    except (TypeError, KeyError, IndexError):
        return None
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def fetch_fund(sym: str) -> dict | None:
    f = CACHE / "fund" / f"{sym}.json"
    if f.exists():
        return json.loads(f.read_text())
    p1 = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())
    d = get_json(TS.format(sym=requests.utils.quote(sym), types=",".join(TYPES), p1=p1, p2=int(time.time())))
    if d is None:
        return None
    out = {}
    for r in (d.get("timeseries") or {}).get("result") or []:
        t = r["meta"]["type"][0]
        vals = [x for x in (r.get(t) or []) if x and x.get("reportedValue")]
        out[t] = [(x["asOfDate"], x["reportedValue"]["raw"], x.get("currencyCode")) for x in vals]
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def main():
    pools = json.loads((HERE / "pools.json").read_text())
    syms = list(dict.fromkeys(t for p in pools.values() for t in p["tickers"])) + list(pools)
    t0, bad = time.time(), []
    for i, s in enumerate(syms, 1):
        c = fetch_chart(s)
        f = fetch_fund(s) if not s.startswith("^") else {}
        if c is None or f is None:
            bad.append(s)
        if i % 50 == 0:
            print(f"{i}/{len(syms)} ({time.time() - t0:.0f}s), missing so far: {len(bad)}", flush=True)
        time.sleep(0.15)
    # FX to USD for every currency seen in prices or fundamentals
    ccys = set()
    for s in syms:
        c = fetch_chart(s)
        if c and c["meta"].get("currency"):
            ccys.add(c["meta"]["currency"])
        f = fetch_fund(s) or {}
        for rows in f.values():
            ccys |= {r[2] for r in rows if r[2]}
    ccys = {("GBP" if x in ("GBp", "GBX") else x.upper()) for x in ccys} - {"USD"}
    for c in sorted(ccys):
        fetch_chart(f"{c}USD=X")
    print(f"done: {len(syms)} symbols, missing {len(bad)}: {bad[:30]}; currencies: {sorted(ccys)}")
    (CACHE / "missing.json").write_text(json.dumps(bad))


if __name__ == "__main__":
    sys.exit(main())
