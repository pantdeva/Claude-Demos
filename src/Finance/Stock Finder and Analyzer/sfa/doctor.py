"""python -m sfa doctor — check that this computer is ready to run the app.

Checks Python and packages, settings (environment variables), which data sources are
reachable, FinBERT weights, disk space and what is already in the database, and prints
what to do about anything missing. Exit code 0 when nothing essential is missing.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sqlite3
import sys

from .config import DB_DIR, ROOT

OK, WARN, BAD = "OK  ", "WARN", "FAIL"
PACKAGES = [("requests", "2.28"), ("yaml", "6.0"), ("numpy", "1.24"), ("scipy", "1.10"), ("pandas", "2.0"),
            ("openpyxl", "3.1")]
SITES = [  # (label, url, essential?)
    ("Yahoo Finance (prices, statements, news)", "https://query1.finance.yahoo.com/v1/finance/search?q=AAPL", True),
    ("FRED (interest rates)", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", True),
    ("Hugging Face (FinBERT download, first run only)", "https://huggingface.co/ProsusAI/finbert/resolve/main/config.json", False),
    ("NewsAPI", "https://newsapi.org/v2/top-headlines?country=us", False),
    ("Economic Times RSS", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", False),
    ("Moneycontrol RSS", "https://www.moneycontrol.com/rss/marketreports.xml", False),
    ("Mint RSS", "https://www.livemint.com/rss/markets", False),
    ("Google News RSS (Reuters, IPO searches)", "https://news.google.com/rss/search?q=IPO&hl=en-IN&gl=IN&ceid=IN:en", False),
    ("Bloomberg RSS", "https://feeds.bloomberg.com/markets/news.rss", False),
    ("Dow Jones RSS (WSJ, MarketWatch)", "https://feeds.content.dowjones.io/public/rss/mw_topstories", False),
    ("SEC EDGAR", "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=S-1&count=1&output=atom", False),
    ("SEBI RSS", "https://www.sebi.gov.in/sebirss.xml", False),
    ("Damodaran country risk premiums", "https://pages.stern.nyu.edu/~adamodar/pc/datasets/ctryprem.xlsx", False),
    ("Firebase Cloud Messaging (phone notifications)", "https://fcm.googleapis.com/", False),
    ("Google sign-in for Firebase", "https://oauth2.googleapis.com/token", False),
]


def _v(ver: str) -> tuple:
    out = []
    for p in ver.split(".")[:3]:
        digits = "".join(ch for ch in p if ch.isdigit())
        out.append(int(digits or 0))
    return tuple(out)


def run() -> int:
    bad = 0
    print("Stock Finder and Analyzer — doctor\n")
    py = sys.version_info
    st = OK if py >= (3, 10) else BAD
    bad += st == BAD
    print(f"[{st}] Python {py.major}.{py.minor}.{py.micro}" + ("" if st == OK else "  → install Python 3.10 or newer (3.12 recommended)"))
    for mod, minv in PACKAGES:
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "?")
            st = OK if ver == "?" or _v(ver) >= _v(minv) else WARN
            print(f"[{st}] {mod} {ver}" + ("" if st == OK else f"  → pip install -U {mod} (need ≥ {minv})"))
        except ImportError:
            bad += 1
            print(f"[{BAD}] {mod} missing  → pip install -r requirements.txt")
    print()
    hints = {"NEWSAPI_KEY": "NewsAPI deep dives on leads (newsapi.org → account → API key)",
             "SFA_SEC_USER_AGENT": 'SEC IPO filings feed: "Your Name you@example.com"',
             "SFA_FCM_SERVICE_ACCOUNT": "optional: Firebase key file for phone notifications (ANDROID.md)",
             "SFA_DASHBOARD_URL": "optional: dashboard address the phone opens (e.g. Tailscale name)",
             "SFA_FINBERT_DIR": "optional: FinBERT weights folder (default db/models/finbert)",
             "SFA_DB": "optional: database file (default db/sfa.sqlite)"}
    for k, h in hints.items():
        st = OK if os.environ.get(k) else (WARN if k in ("NEWSAPI_KEY", "SFA_SEC_USER_AGENT") else "  - ")
        print(f"[{st}] {k} {'set' if os.environ.get(k) else 'not set'}  — {h}")
    key = os.environ.get("SFA_FCM_SERVICE_ACCOUNT")
    if key:
        ok_file = os.path.exists(key)
        try:
            import google.auth  # noqa: F401
            ga = True
        except ImportError:
            ga = False
        st = OK if ok_file and ga else WARN
        print(f"[{st}] Phone notifications: key file {'found' if ok_file else 'NOT FOUND at ' + key}, "
              f"google-auth {'installed' if ga else 'missing → pip install google-auth'}")
    print()
    try:
        import requests
        for label, url, essential in SITES:
            try:
                # FRED refuses browser User-Agents; Yahoo and most news sites rate-limit the default one
                hdr = {} if "stlouisfed" in url else {"User-Agent": "Mozilla/5.0 (sfa doctor)"}
                r = requests.get(url, timeout=15, stream=True, headers=hdr)
                code = r.status_code
                r.close()
                st = OK if code < 400 or code in (401, 403) and "newsapi" in url else (BAD if essential else WARN)
                note = f"HTTP {code}" + (" (reachable; key needed)" if code == 401 else "")
            except Exception as e:  # noqa: BLE001
                st, note = (BAD if essential else WARN), f"not reachable ({type(e).__name__})"
            bad += st == BAD
            print(f"[{st}] {label}: {note}")
    except ImportError:
        pass
    print()
    fb = os.environ.get("SFA_FINBERT_DIR") or str(ROOT / "db" / "models" / "finbert")
    have = all(os.path.exists(os.path.join(fb, f)) for f in ("config.json", "vocab.txt", "model.safetensors"))
    print(f"[{OK if have else WARN}] FinBERT weights {'found' if have else 'not downloaded yet'} in {fb}"
          + ("" if have else "  → downloaded automatically (~440 MB) on the first news run"))
    free = shutil.disk_usage(str(ROOT)).free / 1e9
    st = OK if free > 3 else WARN
    print(f"[{st}] Free disk space {free:.1f} GB" + ("" if st == OK else "  → keep at least 3 GB free (database ~0.5 GB, FinBERT ~0.4 GB, caches)"))
    db = os.environ.get("SFA_DB") or str(DB_DIR / "sfa.sqlite")
    if os.path.exists(db):
        con = sqlite3.connect(db)
        q = lambda sql: con.execute(sql).fetchone()[0] if con.execute(
            "SELECT 1 FROM sqlite_master WHERE name=?", (sql.split(" FROM ")[1].split()[0],)).fetchone() else 0
        n_c = q("SELECT COUNT(*) FROM companies")
        n_f = q("SELECT COUNT(DISTINCT company_id) FROM forecast_scores")
        n_n = q("SELECT COUNT(*) FROM news_items")
        n_l = q("SELECT COUNT(*) FROM finder_leads")
        n_v = q("SELECT COUNT(DISTINCT company_id) FROM valuations")
        print(f"[{OK if n_c else WARN}] Database {db}: {n_c} companies, {n_f} backtested, {n_n} news items, "
              f"{n_l} leads, {n_v} valued")
        if n_c and n_f < n_c * 0.9:
            print(f"[{WARN}] Model leaderboard covers {n_f} of {n_c} companies  → run: python -m sfa models (resumes)")
        con.close()
    else:
        print(f"[{WARN}] No database yet at {db}  → run: python -m sfa all")
    print("\n" + ("Ready." if not bad else f"{bad} essential item(s) missing — fix the FAIL lines above."))
    return 1 if bad else 0
