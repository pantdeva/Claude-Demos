"""Module 13 integrated financial model: assumptions (Ch 4–5), revenue model (Ch 6),
asset / capex / depreciation schedule (Ch 7–8), debt schedule (Ch 9), reserves
schedule (Ch 10–11), projected P&L and balance sheet (Ch 12) and the indirect cash
flow statement (Ch 13), with a balance check every year.

Ratios use the rolling average of the last `margin_years` reported years. Items the
model does not drive ("other" assets and liabilities) are held at their last values,
so the balance sheet keeps balancing as long as the cash flow is consistent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..config import load
from .statements import Statements


def _avg(xs):
    xs = [x for x in xs if x is not None and math.isfinite(x)]
    return sum(xs) / len(xs) if xs else None


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


@dataclass
class Assumptions:
    growth_start: float
    growth_terminal: float
    ebitda_margin: float
    da_rate: float                 # D&A as % of opening net block
    asset_turnover: float          # revenue ÷ net block
    cogs_ratio: float
    inventory_days: float
    receivable_days: float
    payable_days: float
    tax_rate: float
    payout: float
    interest_rate: float           # pre-tax cost of debt in the P&L
    notes: dict = field(default_factory=dict)

    def table(self) -> list[tuple[str, float, str]]:
        n = self.notes
        return [("Revenue growth, year 1", self.growth_start, n.get("growth", "")),
                ("Revenue growth, last year (terminal)", self.growth_terminal, n.get("terminal", "")),
                ("EBITDA margin", self.ebitda_margin, n.get("margin", "")),
                ("Depreciation, % of opening net block", self.da_rate, n.get("da", "")),
                ("Asset turnover (revenue ÷ net block)", self.asset_turnover, n.get("turnover", "")),
                ("Cost of revenue, % of revenue", self.cogs_ratio, n.get("cogs", "")),
                ("Inventory days (on cost of revenue)", self.inventory_days, n.get("days", "")),
                ("Receivable days (on revenue)", self.receivable_days, n.get("days", "")),
                ("Payable days (on cost of revenue)", self.payable_days, n.get("days", "")),
                ("Tax rate", self.tax_rate, n.get("tax", "")),
                ("Dividend payout", self.payout, n.get("payout", "")),
                ("Interest rate on debt", self.interest_rate, n.get("interest", ""))]


def assumptions(st: Statements, terminal_g: float, rf: float) -> Assumptions:
    cfg = load("analyzer")
    a = cfg["assumptions"]
    k = a["margin_years"]
    d = [st.d[y] for y in st.years]
    recent = d[-k:]
    notes = {}
    rev = [r["revenue"] for r in d]
    n = len(rev)
    if a["growth"]["recent"] == "cagr" and rev[0] and rev[0] > 0 and rev[-1] > 0:
        g0 = (rev[-1] / rev[0]) ** (1 / (n - 1)) - 1
        notes["growth"] = f"{n - 1}-year revenue CAGR"
    else:
        g0 = _avg([b / a_ - 1 for a_, b in zip(rev, rev[1:]) if a_]) or 0.0
        notes["growth"] = "average yearly revenue growth"
    lo, hi = a["growth"]["cap"]
    if not lo <= g0 <= hi:
        notes["growth"] += f" (capped from {g0:.1%})"
    g0 = _clip(g0, lo, hi)
    notes["terminal"] = "fades linearly to terminal growth (long-run inflation)"
    m = _avg([r["ebitda"] / r["revenue"] for r in recent if r["ebitda"] is not None and r["revenue"]])
    notes["margin"] = f"{len(recent)}-year average"
    if m is None:
        m = _avg([(r["pat"] or 0) / r["revenue"] for r in recent if r["revenue"]]) or 0.1
        notes["margin"] = "net margin stand-in (no EBITDA)"
    # asset schedule
    nb = [r["net_block"] for r in d]
    da_rates = [d[i]["da"] / nb[i - 1] for i in range(1, n) if d[i]["da"] and nb[i - 1]]
    da_rate = _avg(da_rates[-k:])
    notes["da"] = f"{min(k, len(da_rates))}-year average of D&A ÷ opening net block"
    if da_rate is None:
        da_rate = 0.10
        notes["da"] = "default 10% (no depreciation or block history)"
    da_rate = _clip(da_rate, 0.02, 0.5)
    to = _avg([r["revenue"] / r["net_block"] for r in recent if r["net_block"]])
    notes["turnover"] = f"{len(recent)}-year average"
    if not to:
        to, notes["turnover"] = 5.0, "default 5× (no net block)"
    to = _clip(to, 0.2, 50.0)
    # working capital (days)
    cogs = _avg([r["cogs"] / r["revenue"] for r in recent if r["cogs"] and r["revenue"]])
    notes["cogs"] = f"{len(recent)}-year average"
    if cogs is None:
        cogs = _clip(1 - m - 0.1, 0.2, 0.9)
        notes["cogs"] = "estimated from EBITDA margin (no cost-of-revenue line)"
    pairs = list(zip(d, d[1:]))[-k:] or [(d[-1], d[-1])]

    def days(item, base):
        vals = []
        for p, c in pairs:
            b = c["cogs"] if base == "cogs" and c["cogs"] else (c["revenue"] * cogs if base == "cogs" else c["revenue"])
            if b:
                vals.append(((p[item] or 0) + (c[item] or 0)) / 2 / b * 365)
        return _clip(_avg(vals) or 0.0, 0.0, 365.0)
    inv_d, rec_d, pay_d = days("inventory", "cogs"), days("receivables", "revenue"), days("payables", "cogs")
    notes["days"] = "average balance ÷ annual flow × 365 (Module 13 Ch 5)"
    # tax, payout, interest
    tr = [r["tax"] / r["pbt"] for r in recent if r["tax"] is not None and r["pbt"] and r["pbt"] > 0]
    tlo, thi = a["tax_rate_bounds"]
    tax = _avg(tr)
    notes["tax"] = f"{len(tr)}-year effective rate"
    if tax is None:
        tax, notes["tax"] = a["tax_rate_default"], "default (no positive pre-tax income)"
    tax = _clip(tax, tlo, thi)
    po = _avg([r["dividends"] / r["pat"] for r in recent if r["pat"] and r["pat"] > 0])
    notes["payout"] = f"{len(recent)}-year average dividends ÷ profit"
    po = _clip(po if po is not None else 0.3, *a["payout_bounds"])
    debts = [r["debt"] for r in d]
    ir = [d[i]["interest"] / ((debts[i] + debts[i - 1]) / 2) for i in range(1, n)
          if debts[i] and debts[i - 1] and d[i]["interest"]]
    w = cfg["wacc"]
    ir_v = _avg(ir[-k:])
    lo_, hi_ = w["cost_of_debt_bounds_over_rf"]
    if ir_v is None:
        ir_v, notes["interest"] = rf + w["cost_of_debt_spread"], "risk-free + spread (no usable interest history)"
    else:
        notes["interest"] = "interest ÷ average debt"
        if not rf + lo_ <= ir_v <= rf + hi_:
            notes["interest"] += f" (bounded from {ir_v:.1%})"
    ir_v = _clip(ir_v, rf + lo_, rf + hi_)
    return Assumptions(g0, terminal_g, m, da_rate, to, cogs, inv_d, rec_d, pay_d, tax, po, ir_v, notes)


@dataclass
class Projection:
    years: list[str]
    rows: dict[str, list[float]]            # line → values for history + projection
    n_hist: int
    balance_diff: list[float]


LINES = ["revenue", "growth", "ebitda", "da", "ebit", "interest", "pbt", "tax", "pat", "dividends",
         "net_block", "capex", "inventory", "receivables", "payables", "nwc", "delta_nwc", "debt", "equity", "cash",
         "other_assets", "other_liabilities", "total_assets", "total_liabilities_equity", "cfo", "cfi", "cff",
         "fcff", "eps", "shares"]


def project(st: Statements, a: Assumptions, years: int | None = None) -> Projection:
    N = years or load("analyzer")["projection_years"]
    hist = [st.d[y] for y in st.years]
    rows = {k: [] for k in LINES}
    last = hist[-1]
    shares = st.last("shares")
    # history
    prev = None
    for r in hist:
        nwc = (r["inventory"] or 0) + (r["receivables"] or 0) - (r["payables"] or 0)
        ta = r["total_assets"]
        oa = ta - (r["cash"] + (r["inventory"] or 0) + (r["receivables"] or 0) + (r["net_block"] or 0)) if ta else 0.0
        ol = (ta - (r["equity"] or 0) - (r["debt"] or 0) - (r["payables"] or 0)) if ta else 0.0
        vals = {"revenue": r["revenue"], "growth": (r["revenue"] / prev["revenue"] - 1) if prev and prev["revenue"] else None,
                "ebitda": r["ebitda"], "da": r["da"], "ebit": r["ebit"], "interest": r["interest"], "pbt": r["pbt"],
                "tax": r["tax"], "pat": r["pat"], "dividends": r["dividends"], "net_block": r["net_block"],
                "capex": r["capex"], "inventory": r["inventory"], "receivables": r["receivables"],
                "payables": r["payables"], "nwc": nwc, "delta_nwc": None if prev is None else nwc - rows["nwc"][-1],
                "debt": r["debt"], "equity": r["equity"], "cash": r["cash"], "other_assets": oa,
                "other_liabilities": ol, "total_assets": ta, "total_liabilities_equity": ta, "cfo": r["cfo"],
                "cfi": -r["capex"] if r["capex"] is not None else None, "cff": None, "fcff": None,
                "eps": (r["pat"] / shares) if r["pat"] is not None and shares else None, "shares": r["shares"]}
        if r["ebit"] is not None and r["da"] is not None and r["capex"] is not None and vals["delta_nwc"] is not None:
            vals["fcff"] = r["ebit"] * (1 - a.tax_rate) + r["da"] - r["capex"] - vals["delta_nwc"]
        for k in LINES:
            rows[k].append(vals[k])
        prev = r
    # projection
    rev, nb = last["revenue"], last["net_block"] if last["net_block"] else last["revenue"] / a.asset_turnover
    nwc_prev = rows["nwc"][-1]
    debt = last["debt"] or 0.0
    equity, cash = last["equity"] or 0.0, last["cash"] or 0.0
    oa, ol = rows["other_assets"][-1] or 0.0, rows["other_liabilities"][-1] or 0.0
    diffs = []
    labels = list(st.years)
    y0 = int(st.years[-1][:4])
    for t in range(1, N + 1):
        g = a.growth_start + (a.growth_terminal - a.growth_start) * (t - 1) / max(N - 1, 1)
        rev = rev * (1 + g)
        ebitda = a.ebitda_margin * rev
        da = a.da_rate * nb
        nb_new = rev / a.asset_turnover
        capex = max(0.0, nb_new - nb + da)
        nb_new = nb + capex - da                      # if capex floored at 0, block shrinks by D&A
        ebit = ebitda - da
        interest = a.interest_rate * debt             # debt held flat (Ch 9)
        pbt = ebit - interest
        tax = a.tax_rate * max(pbt, 0.0)
        pat = pbt - tax
        div = a.payout * max(pat, 0.0)
        cogs = a.cogs_ratio * rev
        inv, rec, pay = a.inventory_days / 365 * cogs, a.receivable_days / 365 * rev, a.payable_days / 365 * cogs
        nwc = inv + rec - pay
        dnwc = nwc - nwc_prev
        cfo = pat + da - dnwc
        cfi = -capex
        cff = -div
        cash = cash + cfo + cfi + cff
        equity = equity + pat - div
        ta = cash + inv + rec + nb_new + oa
        tle = pay + ol + debt + equity
        diffs.append(ta - tle)
        fcff = ebit * (1 - a.tax_rate) + da - capex - dnwc
        vals = {"revenue": rev, "growth": g, "ebitda": ebitda, "da": da, "ebit": ebit, "interest": interest, "pbt": pbt,
                "tax": tax, "pat": pat, "dividends": div, "net_block": nb_new, "capex": capex, "inventory": inv,
                "receivables": rec, "payables": pay, "nwc": nwc, "delta_nwc": dnwc, "debt": debt, "equity": equity,
                "cash": cash, "other_assets": oa, "other_liabilities": ol, "total_assets": ta,
                "total_liabilities_equity": tle, "cfo": cfo, "cfi": cfi, "cff": cff, "fcff": fcff,
                "eps": pat / shares if shares else None, "shares": shares}
        for k in LINES:
            rows[k].append(vals[k])
        nb, nwc_prev = nb_new, nwc
        labels.append(f"{y0 + t}E")
    # the historical "other" plug makes year 0 balance; projections must stay balanced
    return Projection(labels, rows, len(st.years), diffs)
