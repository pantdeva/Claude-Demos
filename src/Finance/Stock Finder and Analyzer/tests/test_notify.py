import os
"""Tests for push notifications (event detection, delivery rules, Web Push).

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


class FakeSender:
    """Stands in for WebPushSender: records (endpoint, message); endpoints in `gone` answer 410."""

    def __init__(self, gone=()):
        self.sent, self.gone = [], set(gone)

    def send(self, sub, data, ttl_s=86400):
        assert sub["endpoint"].startswith("https://") and sub["p256dh"] and sub["auth"]
        json.dumps(data)
        if sub["endpoint"] in self.gone:
            from sfa.notify.webpush import PushError
            raise PushError("push service HTTP 410: gone", 410, gone=True)
        self.sent.append((sub["endpoint"], data))
        return 201


PHONE = {"endpoint": "https://fcm.googleapis.com/fcm/send/phone1", "keys": {"p256dh": "BPk", "auth": "au"}}


def db():
    from test_finder import fixture
    con = fixture()
    finder_init(con)
    N.init(con)
    N.subscribe(con, PHONE, "Android · Chrome")
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
    assert out["sent"] == 0 and s.sent == []


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
    assert d["path"].startswith("#company/") and d["id"] and d["sent"]


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


def test_nobody_subscribed_logs_instead():
    con = db()
    N.unsubscribe(con, PHONE["endpoint"])
    out = N.deliver(con, [{"type": "test", "dedupe": "t1", "title": "T", "body": "B", "symbol": "", "path": ""}],
                    local_now=DAY, sender=FakeSender())
    assert out["logged"] == 1 and out["sent"] == 0
    st, err = con.execute("SELECT status, error FROM notify_log WHERE dedupe='t1'").fetchone()
    assert st == "logged" and "Enable notifications" in err


def test_quiet_window():
    assert N.in_quiet(NIGHT, ["22:00", "07:00"]) and not N.in_quiet(DAY, ["22:00", "07:00"])
    assert N.in_quiet(datetime(2026, 1, 1, 6, 59), ["22:00", "07:00"])


def test_muted_types_and_gone_subscriptions():
    con = db()
    tablet = {"endpoint": "https://web.push.apple.com/tablet", "keys": {"p256dh": "BQ", "auth": "a2"}}
    old = {"endpoint": "https://fcm.googleapis.com/fcm/send/old", "keys": {"p256dh": "BO", "auth": "a3"}}
    N.subscribe(con, tablet, "iPhone/iPad · Safari")
    N.subscribe(con, old, "Old phone")
    N.set_muted(con, tablet["endpoint"], ["lead", "nonsense"])
    assert N.device(con, tablet["endpoint"])["muted"] == ["lead"]
    s = FakeSender(gone={old["endpoint"]})
    N.deliver(con, [{"type": "lead", "dedupe": "l1", "title": "L", "body": "", "symbol": "", "path": "#leads"},
                    {"type": "ipo", "dedupe": "i1", "title": "I", "body": "", "symbol": "", "path": "#leads"}],
              local_now=DAY, sender=s)
    got = {(ep.rsplit("/", 1)[1], d["title"]) for ep, d in s.sent}
    assert got == {("phone1", "L"), ("phone1", "I"), ("tablet", "I")}           # tablet muted leads
    assert N.device(con, old["endpoint"]) is None                                   # 410 → removed
    assert [d["label"] for d in N.devices(con)] == ["Android · Chrome", "iPhone/iPad · Safari"]


def test_subscribe_validation_and_refresh():
    con = db()
    for bad in ({}, {"endpoint": "http://x/y", "keys": {"p256dh": "a", "auth": "b"}},
                {"endpoint": "https://x/y", "keys": {"p256dh": "a"}}):
        try:
            N.subscribe(con, bad)
            raise AssertionError("accepted a bad subscription")
        except ValueError:
            pass
    N.subscribe(con, {"endpoint": PHONE["endpoint"], "keys": {"p256dh": "NEW", "auth": "au"}})   # keys rotate, label kept
    r = con.execute("SELECT p256dh, label FROM push_subs").fetchall()
    assert len(r) == 1 and r[0]["p256dh"] == "NEW" and r[0]["label"] == "Android · Chrome"


def test_send_test_to_one_device():
    con, s = db(), FakeSender()
    assert N.send_test(con, sender=s, endpoint=PHONE["endpoint"]) == {"sent": 1}
    assert s.sent[0][1]["type"] == "test"
    assert con.execute("SELECT status FROM notify_log WHERE type='test'").fetchone()[0] == "sent"


def test_webpush_rfc8291_vector_and_vapid():
    """Encryption matches RFC 8291 appendix A; the VAPID token verifies with the public key."""
    import tempfile
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
    from sfa.notify.webpush import Vapid, b64u, b64u_dec, decrypt, encrypt
    key = lambda s: ec.derive_private_key(int.from_bytes(b64u_dec(s), "big"), ec.SECP256R1())  # noqa: E731
    body = encrypt(b"When I grow up, I want to be a watermelon",
                   "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
                   "BTBZMqHH6r4Tts7J_aSIgg", salt=b64u_dec("DGv6ra1nlYgDCS1FRnbzlw"),
                   server_key=key("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"))
    assert b64u(body) == ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8"
                          "wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")
    assert decrypt(body, key("q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"), "BTBZMqHH6r4Tts7J_aSIgg") == \
        b"When I grow up, I want to be a watermelon"
    d = tempfile.mkdtemp()
    v = Vapid(d)
    assert Vapid(d).public_b64 == v.public_b64 and len(b64u_dec(v.public_b64)) == 65      # stored and reused
    hdr = v.auth_header("https://web.push.apple.com/abc", "mailto:me@example.com")
    jwt = hdr.split("t=")[1].split(",")[0]
    h, c, sig = jwt.split(".")
    claims = json.loads(b64u_dec(c))
    assert claims["aud"] == "https://web.push.apple.com" and claims["sub"] == "mailto:me@example.com"
    raw = b64u_dec(sig)
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b64u_dec(v.public_b64))
    pub.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
               f"{h}.{c}".encode(), ec.ECDSA(hashes.SHA256()))


def test_webpush_sender_request():
    """The HTTP request a push service receives: headers, and a body the browser can decrypt."""
    import tempfile
    from cryptography.hazmat.primitives.asymmetric import ec
    from sfa.notify.webpush import PushError, Vapid, WebPushSender, b64u, decrypt
    ua = ec.generate_private_key(ec.SECP256R1())
    from cryptography.hazmat.primitives import serialization
    p256dh = b64u(ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    auth = b64u(b"0123456789abcdef")

    class Resp:
        def __init__(self, code):
            self.status_code, self.text = code, ""

    class Session:
        def __init__(self, code):
            self.code, self.calls = code, []

        def post(self, url, data=None, headers=None, timeout=None):
            self.calls.append((url, data, headers))
            return Resp(self.code)

    sess = Session(201)
    snd = WebPushSender("mailto:me@example.com", Vapid(tempfile.mkdtemp()), sess)
    snd.send({"endpoint": "https://fcm.googleapis.com/fcm/send/x", "p256dh": p256dh, "auth": auth},
             {"title": "Hi", "type": "test"}, ttl_s=60)
    url, body, h = sess.calls[0]
    assert h["Content-Encoding"] == "aes128gcm" and h["TTL"] == "60" and h["Authorization"].startswith("vapid t=")
    assert json.loads(decrypt(body, ua, auth)) == {"title": "Hi", "type": "test"}
    try:
        WebPushSender("mailto:x@y.z", Vapid(tempfile.mkdtemp()), Session(410)).send(
            {"endpoint": "https://a/b", "p256dh": p256dh, "auth": auth}, {"t": 1})
        raise AssertionError("expected PushError")
    except PushError as e:
        assert e.gone


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

