"""Push notifications: detect events in the database and send them to the Android app.

Events (config/notify.yaml):
  lead       a company enters the top N listed leads, or its score jumps
  ipo        a new IPO name, or a move to filed / priced / listed
  valuation  a verdict changes, or the combined fair value moves a lot
  digest     one morning summary
  alert      a job failed, or prices have not been refreshed for too long
  heartbeat  silent: lets the app warn you when the computer stops reporting

Who receives them (config/notify.yaml → audience):
  devices  (default) every phone signed in to SFA Notifier with a Google account listed in
           SFA_NOTIFY_EMAILS. The app records its FCM token in Firestore under
           users/{uid}/devices (security rules let only that user write there); this side
           reads the registry with the service-account key and checks each user's
           verified email with Firebase Authentication before sending.
  topic    the original shared pairing-code mode (anyone with your app build and the code).

The first run only records the current state (no flood of "new" events). Each run
compares with the stored state, applies quiet hours and a per-run cap, and sends via
FCM (or only logs when FCM is not configured). Every message is kept in notify_log.

Message contract with the app (all values are strings):
  id, type, title, body, symbol, path (dashboard route such as "#company/TSM"),
  url (dashboard base URL), sent (UTC ISO time), channel
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from ..config import load
from ..db import now

SCHEMA = """
CREATE TABLE IF NOT EXISTS notify_state (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS notify_log (
    id TEXT PRIMARY KEY, created TEXT, type TEXT, dedupe TEXT, title TEXT, body TEXT, data TEXT,
    status TEXT, sent_at TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS ix_notify_status ON notify_log(status);
"""
CHANNEL = {"lead": "leads", "ipo": "ipo", "valuation": "valuation", "digest": "digest", "alert": "alerts",
           "heartbeat": "heartbeat", "test": "alerts"}
STAGE_ORDER = {"planning": 0, "filed": 1, "priced": 2, "listed": 3}


def init(con):
    con.executescript(SCHEMA)


def _get(con, key, default=None):
    r = con.execute("SELECT value FROM notify_state WHERE key=?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def _set(con, key, value):
    con.execute("INSERT OR REPLACE INTO notify_state VALUES (?,?)", (key, json.dumps(value)))


def topic(con) -> str:
    init(con)
    t = load("notify").get("topic") or _get(con, "topic")
    if not t:
        t = "sfa-" + secrets.token_hex(8)
        _set(con, "topic", t)
        con.commit()
    return t


def dashboard_url() -> str:
    return os.environ.get(load("notify").get("dashboard_url_env", "SFA_DASHBOARD_URL")) or "http://localhost:8000"


def pair_link(con) -> str:
    """Link that sets up the app: the dashboard address, plus the topic in topic mode."""
    if load("notify").get("audience", "devices") == "topic":
        return f"sfa://pair?topic={quote(topic(con))}&url={quote(dashboard_url(), safe='')}"
    return f"sfa://pair?url={quote(dashboard_url(), safe='')}"


def _table(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def _fmt(v, d=2):
    return "—" if v is None else f"{v:+.{d}f}"


# ---------------------------------------------------------------- event detection
def lead_events(con, cfg) -> list[dict]:
    if not _table(con, "finder_leads"):
        return []
    rows = con.execute("""SELECT lead_key, name, symbol, score, news_score, model_score, routes FROM finder_leads
                          WHERE status='active' AND kind='listed' AND score IS NOT NULL ORDER BY score DESC""").fetchall()
    cur = {r["lead_key"]: {"score": r["score"], "rank": i + 1} for i, r in enumerate(rows)}
    prev = _get(con, "leads")
    notified = _get(con, "leads_notified", {})
    _set(con, "leads", cur)
    if prev is None:
        return []
    out, cutoff = [], (datetime.now(timezone.utc) - timedelta(days=cfg["renotify_days"])).isoformat()
    for i, r in enumerate(rows):
        k, rank = r["lead_key"], i + 1
        p = prev.get(k)
        why = None
        if rank <= cfg["top_n"] and (p is None or p["rank"] > cfg["top_n"]):
            why = f"entered the top {cfg['top_n']} (#{rank})"
        elif p is not None and r["score"] - p["score"] >= cfg["score_jump"]:
            why = f"score up {r['score'] - p['score']:+.2f} to {r['score']:+.2f} (#{rank})"
        if not why or notified.get(k, "") > cutoff:
            continue
        verdict = con.execute("""SELECT t.value FROM stock_tags t JOIN listings l ON l.company_id=t.company_id
                                 WHERE l.symbol=? AND t.tag='valuation_verdict'""", (r["symbol"],)).fetchone()
        routes = json.loads(r["routes"] or "[]")
        best = next((x for x in routes if x.get("ok") is True), None)
        body = (f"Score {_fmt(r['score'])} (news {_fmt(r['news_score'])}, model {_fmt(r['model_score'])})"
                + (f" · {verdict['value']}" if verdict else "")
                + (f" · {best['route']}" + (f" ({best['symbol']})" if best.get("symbol") else "") if best else ""))
        out.append({"type": "lead", "dedupe": f"lead:{k}", "title": f"{r['name']} {why}", "body": body,
                    "symbol": r["symbol"], "path": f"#company/{r['symbol']}"})
        notified[k] = now()
    _set(con, "leads_notified", notified)
    return out


def ipo_events(con, cfg) -> list[dict]:
    if not _table(con, "ipo_events"):
        return []
    latest = {}
    for r in con.execute("SELECT name, name_key, stage, event_date, country_hint, title, symbol FROM ipo_events "
                         "ORDER BY event_date"):
        cur = latest.get(r["name_key"])
        if cur is None or STAGE_ORDER[r["stage"]] >= STAGE_ORDER[cur["stage"]]:
            latest[r["name_key"]] = dict(r)
    prev = _get(con, "ipo")
    _set(con, "ipo", {k: v["stage"] for k, v in latest.items()})
    if prev is None:
        return []
    out = []
    for k, e in latest.items():
        if e["stage"] not in cfg["stages"]:
            continue
        before = prev.get(k)
        if before is None:
            title = f"IPO pipeline: {e['name']} ({e['stage']})"
        elif STAGE_ORDER[e["stage"]] > STAGE_ORDER[before]:
            title = f"{e['name']} IPO: {before} → {e['stage']}"
        else:
            continue
        body = (e["title"] or "")[:180] + (f" · {e['country_hint']}" if e["country_hint"] else "")
        out.append({"type": "ipo", "dedupe": f"ipo:{k}:{e['stage']}", "title": title, "body": body,
                    "symbol": e["symbol"] or "", "path": f"#company/{e['symbol']}" if e["symbol"] else "#leads"})
    return out


def valuation_events(con, cfg) -> list[dict]:
    rows = con.execute("""SELECT v.company_id, v.fair_value, v.market_price, v.currency, v.detail, c.name, c.home_symbol
                          FROM valuations v JOIN companies c ON c.id=v.company_id
                          WHERE v.method='combined' AND v.as_of=(SELECT MAX(as_of) FROM valuations w
                                WHERE w.company_id=v.company_id AND w.method='combined')""").fetchall()
    cur = {}
    for r in rows:
        d = json.loads(r["detail"] or "{}")
        cur[str(r["company_id"])] = {"verdict": d.get("verdict"), "fair": r["fair_value"]}
    prev = _get(con, "valuation")
    _set(con, "valuation", cur)
    if prev is None:
        return []
    out = []
    for r in rows:
        k = str(r["company_id"])
        p, c = prev.get(k), cur[k]
        if p is None:
            continue
        d = json.loads(r["detail"] or "{}")
        moved = p.get("fair") and c["fair"] and abs(c["fair"] / p["fair"] - 1) >= cfg["fair_value_move"]
        if c["verdict"] != p.get("verdict"):
            title = f"{r['name']} now {c['verdict']}"
            extra = f" · was {p.get('verdict')}"
        elif moved:
            title = f"{r['name']}: fair value {c['fair'] / p['fair'] - 1:+.0%}"
            extra = f" · was {p['fair']:,.2f}"
        else:
            continue
        up = d.get("upside")
        body = (f"Fair value {c['fair']:,.2f} {r['currency']} vs price {r['market_price']:,.2f}"
                + (f" ({up:+.0%})" if up is not None else "") + extra)
        out.append({"type": "valuation", "dedupe": f"val:{k}:{c['verdict']}:{round(c['fair'] or 0, 2)}", "title": title,
                    "body": body, "symbol": r["home_symbol"], "path": f"#company/{r['home_symbol']}"})
    return out


def digest_event(con, cfg, local_now: datetime) -> list[dict]:
    hh, mm = map(int, cfg["at"].split(":"))
    today = local_now.strftime("%Y-%m-%d")
    if local_now.time() < local_now.replace(hour=hh, minute=mm).time() or _get(con, "digest_day") == today:
        return []
    _set(con, "digest_day", today)
    lines = []
    if _table(con, "finder_leads"):
        for i, r in enumerate(con.execute("""SELECT name, symbol, score FROM finder_leads WHERE status='active'
                                             AND kind='listed' AND score IS NOT NULL ORDER BY score DESC LIMIT ?""",
                                          (cfg["top_leads"],)), 1):
            lines.append(f"{i}. {r['name'][:32]} {_fmt(r['score'])}")
    ver = {r["value"]: r["n"] for r in con.execute(
        "SELECT value, COUNT(*) n FROM stock_tags WHERE tag='valuation_verdict' GROUP BY value")}
    ipo_n = con.execute("SELECT COUNT(DISTINCT name_key) FROM ipo_events WHERE found >= ?",
                        ((datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),)
                        ).fetchone()[0] if _table(con, "ipo_events") else 0
    errs = con.execute("SELECT COUNT(*) FROM job_runs WHERE status='error' AND started >= ?",
                       ((datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),)).fetchone()[0]
    tail = (f"Verdicts: {ver.get('Undervalued', 0)} under / {ver.get('Overvalued', 0)} over · "
            f"{ipo_n} IPO names in 24 h · {'no job errors' if not errs else f'{errs} job error(s)'}")
    return [{"type": "digest", "dedupe": f"digest:{today}", "title": f"Stock Finder digest, {local_now:%d %b}",
             "body": "\n".join(lines + [tail]), "symbol": "", "path": "#overview"}]


def alert_events(con, cfg) -> list[dict]:
    out = []
    last_id = _get(con, "alert_job_id", 0)
    rows = con.execute("SELECT id, job, message FROM job_runs WHERE status='error' AND id > ? ORDER BY id",
                       (last_id,)).fetchall()
    for r in rows:
        msg = (r["message"] or "").strip().splitlines()
        out.append({"type": "alert", "dedupe": f"job:{r['id']}", "title": f"Job failed: {r['job']}",
                    "body": (msg[-1] if msg else "see the Service page")[:200], "symbol": "", "path": "#service"})
    top = con.execute("SELECT MAX(id) FROM job_runs").fetchone()[0] or 0
    _set(con, "alert_job_id", max(last_id, top))
    last_ok = con.execute("SELECT MAX(started) FROM job_runs WHERE job='prices' AND status='ok'").fetchone()[0]
    if last_ok:
        age = datetime.now(timezone.utc) - datetime.strptime(last_ok, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        day = now()[:10]
        if age > timedelta(hours=cfg["stale_hours"]) and _get(con, "stale_day") != day:
            _set(con, "stale_day", day)
            out.append({"type": "alert", "dedupe": f"stale:{day}", "title": "Prices are not being refreshed",
                        "body": f"Last successful price update {age.total_seconds() / 3600:.0f} h ago. Check the "
                                "Service page and logs/sfa.log.", "symbol": "", "path": "#service"})
    return out


# ---------------------------------------------------------------- delivery
def in_quiet(local_now: datetime, quiet: list[str]) -> bool:
    if not quiet:
        return False
    a, b = (datetime.strptime(x, "%H:%M").time() for x in quiet)
    t = local_now.time()
    return (a <= t or t < b) if a > b else (a <= t < b)


def _sender():
    cfg = load("notify")
    if cfg.get("transport") != "fcm":
        return None, "transport is 'log'"
    try:
        from .fcm import FCMError, FCMSender
        return FCMSender(os.environ.get(cfg.get("service_account_env", "SFA_FCM_SERVICE_ACCOUNT"))), None
    except Exception as e:  # noqa: BLE001 - not configured yet: keep logging
        return None, str(e)


def allowed_emails() -> set[str]:
    env = load("notify").get("allowed_emails_env", "SFA_NOTIFY_EMAILS")
    return {e.strip().lower() for e in (os.environ.get(env) or "").replace(";", ",").split(",") if e.strip()}


class NoTargets(RuntimeError):
    pass


def targets(con, sender) -> list[dict]:
    """Where to send: the signed-in devices of allowed accounts (audience "devices"), or
    the shared topic (audience "topic", the original pairing-code mode)."""
    cfg = load("notify")
    if cfg.get("audience", "devices") == "topic":
        return [{"topic": topic(con)}]
    emails = allowed_emails()
    if not emails:
        raise NoTargets(f"set {cfg.get('allowed_emails_env', 'SFA_NOTIFY_EMAILS')} to the Google account(s) allowed "
                        "to receive notifications")
    devs = sender.devices(emails)
    _set(con, "devices", [{k: d.get(k) for k in ("email", "model", "updated", "device")} for d in devs])
    _set(con, "devices_checked", now())
    if not devs:
        raise NoTargets("no signed-in phone yet: sign in to SFA Notifier with an allowed Google account")
    return [{"token": d["token"], "doc": d.get("doc"), "email": d["email"]} for d in devs]


def broadcast(sender, tgts: list[dict], data: dict, ttl_s: int = 86400) -> int:
    """Send to every target; prune devices whose registration is gone. Returns how many got it."""
    ok, last_err = 0, None
    for t in tgts:
        try:
            sender.send(data, token=t.get("token"), topic=t.get("topic"), ttl_s=ttl_s)
            ok += 1
        except Exception as e:  # noqa: BLE001
            last_err = e
            if getattr(e, "unregistered", False) and t.get("doc"):
                try:
                    sender.delete_device(t["doc"])
                except Exception:  # noqa: BLE001
                    pass
    if not ok and last_err is not None:
        raise last_err
    return ok


def _payload(con, ev, mid) -> dict:
    return {"id": mid, "type": ev["type"], "title": ev["title"], "body": ev["body"], "symbol": ev.get("symbol") or "",
            "path": ev.get("path") or "", "url": dashboard_url(), "sent": now(), "channel": CHANNEL[ev["type"]]}


def deliver(con, events: list[dict], local_now: datetime | None = None, sender=None, log=print) -> dict:
    """Queue new events, then send everything due (respecting quiet hours and the cap)."""
    init(con)
    cfg = load("notify")
    local_now = local_now or datetime.now()
    for ev in events:
        if con.execute("SELECT 1 FROM notify_log WHERE dedupe=?", (ev["dedupe"],)).fetchone():
            continue
        mid = secrets.token_hex(6)
        con.execute("INSERT INTO notify_log VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (mid, now(), ev["type"], ev["dedupe"], ev["title"], ev["body"],
                     json.dumps(_payload(con, ev, mid)), "pending", None, None))
    quiet = in_quiet(local_now, cfg["delivery"]["quiet_hours"])
    due = con.execute("SELECT * FROM notify_log WHERE status IN ('pending','held') ORDER BY created").fetchall()
    send_now = [r for r in due if not quiet or r["type"] in ("alert", "heartbeat", "test")]
    for r in due:
        if r not in send_now and r["status"] == "pending":
            con.execute("UPDATE notify_log SET status='held' WHERE id=?", (r["id"],))
    cap = cfg["delivery"]["max_per_run"]
    extra = send_now[cap - 1:] if len(send_now) > cap else []
    send_now = send_now[:cap - 1] if extra else send_now
    if extra:
        mid = secrets.token_hex(6)
        ev = {"type": "digest", "title": f"…and {len(extra)} more updates", "symbol": "", "path": "#leads",
              "body": "; ".join(r["title"] for r in extra)[:300]}
        con.execute("INSERT INTO notify_log VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (mid, now(), "digest", f"fold:{mid}", ev["title"], ev["body"], json.dumps(_payload(con, ev, mid)),
                     "pending", None, None))
        for r in extra:
            con.execute("UPDATE notify_log SET status='folded' WHERE id=?", (r["id"],))
        send_now.append(con.execute("SELECT * FROM notify_log WHERE id=?", (mid,)).fetchone())
    if sender is None:
        sender, why = _sender()
    else:
        why = None
    stats = {"queued": len(events), "sent": 0, "logged": 0, "held": 0, "failed": 0}
    tgts = None
    if sender is not None and send_now:
        try:
            tgts = targets(con, sender)
        except Exception as e:  # noqa: BLE001 - nobody to send to yet: keep the messages as logged
            sender, why = None, str(e)
    for r in send_now:
        data = json.loads(r["data"])
        if sender is None:
            con.execute("UPDATE notify_log SET status='logged', error=? WHERE id=?", (why, r["id"]))
            stats["logged"] += 1
            continue
        try:
            n = broadcast(sender, tgts, data)
            con.execute("UPDATE notify_log SET status='sent', sent_at=?, error=? WHERE id=?",
                        (now(), f"{n} device(s)" if len(tgts) > 1 or "token" in tgts[0] else None, r["id"]))
            stats["sent"] += 1
        except Exception as e:  # noqa: BLE001
            con.execute("UPDATE notify_log SET status='failed', error=? WHERE id=?", (str(e)[:300], r["id"]))
            stats["failed"] += 1
    stats["held"] = con.execute("SELECT COUNT(*) FROM notify_log WHERE status='held'").fetchone()[0]
    con.commit()
    return stats


def heartbeat(con, cfg, sender) -> bool:
    last = _get(con, "heartbeat_at")
    hrs = cfg["delivery"]["heartbeat_hours"]
    if last and datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(hours=hrs):
        return False
    _set(con, "heartbeat_at", datetime.now(timezone.utc).isoformat())
    if sender is None:
        return False
    try:
        broadcast(sender, targets(con, sender), {"type": "heartbeat", "sent": now(), "url": dashboard_url(),
                                                 "every_hours": str(hrs)}, ttl_s=hrs * 3600)
        return True
    except Exception:  # noqa: BLE001
        return False


def run(con, local_now: datetime | None = None, sender=None, log=print) -> dict:
    """One notification pass (the service runs it every 30 minutes)."""
    init(con)
    cfg = load("notify")
    if not cfg.get("enabled"):
        return {"skipped": "notifications disabled"}
    ev_cfg = cfg["events"]
    local_now = local_now or datetime.now()
    events = []
    if ev_cfg["leads"]["enabled"]:
        events += lead_events(con, ev_cfg["leads"])
    if ev_cfg["ipo"]["enabled"]:
        events += ipo_events(con, ev_cfg["ipo"])
    if ev_cfg["valuation"]["enabled"]:
        events += valuation_events(con, ev_cfg["valuation"])
    if ev_cfg["alerts"]["enabled"]:
        events += alert_events(con, ev_cfg["alerts"])
    if ev_cfg["digest"]["enabled"]:
        events += digest_event(con, ev_cfg["digest"], local_now)
    con.commit()
    if sender is None:
        sender, _ = _sender()
    out = deliver(con, events, local_now, sender=sender, log=log)
    out["heartbeat"] = heartbeat(con, cfg, sender)
    con.commit()
    return out


def send_test(con, sender=None) -> dict:
    init(con)
    ev = {"type": "test", "dedupe": f"test:{secrets.token_hex(4)}", "title": "Stock Finder test notification",
          "body": "If you can read this on your phone, push notifications work.", "symbol": "", "path": "#service"}
    return deliver(con, [ev], sender=sender)
