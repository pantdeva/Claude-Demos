"""Command line.  Run from the "Stock Finder and Analyzer" folder:

    python -m sfa init                 create db/sfa.sqlite and load classification events
    python -m sfa universe [--limit N] [--only SYM ...]
    python -m sfa prices | fundamentals
    python -m sfa classify             classify everything and write exports/
    python -m sfa news                 poll the news feeds once
    python -m sfa feeds                show feed health
    python -m sfa all                  universe → prices → fundamentals → classify
    python -m sfa service [--once]     background scheduler
    python -m sfa jobs                 job schedule and last runs
    python -m sfa show SYMBOL          one company's classification and predictions
    python -m sfa models [--jobs N]    Milestone 2: walk-forward → leaderboard → MPT vs 1/N → predictions → export
    python -m sfa leaderboard          rebuild the leaderboard and exports from stored forecasts
    python -m sfa finder [--step news|ipo|leads|all]   Milestone 3: Stage 1 company finder
    python -m sfa leads [--kind listed|new_listing|ipo_pipeline] [-n N]   show current leads
    python -m sfa analyze [SYMBOL ...]  Milestone 4: Module 13 model + valuation (default: top leads)
    python -m sfa web [--host H] [--port P]     dashboard only (http://localhost:8000)
    python -m sfa start [--host H] [--port P]   dashboard + background scheduler (what start-on-boot runs)
    python -m sfa doctor               check Python, packages, settings, network and data
"""

from __future__ import annotations

import argparse
import json

from . import export, pipeline, service, universe
from .classify import market
from .data import rss
from .db import connect


def main(argv=None):
    p = argparse.ArgumentParser(prog="sfa", description="Stock Finder and Analyzer – Stage 0 backend")
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("init", "prices", "fundamentals", "classify", "news", "feeds", "all", "jobs", "leaderboard"):
        sub.add_parser(c)
    fi = sub.add_parser("finder")
    fi.add_argument("--step", choices=["news", "ipo", "leads", "all"], default="all")
    le = sub.add_parser("leads")
    le.add_argument("--kind", default="listed")
    le.add_argument("-n", type=int, default=20)
    for name in ("web", "start"):
        w = sub.add_parser(name)
        w.add_argument("--host", default="127.0.0.1")
        w.add_argument("--port", type=int, default=8000)
    sub.add_parser("doctor")
    an = sub.add_parser("analyze")
    an.add_argument("symbols", nargs="*")
    mo = sub.add_parser("models")
    mo.add_argument("--jobs", type=int)
    mo.add_argument("--only", nargs="*", help="home symbols to run (default: all)")
    u = sub.add_parser("universe")
    u.add_argument("--limit", type=int)
    u.add_argument("--only", nargs="*")
    s = sub.add_parser("service")
    s.add_argument("--once", action="store_true")
    sh = sub.add_parser("show")
    sh.add_argument("symbol")
    a = p.parse_args(argv)
    from .envfile import load_env
    load_env()

    if a.cmd == "doctor":
        from .doctor import run as doctor
        raise SystemExit(doctor())
    con = connect()
    market.seed_events(con)
    con.commit()
    if a.cmd == "init":
        print("database ready")
    elif a.cmd == "universe":
        print(universe.build(con, limit=a.limit, only=a.only))
    elif a.cmd == "prices":
        print(pipeline.refresh_prices(con))
    elif a.cmd == "fundamentals":
        print(pipeline.refresh_fundamentals(con))
    elif a.cmd == "classify":
        print(pipeline.classify_all(con), export.export(con))
    elif a.cmd == "news":
        print(rss.poll(con))
    elif a.cmd == "feeds":
        for h in rss.health(con):
            print(f"{'ok ' if h['ok'] else 'ERR'} {h['source']:15} {h['items_last'] or 0:4} items  {h['url']}"
                  + (f"  ({h['last_error']})" if h["last_error"] else ""))
    elif a.cmd == "all":
        for name in ("universe", "prices", "fundamentals", "classify"):
            print(name, service.run_job(con, name))
    elif a.cmd == "models":
        from .models import run_all
        only = None
        if a.only:
            only = [r[0] for r in con.execute(
                f"SELECT company_id FROM listings WHERE symbol IN ({','.join('?' * len(a.only))})", a.only)]
        print(run_all(con, jobs=a.jobs, only=only))
    elif a.cmd == "leaderboard":
        from .models import leaderboard, report
        print(leaderboard.build(con), report.export(con))
    elif a.cmd == "finder":
        from . import finder
        if a.step in ("news", "all"):
            print("news", finder.run_news(con))
        if a.step in ("ipo", "all"):
            print("ipo", finder.run_ipo(con))
        if a.step in ("leads", "all"):
            print("finder", finder.run_finder(con))
    elif a.cmd == "leads":
        from .finder import leads, routes
        for d in leads.top(con, a.kind, a.n):
            score = d["score"] if d["score"] is not None else float("nan")
            news = None if d["news_score"] is None else round(d["news_score"], 2)
            model = None if d["model_score"] is None else round(d["model_score"], 2)
            print(f"{score:+.2f}  {d['name'][:38]:38} {d['symbol'] or '':12} news {news}  model {model}"
                  f"  → {routes.best(d['routes'] or [])}")
    elif a.cmd == "analyze":
        from . import analyzer
        print(analyzer.run(con, a.symbols or None))
    elif a.cmd == "web":
        from .web.server import serve
        con.close()
        serve(a.host, a.port)
    elif a.cmd == "start":
        from .web.server import serve
        con.close()
        serve(a.host, a.port, block=False)
        service.run()
    elif a.cmd == "service":
        service.run(once=a.once)
    elif a.cmd == "jobs":
        for j in service.status(con):
            print(json.dumps(j, default=str))
    elif a.cmd == "show":
        r = con.execute("SELECT c.* FROM companies c JOIN listings l ON l.company_id=c.id WHERE l.symbol=?",
                        (a.symbol,)).fetchone()
        if not r:
            print("not in universe")
            return
        print(json.dumps(dict(r), indent=1))
        for t in con.execute("SELECT heading, tag, value, detail FROM stock_tags WHERE company_id=? ORDER BY heading",
                             (r["id"],)):
            print(f"{t['heading']:8} {t['tag']:20} {t['value']}   {t['detail'][:160]}")
        for l in con.execute("SELECT symbol, venue, is_home, structure, dr_ratio, share_type FROM listings "
                             "WHERE company_id=?", (r["id"],)):
            print("   ", dict(l))


if __name__ == "__main__":
    main()
