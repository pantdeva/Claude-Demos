"""Walk-forward comparison of the models on one stock.

At each monthly origin (every 21 trading days), every model is fitted on the
previous ``window`` daily returns only (no look-ahead) and forecasts the
distribution of the h-day return for each horizon. Two things are scored:

1. Forecast skill   - direction hit rate, error of the mean forecast, 90% interval
                      coverage and CRPS (a proper score for whole distributions).
2. Trading results  - each forecast sets an allocation between the stock and cash;
                      MPT allocates between the stock, the S&P 500 and cash.
                      Monthly overlapping "tranches" are held for h days each.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .models import FORECAST_MODELS, TRADING_DAYS, Forecast, GARCH, MertonJump
from .portfolio import mean_variance_weights


# ---------------------------------------------------------------- data
def load_stooq(text_or_path) -> pd.Series:
    """Close prices from a Stooq daily CSV (Date,Open,High,Low,Close,Volume)."""
    src = io.StringIO(text_or_path) if isinstance(text_or_path, str) and "\n" in text_or_path else text_or_path
    df = pd.read_csv(src, parse_dates=["Date"])
    return df.set_index("Date")["Close"].astype(float).sort_index()


def load_fred(text_or_path) -> pd.Series:
    """Annual rate (as a decimal) from a FRED CSV such as DTB3; '.' gaps forward-filled."""
    src = io.StringIO(text_or_path) if isinstance(text_or_path, str) and "\n" in text_or_path else text_or_path
    df = pd.read_csv(src)
    date_col = df.columns[0]
    s = pd.to_numeric(df[df.columns[1]], errors="coerce") / 100.0
    s.index = pd.to_datetime(df[date_col])
    return s.sort_index().ffill()


# ---------------------------------------------------------------- scoring helpers
def crps_samples(x: np.ndarray, y: float, max_n: int = 1000) -> float:
    """CRPS of a sample forecast x for outcome y: E|X-y| - 0.5 E|X-X'| (lower is better)."""
    x = np.sort(x[:max_n])
    n = len(x)
    term1 = np.mean(np.abs(x - y))
    term2 = (2.0 / (n * n)) * np.sum((2 * np.arange(1, n + 1) - n - 1) * x)
    return float(term1 - 0.5 * term2)


def perf_stats(daily: pd.Series, rf_daily: pd.Series) -> dict:
    daily = daily.dropna()
    if daily.empty:
        return {}
    eq = (1 + daily).cumprod()
    years = len(daily) / TRADING_DAYS
    cagr = eq.iloc[-1] ** (1 / years) - 1
    vol = daily.std() * math.sqrt(TRADING_DAYS)
    ex = daily - rf_daily.reindex(daily.index).fillna(0)
    sharpe = ex.mean() / daily.std() * math.sqrt(TRADING_DAYS) if daily.std() > 0 else float("nan")
    dd = (eq / eq.cummax() - 1).min()
    return {"cagr": float(cagr), "vol": float(vol), "sharpe": float(sharpe),
            "max_drawdown": float(dd), "multiple": float(eq.iloc[-1])}


