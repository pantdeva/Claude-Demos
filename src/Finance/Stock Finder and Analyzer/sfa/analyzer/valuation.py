"""Valuation (Module 13 Ch 14–18).

DCF:      FCFF = EBIT(1 − t) + D&A − capex − ΔNWC (Ch 15); Ke = Rf + β·ERP (Ch 16, CAPM
          with the local 10-year yield); WACC = E/V·Ke + D/V·Kd(1 − t) (Ch 17, after-tax
          cost of debt = tax shield); terminal value = FCFF_N·(1 + g)/(WACC − g) with
          g ≈ long-run inflation, capped at Rf; EV = Σ FCFF_t/(1 + WACC)^t + TV/(1 + WACC)^N;
          equity = EV − debt + cash − minority; fair price = equity ÷ shares (Ch 18),
          compared with the market price. A WACC × g sensitivity table is included.
Banks:    justified P/B = (ROE − g)/(Ke − g) applied to book value (FCFF does not apply).
Relative: median peer P/E, EV/EBITDA, P/B and EV/Sales applied to the company (Ch 14).
Option:   Merton model — equity as a call on the firm's assets struck at its debt — for
          highly levered or loss-making companies: implied asset value and volatility,
          distance to default and default probability over one year (Ch 14 "option-based").
"""

from __future__ import annotations

import math
from statistics import median

import numpy as np
from scipy import optimize, stats

from ..config import load
from .model import Projection


def capm(rf: float, beta: float, erp: float) -> float:
    return rf + beta * erp


def adjusted_beta(raw: float | None) -> tuple[float, str]:
    cfg = load("analyzer")["wacc"]
    if raw is None or not math.isfinite(raw):
        return 1.0, "beta unavailable; 1.0 assumed"
    b = 0.67 * raw + 0.33 if cfg["beta_adjustment"] == "blume" else raw
    lo, hi = cfg["beta_bounds"]
    note = f"raw {raw:.2f} → Blume-adjusted {b:.2f}"
    if not lo <= b <= hi:
        note += f" → bounded to {max(lo, min(hi, b)):.2f}"
    return max(lo, min(hi, b)), note


def wacc(ke: float, kd: float, tax: float, equity_value: float, debt: float) -> tuple[float, float]:
    """(WACC, debt weight)."""
    cfg = load("analyzer")["wacc"]
    if cfg["capital_structure"] == "target":
        de = cfg["target_debt_to_equity"]
        wd = de / (1 + de)
    else:
        v = equity_value + max(debt, 0.0)
        wd = max(debt, 0.0) / v if v > 0 else 0.0
    return (1 - wd) * ke + wd * kd * (1 - tax), wd


def dcf(fcff: list[float], w: float, g: float, debt: float, cash: float, minority: float, shares: float) -> dict:
    n = len(fcff)
    disc = [1 / (1 + w) ** t for t in range(1, n + 1)]
    pv = [f * d for f, d in zip(fcff, disc)]
    tv = fcff[-1] * (1 + g) / (w - g)
    pv_tv = tv * disc[-1]
    ev = sum(pv) + pv_tv
    eq = ev - debt + cash - minority
    return {"discount_factors": disc, "pv_fcff": pv, "terminal_value": tv, "pv_terminal": pv_tv, "ev": ev,
            "equity_value": eq, "per_share": eq / shares if shares else None,
            "terminal_share_of_ev": pv_tv / ev if ev else None}


def sensitivity(fcff, w, g, debt, cash, minority, shares, steps=(-0.01, -0.005, 0.0, 0.005, 0.01)) -> dict:
    gap = load("analyzer")["wacc"]["min_wacc_minus_g"]
    grid = {}
    for dw in steps:
        row = {}
        for dg in steps:
            ww, gg = w + dw, g + dg
            row[round(gg, 4)] = dcf(fcff, ww, gg, debt, cash, minority, shares)["per_share"] if ww - gg >= gap else None
        grid[round(w + dw, 4)] = row
    return grid


def justified_pb(roe: float, ke: float, g: float) -> float | None:
    return (roe - g) / (ke - g) if ke - g > 0.005 else None


