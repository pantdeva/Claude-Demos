# Stage 0 model leaderboard

Built 2026-10-18T18:59:45Z. 196,164 scored forecasts for 383 companies on 86 forecast dates (2010-01-03 to 2026-07-02). Each model is fitted on the previous 1260 trading days only; forecast dates every ~126 trading days.

Loss: CRPS of the forecast distribution of the log return (lower is better). *Skill* = 1 − CRPS ÷ CRPS of the group's baseline. A model replaces the baseline only with positive skill and a Diebold–Mariano t at least the Bonferroni-corrected 5% level for the number of candidates (≈ 2.73 for 8; Newey–West, small-sample corrected).

## All companies

| Group | Horizon | Baseline | Selected | Basis | Lowest CRPS | Dates | Stocks |
|---|---|---|---|---|---|---|---|
| All companies | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 383 |
| All companies | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 34 | 383 |

## By market class

| Group | Horizon | Baseline | Selected | Basis | Lowest CRPS | Dates | Stocks |
|---|---|---|---|---|---|---|---|
| Developed | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 32 | 313 |
| Developed | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 34 | 313 |
| Emerging | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 31 | 70 |
| Emerging | 3 months | GJR-GARCH(1,1)-t | **EWMA vol + shrunk drift** | beats baseline: skill +8.3%, DM t = 4.86 (needs 2.73) | EWMA vol + shrunk drift | 33 | 70 |

## By cell (market class × sector group)

| Group | Horizon | Baseline | Selected | Basis | Lowest CRPS | Dates | Stocks |
|---|---|---|---|---|---|---|---|
| Developed × Consumer Discretionary & Staples | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 54 |
| Developed × Consumer Discretionary & Staples | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 34 | 54 |
| Developed × Energy, Materials & Utilities | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 40 |
| Developed × Energy, Materials & Utilities | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GJR-GARCH(1,1)-t | 34 | 40 |
| Developed × Financials & Banking | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 62 |
| Developed × Financials & Banking | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 34 | 62 |
| Developed × Healthcare & Biotech | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GJR-GARCH(1,1)-t | 32 | 28 |
| Developed × Healthcare & Biotech | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 34 | 28 |
| Developed × IT & Software | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GJR-GARCH(1,1)-t | 32 | 67 |
| Developed × IT & Software | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GBM | 34 | 67 |
| Developed × Industrials & Real Estate | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 62 |
| Developed × Industrials & Real Estate | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 34 | 62 |
| Emerging × Consumer Discretionary & Staples | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 31 | 10 |
| Emerging × Consumer Discretionary & Staples | 3 months | GJR-GARCH(1,1)-t | **EWMA vol + shrunk drift** | beats baseline: skill +9.7%, DM t = 3.74 (needs 2.73) | EWMA vol + shrunk drift | 33 | 10 |
| Emerging × Energy, Materials & Utilities | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 31 | 10 |
| Emerging × Energy, Materials & Utilities | 3 months | GJR-GARCH(1,1)-t | **EWMA vol + shrunk drift** | beats baseline: skill +10.6%, DM t = 4.47 (needs 2.73) | EWMA vol + shrunk drift | 33 | 10 |
| Emerging × Financials & Banking | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 31 | 27 |
| Emerging × Financials & Banking | 3 months | GJR-GARCH(1,1)-t | **EWMA vol + shrunk drift** | beats baseline: skill +7.5%, DM t = 3.40 (needs 2.73) | EWMA vol + shrunk drift | 33 | 27 |
| Emerging × IT & Software | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Merton jump-diffusion | 31 | 14 |
| Emerging × IT & Software | 3 months | GJR-GARCH(1,1)-t | **EWMA vol + shrunk drift** | beats baseline: skill +7.5%, DM t = 3.70 (needs 2.73) | EWMA vol + shrunk drift | 33 | 14 |
| Emerging × Industrials & Real Estate | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 31 | 7 |
| Emerging × Industrials & Real Estate | 3 months | GJR-GARCH(1,1)-t | **GJR-GARCH(1,1)-t** | baseline (no candidate reached DM t 2.73) | Random walk (zero drift) | 33 | 7 |

## By sector group

| Group | Horizon | Baseline | Selected | Basis | Lowest CRPS | Dates | Stocks |
|---|---|---|---|---|---|---|---|
| Consumer Discretionary & Staples | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 64 |
| Consumer Discretionary & Staples | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 34 | 64 |
| Energy, Materials & Utilities | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 50 |
| Energy, Materials & Utilities | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 34 | 50 |
| Financials & Banking | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 89 |
| Financials & Banking | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 34 | 89 |
| Healthcare & Biotech | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GJR-GARCH(1,1)-t | 32 | 30 |
| Healthcare & Biotech | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 34 | 30 |
| IT & Software | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 32 | 81 |
| IT & Software | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 34 | 81 |
| Industrials & Real Estate | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 69 |
| Industrials & Real Estate | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 34 | 69 |

## By exchange

