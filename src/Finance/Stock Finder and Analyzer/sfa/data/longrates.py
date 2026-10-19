"""Inputs for the cost of capital: 10-year government yields (FRED), equity risk
premiums (Damodaran's country file when reachable, config otherwise) and terminal
growth anchors (inflation targets)."""

from __future__ import annotations

import io
import time

import pandas as pd
import requests

from ..config import DB_DIR, load

CACHE = DB_DIR / "cache" / "rates"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
DAMODARAN = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/ctryprem.xlsx"
COUNTRY_NAMES = {"US": "United States", "GB": "United Kingdom", "FR": "France", "NL": "Netherlands", "BE": "Belgium",
                 "PT": "Portugal", "IE": "Ireland", "IT": "Italy", "NO": "Norway", "DE": "Germany", "ES": "Spain",
                 "CH": "Switzerland", "DK": "Denmark", "SE": "Sweden", "FI": "Finland", "JP": "Japan",
                 "KR": "Korea", "TW": "Taiwan", "HK": "Hong Kong", "CN": "China", "CA": "Canada", "AU": "Australia",
                 "SG": "Singapore", "IN": "India", "SA": "Saudi Arabia", "BR": "Brazil", "MX": "Mexico",
                 "ZA": "South Africa", "ID": "Indonesia", "AE": "United Arab Emirates", "IL": "Israel"}
_mem: dict = {}


def _fred(sid: str) -> pd.Series | None:
    f = CACHE / f"{sid}.csv"
    text = None
    if not f.exists() or time.time() - f.stat().st_mtime > 7 * 86400:
        try:
            r = requests.get(FRED.format(sid=sid), timeout=40)        # default User-Agent: FRED refuses browser ones
            if r.ok and r.text.startswith("observation_date"):
                text = r.text
                CACHE.mkdir(parents=True, exist_ok=True)
                f.write_text(text)
        except requests.RequestException:
            pass
    if text is None and f.exists():
        text = f.read_text()
    if text is None:
        return None
    df = pd.read_csv(io.StringIO(text))
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce") / 100.0
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna().sort_index()


def risk_free(country: str | None) -> tuple[float, str]:
    """(10-year yield, source) for a country."""
    key = ("rf", country)
    if key in _mem:
        return _mem[key]
    cfg = load("analyzer")["risk_free"]
    out = None
    sid = cfg["fred"].get(country or "")
    if sid:
        s = _fred(sid)
        if s is not None and len(s):
            out = (float(s.iloc[-1]), f"FRED {sid} ({s.index[-1].date()})")
    if out is None and country in cfg.get("peg_to_us", []):
        v, src = risk_free("US")
        out = (v, f"US 10-year yield (currency peg); {src}")
    if out is None and country in (cfg.get("approximate") or {}):
        out = (cfg["approximate"][country], "approximate level in config/analyzer.yaml (no FRED series)")
    if out is None:
        v, src = risk_free("US")
        out = (v, f"US 10-year yield (no series for {country}); {src}")
    _mem[key] = out
    return out


def _damodaran() -> dict[str, dict]:
    """{country name: {"erp": total ERP, "crp": country risk premium}} or {}."""
    if "dam" in _mem:
        return _mem["dam"]
    f = CACHE / "damodaran_ctryprem.xlsx"
    if not f.exists() or time.time() - f.stat().st_mtime > 30 * 86400:
        try:
            r = requests.get(DAMODARAN, timeout=60)
            if r.ok and r.content[:2] == b"PK":
                CACHE.mkdir(parents=True, exist_ok=True)
                f.write_bytes(r.content)
        except requests.RequestException:
            pass
    out = {}
    if f.exists():
        try:
            xl = pd.ExcelFile(f)
            for sheet in xl.sheet_names:
                raw = xl.parse(sheet, header=None)
                hdr = None
                for i in range(min(30, len(raw))):
                    cells = [str(c).lower() for c in raw.iloc[i].tolist()]
                    if any("country" == c.strip() or c.startswith("country") for c in cells) and \
                            any("equity risk premium" in c for c in cells):
                        hdr = i
                        break
                if hdr is None:
                    continue
                df = raw.iloc[hdr + 1:].copy()
                df.columns = [str(c).strip().lower() for c in raw.iloc[hdr].tolist()]
                ccol = next(c for c in df.columns if c.startswith("country"))
                ecol = next((c for c in df.columns if "total equity risk premium" in c), None) or \
                    next(c for c in df.columns if "equity risk premium" in c)
                rcol = next((c for c in df.columns if "country risk premium" in c), None)
                for _, r in df.iterrows():
                    name, erp = r[ccol], pd.to_numeric(r[ecol], errors="coerce")
                    if isinstance(name, str) and pd.notna(erp):
                        out[name.strip()] = {"erp": float(erp), "crp": float(pd.to_numeric(r[rcol], errors="coerce"))
                                             if rcol else None}
                if out:
                    break
        except Exception:  # noqa: BLE001 - file layout changes must not stop valuations
            out = {}
    _mem["dam"] = out
    return out


def equity_risk_premium(country: str | None, market_class: str | None) -> tuple[float, str]:
    dam = _damodaran()
    name = COUNTRY_NAMES.get(country or "")
    if name and name in dam:
        return dam[name]["erp"], f"Damodaran total ERP for {name}"
    cfg = load("analyzer")["equity_risk_premium"]
    if country in cfg.get("by_country", {}):
        return cfg["by_country"][country], f"config ERP for {country} (Damodaran file not reachable)"
    if market_class in ("Emerging", "Frontier", "Standalone"):
        return cfg["emerging_default"], "emerging-market stand-in (Damodaran file not reachable; check)"
    return cfg["mature"], "Damodaran mature-market ERP (config)"


def terminal_growth(country: str | None) -> tuple[float, str]:
    cfg = load("analyzer")["terminal_growth"]
    if country in cfg["by_country"]:
        return cfg["by_country"][country], f"inflation target / anchor for {country}"
    return cfg["default"], "default long-run inflation"
