"""Offline tests for Milestone 2 (models, scoring, leaderboard rules).

Run from the "Stock Finder and Analyzer" folder:  python tests/test_models.py
"""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sfa.models import leaderboard as LB  # noqa: E402
from sfa.models import portfolio as PF  # noqa: E402
from sfa.models import walkforward as WF  # noqa: E402
from sfa.models import zoo  # noqa: E402


def _gjr_sim(n=5000, mu=0.0003, om=2e-6, a=0.03, g=0.10, b=0.88, nu=6.0, seed=3):
    rng = np.random.default_rng(seed)
    h = om / (1 - a - g / 2 - b)
    r, e = np.empty(n), 0.0
    for t in range(n):
        if t:
            h = om + (a + g * (e < 0)) * e * e + b * h
        e = math.sqrt(h) * rng.standard_t(nu) * math.sqrt((nu - 2) / nu)
        r[t] = mu + e
    return r


def test_gjr_recovers_leverage_effect():
    m = zoo.GJRGARCH().fit(_gjr_sim())
    p = m.params
    assert 0.06 < p["gamma"] < 0.16 and 0.83 < p["beta"] < 0.93 and p["persistence"] < 1
    assert 4 < p["nu"] < 9


def test_gjr_forecast_spread_matches_variance():
    m = zoo.GJRGARCH().fit(_gjr_sim())
    f = m.forecast(63, 4000, seed=1)
    assert np.isfinite(f.samples).all() and 0.03 < f.samples.std() < 0.2


def test_shrink_weight():
    w = zoo.shrink_weight(0.30, 5, 0.05)
    assert abs(w - 0.0025 / (0.0025 + 0.018)) < 1e-12
    assert zoo.shrink_weight(0.30, 100, 0.05) > zoo.shrink_weight(0.30, 5, 0.05)


def test_ewma_drift_is_pulled_to_prior():
    rng = np.random.default_rng(0)
    r = rng.normal(0.004, 0.02, 1260)            # ~100%/yr historical drift
    m = zoo.EWMAShrunk(erp=0.05).fit(r, 0.03)
    assert 0.08 < m.mu < 0.40                     # pulled most of the way to rf + ERP = 8%
    assert abs(m.params["sigma_annual"] - 0.02 * math.sqrt(252)) < 0.08


def test_random_walk_is_martingale():
    f = zoo.RandomWalk().fit(np.random.default_rng(0).normal(0, 0.02, 1260)).forecast(252, 20000, seed=2)
    assert abs(f.exp_return) < 0.02


def test_all_models_fit_and_forecast():
    r = np.random.default_rng(5).standard_t(5, 1300) * 0.012
    for mid in zoo.model_ids():
        f = zoo.make(mid).fit(r, 0.03).forecast(63, 500, seed=0)
        assert np.isfinite(f.samples).all(), mid


def test_crps_known_values():
    x = np.random.default_rng(0).normal(0, 1, 20000)
    assert abs(WF.crps_samples(x, 0.0) - (math.sqrt(2) - 1) / math.sqrt(math.pi)) < 0.01   # N(0,1) at 0 ≈ 0.2337
    assert WF.crps_samples(x, 3.0) > WF.crps_samples(x, 0.0)


def test_origin_grid_first_trading_day():
    idx = pd.bdate_range("2009-06-01", "2012-12-31")
    pos = WF.origin_grid(idx, "2010-01-01", 126)
    days = [idx[p] for p in pos]
    assert days[0] == pd.Timestamp("2010-01-01") and days[1] == pd.Timestamp("2010-07-01")
    assert all(d.month in (1, 7) for d in days)


def test_clean_prices_drops_reversing_spike():
    px = pd.Series([100, 101, 300, 102, 103.0], index=pd.bdate_range("2020-01-01", periods=5))
    assert 300 not in WF.clean_prices(px).values


def test_dm_stat():
    rng = np.random.default_rng(0)
    assert LB.dm_stat(rng.normal(0.5, 1, 60), 0) > 2.5
    assert abs(LB.dm_stat(rng.normal(0.0, 1, 400), 1)) < 2.5
    assert math.isnan(LB.dm_stat(np.array([1.0, 2.0]), 0))


def test_baseline_rule():
    assert LB.baseline_for("3 months", "Emerging") == "gjr"
    assert LB.baseline_for("3 months", "Developed") == "ewma"
    assert LB.baseline_for("1 year", "Emerging") == "ewma"


def _rows(adv, n_orig=20, n_stock=6, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for o in range(n_orig):
        for s in range(n_stock):
            base = abs(rng.normal(0.1, 0.02))
            for m, loss in (("ewma", base), ("arima", base - adv + rng.normal(0, 0.005)),
                            ("gbm", base + rng.normal(0, 0.02))):
                rows.append({"company_id": s, "origin": f"{2010 + o // 2}-{'01' if o % 2 == 0 else '07'}-0{1 + s % 3}",
                             "model": m, "crps": loss, "hit": 1, "cover90": 1, "err": 0.0})
    return rows


def test_promotion_requires_clear_win():
    stats, choice = LB.evaluate(_rows(adv=0.01), "ewma", 63)
    assert choice["selected"] == "arima" and "beats baseline" in choice["basis"]
    stats, choice = LB.evaluate(_rows(adv=0.0), "ewma", 63)
    assert choice["selected"] == "ewma"
    stats, choice = LB.evaluate(_rows(adv=0.01, n_orig=5), "ewma", 63)
    assert choice["selected"] == "ewma" and "only" in choice["basis"]


def test_bonferroni_threshold():
    assert abs(LB.threshold(8) - 2.734) < 0.01
    assert LB.threshold(1) == 1.96


def test_dates_matched_across_exchange_holidays():
    rows = _rows(adv=0.01)
    assert len({r["origin"] for r in rows}) > 20                  # day differs by exchange
    stats, _ = LB.evaluate(rows, "ewma", 63)
    assert next(s for s in stats if s["model"] == "arima")["n_origins"] == 20


def test_memmel_z_sign():
    rng = np.random.default_rng(0)
    b = rng.normal(0.01, 0.05, 80)
    a = b + 0.02 + rng.normal(0, 0.01, 80)
    assert PF.memmel_z(a, b) > 1.96 and PF.memmel_z(b, a) < -1.96


def test_erp_lookup():
    assert zoo.erp_for("IN", "Emerging")[0] == 0.0708
    assert zoo.erp_for("US", "Developed")[0] == 0.0423


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
