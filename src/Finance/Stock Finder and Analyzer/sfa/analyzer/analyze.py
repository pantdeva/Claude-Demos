"""Stage 2: analyse one company end to end.

1. Categorise with the Stage 0 tags (market class, listing structure, sector group,
   cap band, style, cyclical/defensive).
2. Short-term and 1-year growth from the Milestone 2 chosen model; long-term growth
   from the Module 13 projection (5-year revenue and EPS CAGR).
3. Module 13 integrated model and DCF (or the bank model), peer multiples and the
   option-based check; a combined fair value and verdict against the market price.
"""

from __future__ import annotations

import json
import math

from ..classify import market as M
from ..config import load, venues
from ..data import longrates, yahoo
from ..db import now, set_tag
from ..finder.peers import peers_for
from . import valuation as V
from .model import assumptions, project
from .statements import Statements, fetch

SCHEMA = """CREATE TABLE IF NOT EXISTS valuations (
    company_id INTEGER, method TEXT, fair_value REAL, market_price REAL, currency TEXT,
    detail TEXT, as_of TEXT, PRIMARY KEY (company_id, method, as_of))"""


def _tags(con, cid):
    return {r["tag"]: (r["value"], json.loads(r["detail"] or "{}")) for r in
            con.execute("SELECT tag, value, detail FROM stock_tags WHERE company_id=?", (cid,))}


def _price_series(con, symbol):
    return [r["adj_close"] for r in con.execute("SELECT adj_close FROM prices WHERE symbol=? ORDER BY date", (symbol,))]


def _fx_ratio(stmt_ccy: str | None, trade_ccy: str | None) -> float | None:
    """Trading-currency units per statement-currency unit (e.g. INR per USD; pence per GBP)."""
    a, b = yahoo.fx_to_usd(stmt_ccy or trade_ccy), yahoo.fx_to_usd(trade_ccy or stmt_ccy)
    return a / b if a and b else None


def company_context(con, symbol: str) -> dict | None:
    r = con.execute("""SELECT c.*, l.symbol AS listing FROM companies c JOIN listings l ON l.company_id=c.id
                       WHERE l.symbol=? OR c.home_symbol=? LIMIT 1""", (symbol, symbol)).fetchone()
    if r:
        c = dict(r)
        home = con.execute("SELECT * FROM listings WHERE company_id=? AND is_home=1", (c["id"],)).fetchone()
        t = _tags(con, c["id"])
        return {"company_id": c["id"], "name": c["name"], "symbol": home["symbol"], "currency": home["currency"],
                "country": c["home_country"], "venue": home["venue"], "sector": c["sector"], "industry": c["industry"],
                "statement_ccy": c["statement_ccy"], "tags": t, "price": home["last_price"],
                "prices": _price_series(con, home["symbol"]), "in_universe": True}
    # not in the universe (e.g. a new listing): build the context from Yahoo
    info = next((q for q in yahoo.search(symbol, n=5) if q["symbol"] == symbol), None)
    q = yahoo.last_quote(symbol)
    if not q:
        return None
    v = venues().resolve(symbol, (info or {}).get("exchange")) or {}
    ch = yahoo.chart(symbol, start=0) or {}
    ctry = v.get("country")
    return {"company_id": None, "name": q.get("longName") or symbol, "symbol": symbol, "currency": q.get("currency"),
            "country": ctry, "venue": v.get("id"), "sector": (info or {}).get("sector"),
            "industry": (info or {}).get("industry"), "statement_ccy": None,
            "tags": {"market_class": (M.CLASSES[M.current_class(ctry)] if ctry else None, {})}, "price": q.get("price"),
            "prices": [x for x in (ch.get("adj") or []) if x], "in_universe": False}


