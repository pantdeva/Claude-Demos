# Stock Finder and Analyzer

Local research service that classifies listed companies across world exchanges (Stage 0), finds new leads from news and IPO pipelines (Stage 1) and values them with a Module 13 integrated financial model (Stage 2). See [PLAN.md](PLAN.md) for the full design and milestones.

**Status:** All five milestones are built: Stage 0 classification, the model leaderboard and growth predictions, the Stage 1 company finder, the Stage 2 company analyzer, and the dashboard with service packaging.

**To install on your computer, follow [INSTALL.md](INSTALL.md).**

## Quick start

```bash
cd "src/Finance/Stock Finder and Analyzer"
pip install -r requirements.txt
python -m sfa doctor                       # checks Python, packages, settings, network, data
python -m sfa all                          # universe → prices → fundamentals → classify (≈1–2 h first time)
python -m sfa show TSM                     # one company's classification
python -m sfa models                       # Milestone 2: walk-forward forecasts, leaderboard, predictions (≈3–4 h first time)
python -m sfa finder                       # Milestone 3: news → rules A–D → leads with routes
python -m sfa leads -n 20                  # current top listed leads (also --kind new_listing / ipo_pipeline)
python -m sfa analyze                      # Milestone 4: Module 13 model + valuation for the top leads
python -m sfa analyze INFY.NS 7203.T       # …or for any symbols
python -m sfa start                        # dashboard (http://localhost:8000) + background scheduler
```

Results go to `exports/`: `companies.csv` (one row per company, every classification), `listings.csv` (every listing with its structure), `classification.json` (with the numbers behind each label) and `summary.md` (counts).

Settings go in `sfa.env` (copy `sfa.env.example`; ignored by Git) or in environment variables:

| Variable | Used for |
|---|---|
| `NEWSAPI_KEY` | NewsAPI deep-dive searches on the best leads. Never put the key in a file in this repo. |
| `SFA_FINBERT_DIR` | Folder with the FinBERT weights (otherwise `db/models/finbert`, downloaded on first use, ~440 MB) |
| `SFA_DB` | Use a different database file |
| `SFA_SEC_USER_AGENT` | SEC EDGAR look-ups of US companies' country of incorporation, e.g. `"Your Name you@example.com"` (SEC requires contact details). |

## Commands

| Command | What it does |
|---|---|
| `python -m sfa init` | Create `db/sfa.sqlite` |
| `python -m sfa universe [--limit N] [--only SYM …]` | Resolve seed tickers into companies and all their listings |
| `python -m sfa prices` | Daily prices since 2005 for home listings and benchmark indexes |
| `python -m sfa fundamentals` | Market value, revenue, earnings, equity, shares |
| `python -m sfa classify` | Classify everything and write `exports/` |
| `python -m sfa news` / `feeds` | Poll the news feeds once / show feed health |
| `python -m sfa service [--once]` | Background scheduler (jobs in `sfa/config/jobs.yaml`) |
| `python -m sfa jobs` | Job schedule and last runs |
| `python -m sfa web [--host H] [--port P]` | Dashboard only, at http://localhost:8000 |
| `python -m sfa start [--host H] [--port P]` | Dashboard and scheduler together (what start-on-boot runs) |
| `python -m sfa notify pair\|test\|run\|log` | Phone notifications: pairing code and link, test message, one pass, recent messages |
| `python -m sfa doctor` | Checks Python, packages, settings, reachable data sources, FinBERT weights, disk space and database |
| `python -m sfa models [--jobs N] [--only SYM …]` | Walk-forward forecasts (new dates only), leaderboard, MPT vs 1/N, growth predictions, exports |
| `python -m sfa leaderboard` | Rebuild the leaderboard and exports from stored forecasts (seconds) |
| `python -m sfa finder [--step news\|ipo\|leads\|all]` | Stage 1: collect and score news, IPO pipeline, rules A–D, leads, routes, exports |
| `python -m sfa leads [--kind …] [-n N]` | Show current leads |
| `python -m sfa analyze [SYMBOL …]` | Stage 2: Module 13 integrated model and valuation (default: top 25 leads and new listings) |

