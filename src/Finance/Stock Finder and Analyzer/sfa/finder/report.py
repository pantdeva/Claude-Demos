"""Exports for Stage 1: exports/leads.md, leads.csv, ipo_pipeline.csv, news_signals.csv,
expansion.csv."""

from __future__ import annotations

import csv
import json

from ..config import EXPORT_DIR, load
from ..db import now
from . import leads as L
from . import routes as R


def _csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        if not rows:
            return
        fields = list(dict.fromkeys(k for r in rows for k in r))
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _p(v, d=0):
    return "—" if v is None else f"{v * 100:+.{d}f}%"


def _s(v):
    return "—" if v is None or v == "None" else f"{float(v):+.2f}"


def _esc(t: str) -> str:
    return (t or "").replace("|", "/").replace("\n", " ")


def export(con, out_dir=EXPORT_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = load("finder")
    k = cfg["leads"]["top_n"]
    listed, new, ipo = L.top(con, "listed", 10_000), L.top(con, "new_listing", 500), L.top(con, "ipo_pipeline", 500)
    flat = []
    for d in listed + new + ipo:
        flat.append({"kind": d["kind"], "name": d["name"], "symbol": d["symbol"], "exchange": d["exchange"],
                     "country": d["country"], "market_class": d["market_class"], "sector_group": d["sector_group"],
                     "stage": d["stage"], "score": d["score"], "news_score": d["news_score"],
                     "model_score": d["model_score"], "news_items": d["n_news"],
                     **{f"rule_{r}": (d["rules"] or {}).get(r) for r in "ABCD"},
                     "model": (d["model"] or {}).get("model"), "expected_1y": (d["model"] or {}).get("expected_1y"),
                     "best_route": R.best(d["routes"] or []), "first_seen": d["first_seen"], "updated": d["updated"]})
    _csv(out_dir / "leads.csv", flat)
    _csv(out_dir / "ipo_pipeline.csv", [dict(r) for r in con.execute(
        "SELECT name, stage, event_date, exchange_hint, country_hint, symbol, first_trade, source, title FROM ipo_events "
        "ORDER BY event_date DESC")])
    _csv(out_dir / "news_signals.csv", [dict(r) for r in con.execute(
        """SELECT c.name, c.home_symbol, r.as_of, r.rule, r.score, r.n_items FROM rule_scores r
           JOIN companies c ON c.id=r.company_id WHERE r.as_of=(SELECT MAX(as_of) FROM rule_scores)
           ORDER BY c.name, r.rule""")])
    exp = [dict(r) for r in con.execute("SELECT * FROM expansion_signals WHERE as_of=(SELECT MAX(as_of) FROM "
                                        "expansion_signals) ORDER BY suggest DESC, n_items DESC")]
    _csv(out_dir / "expansion.csv", exp)
    (out_dir / "leads.md").write_text(_md(con, listed, new, ipo, exp, k), encoding="utf-8")
    return {"listed": len(listed), "new_listings": len(new), "ipo_pipeline": len(ipo), "expansion": len(exp)}


def _md(con, listed, new, ipo, exp, k) -> str:
    n_news = con.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
    src = con.execute("SELECT COUNT(DISTINCT CASE WHEN source LIKE 'yahoo_finance:%' THEN substr(source, 15) "
                      "ELSE source END) FROM news_items").fetchone()[0]
    w = load("finder")["rules"]["weights"]
    out = [f"# Stage 1 company finder\n\nBuilt {now()}. {n_news:,} news items from {src} publishers/feeds, scored "
           "with FinBERT and linked to companies and industries.\n",
           "Rules: **A** market sentiment, **B** competition & news releases (rivals' news flipped), **C** "
           "manufacturing industry (supply chain), **D** customers. Each −1…+1. News composite weights "
           f"A {w['A_market_sentiment']:.0%}, B {w['B_competition']:.0%}, C {w['C_manufacturing']:.0%}, "
           f"D {w['D_customers']:.0%}. Lead score = ½ news composite + ½ quant-model signal (the Milestone 2 model "
           "chosen for the company: expected 1-year excess return over its spread).\n"]
    out.append(f"## Top {min(k, len(listed))} listed leads\n")
    out.append("| # | Company | Exchange | Score | News | Model | A | B | C | D | Items | Model (1y expected) | Best route for an Indian resident |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, d in enumerate(listed[:k], 1):
        r, m = d["rules"] or {}, d["model"] or {}
        out.append(f"| {i} | {_esc(d['name'])} ({d['symbol']}) | {d['exchange']} | **{_s(d['score'])}** | "
                   f"{_s(d['news_score'])} | {_s(d['model_score'])} | {_s(r.get('A'))} | {_s(r.get('B'))} | "
                   f"{_s(r.get('C'))} | {_s(r.get('D'))} | {d['n_news']} | {m.get('model', '—')} "
                   f"({_p(m.get('expected_1y'))}) | {_esc(R.best(d['routes'] or []))} |")
    out.append("")
    if listed:
        out.append(f"## Weakest {min(10, len(listed))} listed (most negative)\n")
        out.append("| Company | Score | News | Model | Verdict |")
        out.append("|---|---|---|---|---|")
        for d in listed[::-1][:10]:
            out.append(f"| {_esc(d['name'])} ({d['symbol']}) | {_s(d['score'])} | {_s(d['news_score'])} | "
                       f"{_s(d['model_score'])} | {(d['rules'] or {}).get('verdict')} |")
        out.append("")
        out.append("## Evidence for the top 5\n")
        for d in listed[:5]:
            out.append(f"**{d['name']}** — peers used for rule B: {', '.join((d['rules'] or {}).get('peers') or []) or '—'}\n")
            for rule, items in (d["evidence"] or {}).items():
                for e in items:
                    out.append(f"- {rule}: {_esc(e['title'])} ({e['source'].replace('yahoo_finance:', '')}, "
                               f"{e['date']}, FinBERT {e['sentiment']:+.2f})")
            out.append("")
    out.append("## New listings (first year of trading)\n")
    if new:
        out.append("| Company | Symbol | Score | IPO news | Peer-proxy model | 1y expected | Peers |")
        out.append("|---|---|---|---|---|---|---|")
        for d in new:
            m = d["model"] or {}
            out.append(f"| {_esc(d['name'])} | {d['symbol']} | {_s(d['score'])} | {_s(d['news_score'])} | "
                       f"{m.get('model', '—')} | {_p(m.get('expected_1y'))} | {', '.join((m.get('peers') or [])[:4])} |")
    else:
        out.append("None found in the current news window.")
    out.append("")
    out.append("## IPO pipeline (not trading yet)\n")
    if ipo:
        out.append("| Company | Stage | Country | Score | Stories | Route | Latest headline |")
        out.append("|---|---|---|---|---|---|---|")
        for d in ipo[:40]:
            last = ((d["evidence"] or {}).get("IPO") or [{}])[-1]
            out.append(f"| {_esc(d['name'])} | {d['stage']} | {d['country'] or '—'} | {_s(d['score'])} | {d['n_news']} | "
                       f"{_esc(R.best(d['routes'] or []))} | {_esc(last.get('title', ''))[:90]} |")
    else:
        out.append("None found in the current news window.")
    out.append("")
    out.append("## Markets to consider adding (news on growing industries)\n")
    if exp:
        out.append("| Market | Exchange | Stories | Growth stories | Sentiment | Sectors | Suggest |")
        out.append("|---|---|---|---|---|---|---|")
        for e in exp:
            groups = ", ".join(g for g, _ in json.loads(e["top_groups"] or "[]"))
            out.append(f"| {e['country']} | {e['exchange']} | {e['n_items']} | {e['growth_items']} | "
                       f"{e['sentiment']:+.2f} | {groups or '—'} | {'**yes**' if e['suggest'] else 'no'} |")
    else:
        out.append("No market outside the covered exchanges was mentioned enough.")
    out.append("\nRoutes follow Indian-resident rules as of the dates in config/routes.yaml; check them before acting. "
               "Research output, not investment advice.\n")
    return "\n".join(out)