# ---------------------------------------------------------------- backtest
@dataclass
class Backtest:
    prices: pd.Series                       # the stock
    market: pd.Series | None = None         # market index, for MPT
    rf: pd.Series | None = None             # annual risk-free rate (decimal)
    horizons: dict = field(default_factory=lambda: {"3 months": 63, "1 year": 252})
    window: int = 1260                      # 5 years of daily returns per fit
    step: int = 21                          # monthly origins
    gamma: float = 2.0                      # risk aversion for position sizing
    n_sims: int = 3000
    name: str = "NVDA"                      # labels used in results
    market_name: str = "S&P 500"

    def __post_init__(self):
        idx = self.prices.dropna().index
        if self.market is not None:
            idx = idx.intersection(self.market.dropna().index)
        self.px = self.prices.reindex(idx)
        self.mkt = self.market.reindex(idx) if self.market is not None else None
        rf = self.rf if self.rf is not None else pd.Series(0.0, index=idx)
        self.rf_annual = rf.reindex(idx.union(rf.index)).sort_index().ffill().reindex(idx).fillna(0.0)
        self.logr = np.log(self.px).diff()
        self.simple = self.px.pct_change()
        self.mkt_simple = self.mkt.pct_change() if self.mkt is not None else None
        self.rf_daily = self.rf_annual / TRADING_DAYS

    def origins(self):
        return list(range(self.window, len(self.px) - 1, self.step))

    def run(self, progress=None) -> dict:
        names = [m.name for m in FORECAST_MODELS]
        rows, weights = [], {h: {} for h in self.horizons}   # weights[h][model][origin] -> dict asset->w
        warm = {}
        origins = self.origins()
        r_all = self.logr.values
        for k, i in enumerate(origins):
            r = r_all[i - self.window + 1:i + 1]
            rf0 = float(self.rf_annual.iloc[i])
            for cls in FORECAST_MODELS:
                m = cls()
                if cls in (GARCH, MertonJump) and cls in warm:
                    m.fit(r, rf0, x0=warm[cls])
                else:
                    m.fit(r, rf0)
                if cls in (GARCH, MertonJump):
                    warm[cls] = m.x
                for hname, h in self.horizons.items():
                    f: Forecast = m.forecast(h, self.n_sims, seed=k)
                    rf_h = rf0 * h / TRADING_DAYS
                    real = (math.log(self.px.iloc[i + h] / self.px.iloc[i])
                            if i + h < len(self.px) else float("nan"))
                    lo, med, hi = f.quantiles((0.05, 0.5, 0.95))
                    p_beat = f.prob_above(rf_h)
                    excess = f.exp_return - rf_h
                    w = float(np.clip(excess / (self.gamma * max(f.var_return, 1e-12)), 0, 1))
                    rows.append({
                        "origin": self.px.index[i], "model": m.name, "horizon": hname, "h": h,
                        "exp_return": f.exp_return, "mean_log": f.mean_log, "q05": lo, "q50": med,
                        "q95": hi, "p_beat_cash": p_beat, "rf_h": rf_h, "realized_log": real,
                        "crps": crps_samples(f.samples, real) if not math.isnan(real) else float("nan"),
                        "w_sized": w, "w_signal": 1.0 if p_beat > 0.5 else 0.0,
                    })
            # MPT: stock + S&P 500 + cash, from the same window of simple returns
            if self.mkt_simple is not None:
                a = self.simple.values[i - self.window + 1:i + 1]
                b = self.mkt_simple.values[i - self.window + 1:i + 1]
                X = np.column_stack([a, b])
                for hname, h in self.horizons.items():
                    mu = X.mean(axis=0) * h
                    cov = np.cov(X.T) * h
                    w = mean_variance_weights(mu, cov, rf0 * h / TRADING_DAYS, self.gamma)
                    rows.append({"origin": self.px.index[i], "model": "MPT (mean-variance)",
                                 "horizon": hname, "h": h, "w_stock": float(w[0]),
                                 "w_market": float(w[1])})
            if progress:
                progress(k + 1, len(origins))
        self.table = pd.DataFrame(rows)
        return self.summarise()

    # -------------------------------------------------------------- forecasts from today
    def current_forecasts(self) -> dict:
        """Fit every model on the latest window and forecast each horizon from the last close."""
        from .models import bsm_price, implied_vol

        i = len(self.px) - 1
        r = self.logr.values[i - self.window + 1:i + 1]
        rf0 = float(self.rf_annual.iloc[i])
        S0 = float(self.px.iloc[i])
        out = {"as_of": str(self.px.index[i].date()), "price": S0, "rf": rf0, "models": [], "options": []}
        fitted = {}
        for cls in FORECAST_MODELS:
            m = cls().fit(r, rf0)
            fitted[m.name] = m
            entry = {"model": m.name, "params": {k: (v if isinstance(v, (str, list)) else float(v))
                                                 for k, v in m.params.items()}, "horizons": {}}
            for hname, h in self.horizons.items():
                f = m.forecast(h, 20000, seed=123)
                lo, med, hi = np.exp(f.quantiles((0.05, 0.5, 0.95))) * S0
                rf_h = rf0 * h / TRADING_DAYS
                entry["horizons"][hname] = {
                    "expected_price": S0 * (1 + f.exp_return), "median_price": float(med),
                    "p05_price": float(lo), "p95_price": float(hi),
                    "p_up": f.prob_above(0.0), "p_beat_cash": f.prob_above(rf_h),
                    "exp_return": f.exp_return,
                    "w_sized": float(np.clip((f.exp_return - rf_h) /
                                             (self.gamma * max(f.var_return, 1e-12)), 0, 1)),
                }
            out["models"].append(entry)
        # BSM option prices using the GARCH volatility forecast for each horizon
        g = fitted["GARCH(1,1)"]
        for hname, h in self.horizons.items():
            T = h / TRADING_DAYS
            sig = float(np.std(g.forecast(h, 20000, seed=7).samples) / math.sqrt(T))
            call = bsm_price(S0, S0, T, rf0, sig, "call")
            put = bsm_price(S0, S0, T, rf0, sig, "put")
            out["options"].append({"horizon": hname, "strike": S0, "vol_used": sig,
                                   "call": call, "put": put,
                                   "implied_vol_check": implied_vol(call, S0, S0, T, rf0, "call"),
                                   "breakeven_up": S0 + call, "breakeven_down": S0 - put})
        if self.mkt_simple is not None:
            X = np.column_stack([self.simple.values[i - self.window + 1:i + 1],
                                 self.mkt_simple.values[i - self.window + 1:i + 1]])
            from .portfolio import efficient_frontier
            mu, cov = X.mean(axis=0) * TRADING_DAYS, np.cov(X.T) * TRADING_DAYS
            w = mean_variance_weights(mu, cov, rf0, self.gamma)
            out["mpt"] = {"weights": {self.name: float(w[0]), self.market_name: float(w[1]),
                                      "Cash": float(1 - w.sum())},
                          "frontier": efficient_frontier(mu, cov, rf0),
                          "assets": {self.name: [float(np.sqrt(cov[0, 0])), float(mu[0])],
                                     self.market_name: [float(np.sqrt(cov[1, 1])), float(mu[1])]}}
        return out

    # -------------------------------------------------------------- strategies
    def _tranche_returns(self, sub: pd.DataFrame, h: int, stock_col: str, market_col: str | None) -> pd.Series:
        """Daily returns of overlapping monthly tranches, each held h days."""
        n = len(self.px)
        pos_stock = np.zeros(n)
        pos_mkt = np.zeros(n)
        count = np.zeros(n)
        pos_index = {d: j for j, d in enumerate(self.px.index)}
        for _, row in sub.iterrows():
            i = pos_index[row["origin"]]
            a, b = i + 1, min(i + h, n - 1) + 1
            pos_stock[a:b] += row[stock_col]
            if market_col:
                pos_mkt[a:b] += row[market_col]
            count[a:b] += 1
        live = count > 0
        ws = np.where(live, pos_stock / np.maximum(count, 1), np.nan)
        wm = np.where(live, pos_mkt / np.maximum(count, 1), 0.0)
        r_stock = self.simple.fillna(0).values
        r_mkt = self.mkt_simple.fillna(0).values if self.mkt_simple is not None else np.zeros(n)
        rf = self.rf_daily.values
        daily = ws * r_stock + wm * r_mkt + (1 - ws - wm) * rf
        out = pd.Series(daily, index=self.px.index)
        return out[live]

    def summarise(self) -> dict:
        t = self.table
        out = {"horizons": {}, "period": None}
        for hname, h in self.horizons.items():
            fc = t[(t.horizon == hname) & (t.model != "MPT (mean-variance)")]
            scored = fc.dropna(subset=["realized_log"])
            skill = []
            for model, g in scored.groupby("model", sort=False):
                beat = g.realized_log > np.log1p(g.rf_h)
                skill.append({
                    "model": model, "n": int(len(g)),
                    "hit_rate": float(((g.p_beat_cash > 0.5) == beat).mean()),
                    "mae_log": float((g.mean_log - g.realized_log).abs().mean()),
                    "coverage90": float(((g.realized_log >= g.q05) & (g.realized_log <= g.q95)).mean()),
                    "width90": float((g.q95 - g.q05).mean()),
                    "crps": float(g.crps.mean()),
                })
            strategies = []
            curves = {}
            for model, g in fc.groupby("model", sort=False):
                for rule, col in (("sized", "w_sized"), ("signal", "w_signal")):
                    d = self._tranche_returns(g, h, col, None)
                    stats_ = perf_stats(d, self.rf_daily)
                    stats_.update({"model": model, "rule": rule, "avg_exposure": float(g[col].mean())})
                    strategies.append(stats_)
                    if rule == "sized":
                        curves[model] = d
            mpt = t[(t.horizon == hname) & (t.model == "MPT (mean-variance)")]
            if not mpt.empty:
                d = self._tranche_returns(mpt, h, "w_stock", "w_market")
                s_ = perf_stats(d, self.rf_daily)
                s_.update({"model": "MPT (mean-variance)", "rule": "sized",
                           "avg_exposure": float(mpt.w_stock.mean()),
                           "avg_market": float(mpt.w_market.mean())})
                strategies.append(s_)
                curves["MPT (mean-variance)"] = d
            ref = next(iter(curves.values()))
            bh = self.simple.reindex(ref.index)
            s_ = perf_stats(bh, self.rf_daily)
            s_.update({"model": f"Buy & hold {self.name}", "rule": "benchmark", "avg_exposure": 1.0})
            strategies.append(s_)
            curves[f"Buy & hold {self.name}"] = bh
            if self.mkt_simple is not None:
                s_ = perf_stats(self.mkt_simple.reindex(ref.index), self.rf_daily)
                s_.update({"model": f"Buy & hold {self.market_name}", "rule": "benchmark", "avg_exposure": 0.0})
                strategies.append(s_)
                curves[f"Buy & hold {self.market_name}"] = self.mkt_simple.reindex(ref.index)
            out["horizons"][hname] = {"h": h, "skill": skill, "strategies": strategies,
                                      "curves": {k: (1 + v.fillna(0)).cumprod() for k, v in curves.items()}}
            out["period"] = (str(ref.index[0].date()), str(ref.index[-1].date()))
        return out
