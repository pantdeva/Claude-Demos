"""Offline tests for Milestone 4 (Module 13 model and valuation).

Run from the "Stock Finder and Analyzer" folder:  python tests/test_analyzer.py
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sfa.analyzer import valuation as V  # noqa: E402
from sfa.analyzer.model import assumptions, project  # noqa: E402
from sfa.analyzer.statements import Statements  # noqa: E402


def raw_company(years=4, rev0=1000.0, growth=0.10):
    raw = {"_ccy": "INR"}
    ys = [f"{2022 + i}-03-31" for i in range(years)]
    for i, y in enumerate(ys):
        rev = rev0 * (1 + growth) ** i
        vals = {"TotalRevenue": rev, "CostOfRevenue": 0.6 * rev, "EBITDA": 0.2 * rev, "EBIT": 0.15 * rev,
                "ReconciledDepreciation": 0.05 * rev, "InterestExpense": 8.0, "PretaxIncome": 0.15 * rev - 8,
                "TaxProvision": 0.25 * (0.15 * rev - 8), "NetIncome": 0.75 * (0.15 * rev - 8),
                "Inventory": 0.6 * rev * 60 / 365, "AccountsReceivable": rev * 45 / 365,
                "AccountsPayable": 0.6 * rev * 30 / 365, "CashAndCashEquivalents": 100.0 + 10 * i,
                "NetPPE": rev / 2.0, "TotalDebt": 100.0, "StockholdersEquity": 600.0 + 50 * i,
                "TotalAssets": 1200.0 + 120 * i, "CapitalExpenditure": -0.08 * rev, "CashDividendsPaid": -20.0,
                "OrdinarySharesNumber": 100.0, "CurrentAssets": 400.0, "OperatingCashFlow": 0.17 * rev}
        for k, v in vals.items():
            raw.setdefault(k, {})[y] = v
    return raw


def test_statements_derive_and_usable():
    st = Statements(raw_company())
    assert st.usable() == (True, "ok") and st.ccy == "INR" and len(st.years) == 4
    assert st.last("shares") == 100.0 and not st.is_financial_layout


def test_assumptions_recover_ratios():
    st = Statements(raw_company())
    a = assumptions(st, terminal_g=0.04, rf=0.07)
    assert abs(a.growth_start - 0.10) < 1e-9
    assert abs(a.ebitda_margin - 0.20) < 1e-9 and abs(a.asset_turnover - 2.0) < 1e-9
    assert abs(a.receivable_days - 45) < 3 and abs(a.inventory_days - 60) < 4 and abs(a.payable_days - 30) < 2
    assert abs(a.tax_rate - 0.25) < 1e-9 and 0.07 <= a.interest_rate <= 0.15


def test_projection_balances_and_fades_growth():
    st = Statements(raw_company())
    a = assumptions(st, terminal_g=0.04, rf=0.07)
    p = project(st, a)
    assert max(abs(x) for x in p.balance_diff) < 1e-6
    g = p.rows["growth"][p.n_hist:]
    assert abs(g[0] - 0.10) < 1e-9 and abs(g[-1] - 0.04) < 1e-9 and all(x >= y for x, y in zip(g, g[1:]))
    fc = p.rows["fcff"][p.n_hist:]
    assert all(f > 0 for f in fc)


def test_dcf_matches_hand_calculation():
    d = V.dcf([100, 110, 120], 0.10, 0.03, debt=200, cash=50, minority=0, shares=10)
    pv = 100 / 1.1 + 110 / 1.1 ** 2 + 120 / 1.1 ** 3
    tv = 120 * 1.03 / 0.07
    ev = pv + tv / 1.1 ** 3
    assert abs(d["ev"] - ev) < 1e-9 and abs(d["per_share"] - (ev - 150) / 10) < 1e-9


def test_sensitivity_monotone_and_guarded():
    grid = V.sensitivity([100, 110, 120], 0.065, 0.03, 0, 0, 0, 10)
    ws = sorted(grid)
    mid = [grid[w][0.02] for w in ws]
    assert all(a > b for a, b in zip(mid, mid[1:]))                # higher WACC → lower value
    assert grid[ws[0]][0.04] is None                                 # WACC − g below 2% is left blank


def test_wacc_market_weights_and_tax_shield():
    w, wd = V.wacc(ke=0.12, kd=0.08, tax=0.25, equity_value=800, debt=200)
    assert abs(wd - 0.2) < 1e-12 and abs(w - (0.8 * 0.12 + 0.2 * 0.08 * 0.75)) < 1e-12


def test_capm_and_beta():
    assert abs(V.capm(0.07, 1.2, 0.07) - 0.154) < 1e-12
    b, _ = V.adjusted_beta(1.5)
    assert abs(b - (0.67 * 1.5 + 0.33)) < 1e-12
    assert V.adjusted_beta(None)[0] == 1.0


def test_justified_pb():
    assert abs(V.justified_pb(0.18, 0.13, 0.04) - (0.14 / 0.09)) < 1e-12
    assert V.justified_pb(0.18, 0.04, 0.04) is None


def test_relative_uses_peer_medians_and_financial_subset():
    st = Statements(raw_company())
    peers = [{"pe": 10, "ev_ebitda": 6, "pb": 2, "ev_sales": 1}, {"pe": 12, "ev_ebitda": 7, "pb": 2.5, "ev_sales": 1.2},
             {"pe": 14, "ev_ebitda": 8, "pb": 3, "ev_sales": 1.4}]
    r = V.relative(st, peers, 100)
    assert set(k for k in r if k != "median_per_share") == {"pe", "ev_ebitda", "pb", "ev_sales"}
    assert abs(r["pe"]["per_share"] - 12 * st.last("pat") / 100) < 1e-9
    rf = V.relative(st, peers, 100, financial=True)
    assert set(k for k in rf if k != "median_per_share") == {"pe", "pb"}


def test_merton_recovers_inputs():
    from scipy import stats
    V0, sv, D, r = 1500.0, 0.25, 1000.0, 0.05
    d1 = (math.log(V0 / D) + (r + sv ** 2 / 2)) / sv
    E = V0 * stats.norm.cdf(d1) - D * math.exp(-r) * stats.norm.cdf(d1 - sv)
    se = stats.norm.cdf(d1) * sv * V0 / E
    m = V.merton(E, se, D, r)
    assert abs(m["asset_value"] - V0) < 1 and abs(m["asset_vol"] - sv) < 1e-3 and m["distance_to_default"] > 1


def test_verdict_thresholds():
    assert V.verdict(100, 120)[0] == "Undervalued"
    assert V.verdict(100, 80)[0] == "Overvalued"
    assert V.verdict(100, 105)[0] == "Fairly valued"
    assert V.verdict(None, 100)[0] == "No verdict"


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
