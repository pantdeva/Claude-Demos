import os
"""Tests for push notifications (event detection, delivery rules, FCM payloads).

Run from the "Stock Finder and Analyzer" folder:  python tests/test_notify.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sfa import notify as N  # noqa: E402
from sfa.db import now  # noqa: E402
from sfa.finder import init as finder_init  # noqa: E402


os.environ["SFA_NOTIFY_EMAILS"] = "me@example.com"


class FakeSender:
    """Stands in for FCMSender: one signed-in phone of an allowed account by default."""

    def __init__(self, devs=None, gone=()):
        self.sent, self.deleted, self.gone = [], [], set(gone)
        self.devs = devs if devs is not None else [
            {"uid": "u1", "email": "me@example.com", "device": "d1", "token": "tok1", "model": "Pixel", "updated": "",
             "doc": "projects/x/databases/(default)/documents/users/u1/devices/d1"}]
        self.asked = None

    def devices(self, emails):
        self.asked = set(emails)
        return [d for d in self.devs if d["email"] in emails]

    def send(self, data, token=None, topic=None, ttl_s=86400):
        assert all(isinstance(v, str) for v in data.values()), data
        assert token or topic
        if token in self.gone:
            from sfa.notify.fcm import FCMError
            raise FCMError("FCM HTTP 404: UNREGISTERED", 404, unregistered=True)
        self.sent.append((token or topic, data))
        return "projects/x/messages/1"

    def delete_device(self, doc):
        self.deleted.append(doc)


def db():
    from test_finder import fixture
    con = fixture()
    finder_init(con)
    N.init(con)
    return con


def put_lead(con, key, name, symbol, score):
    con.execute("INSERT OR REPLACE INTO finder_leads (lead_key, kind, name, symbol, score, news_score, model_score, routes, "
                "status) VALUES (?,?,?,?,?,?,?,?,?)", (key, "listed", name, symbol, score, score, score,
                                                        json.dumps([{"route": "Buy directly on NSE/BSE", "symbol": symbol,
                                                                     "ok": True}]), "active"))


DAY = datetime(2026, 10, 19, 12, 0)           # outside quiet hours, after the digest time
NIGHT = datetime(2026, 10, 19, 23, 30)


def test_first_run_only_snapshots():
    con, s = db(), FakeSender()
    put_lead(con, "listed:1", "Infosys Limited", "INFY.NS", 0.3)
    out = N.run(con, local_now=DAY.replace(hour=8), sender=s)       # before 08:45: no digest either
    assert out["sent"] == 0 and [d["type"] for _, d in s.sent] == ["heartbeat"]


def test_new_top_lead_and_score_jump():
    con, s = db(), FakeSender()
    put_lead(con, "listed:1", "Infosys Limited", "INFY.NS", 0.3)
    N.run(con, local_now=DAY.replace(hour=8), sender=s)
    put_lead(con, "listed:2", "Wipro Limited", "WIPRO.NS", 0.5)            # new entrant
    put_lead(con, "listed:1", "Infosys Limited", "INFY.NS", 0.55)          # +0.25 jump
    N.run(con, local_now=DAY.replace(hour=8), sender=s)
    titles = [d["title"] for _, d in s.sent if d["type"] == "lead"]
    assert any(t.startswith("Wipro Limited entered the top") for t in titles)
    assert any(t.startswith("Infosys Limited score up") for t in titles)
    d = next(d for _, d in s.sent if d["type"] == "lead")
    assert d["path"].startswith("#company/") and d["channel"] == "leads" and d["url"]


def test_ipo_new_name_and_stage_advance():
    con, s = db(), FakeSender()
    con.execute("INSERT INTO ipo_events (name, name_key, stage, event_date, news_id, title, found) VALUES "
                "('Lenskart','lenskart','filed','2026-10-01',1,'Lenskart files DRHP',?)", (now(),))
    N.run(con, local_now=DAY.replace(hour=8), sender=s)
    con.execute("INSERT INTO ipo_events (name, name_key, stage, event_date, news_id, title, found) VALUES "
                "('Lenskart','lenskart','priced','2026-10-15',2,'Lenskart IPO opens',?)", (now(),))
    con.execute("INSERT INTO ipo_events (name, name_key, stage, event_date, news_id, title, found) VALUES "
                "('PayPay','paypay','planning','2026-10-16',3,'PayPay plans US IPO',?)", (now(),))
    N.run(con, local_now=DAY.replace(hour=8), sender=s)
    titles = {d["title"] for _, d in s.sent if d["type"] == "ipo"}
    assert "Lenskart IPO: filed → priced" in titles and "IPO pipeline: PayPay (planning)" in titles


def test_valuation_verdict_change():
    con, s = db(), FakeSender()
    con.execute("INSERT INTO valuations VALUES (3,'combined',3000,3100,'JPY',?,?)",
                (json.dumps({"verdict": "Fairly valued", "upside": -0.03}), "2026-10-18"))
    N.run(con, local_now=DAY.replace(hour=8), sender=s)
    con.execute("INSERT INTO valuations VALUES (3,'combined',4000,3100,'JPY',?,?)",
                (json.dumps({"verdict": "Undervalued", "upside": 0.29}), "2026-10-19"))
    N.run(con, local_now=DAY.replace(hour=8), sender=s)
    v = [d for _, d in s.sent if d["type"] == "valuation"]
    assert v and v[0]["title"] == "Toyota Motor Corporation now Undervalued" and "was Fairly valued" in v[0]["body"]


def test_digest_once_per_day_after_time():
    con, s = db(), FakeSender()
    put_lead(con, "listed:1", "Infosys Limited", "INFY.NS", 0.3)
    N.run(con, local_now=DAY.replace(hour=8, minute=0), sender=s)
    assert not [d for _, d in s.sent if d["type"] == "digest"]
    N.run(con, local_now=DAY, sender=s)
    N.run(con, local_now=DAY.replace(hour=13), sender=s)
    dg = [d for _, d in s.sent if d["type"] == "digest"]
    assert len(dg) == 1 and "Infosys" in dg[0]["body"]


def test_job_failure_alert_and_quiet_hours():
    con, s = db(), FakeSender()
    put_lead(con, "listed:1", "Infosys Limited", "INFY.NS", 0.3)
    N.run(con, local_now=NIGHT, sender=s)
    con.execute("INSERT INTO job_runs (job, started, status, message) VALUES ('news', ?, 'error', 'Traceback…\\nValueError: boom')",
                (now(),))
    put_lead(con, "listed:2", "Wipro Limited", "WIPRO.NS", 0.5)
    N.run(con, local_now=NIGHT, sender=s)
    types = [d["type"] for _, d in s.sent]
    assert "alert" in types and "lead" not in types                 # alert goes out at night, the lead waits
    a = next(d for _, d in s.sent if d["type"] == "alert")
    assert a["title"] == "Job failed: news" and "boom" in a["body"]
    N.run(con, local_now=DAY.replace(hour=8), sender=s)               # quiet hours over
    assert "lead" in [d["type"] for _, d in s.sent]


def test_cap_folds_extra_messages():
    con, s = db(), FakeSender()
    evs = [{"type": "ipo", "dedupe": f"ipo:x{i}", "title": f"IPO {i}", "body": "b", "symbol": "", "path": "#leads"}
           for i in range(12)]
    out = N.deliver(con, evs, local_now=DAY, sender=s)
    assert out["sent"] == 8 and s.sent[-1][1]["title"].startswith("…and 5 more")
    N.deliver(con, evs, local_now=DAY, sender=s)                      # same events again: deduplicated
    assert len(s.sent) == 8


def test_no_sender_logs_instead():
    con = db()
    import os
    os.environ.pop("SFA_FCM_SERVICE_ACCOUNT", None)                   # FCM not configured → logged only
    out = N.deliver(con, [{"type": "test", "dedupe": "t1", "title": "T", "body": "B", "symbol": "", "path": ""}],
                    local_now=DAY)
    assert out["logged"] == 1 and out["sent"] == 0
    assert con.execute("SELECT status FROM notify_log WHERE dedupe='t1'").fetchone()[0] == "logged"


def test_quiet_window_and_pairing():
    assert N.in_quiet(NIGHT, ["22:00", "07:00"]) and not N.in_quiet(DAY, ["22:00", "07:00"])
    assert N.in_quiet(datetime(2026, 1, 1, 6, 59), ["22:00", "07:00"])
    con = db()
    t = N.topic(con)
    assert t.startswith("sfa-") and N.topic(con) == t and N.pair_link(con).startswith("sfa://pair?url=")


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    sys.exit(1 if fails else 0)


def test_devices_mode_only_allowed_emails_and_prunes_dead_tokens():
    from sfa import notify
    devs = [{"uid": "u1", "email": "me@example.com", "device": "d1", "token": "tok1", "model": "Pixel", "updated": "", "doc": "D1"},
            {"uid": "u1", "email": "me@example.com", "device": "d2", "token": "dead", "model": "Old", "updated": "", "doc": "D2"},
            {"uid": "u2", "email": "other@example.com", "device": "d3", "token": "tok3", "model": "X", "updated": "", "doc": "D3"}]
    con, s = db(), FakeSender(devs, gone={"dead"})
    tg = notify.targets(con, s)
    assert s.asked == {"me@example.com"} and [t["token"] for t in tg] == ["tok1", "dead"]
    n = notify.broadcast(s, tg, {"type": "test", "title": "t"})
    assert n == 1 and [x[0] for x in s.sent] == ["tok1"] and s.deleted == ["D2"]
    assert len(notify._get(con, "devices")) == 2


def test_no_allowed_emails_or_no_phone_means_logged():
    from sfa import notify
    old = os.environ.pop("SFA_NOTIFY_EMAILS")
    try:
        con, s = db(), FakeSender()
        try:
            notify.targets(con, s)
            raise AssertionError("expected NoTargets")
        except notify.NoTargets as e:
            assert "SFA_NOTIFY_EMAILS" in str(e)
    finally:
        os.environ["SFA_NOTIFY_EMAILS"] = old
    con, s = db(), FakeSender(devs=[])
    try:
        notify.targets(con, s)
        raise AssertionError("expected NoTargets")
    except notify.NoTargets as e:
        assert "sign in" in str(e)


def test_pair_link_devices_mode_has_no_topic():
    from sfa import notify
    con = db()
    assert notify.pair_link(con).startswith("sfa://pair?url=") and "topic=" not in notify.pair_link(con)
