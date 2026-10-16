"""Forecasting models for an h-day horizon, all fitted on daily log returns.

Each model's ``fit(r, rf)`` takes a 1-D array of daily log returns (oldest first)
and the current annual risk-free rate, and ``forecast(h)`` returns a Forecast:
simulated h-day log returns plus summary statistics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import optimize, signal, special, stats

TRADING_DAYS = 252
N_SIMS = 4000


@dataclass
class Forecast:
    model: str
    h: int
    samples: np.ndarray          # simulated h-day log returns

    @property
    def mean_log(self) -> float:
        return float(self.samples.mean())

    @property
    def gross(self) -> np.ndarray:
        return np.exp(self.samples)

    @property
    def exp_return(self) -> float:
        """Expected simple return over the horizon, E[S_h/S_0] - 1."""
        return float(self.gross.mean() - 1)

    @property
    def var_return(self) -> float:
        return float(self.gross.var())

    def prob_above(self, simple_return: float) -> float:
        return float((self.gross - 1 > simple_return).mean())

    def quantiles(self, qs=(0.05, 0.5, 0.95)) -> np.ndarray:
        return np.quantile(self.samples, qs)


def _rng(seed):
    return np.random.default_rng(seed)


# ---------------------------------------------------------------- GBM
class GBM:
    """dS = mu S dt + sigma S dW. Daily log returns ~ N(mu - sigma^2/2, sigma^2)."""

    name = "GBM"

    def fit(self, r: np.ndarray, rf: float = 0.0):
        self.m, self.s = float(np.mean(r)), float(np.std(r, ddof=1))
        return self

    @property
    def params(self):
        return {"mu_annual": (self.m + self.s ** 2 / 2) * TRADING_DAYS,
                "sigma_annual": self.s * math.sqrt(TRADING_DAYS)}

    def forecast(self, h: int, n: int = N_SIMS, seed=0) -> Forecast:
        z = _rng(seed).standard_normal(n)
        return Forecast(self.name, h, self.m * h + self.s * math.sqrt(h) * z)


# ---------------------------------------------------------------- Black-Scholes-Merton
def bsm_price(S, K, T, r, sigma, kind="call"):
    """European option price under Black-Scholes-Merton (no dividends)."""
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if kind == "call" else (K - S))
    d1 = (math.log(S / K) + (r + sigma ** 2 / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if kind == "call":
        return S * stats.norm.cdf(d1) - K * math.exp(-r * T) * stats.norm.cdf(d2)
    return K * math.exp(-r * T) * stats.norm.cdf(-d2) - S * stats.norm.cdf(-d1)


def implied_vol(price, S, K, T, r, kind="call"):
    """Volatility that makes the BSM price equal ``price`` (Brent's method)."""
    intrinsic = max(0.0, (S - K * math.exp(-r * T)) if kind == "call" else (K * math.exp(-r * T) - S))
    if price <= intrinsic + 1e-12:
        return float("nan")
    return optimize.brentq(lambda s: bsm_price(S, K, T, r, s, kind) - price, 1e-6, 10.0)


class BSMRiskNeutral:
    """Black-Scholes-Merton world: the stock drifts at the risk-free rate.

    Without historical option prices there is no market implied volatility, so
    the volatility used is an EWMA (RiskMetrics, lambda=0.94) estimate of
    current volatility. The forecast is the risk-neutral price distribution.
    """

    name = "Black-Scholes-Merton"

    def fit(self, r: np.ndarray, rf: float = 0.0, lam: float = 0.94):
        var = np.var(r[:60])
        for x in r:
            var = lam * var + (1 - lam) * x * x
        self.s = float(math.sqrt(var))
        self.rf = rf
        return self

    @property
    def params(self):
        return {"sigma_annual": self.s * math.sqrt(TRADING_DAYS), "drift": "risk-free rate"}

    def forecast(self, h: int, n: int = N_SIMS, seed=0) -> Forecast:
        T = h / TRADING_DAYS
        z = _rng(seed).standard_normal(n)
        sig = self.s * math.sqrt(TRADING_DAYS)
        return Forecast(self.name, h, (self.rf - sig ** 2 / 2) * T + sig * math.sqrt(T) * z)


# ---------------------------------------------------------------- GARCH(1,1) with Student-t errors
class GARCH:
    """r_t = mu + e_t, e_t = sqrt(h_t) z_t, h_t = omega + alpha e_{t-1}^2 + beta h_{t-1}, z ~ t(nu)."""

    name = "GARCH(1,1)"

    @staticmethod
    def _unpack(x):
        mu = x[0]
        omega = math.exp(min(x[1], 0.0))
        a, b = special.expit(x[2]), special.expit(x[3])
        alpha, beta = a * b, (1 - a) * b          # alpha + beta = b < 1 (stationary)
        nu = 2.05 + math.exp(min(x[4], 5.3))      # caps nu near 200 (effectively normal)
        return mu, omega, alpha, beta, nu

    @staticmethod
    def _variances(e, omega, alpha, beta, h0):
        # h_t = omega + alpha e_{t-1}^2 + beta h_{t-1}, run as a linear filter for speed
        x = omega + alpha * e[:-1] ** 2
        y = signal.lfilter([1.0], [1.0, -beta], x, zi=[beta * h0])[0]
        return np.concatenate([[h0], y])

    def _nll(self, x, r):
        mu, omega, alpha, beta, nu = self._unpack(x)
        e = r - mu
        h = self._variances(e, omega, alpha, beta, np.var(r))
        if np.any(h <= 0):
            return 1e10
        scale = np.sqrt(h * (nu - 2) / nu)
        ll = stats.t.logpdf(e / scale, nu) - np.log(scale)
        return -float(ll.sum())

    def fit(self, r: np.ndarray, rf: float = 0.0, x0=None):
        var = np.var(r)
        if x0 is None:
            x0 = np.array([np.mean(r), math.log(var * 0.05), special.logit(0.1 / 0.95),
                           special.logit(0.95), math.log(6.0)])
        res = optimize.minimize(self._nll, x0, args=(r,), method="Nelder-Mead",
                                options={"maxiter": 3000, "xatol": 1e-6, "fatol": 1e-6})
        self.x = res.x
        self.mu, self.omega, self.alpha, self.beta, self.nu = self._unpack(res.x)
        e = r - self.mu
        h = self._variances(e, self.omega, self.alpha, self.beta, var)
        self.h_next = self.omega + self.alpha * e[-1] ** 2 + self.beta * h[-1]
        self.converged = bool(res.success)
        return self

    @property
    def params(self):
        p = self.alpha + self.beta
        return {"mu_daily": self.mu, "omega": self.omega, "alpha": self.alpha, "beta": self.beta,
                "nu": self.nu, "persistence": p,
                "current_vol_annual": math.sqrt(self.h_next * TRADING_DAYS),
                "long_run_vol_annual": math.sqrt(self.omega / (1 - p) * TRADING_DAYS)}

    def forecast(self, h: int, n: int = N_SIMS, seed=0) -> Forecast:
        rng = _rng(seed)
        z = rng.standard_t(self.nu, size=(h, n)) * math.sqrt((self.nu - 2) / self.nu)
        var = np.full(n, self.h_next)
        total = np.zeros(n)
        for t in range(h):
            e = np.sqrt(var) * z[t]
            total += self.mu + e
            var = self.omega + self.alpha * e * e + self.beta * var
        return Forecast(self.name, h, total)


# ---------------------------------------------------------------- ARIMA(p,0,q) on log returns = ARIMA(p,1,q) on log prices
class ARIMA:
    """ARMA(p,q) on daily log returns, i.e. ARIMA(p,1,q) on log prices.

    Fitted by conditional sum of squares; order chosen by AIC from p,q in {0,1,2}.
    """

    name = "ARIMA"

    def __init__(self, orders=((0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2), (2, 1), (1, 2), (2, 2))):
        self.orders = orders

    @staticmethod
    def _resid(params, r, p, q):
        # (1 - phi(B))(r - c) = (1 + theta(B)) e, pre-sample values set to their means
        c, phi, theta = params[0], params[1:1 + p], params[1 + p:1 + p + q]
        return signal.lfilter(np.r_[1.0, -phi], np.r_[1.0, theta], r - c)

    def _fit_order(self, r, p, q):
        k = 1 + p + q

        def css(x):
            # keep AR and MA parts stationary / invertible via tanh squashing
            x = np.concatenate([[x[0]], np.tanh(x[1:]) * 0.99])
            e = self._resid(x, r, p, q)
            return float(np.sum(e[max(p, q):] ** 2))

        x0 = np.zeros(k)
        x0[0] = np.mean(r)
        res = optimize.minimize(css, x0, method="Nelder-Mead" if k > 1 else "BFGS",
                                options={"maxiter": 2000})
        params = np.concatenate([[res.x[0]], np.tanh(res.x[1:]) * 0.99])
        n = len(r) - max(p, q)
        sigma2 = res.fun / n
        aic = n * math.log(sigma2) + 2 * (k + 1)
        return params, sigma2, aic

    def fit(self, r: np.ndarray, rf: float = 0.0):
        best = None
        for p, q in self.orders:
            params, s2, aic = self._fit_order(r, p, q)
            if best is None or aic < best[3]:
                best = (p, q, params, aic, s2)
        self.p, self.q, self.coef, self.aic, self.sigma2 = best
        self.r_tail = r[-max(self.p, 1):].copy()
        self.e_tail = self._resid(self.coef, r, self.p, self.q)[-max(self.q, 1):]
        return self

    @property
    def params(self):
        return {"order": f"({self.p},1,{self.q})", "const_daily": self.coef[0],
                "ar": list(self.coef[1:1 + self.p]), "ma": list(self.coef[1 + self.p:]),
                "sigma_annual": math.sqrt(self.sigma2 * TRADING_DAYS)}

    def _psi(self, h):
        phi, theta = self.coef[1:1 + self.p], self.coef[1 + self.p:]
        psi = np.zeros(h)
        psi[0] = 1.0
        for j in range(1, h):
            v = theta[j - 1] if j - 1 < self.q else 0.0
            v += sum(phi[i] * psi[j - 1 - i] for i in range(self.p) if j - 1 - i >= 0)
            psi[j] = v
        return psi

    def forecast(self, h: int, n: int = N_SIMS, seed=0) -> Forecast:
        c, phi, theta = self.coef[0], self.coef[1:1 + self.p], self.coef[1 + self.p:]
        hist_r, hist_e = list(self.r_tail), list(self.e_tail)
        means = []
        for step in range(h):
            ar = sum(phi[i] * (hist_r[-1 - i] - c) for i in range(self.p))
            ma = sum(theta[j] * hist_e[-1 - j] for j in range(self.q))
            f = c + ar + ma
            means.append(f)
            hist_r.append(f)
            hist_e.append(0.0)
        psi = self._psi(h)
        cum = np.cumsum(psi)                    # weight of each future shock on the h-day sum
        var = self.sigma2 * float(np.sum(cum[::-1] ** 2))
        z = _rng(seed).standard_normal(n)
        return Forecast(self.name, h, float(np.sum(means)) + math.sqrt(var) * z)


# ---------------------------------------------------------------- Merton jump-diffusion
class MertonJump:
    """GBM plus compound-Poisson jumps: daily return = diffusion + sum of N~Poisson(lam) jumps,
    each jump ~ N(muJ, sigJ^2). Captures fat tails and crash days. Fitted by maximum likelihood."""

    name = "Merton jump-diffusion"
    K = 8

    @staticmethod
    def _unpack(x):
        c = lambda v: math.exp(min(max(v, -30.0), 2.0))
        return x[0], c(x[1]), c(x[2]), x[3], c(x[4])  # m, s, lam, muJ, sJ

    def _nll(self, x, r):
        m, s, lam, muJ, sJ = self._unpack(x)
        if lam > 0.5:
            return 1e10
        k = np.arange(self.K + 1)
        logp = stats.poisson.logpmf(k, lam)
        mean = m + k * muJ
        sd = np.sqrt(s ** 2 + k * sJ ** 2)
        comp = logp[None, :] + stats.norm.logpdf(r[:, None], mean[None, :], sd[None, :])
        return -float(special.logsumexp(comp, axis=1).sum())

    def fit(self, r: np.ndarray, rf: float = 0.0, x0=None):
        s0 = np.std(r)
        if x0 is None:
            x0 = np.array([np.mean(r), math.log(s0 * 0.8), math.log(0.05), 0.0, math.log(s0 * 3)])
        res = optimize.minimize(self._nll, x0, args=(r,), method="Nelder-Mead",
                                options={"maxiter": 4000, "xatol": 1e-7, "fatol": 1e-7})
        self.x = res.x
        self.m, self.s, self.lam, self.muJ, self.sJ = self._unpack(res.x)
        self.converged = bool(res.success)
        return self

    @property
    def params(self):
        return {"diffusion_vol_annual": self.s * math.sqrt(TRADING_DAYS),
                "jumps_per_year": self.lam * TRADING_DAYS, "mean_jump": self.muJ, "jump_sd": self.sJ}

    def forecast(self, h: int, n: int = N_SIMS, seed=0) -> Forecast:
        rng = _rng(seed)
        nj = rng.poisson(self.lam * h, n)
        jumps = nj * self.muJ + np.sqrt(nj) * self.sJ * rng.standard_normal(n)
        diff = self.m * h + self.s * math.sqrt(h) * rng.standard_normal(n)
        return Forecast(self.name, h, diff + jumps)


# ---------------------------------------------------------------- Monte Carlo (stationary block bootstrap)
class BootstrapMC:
    """Model-free Monte Carlo: build h-day paths by resampling blocks of real past
    daily returns (keeps fat tails and short-run volatility clustering)."""

    name = "Monte Carlo (bootstrap)"

    def __init__(self, block: int = 10):
        self.block = block

    def fit(self, r: np.ndarray, rf: float = 0.0):
        self.r = np.asarray(r, dtype=float)
        return self

    @property
    def params(self):
        return {"block_days": self.block, "history_days": len(self.r)}

    def forecast(self, h: int, n: int = N_SIMS, seed=0) -> Forecast:
        rng = _rng(seed)
        nb = math.ceil(h / self.block)
        starts = rng.integers(0, len(self.r) - self.block, size=(n, nb))
        idx = (starts[:, :, None] + np.arange(self.block)[None, None, :]).reshape(n, -1)[:, :h]
        return Forecast(self.name, h, self.r[idx].sum(axis=1))


FORECAST_MODELS = [GBM, BSMRiskNeutral, GARCH, ARIMA, MertonJump, BootstrapMC]
