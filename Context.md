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
| `stock-finder` | Section 8: Stock Finder and Analyzer (branched from `ML`) |

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

## 8. Stock Finder and Analyzer (branch `stock-finder`)

Location: `src/Finance/Stock Finder and Analyzer/` (design in `PLAN.md`, usage in `README.md`). Three stages: Stage 0 company backend (classification and growth prediction), Stage 1 company finder (news-driven leads using the seven quant models, with investment routes for an Indian resident), Stage 2 company analyzer (Module 13 integrated financial model). It runs as a service on the user's computer, with RSS feeds plus NewsAPI for news.

**Milestone 1 (done):**
- Python package `sfa` with a SQLite database and a Yahoo data layer, plus SEC EDGAR look-ups of where US-listed companies are incorporated.
- RSS reader for the 12 news sites the user named: Bloomberg, FT, WSJ, Reuters (via Google News), Yahoo Finance, MarketWatch, The Economist, Economic Times, Mint, Moneycontrol, Pulse by Zerodha and Investing.com India. A feed that fails three times in a row is replaced by a Google News search of its site.
- Scheduler service, command line and 26 offline tests.
- Classification run on 18 Oct 2026: 858 seeds became 826 companies with 2,221 listings. Results are in `exports/`.
  - MSCI market class: 511 Developed, 315 Emerging. FTSE Russell and S&P differ for Korea.
  - Listing structure: 592 Domestic, 133 Cross-listed, 101 with depositary receipts (ADR, GDR, CDR, SDR).
- Fixes made during the run:
  - Name matching is strict: Reliance Industries ≠ Reliance Inc, and Compass Group ≠ Compass Inc.
  - Canadian CDRs of US stocks are labelled as depositary receipts, not home listings.
  - A Xetra, Madrid or Copenhagen listing becomes the home when the company reports in that currency (SAP, Santander, Novo Nordisk).
  - Saudi beta is measured against an equal-weight index built from the Saudi stocks in the universe, because Yahoo has almost no history for ^TASI.SR.
- Known limits:
  - ADR ratios measured from prices include the ADR's premium (TSMC shows 6 although one ADR is 5 shares).
  - The SEBI cap band is ranked within this universe only.
  - The news feeds could not be reached from the cloud workspace; they run on the user's computer.

**Milestone 2 (done; results cover 383 of 826 companies):**
- Nine models compared with walk-forward forecasts:
  - the six earlier quant models;
  - a zero-drift random walk;
  - EWMA volatility with a drift shrunk towards the cash rate plus an equity risk premium;
  - GJR-GARCH-t.
- Method: every ~6 months since 2010, each model is fitted on the previous 5 years only. Forecasts are scored by CRPS.
- Promotion: a model replaces a group's baseline only on a Diebold–Mariano win at the Bonferroni-corrected 5% level (t ≥ 2.73 for 8 candidates).
- Groups: company, exchange, sector group, market class and cell (market class × sector group).
- MPT is tested against 1/N inside each cell.
- The run stopped at the workspace's 2-hour limit after 383 companies (313 developed, 70 emerging). Running `python -m sfa models` on the user's computer resumes the remaining 443.
- Findings:
  - EWMA with shrunk drift has the lowest CRPS at both horizons. Bootstrap Monte Carlo, GBM, ARIMA and Merton follow closely; GARCH, GJR-GARCH, BSM and the random walk do worst.
  - For 3-month forecasts in emerging markets, EWMA beats the GJR-GARCH-t default (skill +8%, DM t 4.9).
  - Only 12 companies (3 months) and 1 (1 year) keep a model of their own after the multiple-testing correction.
  - MPT never beats 1/N by a clear margin in any of the 12 cells.
- Growth predictions (3 months and 1 year) for 822 companies, from each company's chosen model. Cash rates come from FRED for each currency; Python's requests needed the default User-Agent for FRED.

