"""Stage 1: company finder.

news collection (RSS, Yahoo Finance, NewsAPI) → FinBERT scoring → linking to
companies and industries → rules A–D → IPO pipeline and new listings → lead scoring
with the quant models → Indian-resident investment routes → exports.
"""

from __future__ import annotations

SCHEMA = """
CREATE TABLE IF NOT EXISTS news_sentiment (
    news_id INTEGER PRIMARY KEY, positive REAL, negative REAL, neutral REAL, score REAL, model TEXT, scored TEXT
);
CREATE TABLE IF NOT EXISTS news_links (
    news_id INTEGER, target TEXT, rule TEXT, direction INTEGER, basis TEXT,
    PRIMARY KEY (news_id, target, rule)
);
CREATE INDEX IF NOT EXISTS ix_links_target ON news_links(target);
CREATE TABLE IF NOT EXISTS rule_scores (
    company_id INTEGER, as_of TEXT, rule TEXT, score REAL, n_items INTEGER,
    PRIMARY KEY (company_id, as_of, rule)
);
CREATE TABLE IF NOT EXISTS ipo_events (
    id INTEGER PRIMARY KEY, name TEXT, name_key TEXT, stage TEXT, event_date TEXT, news_id INTEGER UNIQUE,
    title TEXT, source TEXT, exchange_hint TEXT, country_hint TEXT, company_id INTEGER, symbol TEXT,
    first_trade TEXT, found TEXT
);
CREATE INDEX IF NOT EXISTS ix_ipo_key ON ipo_events(name_key);
CREATE TABLE IF NOT EXISTS finder_leads (
    lead_key TEXT PRIMARY KEY, kind TEXT, company_id INTEGER, name TEXT, symbol TEXT, exchange TEXT,
    country TEXT, market_class TEXT, sector_group TEXT, stage TEXT, score REAL, news_score REAL,
    model_score REAL, n_news INTEGER, rules TEXT, model TEXT, routes TEXT, evidence TEXT,
    first_seen TEXT, updated TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS expansion_signals (
    country TEXT, as_of TEXT, exchange TEXT, n_items INTEGER, sentiment REAL, growth_items INTEGER,
    top_groups TEXT, headlines TEXT, suggest INTEGER, PRIMARY KEY (country, as_of)
);
CREATE TABLE IF NOT EXISTS finder_state (key TEXT PRIMARY KEY, value TEXT);
"""


def init(con):
    con.executescript(SCHEMA)
    con.commit()


def run_news(con, log=print) -> dict:
    """Collect (RSS + Yahoo Finance), score with FinBERT, link to companies/industries."""
    from . import collect, linking, nlp
    out = {"rss": collect.rss_all(con, log=log), "yahoo": collect.yahoo_batch(con, log=log)}
    out["finbert"] = nlp.score_pending(con, log=log)
    out["links"] = linking.link_pending(con, log=log)
    return out


def run_ipo(con, log=print) -> dict:
    from . import ipo
    return {"scan": ipo.scan(con, log=log), "resolve": ipo.resolve(con, log=log)}


def run_finder(con, log=print) -> dict:
    """Rules A–D → leads → NewsAPI deep dives on the best → expansion signals → exports."""
    from ..config import load
    from . import collect, expansion, leads, linking, nlp, report, rules
    out = {"rules": rules.compute(con, log=log), "leads": leads.build(con, log=log)}
    k = load("finder")["leads"]["deep_dive_top"]
    best = leads.top(con, "listed", k) + leads.top(con, "ipo_pipeline", k)
    dd = collect.newsapi_deep_dive(con, [(d["company_id"] or 0, d["name"].split(",")[0]) for d in best], log=log)
    out["deep_dive"] = dd
    if dd.get("items"):
        nlp.score_pending(con, log=log)
        linking.link_pending(con, log=log)
        out["rules"] = rules.compute(con, log=log)
        out["leads"] = leads.build(con, log=log)
    out["expansion"] = expansion.scan(con, log=log)
    out["export"] = report.export(con)
    return out
