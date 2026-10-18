"""SQLite database: schema and small helpers.

The database lives in db/sfa.sqlite (not committed). Every table the plan lists is
created now so later milestones only add rows.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import DB_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    name_key      TEXT NOT NULL,            -- normalised name used to match listings
    home_symbol   TEXT,                     -- primary listing
    home_venue    TEXT,
    home_country  TEXT,
    domicile      TEXT,                     -- country of incorporation, when known
    domicile_basis TEXT,                    -- 'override' or 'home exchange'
    statement_ccy TEXT,                     -- currency of the financial statements
    sector        TEXT,                     -- Yahoo sector / industry
    industry      TEXT,
    seed_group    TEXT,
    status        TEXT DEFAULT 'active',    -- active | dropped
    note          TEXT,
    updated       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_companies_key ON companies(name_key);

CREATE TABLE IF NOT EXISTS listings (
    symbol        TEXT PRIMARY KEY,
    company_id    INTEGER REFERENCES companies(id),
    venue         TEXT,
    venue_role    TEXT,                     -- covered | secondary | expansion
    country       TEXT,
    currency      TEXT,
    yahoo_code    TEXT,
    long_name     TEXT,
    quote_type    TEXT,
    is_home       INTEGER DEFAULT 0,
    structure     TEXT,                     -- primary | domestic secondary | foreign ordinary | ADR | GDR | BDR | OTC ADR | OTC ordinary
    share_type    TEXT,                     -- common | preferred
    share_class   TEXT,
    dr_ratio      REAL,                     -- home shares per receipt (ADR/GDR), when measurable
    structure_basis TEXT,                   -- how the structure was decided
    last_price    REAL,
    last_date     TEXT,
    updated       TEXT
);
CREATE INDEX IF NOT EXISTS ix_listings_company ON listings(company_id);

CREATE TABLE IF NOT EXISTS classification_events (
    provider TEXT, country TEXT, date TEXT, from_class TEXT, to_class TEXT, note TEXT,
    PRIMARY KEY (provider, country, date)
);

CREATE TABLE IF NOT EXISTS stock_tags (
    company_id INTEGER REFERENCES companies(id),
    heading    TEXT,       -- market | listing | sector | stock
    tag        TEXT,       -- e.g. market_class_msci, sector_group, cap_band
    value      TEXT,
    detail     TEXT,       -- JSON with the numbers behind the value
    as_of      TEXT,
    PRIMARY KEY (company_id, tag)
);

CREATE TABLE IF NOT EXISTS stock_tag_history (
    company_id INTEGER, tag TEXT, value TEXT, as_of TEXT,
    PRIMARY KEY (company_id, tag, as_of)
);

CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT, date TEXT, close REAL, adj_close REAL,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    symbol TEXT, item TEXT, as_of TEXT, value REAL, currency TEXT,
    PRIMARY KEY (symbol, item, as_of)
);

CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY, url TEXT UNIQUE, source TEXT, published TEXT, title TEXT,
    summary TEXT, company_id INTEGER, rule TEXT, sentiment REAL, fetched TEXT
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY, company_id INTEGER, name TEXT, stage TEXT, score REAL,
    reason TEXT, route TEXT, first_seen TEXT, updated TEXT
);

CREATE TABLE IF NOT EXISTS model_results (
    company_id INTEGER, model TEXT, horizon TEXT, metric TEXT, value REAL, as_of TEXT,
    PRIMARY KEY (company_id, model, horizon, metric, as_of)
);

CREATE TABLE IF NOT EXISTS valuations (
    company_id INTEGER, method TEXT, fair_value REAL, market_price REAL, currency TEXT,
    detail TEXT, as_of TEXT,
    PRIMARY KEY (company_id, method, as_of)
);

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY, job TEXT, started TEXT, finished TEXT, status TEXT, message TEXT
);

CREATE TABLE IF NOT EXISTS dropped_seeds (
    symbol TEXT PRIMARY KEY, reason TEXT, updated TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    import os
    path = Path(path) if path else Path(os.environ.get("SFA_DB") or DB_DIR / "sfa.sqlite")
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=120)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    return con


def set_tag(con, company_id: int, heading: str, tag: str, value, detail: dict | None = None,
            as_of: str | None = None):
    """Store a classification and keep a history row whenever the value changes."""
    as_of = as_of or now()[:10]
    value = None if value is None else str(value)
    prev = con.execute("SELECT value FROM stock_tags WHERE company_id=? AND tag=?",
                       (company_id, tag)).fetchone()
    con.execute("INSERT OR REPLACE INTO stock_tags VALUES (?,?,?,?,?,?)",
                (company_id, heading, tag, value, json.dumps(detail or {}, default=str), as_of))
    if prev is None or prev["value"] != value:
        con.execute("INSERT OR REPLACE INTO stock_tag_history VALUES (?,?,?,?)",
                    (company_id, tag, value, as_of))


def tags(con, company_id: int) -> dict[str, str]:
    return {r["tag"]: r["value"] for r in
            con.execute("SELECT tag, value FROM stock_tags WHERE company_id=?", (company_id,))}
