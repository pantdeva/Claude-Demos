"""Local short-term (cash) rates per currency, from FRED, cached in db/cache/rates.

US T-bills (DTB3) for USD and the dollar-pegged HKD and SAR; OECD 3-month interbank
rates for most others; India's call-money rate. Currencies FRED does not cover fall
back to a fixed rate in FALLBACK (flagged in results).
"""

from __future__ import annotations

import io
import time
from datetime import datetime

import pandas as pd
import requests

from ..config import DB_DIR

CACHE = DB_DIR / "cache" / "rates"
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
SERIES = {
    "USD": "DTB3", "HKD": "DTB3", "SAR": "DTB3",
    "GBP": "IR3TIB01GBM156N", "EUR": "IR3TIB01EZM156N", "JPY": "IR3TIB01JPM156N",
    "KRW": "IR3TIB01KRM156N", "AUD": "IR3TIB01AUM156N", "CAD": "IR3TIB01CAM156N",
    "CNY": "IR3TIB01CNM156N", "NOK": "IR3TIB01NOM156N", "CHF": "IR3TIB01CHM156N",
    "DKK": "IR3TIB01DKM156N", "SEK": "IR3TIB01SEM156N", "ZAR": "IR3TIB01ZAM156N",
    "INR": "IRSTCI01INM156N",
}
FALLBACK = {"TWD": 0.015, "SGD": 0.025}      # approximate policy-rate levels, flagged
MINOR = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}
MAX_AGE = 7 * 86400
FAIL_TTL = 6 * 3600          # after a failed download, wait before trying FRED again
SCREEN_CACHE = DB_DIR.parent.parent / "nlp_stock_analyzer" / "screen" / "cache" / "rates"
_mem: dict[str, tuple[pd.Series, str]] = {}


def _fetch(sid: str) -> str | None:
    for k in range(3):
        try:
            r = requests.get(URL.format(sid=sid), timeout=40)     # a browser User-Agent is refused
            if r.ok and r.text.startswith("observation_date"):
                return r.text
        except requests.RequestException:
            pass
        time.sleep(2 * (k + 1))
    return None


def series(ccy: str | None) -> tuple[pd.Series, str]:
    """(annual decimal rate indexed by date, source label). Memoised per process."""
    key = MINOR.get(ccy or "USD", ccy or "USD").upper()
    if key not in _mem:
        _mem[key] = _series(key)
    return _mem[key]


def _series(ccy: str) -> tuple[pd.Series, str]:
    sid = SERIES.get(ccy)
    if sid is None:
        val = FALLBACK.get(ccy)
        if val is None:
            s, _ = series("USD")
            return s, f"USD T-bill (no {ccy} series)"
        idx = pd.date_range("2000-01-01", datetime.now().strftime("%Y-%m-%d"), freq="D")
        return pd.Series(val, index=idx), f"fixed {val:.1%} (approximate; no {ccy} series on FRED)"
    f = CACHE / f"{sid}.csv"
    failed = CACHE / f"{sid}.failed"
    text = None
    stale = not f.exists() or time.time() - f.stat().st_mtime > MAX_AGE
    recently_failed = failed.exists() and time.time() - failed.stat().st_mtime < FAIL_TTL
    if stale and not recently_failed:
        text = _fetch(sid)
        CACHE.mkdir(parents=True, exist_ok=True)
        if text:
            f.write_text(text)
            failed.unlink(missing_ok=True)
        else:
            failed.write_text(datetime.now().isoformat())
    if text is None and f.exists():
        text = f.read_text()
    if text is None and (SCREEN_CACHE / f"{ccy}.csv").exists():      # copy saved by the index screen
        text = (SCREEN_CACHE / f"{ccy}.csv").read_text()
    if text is None:
        idx = pd.date_range("2000-01-01", datetime.now().strftime("%Y-%m-%d"), freq="D")
        return pd.Series(0.0, index=idx), f"0% (FRED {sid} unavailable)"
    df = pd.read_csv(io.StringIO(text))
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce") / 100.0
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna().sort_index(), f"FRED {sid}"