| Group | Horizon | Baseline | Selected | Basis | Lowest CRPS | Dates | Stocks |
|---|---|---|---|---|---|---|---|
| ASX | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 1 |
| ASX | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Merton jump-diffusion | 34 | 1 |
| BME | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 32 | 1 |
| BME | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 34 | 1 |
| EURONEXT_AS | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GJR-GARCH(1,1)-t | 32 | 20 |
| EURONEXT_AS | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 34 | 20 |
| EURONEXT_BR | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 32 | 13 |
| EURONEXT_BR | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 34 | 13 |
| EURONEXT_IR | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 7 |
| EURONEXT_IR | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 34 | 7 |
| EURONEXT_LS | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 10 |
| EURONEXT_LS | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 34 | 10 |
| EURONEXT_MI | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GARCH(1,1)-t | 32 | 16 |
| EURONEXT_MI | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 34 | 16 |
| EURONEXT_OL | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 32 | 17 |
| EURONEXT_OL | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 34 | 17 |
| EURONEXT_PA | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 37 |
| EURONEXT_PA | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 34 | 37 |
| HKEX | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 31 | 20 |
| HKEX | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 33 | 20 |
| JPX | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GARCH(1,1)-t | 31 | 58 |
| JPX | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Random walk (zero drift) | 33 | 58 |
| LSE | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GJR-GARCH(1,1)-t | 32 | 4 |
| LSE | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GJR-GARCH(1,1)-t | 34 | 4 |
| NASDAQ | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GJR-GARCH(1,1)-t | 31 | 35 |
| NASDAQ | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | ARIMA | 33 | 35 |
| NYSE | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 31 | 68 |
| NYSE | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | Monte Carlo (bootstrap) | 33 | 68 |
| OMX_CPH | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GJR-GARCH(1,1)-t | 31 | 1 |
| OMX_CPH | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 33 | 1 |
| SIX | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 1 |
| SIX | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | GBM | 34 | 1 |
| SSE | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 31 | 46 |
| SSE | 3 months | GJR-GARCH(1,1)-t | **EWMA vol + shrunk drift** | beats baseline: skill +7.6%, DM t = 3.35 (needs 2.73) | EWMA vol + shrunk drift | 33 | 46 |
| SZSE | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 31 | 23 |
| SZSE | 3 months | GJR-GARCH(1,1)-t | **EWMA vol + shrunk drift** | beats baseline: skill +10.0%, DM t = 6.93 (needs 2.73) | EWMA vol + shrunk drift | 33 | 23 |
| TSX | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 31 | 3 |
| TSX | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 33 | 3 |
| TWSE | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | ARIMA | 31 | 1 |
| TWSE | 3 months | GJR-GARCH(1,1)-t | **GJR-GARCH(1,1)-t** | baseline (no candidate reached DM t 2.73) | ARIMA | 33 | 1 |
| XETRA | 1 year | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 32 | 1 |
| XETRA | 3 months | EWMA vol + shrunk drift | **EWMA vol + shrunk drift** | baseline (no candidate reached DM t 2.73) | EWMA vol + shrunk drift | 34 | 1 |

## Model table, all companies, 3 months

| Model | Mean CRPS | Skill vs baseline | DM t | Direction hit | 90% coverage | Bias (log) |
|---|---|---|---|---|---|---|
| EWMA vol + shrunk drift (baseline) | 0.0879 | +0.0% | 0.00 | 57% | 84% | -0.013 |
| Monte Carlo (bootstrap) | 0.0881 | -0.3% | -0.14 | 56% | 89% | +0.007 |
| ARIMA | 0.0886 | -0.8% | -0.66 | 56% | 90% | +0.006 |
| GBM | 0.0886 | -0.9% | -0.74 | 56% | 91% | +0.006 |
| Merton jump-diffusion | 0.0887 | -0.9% | -0.67 | 56% | 90% | +0.006 |
| Black-Scholes-Merton | 0.0892 | -1.6% | -1.91 | 52% | 83% | -0.027 |
| Random walk (zero drift) | 0.0893 | -1.6% | -1.06 | 49% | 91% | -0.034 |
| GJR-GARCH(1,1)-t | 0.0897 | -2.1% | -1.37 | 55% | 86% | +0.005 |
| GARCH(1,1)-t | 0.0909 | -3.5% | -2.02 | 56% | 87% | +0.015 |

## Model table, all companies, 1 year

| Model | Mean CRPS | Skill vs baseline | DM t | Direction hit | 90% coverage | Bias (log) |
|---|---|---|---|---|---|---|
| EWMA vol + shrunk drift (baseline) | 0.1762 | +0.0% | 0.00 | 68% | 84% | -0.100 |
| Monte Carlo (bootstrap) | 0.1770 | -0.4% | -0.15 | 65% | 89% | -0.028 |
| Merton jump-diffusion | 0.1783 | -1.2% | -0.40 | 65% | 90% | -0.028 |
| GBM | 0.1783 | -1.2% | -0.44 | 65% | 91% | -0.029 |
| ARIMA | 0.1783 | -1.2% | -0.41 | 64% | 90% | -0.029 |
| GJR-GARCH(1,1)-t | 0.1816 | -3.1% | -0.98 | 64% | 87% | -0.030 |
| GARCH(1,1)-t | 0.1852 | -5.1% | -1.36 | 65% | 88% | +0.009 |
| Black-Scholes-Merton | 0.1904 | -8.0% | -4.71 | 50% | 81% | -0.158 |
| Random walk (zero drift) | 0.1958 | -11.1% | -4.37 | 43% | 89% | -0.186 |

