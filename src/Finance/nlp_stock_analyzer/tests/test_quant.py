"""Offline checks for the quant models: each recovers known parameters from simulated data.

Run from the project folder:  python -m unittest discover -s tests
"""

import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stock_analyzer.quant import (ARIMA, GARCH, GBM, BootstrapMC, BSMRiskNeutral,  # noqa: E402
                                  MertonJump, bsm_price, implied_vol, mean_variance_weights)
from stock_analyzer.quant.backtest import Backtest, crps_samples, load_fred, load_stooq  # noqa: E402


class TestBSM(unittest.TestCase):
    def test_textbook_values_and_parity(self):
        c = bsm_price(100, 100, 1, 0.05, 0.2, "call")
        p = bsm_price(100, 100, 1, 0.05, 0.2, "put")
        self.assertAlmostEqual(c, 10.4506, places=4)
        self.assertAlmostEqual(p, 5.5735, places=4)
        self.assertAlmostEqual(c - p, 100 - 100 * math.exp(-0.05), places=8)
        self.assertAlmostEqual(implied_vol(c, 100, 100, 1, 0.05), 0.2, places=6)

    def test_risk_neutral_forecast_drifts_at_cash(self):
        rng = np.random.default_rng(0)
        m = BSMRiskNeutral().fit(rng.normal(0.002, 0.02, 1000), rf=0.04)
        f = m.forecast(252, 40000)
        self.assertAlmostEqual(f.exp_return, math.exp(0.04) - 1, delta=0.01)


class TestModels(unittest.TestCase):
    def test_garch_recovers_parameters(self):
        rng = np.random.default_rng(1)
        n, mu, om, a, b, nu = 3000, 0.0005, 2e-6, 0.08, 0.90, 6
        e, h = np.zeros(n), np.zeros(n)
        h[0] = om / (1 - a - b)
        z = rng.standard_t(nu, n) * math.sqrt((nu - 2) / nu)
        for t in range(n):
            if t:
                h[t] = om + a * e[t - 1] ** 2 + b * h[t - 1]
            e[t] = math.sqrt(h[t]) * z[t]
        g = GARCH().fit(mu + e)
        self.assertAlmostEqual(g.alpha, a, delta=0.03)
        self.assertAlmostEqual(g.beta, b, delta=0.03)
        # simulated 63-day variance matches the analytic term structure
        p, lr = g.alpha + g.beta, g.omega / (1 - g.alpha - g.beta)
        analytic = sum(lr + p ** k * (g.h_next - lr) for k in range(63))
        self.assertAlmostEqual(g.forecast(63, 20000).samples.var() / analytic, 1.0, delta=0.08)

    def test_arima_recovers_arma11(self):
        rng = np.random.default_rng(10)
        n, c, phi, th = 8000, 0.0004, 0.5, -0.3
        eps = rng.normal(0, 0.02, n)
        r = np.zeros(n)
        for t in range(1, n):
            r[t] = c + phi * (r[t - 1] - c) + eps[t] + th * eps[t - 1]
        m = ARIMA(orders=((1, 1),)).fit(r)
        self.assertAlmostEqual(m.coef[1], phi, delta=0.06)
        self.assertAlmostEqual(m.coef[2], th, delta=0.06)

    def test_arima_random_walk_variance(self):
        w = np.random.default_rng(2).normal(0, 0.02, 4000)
        f = ARIMA(orders=((0, 0),)).fit(w).forecast(63, 20000)
        self.assertAlmostEqual(f.samples.std(), w.std() * math.sqrt(63), delta=0.004)

    def test_merton_finds_jumps(self):
        rng = np.random.default_rng(1)
        n, m, sd, lam, muJ, sJ = 3000, 0.0008, 0.015, 0.02, -0.05, 0.06
        nj = rng.poisson(lam, n)
        x = m + sd * rng.standard_normal(n) + nj * muJ + np.sqrt(nj) * sJ * rng.standard_normal(n)
        j = MertonJump().fit(x)
        self.assertAlmostEqual(j.lam, lam, delta=0.01)
        self.assertLess(j.muJ, 0)
        self.assertAlmostEqual(j.s, sd, delta=0.002)

    def test_gbm_and_bootstrap_means(self):
        x = np.random.default_rng(3).normal(0.001, 0.02, 3000)
        self.assertAlmostEqual(GBM().fit(x).forecast(63, 20000).mean_log, 63 * x.mean(), delta=0.006)
        self.assertAlmostEqual(BootstrapMC().fit(x).forecast(63, 20000).mean_log, 63 * x.mean(), delta=0.006)

    def test_mean_variance_long_only(self):
        w = mean_variance_weights(np.array([0.3, 0.1]), np.array([[0.25, 0.05], [0.05, 0.04]]), 0.03, 3)
        self.assertTrue(np.all(w >= -1e-9) and w.sum() <= 1 + 1e-9)
        # unconstrained optimum here is inside the box: w = inv(S)(mu - rf)/gamma
        exact = np.linalg.solve(np.array([[0.25, 0.05], [0.05, 0.04]]), np.array([0.27, 0.07])) / 3
        np.testing.assert_allclose(w, exact, atol=1e-3)

    def test_crps(self):
        x = np.random.default_rng(4).normal(0, 1, 1000)
        # CRPS of N(0,1) at y=0 is about 0.2337
        self.assertAlmostEqual(crps_samples(x, 0.0), 0.2337, delta=0.02)


class TestBacktest(unittest.TestCase):
    def test_runs_without_lookahead(self):
        rng = np.random.default_rng(0)
        n = 900
        idx = pd.bdate_range("2015-01-01", periods=n)
        nv = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.001, 0.025, n))), idx)
        sp = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n))), idx)
        bt = Backtest(nv, sp, pd.Series(0.02, idx), horizons={"3 months": 63}, window=500, step=63, n_sims=300)
        res = bt.run()
        hz = res["horizons"]["3 months"]
        names = {s["model"] for s in hz["strategies"]}
        self.assertIn("MPT (mean-variance)", names)
        self.assertIn("Buy & hold NVDA", names)
        # the last origin's realised return must be NaN when its horizon runs past the data
        last = bt.table[bt.table.model == "GBM"].iloc[-1]
        self.assertTrue(math.isnan(last.realized_log) or bt.px.index.get_loc(last.origin) + 63 < n)
        cf = bt.current_forecasts()
        self.assertEqual(len(cf["models"]), 6)
        self.assertAlmostEqual(cf["options"][0]["implied_vol_check"], cf["options"][0]["vol_used"], places=6)

    def test_loaders(self):
        st = "Date,Open,High,Low,Close,Volume\n2020-01-02,1,1,1,10,5\n2020-01-03,1,1,1,11,5\n"
        self.assertEqual(list(load_stooq(st)), [10.0, 11.0])
        fr = "observation_date,DTB3\n2020-01-02,1.50\n2020-01-03,.\n"
        self.assertEqual(list(load_fred(fr)), [0.015, 0.015])


if __name__ == "__main__":
    unittest.main()
