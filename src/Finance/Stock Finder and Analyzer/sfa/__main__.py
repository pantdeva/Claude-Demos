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
    python -m sfa show SYMBOL          one company's classification
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
    for c in ("init", "prices", "fundamentals", "classify", "news", "feeds", "all", "jobs"):
        sub.add_parser(c)
    u = sub.add_parser("universe")
    u.add_argument("--limit", type=int)
    u.add_argument("--only", nargs="*")
    s = sub.add_parser("service")
    s.add_argument("--once", action="store_true")
    sh = sub.add_parser("show")
    sh.add_argument("symbol")
    a = p.parse_args(argv)

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