## Stage 0 classification

| Heading | Labels | How |
|---|---|---|
| 1. Market development | Developed / Emerging / Frontier / Standalone, by MSCI (primary), FTSE Russell and S&P DJI | Home exchange's country; dated events so past labels can be looked up (`config/market_classification.yaml`) |
| 2. Listing structure | Domestic / Cross-listed (foreign ordinary) / Depositary receipts; per listing: primary, domestic secondary, foreign ordinary, ADR, GDR, CDR, SDR, BDR, OTC ADR, OTC ordinary | All listings found by Yahoo search and matched by legal name; home listing chosen by statement currency, seed and overrides; ADR ratio from price ÷ home price in USD; GDR from the London International Order Book; domicile from overrides or SEC EDGAR |
| 3. Industry | Six groups: IT & Software; Financials & Banking; Healthcare & Biotech; Consumer Discretionary & Staples; Energy, Materials & Utilities; Industrials & Real Estate | Yahoo sector → GICS sector → group, with industry overrides (`config/sectors.yaml`) |
| 4. Stock level | Cap band (USD; SEBI rank band for India), Growth / Blend / Value, Cyclical / Defensive, common / preferred | Style score = z(revenue growth) − mean z(earnings, book and sales yield) among peers in the same market class × sector group; cyclical/defensive from super-sector, industry and 3-year weekly beta to the home index; preferred lines by exchange symbol rules |

Every label is stored with the numbers and rule behind it (`stock_tags.detail`) and a history row whenever it changes (`stock_tag_history`).

## Stage 0 model leaderboard (Milestone 2)

Nine forecasting models are compared on every company's home listing:

- the six quant models from the earlier work: GBM, Black-Scholes-Merton, GARCH(1,1)-t, ARIMA, Merton jump-diffusion and bootstrap Monte Carlo;
- three research baselines: a zero-drift random walk, EWMA volatility with a shrunk drift, and GJR-GARCH-t. The shrunk drift is pulled towards the cash rate plus an equity risk premium; GJR-GARCH-t lets volatility rise more after falls.

| Step | How |
|---|---|
| Walk-forward | Every ~6 months since 2010, each model is fitted on the previous 5 years only and forecasts the 3-month and 1-year return distribution. Settings are in `sfa/config/models.yaml`; set `step_days: 63` for quarterly dates. |
| Scoring | CRPS of the whole forecast distribution (main loss), direction hit rate, 90% interval coverage and bias |
| Baselines | 3 months: GJR-GARCH-t in emerging markets, EWMA with shrunk drift elsewhere. 1 year: EWMA with shrunk drift. |
| Promotion | A model replaces the baseline only with lower CRPS and a Diebold–Mariano t at or above the Bonferroni-corrected 5% level for the number of candidates (≈ 2.73 for 8). The test uses Newey–West variance for overlapping horizons and the Harvey–Leybourne–Newbold small-sample correction. |
| Groups | Every company, exchange, sector group, market class and cell (market class × sector group), and all companies together |
| MPT | Mean-variance portfolios of each cell's largest stocks against the 1/N equal-weight benchmark, rebalanced quarterly in US dollars, with Memmel's test of the Sharpe-ratio difference |
| Predictions | 3-month and 1-year expected return, median, 5–95% range and chance of beating cash. The model comes from the company's own record if it shows a clear win, otherwise from its cell, then its market class. Stored as `growth_3m` / `growth_1y`. |

Outputs in `exports/`: `leaderboard.md` (readable summary), `leaderboard.csv` (every group × horizon × model), `model_choice.csv`, `predictions.csv`, `portfolio_tests.csv`. Cash rates come from FRED for each currency; TWD uses a flagged fixed rate.

## Stage 1 company finder (Milestone 3)