def bank_value(st, ke: float, g: float, shares: float) -> dict | None:
    k = load("analyzer")["financials"]["roe_years"]
    d = [st.d[y] for y in st.years]
    roes = [d[i]["pat"] / ((d[i]["equity"] + d[i - 1]["equity"]) / 2)
            for i in range(1, len(d)) if d[i]["pat"] is not None and d[i]["equity"] and d[i - 1]["equity"]]
    if not roes:
        return None
    roe = sum(roes[-k:]) / len(roes[-k:])
    pb = justified_pb(roe, ke, g)
    book = st.last("equity")
    if pb is None or not book:
        return None
    return {"roe": roe, "justified_pb": pb, "book_value": book, "equity_value": pb * book,
            "per_share": pb * book / shares if shares else None}


def multiples(mcap: float, st) -> dict:
    """Company's own multiples from its latest statements (statement currency)."""
    debt, cash = st.last("debt") or 0.0, st.last("cash") or 0.0
    ev = mcap + debt - cash
    pat, ebitda, eq, rev = st.last("pat"), st.last("ebitda"), st.last("equity"), st.last("revenue")
    out = {"pe": mcap / pat if pat and pat > 0 else None,
           "ev_ebitda": ev / ebitda if ebitda and ebitda > 0 else None,
           "pb": mcap / eq if eq and eq > 0 else None,
           "ev_sales": ev / rev if rev and rev > 0 else None}
    bounds = {"pe": 150, "ev_ebitda": 80, "pb": 50, "ev_sales": 50}
    return {k: v for k, v in out.items() if v is not None and 0 < v < bounds[k]}


def relative(st, peer_multiples: list[dict], shares: float, financial: bool = False) -> dict:
    """Implied price per share from median peer multiples. Financials use P/E and P/B
    only: enterprise-value multiples mean little when debt is mostly deposits."""
    debt, cash = st.last("debt") or 0.0, st.last("cash") or 0.0
    base = {"pe": st.last("pat"), "ev_ebitda": st.last("ebitda"), "pb": st.last("equity"), "ev_sales": st.last("revenue")}
    out = {}
    keys = [k for k in load("analyzer")["relative"]["multiples"] if not financial or k in ("pe", "pb")]
    for k in keys:
        vals = [p[k] for p in peer_multiples if p.get(k)]
        if len(vals) < 3 or not base[k] or base[k] <= 0:
            continue
        m = median(vals)
        val = m * base[k]
        eq = val if k in ("pe", "pb") else val - debt + cash
        out[k] = {"peer_median": m, "peers": len(vals), "equity_value": eq, "per_share": eq / shares if shares else None}
    if out:
        out["median_per_share"] = median(v["per_share"] for v in out.values() if v["per_share"] is not None)
    return out


def merton(equity_value: float, sigma_e: float, debt: float, rf: float, T: float = 1.0) -> dict | None:
    """Solve E = V·N(d1) − D·e^(−rT)·N(d2) and σE·E = N(d1)·σV·V for V, σV."""
    if equity_value <= 0 or debt <= 0 or not sigma_e or sigma_e <= 0:
        return None

    def eqs(x):
        V, sv = math.exp(x[0]), math.exp(x[1])
        d1 = (math.log(V / debt) + (rf + sv * sv / 2) * T) / (sv * math.sqrt(T))
        d2 = d1 - sv * math.sqrt(T)
        e = V * stats.norm.cdf(d1) - debt * math.exp(-rf * T) * stats.norm.cdf(d2)
        return [(e - equity_value) / equity_value, (stats.norm.cdf(d1) * sv * V - sigma_e * equity_value) / equity_value]
    v0 = equity_value + debt
    x, info, ok, _ = optimize.fsolve(eqs, [math.log(v0), math.log(sigma_e * equity_value / v0)], full_output=True)
    if ok != 1:
        return None
    V, sv = math.exp(x[0]), math.exp(x[1])
    dd = (math.log(V / debt) + (rf - sv * sv / 2) * T) / (sv * math.sqrt(T))
    return {"asset_value": V, "asset_vol": sv, "distance_to_default": dd, "default_prob_1y": float(stats.norm.cdf(-dd))}


def equity_vol(prices: list[float]) -> float | None:
    p = np.asarray([x for x in prices if x and x > 0], float)
    if len(p) < 120:
        return None
    r = np.diff(np.log(p[-253:]))
    return float(r.std(ddof=1) * math.sqrt(252))


def verdict(price: float | None, fair: float | None) -> tuple[str, float | None]:
    v = load("analyzer")["verdict"]
    if not price or fair is None:
        return "No verdict", None
    up = fair / price - 1
    return ("Undervalued" if up >= v["undervalued"] else "Overvalued" if up <= v["overvalued"] else "Fairly valued"), up


def fcff_projection(p: Projection) -> list[float]:
    return p.rows["fcff"][p.n_hist:]