**Milestone 3 (done):**
- Stage 1 company finder:
  - news from the 12 requested sites plus SEC, SEBI and Google News IPO feeds (these need the user's computer; the workspace blocks them), Yahoo Finance news (3,906 stories from 119 publishers) and NewsAPI deep dives (needs `NEWSAPI_KEY`);
  - FinBERT scoring and linking to companies and industries;
  - rules A–D;
  - IPO pipeline with peer-proxy forecasts for new listings;
  - leads scored as ½ news + ½ model signal;
  - Indian-resident investment routes;
  - exchange-expansion suggestions.
- Results in `exports/leads.md`: 774 listed leads; one IPO-pipeline lead (the NSE IPO). The top leads include COSCO Shipping (H-shares route), Eli Lilly (US shares under LRS) and Tata Consumer (NSE directly).

**Milestone 4 (done):**
- Stage 2 company analyzer following Zerodha Varsity Module 13 on Yahoo's annual statements:
  - assumptions from rolling averages;
  - revenue, capex/depreciation, working-capital, debt and reserves schedules;
  - 5-year P&L, balance sheet and cash flow, balanced every year;
  - FCFF DCF with CAPM on the local 10-year yield (FRED) and Blume beta (floored at 0.6), market-weight WACC, terminal growth at long-run inflation capped at Rf, and a WACC × g sensitivity table;
  - justified P/B for banks and insurers;
  - peer multiples;
  - a Merton option check for levered firms.
- Combined fair value (½ DCF or P/B + ½ peers) gives a verdict at ±15%.
- Per-company markdown report and Excel model in `exports/analysis/`.
- Top 25 leads analysed: 15 undervalued (mostly Chinese, Hong Kong and Indian state-linked value stocks), 1 fairly valued, 9 overvalued (high-multiple names such as Eli Lilly, Tata Consumer and Indian Hotels, whose growth fades to inflation within the 5-year projection).
- Flags in the reports: approximate risk-free rates (CN, TW), the ERP stand-in until Damodaran's file is reachable, debt-heavy capital structures, and terminal value above 85% of EV.

**Milestone 5 (done):**
- Local dashboard (`python -m sfa web`, http://localhost:8000) with six pages: Overview, Leads, Company (with Analyze now), Models, Markets, Service. It is a JSON API over the SQLite database, works at phone width, and has no external dependencies.
- `python -m sfa start` runs the dashboard and scheduler together.
- `python -m sfa doctor` checks readiness.
- `sfa.env` settings file (ignored by Git) holds the NewsAPI key and SEC contact.
- Start-on-boot scripts for Windows Task Scheduler, macOS launchd and Linux systemd.
- `INSTALL.md` covers every remaining prerequisite: Python ≥ 3.10, a new NewsAPI key, the SEC contact, network allowlist, the first full build (including the remaining 443 companies of the leaderboard), the service, sleep settings and troubleshooting.
- 75 offline tests across five suites (26 Stage 0, 16 models, 13 finder, 11 analyzer, 9 web).

**Phone notifications (after Milestone 5):**
- `sfa/notify` detects events: new or rising top leads, IPO pipeline new names and stage moves, valuation verdict changes or big fair-value moves, a daily digest at 08:45, failed jobs and stale prices.
- Sent every 30 minutes as Firebase Cloud Messaging (HTTP v1) data messages to signed-in phones. The app signs in with Google (Credential Manager → Firebase Authentication) and writes its token to Firestore `users/{uid}/devices/{id}` (rules in `android/firestore.rules`: owner only). The computer reads the registry with the service-account key, checks each user's verified email through Identity Toolkit `accounts:lookup`, sends only to accounts in `SFA_NOTIFY_EMAILS`, and deletes unregistered tokens. The older shared-topic mode remains as `audience: topic`.
- Delivery rules: quiet hours 22:00–07:00 (alerts still go through), at most 8 per pass (extras folded into one), and duplicates suppressed. Everything is logged in `notify_log`.
- A silent heartbeat goes out every 6 hours.
- `android/` holds the Android Studio project **SFA Notifier** (Kotlin, Jetpack Compose, Firebase Messaging, WorkManager): five notification channels, alert history, the dashboard in a WebView, Google sign-in/out, an `sfa://pair?url=` set-up link for the dashboard address, per-type mute, and a watchdog when the computer is quiet for 12 hours.
- It wasn't compiled in the cloud session (Google's Android repositories are blocked there); the user builds it in Android Studio.
- Setup guide in `ANDROID.md`: Android Studio per OS, Firebase project, Google sign-in provider, SHA-1 fingerprint, google-services.json, Firestore and rules, service-account key, build/run/APK/update, sign-in and test, Tailscale, battery settings, troubleshooting, security model.
- New settings: `SFA_FCM_SERVICE_ACCOUNT`, `SFA_NOTIFY_EMAILS`, `SFA_DASHBOARD_URL`, `SFA_HOST`.
- 12 more tests (87 in total).

---

## 9. Environment notes

- Network allowlist (claude.ai Settings → Capabilities) was extended to newsapi.org, huggingface.co, *.hf.co, fred.stlouisfed.org and Yahoo Finance; stooq.com stayed blocked. Package installs from PyPI were blocked, so PyTorch, transformers and Streamlit could not run in the session.
- An earlier version of this file was emailed to mitul.sharma160696@gmail.com on 16 Oct 2026.

---

## 10. Open items

1. Create tag `V2.0.0` on GitHub.
2. Optional: per-company "competitor news as sector signal" option (helps Micron).
3. Optional: update or disable the `demos-default-repo` skill if no default repo is wanted.
4. Optional: merge `STA` and `ML` into `main` via pull requests.
5. Regenerate the NewsAPI key that was shared in chat.

All results are research output, not investment advice.
