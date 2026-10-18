"""Background service: runs each job in config/jobs.yaml on its own timer.

    python -m sfa service            run forever (Ctrl+C to stop)
    python -m sfa service --once     run every due job once and exit
    python -m sfa jobs               show jobs and their last run

Each run is recorded in the job_runs table. A job that fails is logged and retried on
its next slot; the service keeps going. Start-on-boot packaging is Milestone 5.
"""

from __future__ import annotations

import signal
import time
import traceback
from datetime import datetime, timedelta

from . import export, pipeline, universe
from .config import load
from .data import rss
from .db import connect, now

JOBS = {
    "universe": lambda con, log: universe.build(con, log=log),
    "prices": lambda con, log: pipeline.refresh_prices(con, refresh=True, log=log),
    "fundamentals": lambda con, log: pipeline.refresh_fundamentals(con, refresh=True, log=log),
    "classify": lambda con, log: {**pipeline.classify_all(con, log=log), **export.export(con)},
    "news": lambda con, log: rss.poll(con),
    "leaderboard": lambda con, log: _models(con, log),
}


def _models(con, log):
    from .models import run_all
    return run_all(con, log=log)

_stop = [False]


def _last_ok(con, job: str) -> datetime | None:
    r = con.execute("SELECT started FROM job_runs WHERE job=? AND status='ok' ORDER BY id DESC LIMIT 1",
                    (job,)).fetchone()
    return datetime.strptime(r["started"], "%Y-%m-%dT%H:%M:%SZ") if r else None


def is_due(spec: dict, last: datetime | None, now_utc: datetime, local_now: datetime) -> bool:
    if last is None:
        return True
    if "at" in spec:
        hh, mm = map(int, spec["at"].split(":"))
        slot = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if local_now < slot:
            slot -= timedelta(days=1)
        offset = local_now - now_utc            # local minus UTC
        return last + offset < slot
    return now_utc - last >= timedelta(hours=spec.get("every_hours", 24))


def run_job(con, name: str, log=print) -> str:
    if name not in JOBS:
        return "not built yet"
    cur = con.execute("INSERT INTO job_runs (job, started, status) VALUES (?,?,?)", (name, now(), "running"))
    rid = cur.lastrowid
    con.commit()
    try:
        res = JOBS[name](con, log)
        con.execute("UPDATE job_runs SET finished=?, status='ok', message=? WHERE id=?", (now(), str(res)[:500], rid))
        con.commit()
        return f"ok {res}"
    except Exception as e:  # noqa: BLE001 - the service must survive any job failure
        con.execute("UPDATE job_runs SET finished=?, status='error', message=? WHERE id=?",
                    (now(), traceback.format_exc()[-1500:], rid))
        con.commit()
        return f"error {e}"


def due_jobs(con) -> list[str]:
    specs = load("jobs")["jobs"]
    utc, local = datetime.utcnow(), datetime.now()
    return [n for n, s in specs.items() if s.get("enabled") and n in JOBS and is_due(s, _last_ok(con, n), utc, local)]


def run(once: bool = False, log=print):
    con = connect()
    signal.signal(signal.SIGINT, lambda *_: _stop.__setitem__(0, True))
    signal.signal(signal.SIGTERM, lambda *_: _stop.__setitem__(0, True))
    order = ["universe", "prices", "fundamentals", "classify", "leaderboard", "news"]
    log(f"sfa service started {now()}")
    while not _stop[0]:
        for name in sorted(due_jobs(con), key=lambda n: order.index(n) if n in order else 99):
            log(f"[{datetime.now():%H:%M}] {name} …")
            log(f"[{datetime.now():%H:%M}] {name} {run_job(con, name, log)}")
            if _stop[0]:
                break
        if once:
            break
        for _ in range(60):
            if _stop[0]:
                break
            time.sleep(1)
    log("sfa service stopped")


def status(con) -> list[dict]:
    out = []
    for n, s in load("jobs")["jobs"].items():
        r = con.execute("SELECT started, finished, status, message FROM job_runs WHERE job=? ORDER BY id DESC LIMIT 1",
                        (n,)).fetchone()
        out.append({"job": n, "enabled": s.get("enabled"), "built": n in JOBS,
                    "schedule": s.get("at") or f"every {s.get('every_hours')} h",
                    "last": dict(r) if r else None, "desc": s.get("desc")})
    return out
