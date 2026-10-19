# Stock Finder and Analyzer: development plan

A local service that classifies listed companies across world exchanges, finds new investment leads from news and IPO pipelines, and analyses each lead with quantitative models and a Module 13 integrated financial model. Built for an Indian-resident investor. Research only, not investment advice.

Branch: `stock-finder` (branched from `ML`, so the existing news, FinBERT, quant-model and fundamentals code can be reused).

## Architecture

```
Stock Finder and Analyzer/
  sfa/                 Python package
    config/            exchanges, classification events, sector maps, seeds
    data/              Yahoo prices, fundamentals, search; FX; rates
    classify/          market, listing, sector, fundamental classifiers
    models/            leaderboard over the seven quant models (reuses stock_analyzer.quant)
    finder/            RSS + NewsAPI ingestion, IPO feeds, lead scoring, investment routes
    analyzer/          Module 13 integrated model, DCF, relative and option-style checks
    service.py         scheduler that runs each job on its own timer
    web/               local dashboard (http://localhost:8000)
  db/sfa.sqlite        local database (not committed)
  tests/
```

Database tables: companies, listings, classification_events, stock_tags, prices (cache), fundamentals, news_items, leads, model_results, valuations, job_runs.

## Stages (from the brief)

- **Stage 0, Company Backend:** constantly classifies companies and predicts growth using evaluations and NLP news. Classification headings:
  1. Market development: Developed / Emerging / Frontier / Standalone (MSCI primary; FTSE Russell and S&P DJI shown alongside; every label dated).
  2. Geographic and listing structure: domestic, cross-listing / foreign ordinary, depositary receipt (ADR/GDR).
  3. Industry and sector: GICS sector mapped to six groups (IT & Software; Financials & Banking; Healthcare & Biotech; Consumer Discretionary & Staples; Energy, Materials & Utilities; Industrials & Real Estate).
  4. Stock-level: market-cap band, growth vs value, cyclical vs defensive, common vs preferred.
  Models are compared across market class × sector group × horizon to learn which scheme predicts best where.
- **Stage 1, Company Finder:** leads on companies newly listed, already listed or about to list. NLP monitors news on four rules: (A) market sentiment, (B) competition and company news releases, (C) the manufacturing industry it depends on, (D) its customers. Uses the seven quant models (GBM, Black-Scholes-Merton, GARCH, ARIMA, MPT, Merton jump-diffusion, Monte Carlo). When direct investment is not allowed, an investment-routes engine proposes alternatives for an Indian resident.
- **Stage 2, Company Analyzer:** categorises with the Stage 0 metrics, predicts short- and long-term growth with the best scheme for its cell, and applies Zerodha Varsity Module 13 (historical statements → ratio and rolling-average assumptions → revenue, capex/depreciation, debt and reserves schedules → 5-year projections → cash flow → FCFF, CAPM cost of equity, WACC with tax shield, terminal growth ≈ long-run inflation → DCF fair price vs market price, plus relative and option-based checks).

Starting exchanges: Nasdaq, NYSE, Shanghai, Euronext, Japan Exchange Group, Shenzhen, HKEX, TMX (TSX), NSE India, BSE India, London, Taiwan, Korea Exchange, Saudi Exchange. Smaller exchanges are added through configuration as news shows growing industries there.

## Milestones