| Step | How |
|---|---|
| Collect | RSS feeds of the 12 news sites, plus SEC EDGAR S-1/F-1 filings, SEBI and Google News IPO searches. Yahoo Finance news is fetched for about 120 companies an hour, rotating through the universe. NewsAPI deep dives run on the best leads when `NEWSAPI_KEY` is set. |
| Score | FinBERT (NumPy version of ProsusAI/finbert): P(positive) − P(negative), from −1 to +1 |
| Link | Stories are linked to companies by Yahoo's related-ticker tags, by tickers in the headline such as "(TSM)", and by names and aliases (`config/aliases.yaml`); one-word names next to generic corporate words are rejected, so "Reliance Steel" is not Reliance Industries. They are linked to industries by supplier and customer terms (`config/industry_links.yaml`, 74 industries plus 11 sector defaults). |
| Rules | **A** market sentiment (stories about the company); **B** competition & news releases (its own announcements count positive; its largest same-industry rivals' news counts negative); **C** manufacturing industry (its supply chain); **D** customers (its end markets). Each rule is a recency-weighted average with a 3-day half-life; the composite weights them 30/25/20/25. |
| IPO pipeline | Planning / filed / priced / listed stages are read from headlines and filing feeds (`config/finder.yaml`). Names are looked up on Yahoo; a company in its first year of trading gets a **peer-proxy forecast**: an equal-weight index of its largest same-industry peers, rescaled to its own volatility, forecast with the model the leaderboard chose for its cell. |
| Leads | Listed: ½ news composite + ½ quant-model signal, where the model signal is the expected 1-year excess return over its spread (Milestone 2 chosen model). New listings: IPO news + peer-proxy model. IPO pipeline: IPO-news sentiment weighted by the number of separate stories. |
| Routes | Indian-resident rules in `config/routes.yaml`, each dated. In order: NSE/BSE directly; US listing or ADR under LRS; home market under LRS (China A-shares through Northbound Stock Connect, H-shares); country ETF; sector ETF. Unlisted companies: the IPO application route, with SEBI and FEMA/ODI warnings on pre-IPO shares. NSE IFSC Receipts are always marked avoid. |
| Expansion | Markets outside the covered exchanges that the news links to growing industries are suggested for `config/exchanges.yaml` |

Outputs in `exports/`: `leads.md`, `leads.csv`, `ipo_pipeline.csv`, `news_signals.csv`, `expansion.csv`.

## Stage 2 company analyzer (Milestone 4)

Follows Zerodha Varsity Module 13 (Integrated Financial Modelling) on Yahoo's annual statements, kept in the statement currency and converted to the trading currency at the end. Infosys, for example, reports in USD and trades in INR.

| Module 13 | Here |
|---|---|
| Ch 2–3 historical data | Up to 5 reported years: about 40 income-statement, balance-sheet and cash-flow lines, with derived lines noted when missing |
| Ch 4–5 assumptions | Rolling 3-year averages: EBITDA margin; depreciation as % of opening net block; asset turnover; inventory, receivable and payable days (average balance ÷ annual flow × 365); tax rate; payout; interest ÷ average debt. Revenue growth starts at the historical CAGR and fades to terminal growth. |
| Ch 6–11 schedules | Revenue model, capex and depreciation (net block from asset turnover), working capital, debt held flat, reserves (equity + profit − dividends) |
| Ch 12–13 projections | 5-year P&L, balance sheet and indirect cash flow. The balance sheet must balance every year: other assets and liabilities are held, and cash comes from the cash flow. |
| Ch 15 free cash flow | FCFF = EBIT(1 − t) + D&A − capex − ΔNWC |
| Ch 16 cost of equity | CAPM: Ke = Rf + β·ERP, with Rf the local 10-year government yield (FRED), β the 3-year weekly beta to the home index (Blume-adjusted), and ERP from Damodaran's country file when reachable, otherwise config (flagged) |
| Ch 17 WACC and terminal value | Market-value weights, after-tax cost of debt (tax shield); TV = FCFF₅(1 + g)/(WACC − g), with g = the inflation target capped at Rf |
| Ch 18 fair value | EV = Σ PV(FCFF) + PV(TV); equity = EV − debt + cash − minority; ÷ shares; compared with the market price; WACC × g sensitivity table |
| Ch 14 other methods | Relative valuation (median peer P/E, EV/EBITDA, P/B, EV/Sales; P/E and P/B only for financials); option-based check (Merton model) for levered or loss-making companies |

Banks and insurers use the justified price-to-book model, P/B = (ROE − g)/(Ke − g), instead of FCFF. The verdict compares the combined fair value (½ DCF or P/B model + ½ peer multiples) with the price: Undervalued above +15%, Overvalued below −15%.

Each report also carries the company's Stage 0 categories, the Milestone 2 3-month and 1-year growth forecasts, and the 5-year revenue and EPS growth from the projection. It flags weak spots, for example:
- debt over half of capital (captive finance arms);
- terminal value above 85% of EV;
- approximate risk-free rates (CN, TW);
- negative projected FCFF.

Outputs: `exports/analysis/<SYMBOL>.md` (readable report), `exports/analysis/<SYMBOL>.xlsx` (the model sheet by sheet: Summary, Assumptions, P&L, Balance sheet, Cash flow, DCF, Peers) and `exports/analysis_summary.csv`. Settings are in `sfa/config/analyzer.yaml`.

## Dashboard and service (Milestone 5)

`python -m sfa start` serves the dashboard at http://localhost:8000 and runs every job on its schedule (`sfa/config/jobs.yaml`).

| Page | Shows |
|---|---|
| Overview | Counts, top leads, chosen models, verdicts, last job runs |
| Leads | Listed / new listings / IPO pipeline with rules A–D, model signal, verdict and best Indian-resident route |
| Company | Stage 0 categories, price chart, growth, news evidence, routes, Module 13 valuation with report and Excel model, model record; **Analyze now** |
| Models | Leaderboards and MPT vs 1/N |
| Markets | Classification maps, expansion suggestions, IPO events |
| Service | Settings detected, schedule, runs, feed health |

**Phone notifications:** the `notify` job (every 30 min) sends Firebase push messages to the **SFA Notifier** Android app in `android/`. The events are new or rising top leads, IPO pipeline changes, valuation verdict changes, a daily digest at 08:45, and failed jobs or stale data. Quiet hours run 22:00–07:00. The app keeps an alert history, opens the dashboard, and warns when the computer goes quiet. Setup is in [ANDROID.md](ANDROID.md); commands: `python -m sfa notify pair|test|run|log`.

Start-on-boot scripts are in `deploy/`: Windows Task Scheduler (`install_task.ps1`), macOS launchd (`install_launchd.sh`) and Linux systemd user service (`install_systemd.sh`). Each restarts the app if it stops and logs to `logs/sfa.log`. See [INSTALL.md](INSTALL.md).

## Data sources

**Market data** (`config/data_sources.yaml`): Yahoo Finance (prices, fundamentals, listings) is the main source. SEC EDGAR provides US company facts, FRED provides interest rates, the ECB provides exchange-rate checks and Damodaran provides country risk premiums. Any source that fails is skipped, and its last cached data is used.

**News** (`config/news_sources.yaml`, used from Milestone 3):

| Global | India |
|---|---|
| Bloomberg, Financial Times, The Wall Street Journal, Reuters (via Google News; no public RSS), Yahoo Finance, MarketWatch, The Economist | The Economic Times, Mint, Moneycontrol, Pulse by Zerodha, Investing.com India |

Plus NewsAPI for deep dives on individual leads. Paywalled sites contribute headlines and summaries only. When a site's feed fails three times in a row, it is read through Google News limited to that domain instead. `python -m sfa feeds` shows which feeds are working.

## Adding an exchange or companies

Add the exchange to `sfa/config/exchanges.yaml` (Yahoo suffix, exchange codes, country, benchmark), and add tickers to `sfa/config/universe_seeds.yaml`. Correct any misread home listing, domicile or share type in `sfa/config/overrides.yaml`. If Yahoo has too little history for an exchange's index, beta is measured against an equal-weight index of that exchange's stocks in the universe.

## Tests

```bash
python tests/test_stage0.py && python tests/test_models.py && python tests/test_finder.py && python tests/test_analyzer.py && python tests/test_web.py && python tests/test_notify.py
```

For research and education only. Not investment advice. Yahoo, MSCI and FTSE data carry licence limits: fine for personal use, not for redistribution.
