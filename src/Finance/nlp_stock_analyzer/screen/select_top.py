"""Score every candidate on four fundamentals and keep the best 25 per index.

Metrics (all from Yahoo Finance):
  valuation    market capitalisation in USD, rolled forward to today's price
  size         trailing 12-month revenue in USD (how big the business is)
  growth       revenue growth: latest trailing 12 months vs the 12 months a year earlier
               (falls back to the latest fiscal year vs the year before)
  profitability net profit margin: trailing 12-month net income / revenue

Composite = average of each metric's percentile rank within the index's pool
(at least 3 of the 4 metrics needed). Ties are broken by market value.
"""

from __future__ import annotations

import json
from bisect import bisect_right
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
CACHE = HERE / "cache"
NASDAQ = {"NMS", "NGM", "NCM"}
NYSE = {"NYQ"}


def load(kind, sym):
    f = CACHE / kind / f"{sym}.json"
    return json.loads(f.read_text()) if f.exists() else None


def fx_to_usd(ccy: str | None) -> float | None:
    if not ccy:
        return None
    if ccy in ("GBp", "GBX"):
        return (fx_to_usd("GBP") or np.nan) / 100
    ccy = ccy.upper()
    if ccy == "USD":
        return 1.0
    c = load("chart", f"{ccy}USD=X")
    if not c:
        return None
    vals = [v for v in c["c"] if v]
    return vals[-1] if vals else None


def price_on(chart, iso: str) -> float | None:
    ts = int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()) + 86399
    i = bisect_right(chart["t"], ts) - 1
    while i >= 0 and not chart["c"][i]:
        i -= 1
    return chart["c"][i] if i >= 0 else None


def metrics(sym: str) -> dict | None:
    ch, fd = load("chart", sym), load("fund", sym)
    if not ch or fd is None:
        return None
    closes = [(t, c) for t, c in zip(ch["t"], ch["c"]) if c]
    if not closes:
        return None
    last_t, last_px = closes[-1]
    m = ch["meta"]
    out = {"ticker": sym, "name": m.get("longName") or m.get("shortName") or sym,
           "exchange": m.get("exchangeName"), "currency": m.get("currency"),
           "price": last_px, "price_date": str(datetime.fromtimestamp(last_t, timezone.utc).date()),
           "history_start": str(datetime.fromtimestamp(closes[0][0], timezone.utc).date())}
    # market value, rolled forward from the last reported date to the latest close
    mc = fd.get("trailingMarketCap") or []
    if mc:
        d, v, ccy = mc[-1]
        p0 = price_on(ch, d)
        scale = last_px / p0 if p0 else 1.0
        fx = fx_to_usd(ccy or m.get("currency"))
        out["mcap_usd"] = v * scale * fx if fx else None
    # revenue, growth, margin
    tr, tn = fd.get("trailingTotalRevenue") or [], fd.get("trailingNetIncome") or []
    ar, an = fd.get("annualTotalRevenue") or [], fd.get("annualNetIncome") or []
    rev = rev_ccy = rev_date = None
    if tr:
        rev_date, rev, rev_ccy = tr[-1]
    elif ar:
        rev_date, rev, rev_ccy = ar[-1]
    if rev is not None:
        fx = fx_to_usd(rev_ccy or m.get("currency"))
        out["revenue_usd"] = rev * fx if fx else None
        out["revenue_date"] = rev_date
    growth = None
    if len(tr) >= 2:
        d_last = date.fromisoformat(tr[-1][0])
        prior = [r for r in tr[:-1] if 300 <= (d_last - date.fromisoformat(r[0])).days <= 430]
        if prior and prior[-1][1] > 0:
            growth = tr[-1][1] / prior[-1][1] - 1
            out["growth_basis"] = "trailing 12 months"
    if growth is None and len(ar) >= 2 and ar[-2][1] > 0:
        growth = ar[-1][1] / ar[-2][1] - 1
        out["growth_basis"] = "fiscal year"
        # a prior year under a quarter of the current one (or 6x growth) is usually a bad data
        # point; fall back to the average yearly growth over two years
        if (ar[-2][1] < 0.25 * ar[-1][1] or growth > 5) and len(ar) >= 3 and ar[-3][1] > 0:
            growth = (ar[-1][1] / ar[-3][1]) ** 0.5 - 1
            out["growth_basis"] = "2-year average (prior-year figure looked wrong)"
    if growth is not None and growth > 5:
        growth, out["growth_basis"] = None, "unreliable"
    out["rev_growth"] = growth
    margin = None
    if tr and tn:
        same = [n for n in tn if n[0] == tr[-1][0]]
        if same and tr[-1][1] > 0:
            margin = same[-1][1] / tr[-1][1]
    if margin is None and ar and an:
        same = [n for n in an if n[0] == ar[-1][0]]
        if same and ar[-1][1] > 0:
            margin = same[-1][1] / ar[-1][1]
    out["net_margin"] = margin
    # net income above revenue comes from investment/revaluation gains or one-off items,
    # not operating profitability: show it, but leave it out of the score
    out["net_margin_scored"] = margin if margin is None or margin <= 1.0 else None
    if margin is not None and margin > 1.0:
        out["flag"] = "Net income exceeds revenue (investment, revaluation or one-off gains)"
    pe = fd.get("trailingPeRatio") or []
    out["pe"] = pe[-1][1] if pe else None
    return out


def main():
    pools = json.loads((HERE / "pools.json").read_text())
    cache = {}
    selection, dropped = {}, {}
    for idx, p in pools.items():
        rows = []
        for s in p["tickers"]:
            if s not in cache:
                cache[s] = metrics(s)
            r = cache[s]
            if r is None:
                dropped.setdefault(idx, []).append((s, "no data"))
                continue
            ex = p.get("filter_exchange")
            if ex == "NMS" and r["exchange"] not in NASDAQ:
                continue
            if ex == "NYQ" and r["exchange"] not in NYSE:
                continue
            rows.append(dict(r))
        df = pd.DataFrame(rows)
        cols = ["mcap_usd", "revenue_usd", "rev_growth", "net_margin_scored"]
        for c in cols + ["net_margin"]:
            if c not in df:
                df[c] = np.nan
        ranks = df[cols].rank(pct=True)
        df["n_metrics"] = df[cols].notna().sum(axis=1)
        df["score"] = ranks.mean(axis=1, skipna=True)
        for c in cols:
            df[f"pct_{c.replace('_scored', '')}"] = ranks[c]
        ok = df[df.n_metrics >= 3].sort_values(["score", "mcap_usd"], ascending=False)
        for _, r in df[df.n_metrics < 3].iterrows():
            dropped.setdefault(idx, []).append((r.ticker, "missing fundamentals"))
        top = ok.head(25).reset_index(drop=True)
        top["rank"] = top.index + 1
        selection[idx] = {"name": p["name"], "region": p["region"], "ccy": p["ccy"],
                          "pool_size": int(len(df)), "pool_complete": p.get("complete", False),
                          "companies": json.loads(top.to_json(orient="records"))}
        print(f"{p['name']:<26} pool {len(df):3d} → top {len(top)}: "
              + ", ".join(top.ticker.head(6)))
    (HERE / "selection.json").write_text(json.dumps(selection, indent=1))
    (HERE / "dropped.json").write_text(json.dumps(dropped, indent=1))
    uniq = {c["ticker"] for v in selection.values() for c in v["companies"]}
    print(f"unique selected tickers: {len(uniq)}")


if __name__ == "__main__":
    main()
