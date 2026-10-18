# NLP Stock Analyzer

Scores recent news about a stock with **FinBERT** (a finance-tuned BERT model) across four factors and shows the result in a **Streamlit** dashboard. Works for US (NASDAQ/NYSE) and Indian (NSE/BSE) tickers.

| Factor | What it searches | How it counts |
|---|---|---|
| Market sentiment | News mentioning the company | Positive news → positive |
| Competition & news releases | The company's own announcements, plus competitor news | Company releases count as is; **competitor good news counts against the company** |
| Manufacturing industry | Suppliers, inputs and the production side of the industry | Healthy supply → positive |
| Customers | Key customers and end markets | Strong customer demand → positive |

## How the scores work

1. **Fetch** — For each factor, the app builds NewsAPI queries from the words in `config/companies.yaml` and searches headlines and descriptions over the look-back window.
2. **Filter** — Articles that don't actually contain one of the factor's words (whole-word match) are dropped. Duplicates within a factor are removed.
3. **Score** — FinBERT labels each headline + description; the article score is `P(positive) − P(negative)`, from −1 to +1. Competitor articles are flipped (set `competitor_direction: 1` to stop that).
4. **Weight** — Newer articles count more: an article `half_life_days` old counts half as much as one from today.
5. **Combine** — Each factor score is the recency-weighted mean of its articles. The composite is the weighted mean of factors that found news, using the sidebar weights. Above `+0.15` is *Bullish*, below `−0.15` *Bearish*, otherwise *Neutral* (thresholds are configurable).

## Setup

```bash
cd src/Finance/nlp_stock_analyzer
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Get a free key at [newsapi.org](https://newsapi.org/register), then provide it one of three ways:

```bash
export NEWSAPI_KEY=your_key                          # environment variable
# or create .streamlit/secrets.toml with:  NEWSAPI_KEY = "your_key"
# or paste it into the dashboard's sidebar
```

Run the dashboard:

```bash
streamlit run app.py
```

The first run downloads the FinBERT model (`ProsusAI/finbert`, about 440 MB) from Hugging Face. A GPU is used automatically if PyTorch can see one.

### Command line (no Streamlit)

```bash
python run.py NVDA TATASTEEL.NS --days 7      # prints scores, writes results/<ticker>.json and _articles.csv
python run.py --all
```

### Without PyTorch

`stock_analyzer/finbert_numpy.py` runs the same FinBERT weights in plain NumPy. Download `config.json`, `vocab.txt` and `model.safetensors` from the [model page](https://huggingface.co/ProsusAI/finbert/tree/main) into a folder, then:

```bash
python run.py NVDA --scorer numpy --model-dir ./finbert
```

## Quant model comparison

`quant_run.py` backtests seven price models on a stock and builds a dashboard (`results/quant_<TICKER>.html`, also shown on the Streamlit app's **Quant Models** page):

| Model | What it adds |
|---|---|
| GBM | Constant drift and volatility (the baseline) |
| Black-Scholes-Merton | Risk-neutral distribution and option prices; implied-vol solver |
| GARCH(1,1), Student-t | Volatility clustering and fat tails |
| ARIMA | Autoregressive / moving-average structure, order picked by AIC |
| Merton jump-diffusion | Sudden jumps on top of GBM |
| Monte Carlo (bootstrap) | Resamples real past returns, no distribution assumed |
| MPT (mean-variance) | Long-only allocation across the stock, the S&P 500 and cash |

Every month each model is fitted on the previous 5 years only, forecasts 3-month and 1-year returns, and sets an allocation. Forecasts are scored (hit rate, 90% interval coverage, CRPS) and the resulting strategies are compared with buy & hold.

```bash
python quant_run.py --download            # prices from Stooq or Yahoo Finance, T-bill rate from FRED (Yahoo ^IRX fallback)
python quant_run.py --download --step 63  # faster: quarterly forecast dates
```

Everything is NumPy/SciPy only. `tests/test_quant.py` checks each model recovers known parameters from simulated data.

## Adding a company

Add an entry under `companies:` in `config/companies.yaml`:

```yaml
  INFY.NS:
    name: Infosys
    market: India
    language: en
    aliases: [Infosys]
    competitors: [TCS, Wipro, HCLTech]
    manufacturing: [IT services demand, offshore delivery]
    customers: [US banking IT spending, BFSI clients]
```

Pick terms that appear in headlines. Matching rules that keep noise down:

- **Capitalised terms are case-sensitive.** `Intel` won't match "intel sharing" and `SAIL` won't match "sail"; all-lowercase terms like `iron ore` match in any case.
- **`context:`** lists extra words an article must also contain for the competitors, manufacturing or customers group, so `Microsoft` only counts when the story mentions AI, capex, chips and so on.
- **`exclude:`** drops articles containing any of the listed words (Tata Steel excludes "AI infrastructure" so AI data-centre stories don't count as construction demand).
- **`exclude_sources:`** in `settings` drops deal and coupon sites.
- Competitor stories that also name the company stay in market sentiment instead of being flipped, and a syndicated headline counts once per factor.

## NewsAPI limits

- The free Developer plan allows **100 requests a day**, covers articles up to **one month old**, and delivers them with a **24-hour delay** — so a 1-day look-back will usually come back empty on the free plan. It is for development and testing only; any other use needs a paid plan.
- Each analysis makes one request per factor group (about 5 per company). Responses are cached for an hour in `~/.cache/nlp_stock_analyzer` so reruns don't use up quota.
- Coverage of Indian outlets in NewsAPI is thinner than US coverage, so Indian tickers may return fewer articles.

## Tests

The tests run offline with a fake NewsAPI client and a fake scorer, so they don't need a key, PyTorch or Streamlit:

```bash
python -m unittest discover -s tests
```

## Project layout

```
app.py                       Streamlit dashboard
run.py                       Command-line runner
stock_analyzer/finbert_numpy.py  FinBERT in NumPy (no PyTorch)
config/companies.yaml        Tickers, factor terms, weights and thresholds
stock_analyzer/config.py     Loads and validates the YAML
stock_analyzer/factors.py    Builds per-factor NewsAPI queries and relevance filters
stock_analyzer/news.py       NewsAPI client with disk cache
stock_analyzer/sentiment.py  FinBERT scorer
stock_analyzer/analyzer.py   Scoring, recency weighting and composite
tests/test_analyzer.py       Offline unit tests
```

## Limitations

- Only headlines and descriptions are scored, not full article text.
- Sentiment is not a price forecast, and the factor directions are simple rules of thumb. FinBERT scores the tone of a headline, not its effect on this company: "coking coal prices hiked 14%" reads as positive news, though higher input costs hurt a steelmaker.
- Indian companies get far fewer NewsAPI articles than US ones, so their scores rest on a handful of headlines.
- This is for research and education only — **not investment advice**.
