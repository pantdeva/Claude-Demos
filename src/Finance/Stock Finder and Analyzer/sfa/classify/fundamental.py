"""Heading 4: stock-level characteristics.

cap band      USD bands everywhere; for India also the SEBI rank band (1–100 large,
              101–250 mid, 251+ small), ranked within the universe (approximate:
              SEBI/AMFI rank across all listed companies by 6-month average value).
growth/value  style score = z(revenue growth) − mean(z(E/P), z(B/P), z(S/P)) within
              peers (same market class × sector group when ≥ 15 peers, else same group);
              > +0.5 Growth, < −0.5 Value, otherwise Blend.
beta          weekly returns vs the home benchmark over 3 years (used by cyclical/defensive).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np

USD_BANDS = [(200e9, "Mega"), (10e9, "Large"), (2e9, "Mid"), (300e6, "Small"), (0, "Micro")]


def usd_band(mcap_usd: float | None) -> str | None:
    if mcap_usd is None or not math.isfinite(mcap_usd):
        return None
    return next(lbl for lim, lbl in USD_BANDS if mcap_usd >= lim)


def sebi_band(rank: int | None) -> str | None:
    if rank is None:
        return None
    return "Large" if rank <= 100 else "Mid" if rank <= 250 else "Small"


def _winsor_z(x: np.ndarray) -> np.ndarray:
    m = np.isfinite(x)
    out = np.full_like(x, np.nan, dtype=float)
    if m.sum() < 3:
        return out
    v = x[m]
    lo, hi = np.percentile(v, [5, 95])
    v = np.clip(v, lo, hi)
    sd = v.std()
    out[m] = 0.0 if sd == 0 else (v - v.mean()) / sd
    return np.clip(out, -3, 3)


def style_scores(rows: list[dict], min_cell: int = 15) -> dict[int, dict]:
    """rows: {id, cell, group, growth, ep, bp, sp}. Returns {id: {score, label, peers, basis}}."""
    out = {}
    by_cell, by_group = {}, {}
    for r in rows:
        by_cell.setdefault(r["cell"], []).append(r)
        by_group.setdefault(r["group"], []).append(r)
    for r in rows:
        peers, basis = by_cell[r["cell"]], "market class × sector group"
        if len(peers) < min_cell:
            peers, basis = by_group[r["group"]], "sector group (global)"
        idx = {p["id"]: i for i, p in enumerate(peers)}
        z = {k: _winsor_z(np.array([p[k] if p[k] is not None else np.nan for p in peers], float))
             for k in ("growth", "ep", "bp", "sp")}
        i = idx[r["id"]]
        zg = z["growth"][i]
        zv = [z[k][i] for k in ("ep", "bp", "sp") if math.isfinite(z[k][i])]
        if not math.isfinite(zg) and not zv:
            out[r["id"]] = {"score": None, "label": "Unclassified", "peers": len(peers), "basis": basis}
            continue
        s = (zg if math.isfinite(zg) else 0.0) - (float(np.mean(zv)) if zv else 0.0)
        lbl = "Growth" if s > 0.5 else "Value" if s < -0.5 else "Blend"
        out[r["id"]] = {"score": round(s, 3), "label": lbl, "peers": len(peers), "basis": basis,
                        "z": {"growth": _r(zg), **{k: _r(z[k][i]) for k in ("ep", "bp", "sp")}}}
    return out


def _r(v):
    return None if v is None or not math.isfinite(v) else round(float(v), 3)


def weekly_beta(px: dict[str, float], bench: dict[str, float], years: int = 3) -> tuple[float | None, int]:
    """OLS beta of weekly (Friday-to-Friday) log returns. px/bench: {iso date: close}."""
    if not px or not bench:
        return None, 0
    cutoff = datetime.now(timezone.utc).timestamp() - years * 365.25 * 86400
    common = sorted(d for d in px.keys() & bench.keys()
                    if datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp() >= cutoff)
    if len(common) < 60:
        return None, 0
    weekly, last_wk = [], None
    for d in common:
        wk = datetime.fromisoformat(d).isocalendar()[:2]
        if wk != last_wk:
            weekly.append(d)
            last_wk = wk
        else:
            weekly[-1] = d
    a = np.log([px[d] for d in weekly])
    b = np.log([bench[d] for d in weekly])
    ra, rb = np.diff(a), np.diff(b)
    m = np.isfinite(ra) & np.isfinite(rb)
    ra, rb = ra[m], rb[m]
    if len(ra) < 40 or rb.var() == 0:
        return None, len(ra)
    return float(np.cov(ra, rb)[0, 1] / rb.var(ddof=1)), len(ra)


def latest(series: list[dict] | None, n: int = 1):
    return (series or [])[-n:] if series else []


def growth_rate(fund: dict) -> tuple[float | None, str]:
    """Revenue growth: latest annual YoY; 2-year CAGR when the last year looks broken."""
    a = [p for p in fund.get("annualTotalRevenue") or [] if p["value"]]
    if len(a) >= 2 and a[-2]["value"] > 0:
        g = a[-1]["value"] / a[-2]["value"] - 1
        if (g > 5 or a[-2]["value"] < 0.25 * a[-1]["value"]) and len(a) >= 3 and a[-3]["value"] > 0:
            return (a[-1]["value"] / a[-3]["value"]) ** 0.5 - 1, "2-year CAGR (last year looked broken)"
        return g, "annual YoY"
    q = [p for p in fund.get("quarterlyTotalRevenue") or [] if p["value"]]
    if len(q) >= 5 and q[-5]["value"] > 0:
        return q[-1]["value"] / q[-5]["value"] - 1, "quarter vs same quarter last year"
    return None, "no revenue history"
