"""Streamlit dashboard for the NLP stock analyzer.

Run:  streamlit run app.py
Needs a NewsAPI key in the NEWSAPI_KEY environment variable, in
.streamlit/secrets.toml (NEWSAPI_KEY = "..."), or typed into the sidebar.
"""

from __future__ import annotations

import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from stock_analyzer import FACTORS, Analyzer, load_config
from stock_analyzer.analyzer import AnalysisResult
from stock_analyzer.news import NewsAPIClient, NewsAPIError

CONFIG_PATH = Path(__file__).parent / "config" / "companies.yaml"
POS, NEG, MID = "#2A9D8F", "#C0392B", "#8A99A6"

st.set_page_config(page_title="NLP Stock Analyzer", page_icon="📈", layout="wide")


@st.cache_data
def get_config(path: str, mtime: float):
    return load_config(path)


@st.cache_resource(show_spinner="Loading FinBERT (first run downloads the model)…")
def get_scorer():
    from stock_analyzer.sentiment import FinBERTScorer
    return FinBERTScorer()


def default_api_key() -> str:
    try:
        return st.secrets.get("NEWSAPI_KEY", "") or os.environ.get("NEWSAPI_KEY", "")
    except Exception:  # no secrets.toml
        return os.environ.get("NEWSAPI_KEY", "")


def fmt(score: float | None) -> str:
    return "—" if score is None else f"{score:+.2f}"


cfg = get_config(str(CONFIG_PATH), CONFIG_PATH.stat().st_mtime)
settings = cfg.settings

# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Analysis")
    tickers = list(cfg.companies)
    ticker = st.selectbox("Company", tickers, format_func=lambda t: cfg.companies[t].label)
    days = st.slider("Look back (days)", 1, 30, settings.lookback_days,
                     help="NewsAPI's free plan covers up to a month back, with a 24-hour delay.")
    api_key = st.text_input("NewsAPI key", value=default_api_key(), type="password")
    run = st.button("Analyze", type="primary", use_container_width=True)

    st.subheader("Factor weights")
    weights = {k: st.slider(label, 0.0, 1.0, float(settings.weights.get(k, 0.25)), 0.05,
                            key=f"w_{k}") for k, label in FACTORS.items()}
    st.caption("Weights are rescaled over factors that have news, so they needn't sum to 1.")

st.title("NLP Stock Analyzer")
st.caption("FinBERT sentiment on NewsAPI headlines across four factors: market sentiment, "
           "competition & news releases, manufacturing industry, and customers.")

if run:
    if not api_key:
        st.error("Add a NewsAPI key in the sidebar (free at newsapi.org).")
        st.stop()
    try:
        with st.spinner(f"Fetching and scoring news for {cfg.companies[ticker].name}…"):
            analyzer = Analyzer(NewsAPIClient(api_key), get_scorer(), settings)
            st.session_state["result"] = analyzer.run(cfg.companies[ticker], days)
    except NewsAPIError as exc:
        st.error(f"NewsAPI error — {exc}")
        st.stop()
    except ImportError:
        st.error("FinBERT needs transformers and torch: pip install -r requirements.txt")
        st.stop()

result: AnalysisResult | None = st.session_state.get("result")
if result is None:
    st.info("Pick a company and press **Analyze**.")
    st.stop()

# ---------------- Headline numbers ----------------
company = result.company
composite = result.composite(weights)
verdict = AnalysisResult.verdict(composite, settings)
st.subheader(company.label)
st.caption(f"News from {result.start:%d %b %Y} to {result.end:%d %b %Y} (UTC) · "
           f"newer articles weigh more (half-life {settings.half_life_days:g} days)")

top = st.columns([1.3, 1, 1, 1, 1])
top[0].metric("Composite", fmt(composite), verdict,
              delta_color="off" if verdict in ("Neutral", "No data")
              else ("normal" if verdict == "Bullish" else "inverse"))
for col, (key, f) in zip(top[1:], result.factors.items()):
    col.metric(f.label, fmt(f.score), f"{f.n_articles} articles", delta_color="off")

for w in result.warnings:
    st.warning(w)

# ---------------- Charts ----------------
left, right = st.columns(2)
bars = pd.DataFrame([{"factor": f.label, "score": f.score, "articles": f.n_articles,
                      "weight": weights[k]} for k, f in result.factors.items()
                     if f.score is not None])
with left:
    st.markdown("**Score by factor**")
    if bars.empty:
        st.write("No relevant news found in this window.")
    else:
        bars["tone"] = ["Positive" if s >= 0 else "Negative" for s in bars["score"]]
        chart = alt.Chart(bars).mark_bar(cornerRadius=3).encode(
            x=alt.X("score:Q", scale=alt.Scale(domain=[-1, 1]), title="Impact on company (−1 to +1)"),
            y=alt.Y("factor:N", sort=list(FACTORS.values()), title=None),
            color=alt.Color("tone:N", scale=alt.Scale(domain=["Positive", "Negative"],
                                                      range=[POS, NEG]), legend=None),
            tooltip=["factor", alt.Tooltip("score:Q", format="+.2f"), "articles", "weight"],
        )
        rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=MID).encode(x="x:Q")
        st.altair_chart(chart + rule, use_container_width=True)

daily = result.daily_frame()
with right:
    st.markdown("**Daily trend**")
    if daily.empty:
        st.write("No dated articles to chart.")
    else:
        trend = alt.Chart(daily).mark_line(point=True).encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("impact:Q", scale=alt.Scale(domain=[-1, 1]), title="Mean impact"),
            color=alt.Color("factor:N", sort=list(FACTORS.values()), title=None,
                            legend=alt.Legend(orient="bottom")),
            tooltip=["date:T", "factor", alt.Tooltip("impact:Q", format="+.2f"), "articles"],
        )
        st.altair_chart(trend, use_container_width=True)

# ---------------- Articles ----------------
st.markdown("**Articles behind the scores**")
frame = result.articles_frame()
tabs = st.tabs([f"{f.label} ({f.n_articles})" for f in result.factors.values()])
for tab, f in zip(tabs, result.factors.values()):
    with tab:
        rows = frame[frame["factor"] == f.label].drop(columns=["factor"])
        if rows.empty:
            st.write("No relevant articles for this factor.")
            continue
        st.dataframe(
            rows, hide_index=True, use_container_width=True,
            column_config={
                "published": st.column_config.DatetimeColumn("Published", format="DD MMM, HH:mm"),
                "url": st.column_config.LinkColumn("Link", display_text="open"),
                "impact": st.column_config.NumberColumn(
                    "Impact", help="Sentiment as it affects the company; competitor news is flipped",
                    format="%+.2f"),
                "sentiment": st.column_config.NumberColumn("FinBERT score", format="%+.2f"),
                "weight": st.column_config.ProgressColumn("Recency weight", min_value=0.0,
                                                          max_value=1.0, format="%.2f"),
            },
        )

st.caption("For research and education only — not investment advice. Headlines and "
           "descriptions only; full article text isn't analysed.")