def analyze(con, symbol: str) -> dict:
    con.execute(SCHEMA)
    cfg = load("analyzer")
    ctx = company_context(con, symbol)
    if ctx is None:
        return {"symbol": symbol, "error": "symbol not found"}
    out = {"symbol": ctx["symbol"], "name": ctx["name"], "country": ctx["country"], "currency": ctx["currency"],
           "as_of": now()[:10], "flags": []}
    t = ctx["tags"]
    out["classification"] = {k: (t.get(k) or (None,))[0] for k in (
        "market_class", "market_class_ftse", "listing_structure", "sector_group", "gics_sector", "cap_band",
        "cap_band_sebi", "growth_value", "cyclical_defensive", "share_type", "news_composite", "news_verdict")}
    mc = out["classification"]["market_class"]
    for tag, lbl in (("growth_3m", "3 months"), ("growth_1y", "1 year")):
        g = t.get(tag)
        if g:
            out.setdefault("growth", {})[lbl] = {"expected": float(g[0]), "model": g[1].get("model"),
                                                 "range_5_95": g[1].get("range_5_95"), "p_beat_cash": g[1].get("p_beat_cash")}
    raw = fetch(ctx["symbol"])
    st = Statements(raw)
    ok, why = st.usable()
    if not ok:
        out["error"] = f"statements not usable: {why}"
        return out
    stmt_ccy = st.ccy or ctx["statement_ccy"] or ctx["currency"]
    k = _fx_ratio(stmt_ccy, ctx["currency"])
    price = ctx["price"] or (ctx["prices"][-1] if ctx["prices"] else None)
    shares = st.last("shares")
    if not price or not k:
        out["error"] = "no market price or exchange rate"
        return out
    price_stmt = price / k                                  # market price in statement currency
    mcap = price_stmt * shares
    out.update({"price": price, "statement_ccy": stmt_ccy, "fx_trade_per_stmt": k, "shares": shares,
                "market_cap_stmt": mcap, "years": st.years, "notes": dict(st.notes)})
    # cost of capital
    rf, rf_src = longrates.risk_free(ctx["country"])
    erp, erp_src = longrates.equity_risk_premium(ctx["country"], mc)
    beta_raw = float(t["beta"][0]) if t.get("beta") and t["beta"][0] not in (None, "None") else None
    beta, beta_src = V.adjusted_beta(beta_raw)
    ke = V.capm(rf, beta, erp)
    g_target, g_src = longrates.terminal_growth(ctx["country"])
    g = min(g_target, rf)
    a = assumptions(st, g, rf)
    kd = a.interest_rate
    debt, cash, minority = st.last("debt") or 0.0, st.last("cash") or 0.0, st.last("minority") or 0.0
    w, wd = V.wacc(ke, kd, a.tax_rate, mcap, debt)
    fin = st.is_financial_layout or out["classification"]["sector_group"] == "Financials & Banking"
    if "bounded" in beta_src:
        out["flags"].append(f"beta {beta_src}: the local-index beta looks too low or high for CAPM")
    if wd > 0.5 and not fin:
        out["flags"].append(f"debt is {wd:.0%} of capital (captive finance, leasing or distress?): WACC and the DCF "
                            "are unreliable; lean on the relative value")
    gap = cfg["wacc"]["min_wacc_minus_g"]
    if w - g < gap:
        g = w - gap
        out["flags"].append(f"terminal growth lowered to {g:.1%} to keep WACC − g ≥ {gap:.0%}")
    if "approximate" in rf_src:
        out["flags"].append(f"risk-free rate is an approximation ({rf:.1%}); check it")
    if "stand-in" in erp_src:
        out["flags"].append("equity risk premium is a stand-in until Damodaran's country file is reachable")
    out["cost_of_capital"] = {"rf": rf, "rf_source": rf_src, "erp": erp, "erp_source": erp_src, "beta": beta,
                              "beta_source": beta_src, "ke": ke, "kd_pre_tax": kd, "kd_after_tax": kd * (1 - a.tax_rate),
                              "tax_rate": a.tax_rate, "debt_weight": wd, "wacc": w, "g": g, "g_source": g_src}
    p = project(st, a)
    out["assumptions"] = a.table()
    out["projection"] = {"years": p.years, "rows": p.rows, "n_hist": p.n_hist, "balance_diff": p.balance_diff}
    rev = p.rows["revenue"]
    eps = p.rows["eps"]
    n = len(rev) - p.n_hist
    out["long_term_growth"] = {
        "revenue_cagr_5y": (rev[-1] / rev[p.n_hist - 1]) ** (1 / n) - 1 if rev[p.n_hist - 1] else None,
        "eps_cagr_5y": ((eps[-1] / eps[p.n_hist - 1]) ** (1 / n) - 1) if eps[p.n_hist - 1] and eps[p.n_hist - 1] > 0
        and eps[-1] and eps[-1] > 0 else None}
    methods = {}
    if fin:
        b = V.bank_value(st, ke, g, shares)
        if b:
            methods["bank_pb"] = {**b, "per_share_trade": b["per_share"] * k}
        out["flags"].append("financial company: valued with justified P/B = (ROE − g)/(Ke − g), not FCFF")
    else:
        fc = V.fcff_projection(p)
        if fc[-1] <= 0 or sum(fc) <= 0:
            out["flags"].append("projected free cash flow is negative: DCF not meaningful")
        else:
            d = V.dcf(fc, w, g, debt, cash, minority, shares)
            d["per_share_trade"] = d["per_share"] * k
            d["sensitivity"] = {wk: {gk: (v * k if v is not None else None) for gk, v in row.items()}
                                for wk, row in V.sensitivity(fc, w, g, debt, cash, minority, shares).items()}
            methods["dcf"] = d
            if d["terminal_share_of_ev"] and d["terminal_share_of_ev"] > 0.85:
                out["flags"].append(f"terminal value is {d['terminal_share_of_ev']:.0%} of EV: highly sensitive to WACC and g")
    # relative valuation
    peers = peers_for(con, ctx["industry"], ctx["sector"], mc, k=load("analyzer")["relative"]["peers"] + 1)
    peer_rows = []
    for pr in peers:
        if pr["symbol"] == ctx["symbol"] or not pr["mcap"]:
            continue
        pst = Statements(fetch(pr["symbol"]))
        if not pst.usable()[0]:
            continue
        fx = yahoo.fx_to_usd(pst.ccy)
        if not fx:
            continue
        mult = V.multiples(pr["mcap"] / fx, pst)
        if mult:
            peer_rows.append({"name": pr["name"], "symbol": pr["symbol"], **mult})
    out["peers"] = peer_rows
    rel = V.relative(st, peer_rows, shares, financial=fin)
    if rel.get("median_per_share"):
        rel["per_share_trade"] = rel["median_per_share"] * k
        methods["relative"] = rel
    out["own_multiples"] = V.multiples(mcap, st)
    # option-based check
    lev = debt / mcap if mcap else 0
    if lev >= cfg["option_check"]["leverage_trigger"] or (st.last("ebitda") or 0) < 0:
        mo = V.merton(mcap, V.equity_vol(ctx["prices"]), debt, rf, cfg["option_check"]["horizon_years"])
        if mo:
            methods["option_merton"] = mo
            if mo["distance_to_default"] < 2:
                out["flags"].append(f"Merton distance to default {mo['distance_to_default']:.1f}: equity trades like an option on the assets")
    out["valuations"] = methods
    # combined fair value (trading currency)
    parts = [(0.5, methods[m]["per_share_trade"]) for m in ("dcf", "bank_pb") if m in methods]
    if "relative" in methods:
        parts.append((0.5, methods["relative"]["per_share_trade"]))
    parts = [(wt, v) for wt, v in parts if v is not None and math.isfinite(v) and v > 0]
    fair = sum(wt * v for wt, v in parts) / sum(wt for wt, _ in parts) if parts else None
    out["fair_value"] = fair
    out["verdict"], out["upside"] = V.verdict(price, fair)
    if ctx["company_id"]:
        _store(con, ctx["company_id"], out)
    return out


def _store(con, cid, out):
    day = out["as_of"]
    for m, v in out["valuations"].items():
        fv = v.get("per_share_trade")
        con.execute("INSERT OR REPLACE INTO valuations VALUES (?,?,?,?,?,?,?)",
                    (cid, m, fv, out["price"], out["currency"], json.dumps(
                        {k: v[k] for k in v if k not in ("sensitivity", "discount_factors", "pv_fcff")}, default=float), day))
    con.execute("INSERT OR REPLACE INTO valuations VALUES (?,?,?,?,?,?,?)",
                (cid, "combined", out["fair_value"], out["price"], out["currency"],
                 json.dumps({"verdict": out["verdict"], "upside": out["upside"], "flags": out["flags"]}), day))
    set_tag(con, cid, "valuation", "fair_value", None if out["fair_value"] is None else round(out["fair_value"], 4),
            {"currency": out["currency"], "price": out["price"], "methods": list(out["valuations"])}, day)
    set_tag(con, cid, "valuation", "valuation_upside", None if out["upside"] is None else round(out["upside"], 4), {}, day)
    set_tag(con, cid, "valuation", "valuation_verdict", out["verdict"], {"flags": out["flags"]}, day)
    con.commit()
