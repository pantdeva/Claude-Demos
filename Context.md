# Session Context (16–18 Oct 2026, IST)

Record of the working sessions with Claude that built this repository: GitHub setup, an STA (Static Timing Analysis) learning kit, an NLP stock analyzer, a seven-model quantitative comparison, a world top-100 company list and a 14-index screening dashboard. Secrets (the NewsAPI key) are deliberately left out.

---

## 1. Repository and branches

- **Repository:** `pantdeva/Claude-Demos` (the old `claude-demos` URL still redirects).
- GitHub is linked through Claude's GitHub integration on claude.ai.
- **Default-repo skills:** `default-git-repo` was changed to "no default repo"; `demos-default-repo` still names `pantdeva/Claude-Demos`.

| Branch | Contents |
|---|---|
| `main` | Folder skeleton: `src/Finance`, `src/ML`, `src/Electronics` (commit `6c5fd86`) |
| `STA` | `4654680` "First Stage STA repo bringup": two STA decks |
| `ML` | Everything in sections 3–7 (finance tools live in `src/Finance/nlp_stock_analyzer/`) |

Key ML-branch commits: `f2463ea` "Financial Prediction Tool Phase 1", `d8ca5f0` move to `src/Finance`, then the quant, basket, top-100 and 14-index work.

**Tag `V2.0.0`** ("Financial Prediction Tool Phase 1") could not be pushed from the session (tag pushes returned HTTP 403). Create it on GitHub: Releases → Draft a new release → tag `V2.0.0` on the ML branch.

---

## 2. STA learning kit (branch `STA`)

Location: `src/Electronics/STA KB/Ramp/`

- Transcribing the YouTube "STA Series" (Chip Design with Rashid, playlist `PL0-xus8sJBCTw1aDsx3RXQv3D8MfYJ602`) was dropped because YouTube blocks automated transcripts. A web-researched plan was built instead, mapped to the playlist video titles supplied (weeks 1, 2, 5–8, 10–12) by title only.
- **`STA_Ramp_Up_3_Day_Plan.pptx`** (14 slides): Day 1 foundations and inputs, Day 2 running STA, Day 3 margins and full chip; playlist mapping; six kinds of SDC constraints; tool capability table (PrimeTime, Tempus, Fusion Compiler/ICC II, Genus/Innovus, Aprisa, OpenSTA, Path FX); modelling stack (NLDM→CCS/ECSM, wire-load→SPEF, OCV→AOCV→POCV/SOCV→LVF, ETM/ILM).
- **`Running_PrimeTime.pptx`** (11 slides): environment setup, launching `pt_shell`, six-step run flow, minimal script, sanity checks, reports, sessions. Commands come from public university labs; confirm with `man <command>`.
- Core reading: Bhasker & Chadha, *Static Timing Analysis for Nanometer Designs*; Liberty User Guide 2017.06; tool documentation.

---

## 3. NLP stock analyzer

Location: `src/Finance/nlp_stock_analyzer/` (`app.py` Streamlit dashboard, `run.py` CLI, `stock_analyzer/`, `config/companies.yaml`).

- **News:** NewsAPI `/v2/everything` (free plan: 100 requests/day, one month back, 24-hour delay, development use only). Key supplied via `NEWSAPI_KEY`; regenerate the one shared in chat.
- **NLP:** FinBERT (`ProsusAI/finbert`); `finbert_numpy.py` runs the same weights without PyTorch.
- **Four factors:** market sentiment, competition and news releases (competitor news flipped), manufacturing industry, customers. Recency-weighted (3-day half-life); Bullish ≥ +0.15, Bearish ≤ −0.15.
- **Relevance fixes:** case-sensitive capitalised terms, per-company `context`/`exclude` words, deal-site source filter, syndicated headlines counted once, hour-rounded cache.

Live results (7 days to 16 Oct 2026, saved in `reports/sentiment/`):

| | NVDA | Tata Steel | Micron |
|---|---|---|---|
| Composite | +0.14 Neutral | +0.26 Bullish | −0.06 Neutral |
| Market sentiment | +0.10 | +0.06 | −0.32 |
| Competition & releases | +0.15 | −0.20 | +0.15 |
| Manufacturing | +0.32 | +0.45 | +0.13 |
| Customers | +0.05 | +0.83 | −0.09 |

Micron's competition score is inflated: competitors fell in the same sector sell-off and their losses were flipped to positives. A per-company "competitor news as sector signal" option was suggested, not built.

---

## 4. Seven-model quant comparison

Code: `stock_analyzer/quant/` (`models.py`, `backtest.py`, `portfolio.py`, `report.py`), `quant_run.py`, `quant_basket.py`, Streamlit page `pages/2_Quant_Models.py`. NumPy/SciPy only; 31 tests in `tests/test_quant.py` check each model recovers known parameters from simulated data.

Models: GBM, Black-Scholes-Merton (risk-neutral; option pricing and implied vol), GARCH(1,1) with Student-t errors, ARIMA (order by AIC), Merton jump-diffusion, Monte Carlo block bootstrap, and mean-variance MPT (stock + index + cash).

Walk-forward method: at each forecast date every model is fitted on the previous 5 years only, forecasts 3-month and 1-year returns, and sets a stock/cash position ("sized" by expected excess return ÷ variance, or all-in "signal" when the odds of beating cash exceed 50%). Results are compared with buy & hold.

