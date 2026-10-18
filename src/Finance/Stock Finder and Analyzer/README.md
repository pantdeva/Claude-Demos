# Stock Finder and Analyzer

Local research service that classifies listed companies across world exchanges (Stage 0), finds new leads from news and IPO pipelines (Stage 1) and values them with a Module 13 integrated financial model (Stage 2). See [PLAN.md](PLAN.md) for the full design and milestones.

**Status:** Milestone 1 (Stage 0 foundation and classification) is built. Milestones 2–5 are planned.

## Quick start

```bash
cd "src/Finance/Stock Finder and Analyzer"
pip install requests pyyaml numpy          # the only dependencies so far
python -m sfa all                          # universe → prices → fundamentals → classify (≈1–2 h first time)
python -m sfa show TSM                     # one company's classification
python -m sfa service                      # keep everything refreshed on schedule (Ctrl+C to stop)
```

Results go to `exports/`: `companies.csv` (one row per company, every classification), `listings.csv` (every listing with its structure), `classification.json` (with the numbers behind each label) and `summary.md` (counts).

Optional environment variables:

| Variable | Used for |
|---|---|
| `NEWSAPI_KEY` | NewsAPI deep-dive searches (Milestone 3). Never put the key in a file in this repo. |
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

## Stage 0 classification

| Heading | Labels | How |
|---|---|---|
| 1. Market development | Developed / Emerging / Frontier / Standalone, by MSCI (primary), FTSE Russell and S&P DJI | Home exchange's country; dated events so past labels can be looked up (`config/market_classification.yaml`) |
| 2. Listing structure | Domestic / Cross-listed (foreign ordinary) / Depositary receipts; per listing: primary, domestic secondary, foreign ordinary, ADR, GDR, CDR, SDR, BDR, OTC ADR, OTC ordinary | All listings found by Yahoo search and matched by legal name; home listing chosen by statement currency, seed and overrides; ADR ratio from price ÷ home price in USD; GDR from the London International Order Book; domicile from overrides or SEC EDGAR |
| 3. Industry | Six groups: IT & Software; Financials & Banking; Healthcare & Biotech; Consumer Discretionary & Staples; Energy, Materials & Utilities; Industrials & Real Estate | Yahoo sector → GICS sector → group, with industry overrides (`config/sectors.yaml`) |
| 4. Stock level | Cap band (USD; SEBI rank band for India), Growth / Blend / Value, Cyclical / Defensive, common / preferred | Style score = z(revenue growth) − mean z(earnings, book and sales yield) among peers in the same market class × sector group; cyclical/defensive from super-sector, industry and 3-year weekly beta to the home index; preferred lines by exchange symbol rules |

Every label is stored with the numbers and rule behind it (`stock_tags.detail`) and a history row whenever it changes (`stock_tag_history`).

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
python tests/test_stage0.py        # or: python -m pytest tests -q
```

For research and education only. Not investment advice. Yahoo, MSCI and FTSE data carry licence limits: fine for personal use, not for redistribution.
