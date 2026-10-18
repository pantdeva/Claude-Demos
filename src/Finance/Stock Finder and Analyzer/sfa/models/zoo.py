"""All forecasting models used by the leaderboard, behind one interface:

    m = make(model_id, erp=0.05)
    m.fit(daily_log_returns, rf_annual)
    f = m.forecast(h_days, n_sims, seed)     # f.samples: simulated h-day log returns

The six models from the earlier quant work (GBM, Black-Scholes-Merton, GARCH(1,1)-t,
ARIMA, Merton jump-diffusion, bootstrap Monte Carlo) are reused unchanged from
src/Finance/nlp_stock_analyzer. Added here are the research baselines:

  rw     random walk: zero expected price change, sample volatility
  ewma   RiskMetrics EWMA volatility (lambda 0.94) with the drift shrunk towards
         rf + equity risk premium by precision weighting
  gjr    GJR-GARCH(1,1) with Student-t errors (volatility rises more after falls)
MPT is a portfolio rule, so it is compared with 1/N separately (portfolio.py).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from scipy import optimize, signal, special, stats

_QUANT = Path(__file__).resolve().parents[3] / "nlp_stock_analyzer"
if str(_QUANT) not in sys.path:
    sys.path.insert(0, str(_QUANT))

from stock_analyzer.quant.models import (ARIMA, GARCH, GBM, TRADING_DAYS, BootstrapMC,  # noqa: E402
                                         BSMRiskNeutral, Forecast, MertonJump)

from ..config import load  # noqa: E402


def _rng(seed):
    return np.random.default_rng(seed)


class RandomWalk:
    """Price is a martingale: E[S_h] = S_0. Log-return mean −σ²h/2, σ = sample vol."""

    name = "Random walk (zero drift)"

    def fit(self, r: np.ndarray, rf: float = 0.0):
        self.s = float(np.std(r, ddof=1))
        return self

    @property
    def params(self):
        return {"sigma_annual": self.s * math.sqrt(TRADING_DAYS)}

    def forecast(self, h: int, n: int = 2000, seed=0) -> Forecast:
        z = _rng(seed).standard_normal(n)
        return Forecast(self.name, h, -0.5 * self.s ** 2 * h + self.s * math.sqrt(h) * z)


def shrink_weight(sigma_annual: float, years: float, tau: float) -> float:
    """Weight on the historical mean: tau² / (tau² + σ²/T)."""
    se2 = sigma_annual ** 2 / max(years, 1e-9)
    return tau ** 2 / (tau ** 2 + se2)


class EWMAShrunk:
    """EWMA volatility; drift = w·historical + (1 − w)·(rf + ERP)."""

    name = "EWMA vol + shrunk drift"

    def __init__(self, erp: float = 0.0423, lam: float = 0.94, tau: float | None = None):
        self.erp, self.lam = erp, lam
        self.tau = tau if tau is not None else load("models")["shrinkage"]["tau_annual"]

    def fit(self, r: np.ndarray, rf: float = 0.0):
        var = float(np.var(r[:60]))
        x2 = r * r
        # var_t = lam var_{t-1} + (1-lam) r_t^2, as a linear filter
        var = signal.lfilter([1 - self.lam], [1, -self.lam], x2, zi=[self.lam * var])[0][-1]
        self.s = math.sqrt(var)
        s_hist = float(np.std(r, ddof=1)) * math.sqrt(TRADING_DAYS)
        mu_hist = float(np.mean(r)) * TRADING_DAYS + s_hist ** 2 / 2         # arithmetic, annual
        self.w = shrink_weight(s_hist, len(r) / TRADING_DAYS, self.tau)
        self.mu = self.w * mu_hist + (1 - self.w) * (rf + self.erp)
        return self

    @property
    def params(self):
        return {"sigma_annual": self.s * math.sqrt(TRADING_DAYS), "mu_annual": self.mu, "w_hist": self.w,
                "erp": self.erp}

    def forecast(self, h: int, n: int = 2000, seed=0) -> Forecast:
        z = _rng(seed).standard_normal(n)
        m = self.mu / TRADING_DAYS - 0.5 * self.s ** 2
        return Forecast(self.name, h, m * h + self.s * math.sqrt(h) * z)


class GJRGARCH:
    """r_t = mu + e_t; h_t = ω + (α + γ·1[e_{t−1}<0]) e²_{t−1} + β h_{t−1}; z ~ t(ν).

    Stationarity α + γ/2 + β < 1 is built into the parameterisation.
    """

    name = "GJR-GARCH(1,1)-t"

    @staticmethod
    def _unpack(x):
        mu = x[0]
        omega = math.exp(min(x[1], 0.0))
        b = special.expit(x[2]) * 0.999                      # persistence α + γ/2 + β
        w = np.exp(np.clip(x[3:6], -20, 20))
        w = w / w.sum()
        alpha, gamma, beta = b * w[0], 2 * b * w[1], b * w[2]
        nu = 2.05 + math.exp(min(x[6], 5.3))
        return mu, omega, alpha, gamma, beta, nu

    @staticmethod
    def _variances(e, omega, alpha, gamma, beta, h0):
        a = alpha + gamma * (e[:-1] < 0)
        x = omega + a * e[:-1] ** 2
        y = signal.lfilter([1.0], [1.0, -beta], x, zi=[beta * h0])[0]
        return np.concatenate([[h0], y])

    def _nll(self, x, r):
        mu, omega, alpha, gamma, beta, nu = self._unpack(x)
        e = r - mu
        h = self._variances(e, omega, alpha, gamma, beta, np.var(r))
        if np.any(h <= 0) or not np.all(np.isfinite(h)):
            return 1e10
        scale = np.sqrt(h * (nu - 2) / nu)
        return -float((stats.t.logpdf(e / scale, nu) - np.log(scale)).sum())

    def fit(self, r: np.ndarray, rf: float = 0.0, x0=None):
        var = float(np.var(r))
        if x0 is None:
            # start near α=0.05, γ=0.08, β=0.88 (typical equity values)
            x0 = np.array([np.mean(r), math.log(var * 0.03), special.logit(0.97 / 0.999),
                           math.log(0.05), math.log(0.04), math.log(0.88), math.log(6.0)])
        res = optimize.minimize(self._nll, x0, args=(r,), method="Nelder-Mead",
                                options={"maxiter": 4000, "xatol": 1e-6, "fatol": 1e-6})
        self.x = res.x
        self.mu, self.omega, self.alpha, self.gamma, self.beta, self.nu = self._unpack(res.x)
        e = r - self.mu
        h = self._variances(e, self.omega, self.alpha, self.gamma, self.beta, var)
        self.h_next = self.omega + (self.alpha + self.gamma * (e[-1] < 0)) * e[-1] ** 2 + self.beta * h[-1]
        self.converged = bool(res.success)
        return self

    @property
    def params(self):
        p = self.alpha + self.gamma / 2 + self.beta
        return {"mu_daily": self.mu, "omega": self.omega, "alpha": self.alpha, "gamma": self.gamma,
                "beta": self.beta, "nu": self.nu, "persistence": p,
                "current_vol_annual": math.sqrt(self.h_next * TRADING_DAYS),
                "long_run_vol_annual": math.sqrt(self.omega / max(1 - p, 1e-6) * TRADING_DAYS)}

    def forecast(self, h: int, n: int = 2000, seed=0) -> Forecast:
        rng = _rng(seed)
        z = rng.standard_t(self.nu, size=(h, n)) * math.sqrt((self.nu - 2) / self.nu)
        var = np.full(n, self.h_next)
        total = np.zeros(n)
        for t in range(h):
            e = np.sqrt(var) * z[t]
            total += self.mu + e
            var = self.omega + (self.alpha + self.gamma * (e < 0)) * e * e + self.beta * var
        return Forecast(self.name, h, total)


FACTORIES = {
    "rw": lambda erp: RandomWalk(),
    "ewma": lambda erp: EWMAShrunk(erp=erp),
    "gjr": lambda erp: GJRGARCH(),
    "gbm": lambda erp: GBM(),
    "bsm": lambda erp: BSMRiskNeutral(),
    "garch": lambda erp: GARCH(),
    "arima": lambda erp: ARIMA(),
    "merton": lambda erp: MertonJump(),
    "mc": lambda erp: BootstrapMC(),
}
WARM_START = {"gjr", "garch", "merton"}       # refits start from the previous solution


def model_ids() -> list[str]:
    return list(load("models")["models"])


def name(mid: str) -> str:
    return load("models")["models"][mid]["name"]


def make(mid: str, erp: float = 0.0423):
    return FACTORIES[mid](erp)


def erp_for(country: str | None, market_class: str | None) -> tuple[float, str]:
    cfg = load("models")["erp"]
    if country in cfg.get("by_country", {}):
        return cfg["by_country"][country], f"ERP for {country}"
    if market_class in ("Emerging", "Frontier", "Standalone"):
        return cfg["emerging_default"], "emerging-market stand-in (pending Damodaran country data)"
    return cfg["mature"], "Damodaran mature-market ERP"
