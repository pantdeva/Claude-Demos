"""Modern Portfolio Theory: long-only mean-variance allocation.

Chooses weights w (no shorting, sum(w) <= 1, rest in cash) that maximise
    w·(mu - rf) - (gamma / 2) · w' Σ w
i.e. the best expected excess return for the risk taken. gamma is risk aversion.
"""

from __future__ import annotations

import numpy as np
from scipy import optimize


def mean_variance_weights(mu: np.ndarray, cov: np.ndarray, rf: float, gamma: float = 3.0) -> np.ndarray:
    mu, cov = np.asarray(mu, float), np.asarray(cov, float)
    n = len(mu)
    excess = mu - rf

    def neg_util(w):
        return -(w @ excess - 0.5 * gamma * w @ cov @ w)

    def grad(w):
        return -(excess - gamma * cov @ w)

    res = optimize.minimize(neg_util, np.full(n, 1.0 / (n + 1)), jac=grad, method="SLSQP",
                            bounds=[(0.0, 1.0)] * n,
                            constraints=[{"type": "ineq", "fun": lambda w: 1.0 - w.sum()}])
    w = np.clip(res.x, 0, 1)
    return w / max(1.0, w.sum())


def efficient_frontier(mu: np.ndarray, cov: np.ndarray, rf: float, gammas=None):
    """(risk, return, weights) points along the long-only frontier."""
    gammas = gammas if gammas is not None else np.geomspace(0.5, 50, 25)
    pts = []
    for g in gammas:
        w = mean_variance_weights(mu, cov, rf, g)
        ret = rf + w @ (mu - rf)
        pts.append((float(np.sqrt(w @ cov @ w)), float(ret), w.tolist()))
    return pts