### NVIDIA, 2004–2026 (`reports/quant_nvda/`)
- No model beat holding NVIDIA (37%/yr, Sharpe 0.86, worst drop −85%).
- 3 months: GBM (sized) Sharpe 0.83, 27%/yr, worst drop −60%. 1 year: GBM/ARIMA (signal) 33%/yr, Sharpe 0.82.
- GARCH gave the most accurate forecasts; BSM never bought (risk-neutral by design).

### Basket of 11 stocks, 1999–2026 (`reports/basket/`)
INTC, C, CSCO, MU, XOM, PG, KO, Tata Steel, Infosys, S&P 500, NVDA.
- No model reliably beat holding; GARCH (signal) ranked best at both horizons, the Monte Carlo bootstrap second and the most accurate forecaster.
- Position sizing acted as insurance: worst drop cut by a median 10–15 points (3 months) and about 25 points (1 year), costing 3–4 points of growth a year.
- MPT was best on the decliners (Citigroup, ExxonMobil, Intel); jump/GARCH helped on Micron.

---

## 5. World top 100 companies (`reports/top100/`)

Ranked by market value on 18 Oct 2026 (companiesmarketcap.com), tagged with index membership checked against 2026 changes (SpaceX into the Nasdaq-100 on 7 Jul 2026, not yet S&P 500; Alphabet into the Dow 29 Jun 2026; Marvell into the S&P 500 22 Jun 2026; Walmart replaced AstraZeneca in the Nasdaq-100 Jan 2026; CXMT listed on the STAR Market Jul 2026).
- Combined value $64.1T; 61 US companies hold 76%; top 10 hold 47%.
- No Indian company in the top 100 (Reliance ≈ $173B).

---

## 6. 14-index model screen (`src/Finance/nlp_stock_analyzer/screen/`)

Indexes: Dow, S&P 500, NASDAQ Composite, NYSE Composite, FTSE 100, DAX, CAC 40, EURO STOXX 50, Nikkei 225, Hang Seng, Sensex, Nifty 50, KOSPI, ASX 200.

Pipeline: `fetch.py` → `select_top.py` → `run_models.py` → `build_app.py` → `serve.py` (see `screen/README.md`).

- **Selection (composite score):** equal-weight percentile ranks of market value (USD), trailing 12-month revenue, revenue growth and net margin; top 25 per index. Full member lists for the small indexes; largest 30–120 members for the big ones. 276 unique companies.
- **Data checks:** IAG.AX's corrupt 2025 revenue replaced by a 2-year average; net margins above 100% (Prosus, Goodman) shown but not scored; one-day reversing price spikes removed.
- **Models:** 10-year backtest (prices since 2011, quarterly forecast dates since 2016) plus today's forecasts; local cash rates from FRED (US T-bills, also for Hong Kong; OECD 3-month rates for UK, euro area, Japan, Korea, Australia; India call-money rate).
- **Coverage:** 262 backtested, 13 newer listings forecast-only (flagged), SpaceX not modelled.

Findings:
- GARCH (signal) was the best strategy in 10 of 14 indexes; India and Korea favoured Monte Carlo (3 months) and GBM (1 year); Hang Seng favoured GBM/jump models.
- Models rarely beat holding in the US (top strategy beat holding on at most 2 of 22–25 stocks); better in Europe and India (8/25 FTSE, 6/25 CAC, 7/24 Nifty at 3 months).
- 118 of 332 one-year "best strategies" simply matched holding (labelled "Hold").
- Median 1-year model upside: Nikkei +33%, US ≈ +20%, Hang Seng +7% (extrapolates the last 5 years).
- Index levels on 16 Oct 2026 matched the figures supplied (Dow 52,002.41; S&P 500 7,659.44; NASDAQ 26,140.03; Nikkei 65,324.29; Sensex 74,729.27; Nifty 23,146.15).

Dashboard: `screen/app/index.html` (served at http://localhost:8000 by `python serve.py`) and `screen/app/dashboard_mobile.html` (single file for phones, no server needed).

---

## 7. Published pages (private claude.ai links)

| Page | Link |
|---|---|
| NVDA model comparison | https://claude.ai/artifact/EYpXyk2nUR2TdUfBedARJx |
| Quant model basket test | https://claude.ai/artifact/Se99eJdTSMLcn2qpNA5Bk9 |
| World's top 100 companies | https://claude.ai/artifact/E4xPKDFs6fuo5NVjFuyywc |
| Global index model screen | https://claude.ai/artifact/Nx1jxnb7iX56qRNfvj79Bj |

The same pages are saved as HTML under `src/Finance/nlp_stock_analyzer/reports/` and `screen/app/`.

---

## 8. Environment notes

- Network allowlist (claude.ai Settings → Capabilities) was extended to newsapi.org, huggingface.co, *.hf.co, fred.stlouisfed.org and Yahoo Finance; stooq.com stayed blocked. Package installs from PyPI were blocked, so PyTorch, transformers and Streamlit could not run in the session.
- An earlier version of this file was emailed to mitul.sharma160696@gmail.com on 16 Oct 2026.

---

## 9. Open items

1. Create tag `V2.0.0` on GitHub.
2. Optional: per-company "competitor news as sector signal" option (helps Micron).
3. Optional: update or disable the `demos-default-repo` skill if no default repo is wanted.
4. Optional: merge `STA` and `ML` into `main` via pull requests.
5. Regenerate the NewsAPI key that was shared in chat.

All results are research output, not investment advice.
