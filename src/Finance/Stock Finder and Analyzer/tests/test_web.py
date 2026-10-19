"""Tests for Milestone 5: dashboard API, settings file and doctor helpers.

Run from the "Stock Finder and Analyzer" folder:  python tests/test_web.py
"""

import json
import os
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sfa.db import set_tag  # noqa: E402
from sfa.doctor import _v  # noqa: E402
from sfa.envfile import load_env  # noqa: E402
from sfa.finder import leads, linking, rules  # noqa: E402
from sfa.web import server  # noqa: E402

_srv = {}


def _start():
    if _srv:
        return _srv["base"]
    import sqlite3
    from test_finder import add_news, fixture
    mem = fixture()
    for k in range(4):
        add_news(mem, f"Toyota sales rise in month {k}", 0.6, days_ago=k)
    linking.link_pending(mem)
    rules.compute(mem)
    set_tag(mem, 3, "growth", "growth_1y", 0.12, {"range_5_95": [-0.2, 0.5], "rf_annual": 0.01, "model": "EWMA"})
    leads.build(mem)
    path = os.path.join(tempfile.mkdtemp(), "t.sqlite")
    disk = sqlite3.connect(path)
    mem.backup(disk)
    disk.close()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server.serve("127.0.0.1", port, db_path=path, block=False)
    time.sleep(0.3)
    _srv["base"] = f"http://127.0.0.1:{port}"
    return _srv["base"]


def get(path):
    with urllib.request.urlopen(_start() + path, timeout=10) as r:
        return r.status, r.read()


def getj(path):
    code, body = get(path)
    return code, json.loads(body)


def test_index_served():
    code, body = get("/")
    assert code == 200 and b"Stock Finder and Analyzer" in body


def test_overview_counts():
    code, d = getj("/api/overview")
    assert code == 200 and d["companies"] == 5 and d["leads"].get("listed", 0) >= 1


def test_leads_and_search():
    _, d = getj("/api/leads?kind=listed")
    assert d["leads"] and d["leads"][0]["name"].startswith("Toyota") and isinstance(d["leads"][0]["routes"], list)
    _, s = getj("/api/search?q=info")
    assert any(r["home_symbol"] == "INFY.NS" for r in s["results"])


def test_company_page():
    _, d = getj("/api/company?symbol=TM")                  # any listing symbol finds the company
    assert d["company"]["home_symbol"] == "7203.T" and d["lead"]["routes"]
    _, e = getj("/api/company?symbol=NOPE")
    assert "error" in e


def test_markets_service_and_leaderboard_empty_ok():
    for p in ("/api/markets", "/api/service", "/api/leaderboard?group_type=cell"):
        code, _ = getj(p)
        assert code == 200, p


def test_not_found_and_traversal_blocked():
    for p in ("/nope", "/files/../db/sfa.sqlite", "/files/%2e%2e/sfa/db.py"):
        try:
            get(p)
            raise AssertionError(p)
        except urllib.error.HTTPError as e:
            assert e.code == 404


def test_clean_json():
    assert server.clean({"a": float("nan"), "b": [1.0, float("inf")]}) == {"a": None, "b": [1.0, None]}


def test_envfile_loads_without_overriding():
    d = tempfile.mkdtemp()
    f = Path(d) / "sfa.env"
    f.write_text("# comment\nSFA_TEST_A=one\nSFA_TEST_B='two'\nSFA_TEST_EMPTY=\n")
    os.environ["SFA_TEST_B"] = "already"
    loaded = load_env(f)
    assert os.environ["SFA_TEST_A"] == "one" and os.environ["SFA_TEST_B"] == "already" and loaded == ["SFA_TEST_A"]
    assert "SFA_TEST_EMPTY" not in os.environ


def test_version_compare():
    assert _v("2.0.3") >= _v("2.0") and _v("1.26.4") < _v("2.0") and _v("3.1.5") >= _v("3.1")


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