| # | Milestone | Delivers |
|---|---|---|
| 1 ✓ | Stage 0 foundation and classification | Package, database, exchange config, company universe (largest companies per exchange), dated market-classification events, listing-structure detection (domestic / cross-listing / ADR / GDR), sector mapping, cap band, growth/value, cyclical/defensive, common/preferred; scheduler skeleton; tests; classification export |
| 2 ✓ | Stage 0 model leaderboard | Seven models run per market class × sector group × horizon (3 months, 1 year); research-based baselines (GJR-GARCH-t short-term in EM, EWMA / random walk for 1-year volatility, shrunk drift, 1/N benchmark); a model replaces a baseline only on a clear out-of-sample win (Diebold–Mariano); growth predictions per stock |
| 3 ✓ | Stage 1 company finder | RSS ingestion (Bloomberg, FT, WSJ, Reuters, Yahoo Finance, MarketWatch, The Economist, ET, Mint, Moneycontrol, Pulse by Zerodha, Investing.com India, plus SEC, SEBI, RBI and HKEX) scored with FinBERT on rules A–D; NewsAPI for deep dives; IPO pipeline (SEC EDGAR S-1/F-1, Nasdaq calendar, SEBI DRHPs, HKEX, JPX; news NLP elsewhere); lead scoring; peer-proxy modelling for new listings; Indian-resident investment-routes engine |
| 4 ✓ | Stage 2 company analyzer | Module 13 integrated model from Yahoo annual statements; live 10-year yields; Damodaran country risk premiums; beta vs local index; WACC; terminal value capped by long-run inflation; fair price and sensitivity table; peer multiples; option-style flag for event-driven companies |
| 5 | Dashboard and service packaging | Local web dashboard (leads, company page, model leaderboard, classification maps); start-on-boot instructions for Windows, macOS and Linux; config for adding exchanges |

## Investment-routes order (Indian resident, October 2026)

1. NSE/BSE listing → buy directly.
2. Foreign company with a US listing or ADR → LRS (USD 250,000 per financial year; TCS 20% on investment remittances above ₹10 lakh) via a US broker or a GIFT City Global Access provider.
3. China A-share → Stock Connect through a Hong Kong broker (not STAR or ChiNext); otherwise an H-share, ADR or China/HK ETF.
4. Market with no direct route → country ETF listed in the US or London.
5. Unlisted / pre-IPO → overseas direct investment (ODI) rules, SEBI warning on unlisted-share platforms, SEBI-registered AIFs.

Never route new money into NSE IFSC Receipts (new buys stopped 30 Jul 2026; dealing ends 1 Feb 2027). Indian international mutual funds are mostly closed to new money because of the overseas cap; check a fund's status and an ETF's premium to NAV before suggesting it.

## Data sources

- Prices, fundamentals, sector/industry, cross-listings: Yahoo Finance chart, fundamentals-timeseries and search endpoints.
- Rates: FRED (US T-bills, OECD 3-month and 10-year yields; India call-money rate).
- Equity risk premiums: Damodaran country risk premium dataset.
- News (config/news_sources.yaml): Bloomberg, Financial Times, The Wall Street Journal, Reuters (through Google News, since Reuters has no public RSS), Yahoo Finance, MarketWatch and The Economist; in India, The Economic Times, Mint, Moneycontrol, Pulse by Zerodha and Investing.com India; plus regulator and exchange feeds (SEC, SEBI, RBI, HKEX). Paywalled sites give headlines and summaries only. A feed that fails three times in a row is replaced by a Google News search of its site. NewsAPI (100 requests/day) is used for deep dives on leads.
- Second sources for market data (config/data_sources.yaml): SEC EDGAR (US company facts and domicile), NSE (Indian prices), ECB and FRED (exchange rates), Damodaran (risk premiums). Yahoo stays the main source; when a source fails, the next one or the last cached data is used.
- IPOs: SEC EDGAR Atom feeds (declared User-Agent, ≤10 requests/second), Nasdaq IPO calendar (undocumented), SEBI draft offer documents, HKEX and JPX new-listing pages.

## Caveats

- MSCI, FTSE Russell and Yahoo data carry licence limits: fine for a personal local tool, not for redistribution.
- Several IPO endpoints are undocumented and may change.
- Rules that change often (LRS/TCS, fund caps, GIFT City, index classifications) are stored with dates and must be reviewed.
- Model evidence is market- and period-specific; the leaderboard only promotes a model on clear out-of-sample wins.
