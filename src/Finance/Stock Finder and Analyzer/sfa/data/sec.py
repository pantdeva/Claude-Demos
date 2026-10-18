"""SEC EDGAR company facts for US-listed companies (second source next to Yahoo).

Gives state or country of incorporation and whether the company files as a foreign
private issuer (20-F / 40-F), which settles domicile for foreign companies listed only
in the US (Arm, NXP, Nebius …). SEC asks for a declared User-Agent with contact
details: set SFA_SEC_USER_AGENT="Your Name your@email". Requests are kept under
8 per second. Every call fails soft: no network → None, and classification falls back
to the home exchange.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from ..config import DB_DIR

CACHE = DB_DIR / "cache" / "sec"
TICKERS = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# EDGAR state/country codes: two-letter US state codes are US; these are the common
# non-US ones among large foreign issuers. Unknown codes are kept raw.
EDGAR_COUNTRY = {"X0": "GB", "E9": "KY", "D0": "BM", "F4": "CN", "K3": "HK",
                 **{c: "CA" for c in ("A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "B0")}}
US_STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
                "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR".split())

_last = [0.0]


def _get(url: str):
    ua = os.environ.get("SFA_SEC_USER_AGENT")
    if not ua:
        return None
    gap = 0.13 - (time.time() - _last[0])
    if gap > 0:
        time.sleep(gap)
    _last[0] = time.time()
    try:
        r = requests.get(url, headers={"User-Agent": ua}, timeout=20)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def _cached(name: str, url: str, max_age: float):
    f = CACHE / name
    if f.exists() and time.time() - f.stat().st_mtime < max_age:
        return json.loads(f.read_text())
    d = _get(url)
    if d is None:
        return json.loads(f.read_text()) if f.exists() else None
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d))
    return d


def cik_for(ticker: str) -> int | None:
    d = _cached("company_tickers_exchange.json", TICKERS, 7 * 86400)
    if not d:
        return None
    i = d["fields"].index("ticker")
    for row in d["data"]:
        if row[i] == ticker.upper():
            return row[d["fields"].index("cik")]
    return None


def company_facts(ticker: str) -> dict | None:
    """{cik, name, incorporation_code, domicile, foreign_private_issuer, sic, sic_desc}."""
    cik = cik_for(ticker)
    if cik is None:
        return None
    d = _cached(f"CIK{cik:010d}.json", SUBMISSIONS.format(cik=cik), 30 * 86400)
    if not d:
        return None
    code = (d.get("stateOfIncorporation") or "").upper()
    forms = set((d.get("filings", {}).get("recent", {}).get("form") or [])[:200])
    dom = "US" if code in US_STATES else EDGAR_COUNTRY.get(code)
    return {"cik": cik, "name": d.get("name"), "incorporation_code": code or None, "domicile": dom,
            "foreign_private_issuer": bool(forms & {"20-F", "40-F", "6-K"}),
            "sic": d.get("sic"), "sic_desc": d.get("sicDescription")}
