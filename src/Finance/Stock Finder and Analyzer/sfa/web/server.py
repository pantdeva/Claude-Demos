"""Local dashboard: http://localhost:8000 (python -m sfa web, or python -m sfa start).

A small threaded HTTP server: the page (static/index.html) calls the JSON endpoints
below, each of which reads the SQLite database read-only. "Analyze now" runs the
Stage 2 analyzer for one symbol in a background thread with its own connection.

Binds to 127.0.0.1 by default; pass --host 0.0.0.0 to open it to other devices on
your network (there is no login, so only do that on a network you trust).
"""

from __future__ import annotations

import json
import mimetypes
import os
import sqlite3
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from ..config import EXPORT_DIR, load
from ..db import connect

STATIC = Path(__file__).parent / "static"
_jobs: dict[str, dict] = {}


def ro(db_path: str | None = None) -> sqlite3.Connection:
    con = connect(db_path)                     # creates tables if missing, then used read-only in practice
    con.execute("PRAGMA query_only=ON")
    return con


def _rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args)]


def _exists(con, table):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def clean(v):
    """JSON-safe copy: NaN and infinities become null."""
    import math
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    return v


def _json(v):
    if isinstance(v, str) and v[:1] in "[{":
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


# ---------------------------------------------------------------- endpoints
def api_overview(con, q):
    out = {"now": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    one = lambda sql, a=(): con.execute(sql, a).fetchone()[0]
    out["companies"] = one("SELECT COUNT(*) FROM companies WHERE status='active'")
    out["listings"] = one("SELECT COUNT(*) FROM listings")
    out["exchanges"] = one("SELECT COUNT(DISTINCT home_venue) FROM companies WHERE status='active'")
    out["news_items"] = one("SELECT COUNT(*) FROM news_items")
    out["news_scored"] = one("SELECT COUNT(*) FROM news_sentiment") if _exists(con, "news_sentiment") else 0
    out["leads"] = {r["kind"]: r["n"] for r in con.execute(
        "SELECT kind, COUNT(*) n FROM finder_leads WHERE status='active' GROUP BY kind")} if _exists(con, "finder_leads") else {}
    out["modelled"] = one("SELECT COUNT(DISTINCT company_id) FROM forecast_scores") if _exists(con, "forecast_scores") else 0
    out["valued"] = one("SELECT COUNT(DISTINCT company_id) FROM valuations")
    out["verdicts"] = {r["value"]: r["n"] for r in con.execute(
        "SELECT value, COUNT(*) n FROM stock_tags WHERE tag='valuation_verdict' GROUP BY value")}
    out["market_class"] = {r["value"]: r["n"] for r in con.execute(
        "SELECT value, COUNT(*) n FROM stock_tags WHERE tag='market_class' GROUP BY value")}
    out["jobs"] = _rows(con, """SELECT job, MAX(started) started, status, message FROM job_runs
                                GROUP BY job ORDER BY job""")
    if _exists(con, "finder_leads"):
        out["top_leads"] = _leads(con, "listed", 8)
    if _exists(con, "model_choice"):
        names = {k: v["name"] for k, v in load("models")["models"].items()}
        out["model_choice"] = [dict(r, selected=names.get(r["selected"], r["selected"])) for r in _rows(
            con, "SELECT group_key, horizon, selected, basis, n_stocks FROM model_choice "
                 "WHERE group_type IN ('all','market_class') ORDER BY group_type, group_key, horizon")]
    return out


def _leads(con, kind, limit):
    cond = "" if kind == "ipo_pipeline" else " AND score IS NOT NULL"
    rows = _rows(con, f"""SELECT lead_key, kind, company_id, name, symbol, exchange, country, market_class, sector_group,
                              stage, score, news_score, model_score, n_news, rules, model, routes, first_seen, updated
                          FROM finder_leads WHERE status='active' AND kind=?{cond}
                          ORDER BY score IS NULL, score DESC LIMIT ?""", (kind, limit))
    for r in rows:
        for k in ("rules", "model", "routes"):
            r[k] = _json(r[k])
        if r["company_id"]:
            v = con.execute("SELECT value FROM stock_tags WHERE company_id=? AND tag='valuation_verdict'",
                            (r["company_id"],)).fetchone()
            r["verdict"] = v["value"] if v else None
    return rows


def api_leads(con, q):
    kind = q.get("kind", ["listed"])[0]
    limit = min(int(q.get("limit", ["200"])[0]), 2000)
    return {"kind": kind, "leads": _leads(con, kind, limit) if _exists(con, "finder_leads") else []}


def api_search(con, q):
    s = (q.get("q", [""])[0] or "").strip()
    if len(s) < 1:
        return {"results": []}
    like = f"%{s}%"
    return {"results": _rows(con, """SELECT DISTINCT c.id, c.name, c.home_symbol, c.home_venue, c.home_country
                                     FROM companies c LEFT JOIN listings l ON l.company_id=c.id
                                     WHERE c.status='active' AND (c.name LIKE ? OR l.symbol LIKE ?)
                                     ORDER BY c.name LIMIT 25""", (like, like))}


def api_company(con, q):
    sym = q.get("symbol", [""])[0]
    c = con.execute("""SELECT c.* FROM companies c JOIN listings l ON l.company_id=c.id
                       WHERE l.symbol=? OR c.home_symbol=? LIMIT 1""", (sym, sym)).fetchone()
    if not c:
        return {"error": f"{sym} is not in the universe"}
    c = dict(c)
    cid = c["id"]
    tags = {}
    for r in con.execute("SELECT heading, tag, value, detail, as_of FROM stock_tags WHERE company_id=?", (cid,)):
        tags.setdefault(r["heading"], {})[r["tag"]] = {"value": r["value"], "detail": _json(r["detail"]), "as_of": r["as_of"]}
    out = {"company": c, "tags": tags,
           "listings": _rows(con, "SELECT symbol, venue, country, currency, is_home, structure, dr_ratio, share_type, "
                                  "last_price, last_date FROM listings WHERE company_id=? ORDER BY is_home DESC, symbol", (cid,))}
    if _exists(con, "finder_leads"):
        lead = con.execute("SELECT * FROM finder_leads WHERE company_id=? AND status='active'", (cid,)).fetchone()
        if lead:
            lead = dict(lead)
            for k in ("rules", "model", "routes", "evidence"):
                lead[k] = _json(lead[k])
            out["lead"] = lead
    if _exists(con, "model_choice"):
        out["models"] = _rows(con, "SELECT l.horizon, l.model, l.crps, l.skill, l.dm_t, l.hit, l.cover90, l.is_baseline, "
                                   "l.selected FROM leaderboard l WHERE group_type='company' AND group_key=? "
                                   "ORDER BY horizon, crps", (str(cid),))
    out["valuations"] = _rows(con, """SELECT method, fair_value, market_price, currency, detail, as_of FROM valuations
                                      WHERE company_id=? AND as_of=(SELECT MAX(as_of) FROM valuations WHERE company_id=?)""",
                              (cid, cid))
    for v in out["valuations"]:
        v["detail"] = _json(v["detail"])
    home = c["home_symbol"]
    files = {}
    for ext in ("md", "xlsx"):
        f = EXPORT_DIR / "analysis" / f"{home}.{ext}"
        if f.exists():
            files[ext] = f"/files/analysis/{home}.{ext}"
    out["files"] = files
    out["prices"] = [[r["date"], r["adj_close"]] for r in con.execute(
        "SELECT date, adj_close FROM prices WHERE symbol=? AND date >= date('now','-3 years') ORDER BY date", (home,))]
    return out


def api_leaderboard(con, q):
    if not _exists(con, "model_choice"):
        return {"choices": [], "rows": []}
    gt = q.get("group_type", ["cell"])[0]
    choices = _rows(con, "SELECT * FROM model_choice WHERE group_type=? ORDER BY group_key, horizon", (gt,))
    if gt == "company":
        names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM companies")}
        choices = [dict(r, group_name=names.get(int(r["group_key"]), r["group_key"])) for r in choices
                   if r["selected"] != r["baseline"]]
    key = q.get("group_key", [None])[0]
    rows = _rows(con, "SELECT * FROM leaderboard WHERE group_type=? AND group_key=? ORDER BY horizon, crps",
                 (gt, key)) if key else []
    portfolio = _rows(con, "SELECT * FROM portfolio_tests ORDER BY cell, strategy") if _exists(con, "portfolio_tests") else []
    return {"group_type": gt, "choices": choices, "rows": rows, "portfolio": portfolio,
            "models": {k: v["name"] for k, v in load("models")["models"].items()}}


def api_markets(con, q):
    pivot = _rows(con, """SELECT m.value market_class, s.value sector_group, COUNT(*) n FROM stock_tags m
                          JOIN stock_tags s ON s.company_id=m.company_id AND s.tag='sector_group'
                          WHERE m.tag='market_class' GROUP BY 1, 2""")
    count = lambda tag: _rows(con, "SELECT value, COUNT(*) n FROM stock_tags WHERE tag=? GROUP BY value ORDER BY n DESC", (tag,))
    out = {"pivot": pivot, "exchanges": _rows(con, "SELECT home_venue value, COUNT(*) n FROM companies WHERE status='active' "
                                                   "GROUP BY 1 ORDER BY n DESC")}
    for t in ("listing_structure", "cap_band", "growth_value", "cyclical_defensive", "market_class_ftse", "news_verdict",
              "valuation_verdict"):
        out[t] = count(t)
    out["expansion"] = _rows(con, "SELECT * FROM expansion_signals WHERE as_of=(SELECT MAX(as_of) FROM expansion_signals) "
                                  "ORDER BY suggest DESC, n_items DESC") if _exists(con, "expansion_signals") else []
    for e in out["expansion"]:
        e["top_groups"], e["headlines"] = _json(e["top_groups"]), _json(e["headlines"])
    out["ipo"] = _rows(con, "SELECT name, stage, event_date, country_hint, exchange_hint, symbol, title, source "
                            "FROM ipo_events ORDER BY event_date DESC LIMIT 200") if _exists(con, "ipo_events") else []
    return out


def api_service(con, q):
    from ..service import status
    out = {"jobs": status(con)}
    out["runs"] = _rows(con, "SELECT job, started, finished, status, substr(message, 1, 300) message FROM job_runs "
                             "ORDER BY id DESC LIMIT 40")
    out["feeds"] = _rows(con, "SELECT source, url, ok, fails, last_ok, last_error, items_last, checked FROM feed_health "
                              "ORDER BY source, url") if _exists(con, "feed_health") else []
    import os
    out["env"] = {k: bool(os.environ.get(k)) for k in ("NEWSAPI_KEY", "SFA_SEC_USER_AGENT", "SFA_FCM_SERVICE_ACCOUNT",
                                                       "SFA_DASHBOARD_URL", "SFA_FINBERT_DIR", "SFA_DB")}
    out["phone"] = phone_info(con)
    return out


def phone_info(con):
    from .. import notify
    t = notify._get(con, "topic") if _exists(con, "notify_state") else None
    info = {"topic": t, "dashboard_url": notify.dashboard_url(),
            "pair_link": None, "fcm_configured": bool(os.environ.get("SFA_FCM_SERVICE_ACCOUNT")),
            "recent": _rows(con, "SELECT created, type, status, title, error FROM notify_log ORDER BY created DESC LIMIT 15")
            if _exists(con, "notify_log") else []}
    if t:
        from urllib.parse import quote
        info["pair_link"] = f"sfa://pair?topic={quote(t)}&url={quote(info['dashboard_url'], safe='')}"
    return info


def api_analyze_status(con, q):
    sym = q.get("symbol", [""])[0]
    return _jobs.get(sym, {"state": "idle"})


ROUTES = {"/api/overview": api_overview, "/api/leads": api_leads, "/api/search": api_search,
          "/api/company": api_company, "/api/leaderboard": api_leaderboard, "/api/markets": api_markets,
          "/api/service": api_service, "/api/analyze_status": api_analyze_status}


def start_analysis(symbol: str, db_path: str | None):
    if _jobs.get(symbol, {}).get("state") == "running":
        return _jobs[symbol]
    _jobs[symbol] = {"state": "running", "started": datetime.now(timezone.utc).isoformat()}

    def work():
        try:
            from ..analyzer import run
            con = connect(db_path)
            res = run(con, [symbol], log=lambda *a: None)
            _jobs[symbol] = {"state": "done", "result": res}
        except Exception as e:  # noqa: BLE001
            _jobs[symbol] = {"state": "error", "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-800:]}
    threading.Thread(target=work, daemon=True).start()
    return _jobs[symbol]


class Handler(BaseHTTPRequestHandler):
    db_path: str | None = None
    server_version = "sfa-dashboard/1.0"

    def log_message(self, fmt, *args):            # quiet console
        pass

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(clean(obj), default=str, allow_nan=False).encode())

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if u.path in ROUTES:
                con = ro(self.db_path)
                try:
                    return self._json(200, ROUTES[u.path](con, q))
                finally:
                    con.close()
            if u.path.startswith("/files/"):
                rel = unquote(u.path[len("/files/"):])
                f = (EXPORT_DIR / rel).resolve()
                if EXPORT_DIR.resolve() not in f.parents or not f.is_file():
                    return self._json(404, {"error": "not found"})
                ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                if f.suffix == ".md":
                    ctype = "text/plain; charset=utf-8"
                extra = {"Content-Disposition": f'attachment; filename="{f.name}"'} if f.suffix == ".xlsx" else None
                return self._send(200, f.read_bytes(), ctype, extra)
            return self._json(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/analyze":
            sym = q.get("symbol", [""])[0].strip()
            if not sym:
                return self._json(400, {"error": "symbol required"})
            return self._json(202, start_analysis(sym, self.db_path))
        if u.path == "/api/notify_test":
            from .. import notify
            con = connect(self.db_path)
            try:
                notify.topic(con)
                return self._json(200, notify.send_test(con))
            finally:
                con.close()
        return self._json(404, {"error": "not found"})


def serve(host: str = "127.0.0.1", port: int = 8000, db_path: str | None = None, block: bool = True):
    Handler.db_path = db_path
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard: http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}")
    if block:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()
        return None
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
