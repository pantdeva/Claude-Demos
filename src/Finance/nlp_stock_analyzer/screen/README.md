# 14-index model screen

Picks the 25 strongest companies in each of 14 stock indexes on fundamentals, runs the seven quant models on each, and serves the results as a local web dashboard.

Indexes: Dow Jones, S&P 500, NASDAQ Composite, NYSE Composite, FTSE 100, DAX, CAC 40, EURO STOXX 50, Nikkei 225, Hang Seng, BSE Sensex, Nifty 50, KOSPI, S&P/ASX 200.

## Run order

```bash
cd src/Finance/nlp_stock_analyzer/screen
python fetch.py          # prices since 2011 + fundamentals + FX from Yahoo Finance (~15 min, cached in cache/)
python select_top.py     # composite score per index → selection.json
python run_models.py     # 7-model backtest per stock (~30 s each, 2 at a time) → results/
python build_app.py      # → app/index.html and app/data.json
python serve.py          # opens http://localhost:8000
```

`serve.py --host 0.0.0.0` lets other devices on your network open it at `http://<your-computer's-IP>:8000`.

The built dashboard is committed in `app/`, so `python serve.py` works straight away without rerunning the pipeline.

Local cash rates (`cache/rates/*.csv`) come from FRED: US T-bills (DTB3, also used for Hong Kong), OECD 3-month interbank rates for the UK, euro area, Japan, Korea and Australia, and India's call-money rate. Download them with:

```bash
mkdir -p cache/rates
for p in USD:DTB3 GBP:IR3TIB01GBM156N EUR:IR3TIB01EZM156N JPY:IR3TIB01JPM156N \
         KRW:IR3TIB01KRM156N AUD:IR3TIB01AUM156N INR:IRSTCI01INM156N; do
  curl -s "https://fred.stlouisfed.org/graph/fredgraph.csv?id=${p##*:}" -o cache/rates/${p%%:*}.csv
done
```

## Files

| File | What it does |
|---|---|
| `pools.json` | Candidate members per index (full lists for small indexes, largest 30–120 for big ones) |
| `fetch.py` | Downloads and caches prices, fundamentals and FX |
| `select_top.py` | Scores market value, revenue, revenue growth and net margin; keeps the top 25 per index |
| `run_models.py` | Backtests GBM, Black-Scholes-Merton, GARCH, ARIMA, Merton jumps, bootstrap Monte Carlo and MPT on each stock |
| `build_app.py` | Combines everything into the dashboard |
| `app_template.html` | Dashboard page |
| `serve.py` | Local web server for `app/` |

## Data checks

- A prior-year revenue under a quarter of the current year (or growth above 500%) is treated as a bad data point; growth falls back to a 2-year average.
- Net margins above 100% (holding and investment companies, revaluation gains) are shown but left out of the score.
- One-day price spikes that reverse the next day are removed before modelling.

For research and education only. Not investment advice.