## Companies

- 3 months: 12 of 383 companies have a model that clearly beats their baseline (Random walk (zero drift) 5, EWMA vol + shrunk drift 3, Black-Scholes-Merton 2, Monte Carlo (bootstrap) 1, ARIMA 1).
- 1 year: 1 of 383 companies have a model that clearly beats their baseline (GJR-GARCH(1,1)-t 1).

## MPT vs 1/N inside each cell (quarterly rebalancing, US-dollar returns)

| Cell | Strategy | Quarters | Assets | Annual return | Volatility | Sharpe | Worst quarter | Sharpe-difference z |
|---|---|---|---|---|---|---|---|---|
| Developed × Consumer Discretionary & Staples | 1/N equal weight | 67 | 50 | +13.2% | 13.1% | 0.91 | -17.9% |  |
| Developed × Consumer Discretionary & Staples | MPT (mean-variance) | 67 | 50 | +18.1% | 28.8% | 0.67 | -23.7% | -1.22 |
| Developed × Energy, Materials & Utilities | 1/N equal weight | 67 | 56 | +10.5% | 21.4% | 0.51 | -31.6% |  |
| Developed × Energy, Materials & Utilities | MPT (mean-variance) | 67 | 56 | +8.6% | 22.3% | 0.43 | -39.2% | -0.50 |
| Developed × Financials & Banking | 1/N equal weight | 67 | 56 | +12.2% | 20.5% | 0.61 | -31.3% |  |
| Developed × Financials & Banking | MPT (mean-variance) | 67 | 56 | +18.2% | 17.7% | 0.98 | -16.8% | +1.60 |
| Developed × Healthcare & Biotech | 1/N equal weight | 67 | 33 | +14.6% | 15.6% | 0.86 | -12.2% |  |
| Developed × Healthcare & Biotech | MPT (mean-variance) | 67 | 33 | +21.0% | 31.2% | 0.70 | -21.5% | -0.80 |
| Developed × IT & Software | 1/N equal weight | 67 | 47 | +23.9% | 20.9% | 1.09 | -17.7% |  |
| Developed × IT & Software | MPT (mean-variance) | 67 | 47 | +31.9% | 38.9% | 0.89 | -50.8% | -1.10 |
| Developed × Industrials & Real Estate | 1/N equal weight | 67 | 55 | +14.9% | 18.2% | 0.80 | -25.9% |  |
| Developed × Industrials & Real Estate | MPT (mean-variance) | 67 | 55 | +20.0% | 25.3% | 0.82 | -35.1% | +0.09 |
| Emerging × Consumer Discretionary & Staples | 1/N equal weight | 67 | 35 | +11.5% | 17.5% | 0.63 | -23.9% |  |
| Emerging × Consumer Discretionary & Staples | MPT (mean-variance) | 67 | 35 | +13.8% | 25.8% | 0.58 | -21.9% | -0.25 |
| Emerging × Energy, Materials & Utilities | 1/N equal weight | 67 | 45 | +7.7% | 20.0% | 0.40 | -30.7% |  |
| Emerging × Energy, Materials & Utilities | MPT (mean-variance) | 67 | 45 | +17.1% | 35.5% | 0.58 | -48.1% | +0.93 |
| Emerging × Financials & Banking | 1/N equal weight | 67 | 47 | +10.1% | 19.5% | 0.52 | -23.8% |  |
| Emerging × Financials & Banking | MPT (mean-variance) | 67 | 47 | +12.6% | 32.2% | 0.49 | -44.5% | -0.16 |
| Emerging × Healthcare & Biotech | 1/N equal weight | 67 | 12 | +15.9% | 20.3% | 0.75 | -12.6% |  |
| Emerging × Healthcare & Biotech | MPT (mean-variance) | 67 | 12 | +13.0% | 30.4% | 0.49 | -20.2% | -1.48 |
| Emerging × IT & Software | 1/N equal weight | 67 | 44 | +16.5% | 31.0% | 0.60 | -45.2% |  |
| Emerging × IT & Software | MPT (mean-variance) | 67 | 44 | +13.6% | 34.1% | 0.50 | -29.9% | -0.54 |
| Emerging × Industrials & Real Estate | 1/N equal weight | 67 | 34 | +16.1% | 26.1% | 0.65 | -29.8% |  |
| Emerging × Industrials & Real Estate | MPT (mean-variance) | 67 | 34 | +9.3% | 30.9% | 0.39 | -29.3% | -1.27 |

z > 1.96 would mean MPT's Sharpe ratio is clearly higher than 1/N's; z < −1.96 clearly lower.

Caveats: the universe is today's largest companies (survivorship lifts every model's past results equally); forecasts extrapolate the last five years; research output, not investment advice.
