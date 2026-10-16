"""Fetch news per factor, score it with FinBERT, and roll it up into scores.

Factor score   = recency-weighted mean of article scores (signed by direction)
Composite      = weighted mean of the factor scores that have news
Verdict        = Bullish / Neutral / Bearish against the configured thresholds
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd

from .config import Company, Settings
from .factors import FACTORS, FactorGroup, build_factor_groups
from .news import Article, NewsAPIError
from .sentiment import Sentiment, SentimentScorer


@dataclass(frozen=True)
class ScoredArticle:
    article: Article
    factor: str
    group: str
    direction: int
    sentiment: Sentiment
    weight: float

    @property
    def signed(self) -> float:
        """Sentiment as it affects the company (competitor news is flipped)."""
        return self.sentiment.score * self.direction


@dataclass
class FactorResult:
    factor: str
    label: str
    score: float | None
    articles: list[ScoredArticle] = field(default_factory=list)

    @property
    def n_articles(self) -> int:
        return len(self.articles)


@dataclass
class AnalysisResult:
    company: Company
    start: datetime
    end: datetime
    factors: dict[str, FactorResult]
    warnings: list[str] = field(default_factory=list)

    def composite(self, weights: dict[str, float]) -> float | None:
        used = [(weights.get(k, 0.0), f.score) for k, f in self.factors.items()
                if f.score is not None and weights.get(k, 0.0) > 0]
        total = sum(w for w, _ in used)
        return sum(w * s for w, s in used) / total if total else None

    @staticmethod
    def verdict(score: float | None, settings: Settings) -> str:
        if score is None:
            return "No data"
        if score >= settings.bullish:
            return "Bullish"
        if score <= settings.bearish:
            return "Bearish"
        return "Neutral"

    def articles_frame(self) -> pd.DataFrame:
        rows = []
        for f in self.factors.values():
            for a in f.articles:
                rows.append({
                    "published": a.article.published_at,
                    "factor": f.label,
                    "group": a.group,
                    "source": a.article.source,
                    "headline": a.article.title,
                    "url": a.article.url,
                    "finbert": a.sentiment.label,
                    "sentiment": round(a.sentiment.score, 3),
                    "impact": round(a.signed, 3),
                    "weight": round(a.weight, 3),
                })
        cols = ["published", "factor", "group", "source", "headline", "url",
                "finbert", "sentiment", "impact", "weight"]
        df = pd.DataFrame(rows, columns=cols)
        return df.sort_values("published", ascending=False, ignore_index=True)

    def daily_frame(self) -> pd.DataFrame:
        """Mean impact per factor per day, for the trend chart."""
        df = self.articles_frame()
        if df.empty:
            return pd.DataFrame(columns=["date", "factor", "impact", "articles"])
        df["date"] = pd.to_datetime(df["published"], utc=True).dt.tz_localize(None).dt.normalize()
        return (df.groupby(["date", "factor"], as_index=False)
                  .agg(impact=("impact", "mean"), articles=("impact", "size")))


def recency_weight(published: datetime, now: datetime, half_life_days: float) -> float:
    age_days = max(0.0, (now - published).total_seconds() / 86400)
    return 0.5 ** (age_days / half_life_days) if half_life_days > 0 else 1.0


class Analyzer:
    def __init__(self, client, scorer: SentimentScorer, settings: Settings):
        self.client = client
        self.scorer = scorer
        self.settings = settings

    def collect(self, company: Company, start: datetime, end: datetime,
                warnings: list[str]) -> list[tuple[FactorGroup, Article]]:
        """Fetch and relevance-filter articles; one copy per factor per URL."""
        seen: set[tuple[str, str]] = set()
        picked, attempted, failed = [], 0, 0
        for group in build_factor_groups(company, self.settings):
            for query in group.queries():
                attempted += 1
                try:
                    articles = self.client.search(query, company.language, start, end,
                                                  self.settings.max_articles_per_query)
                except NewsAPIError as exc:
                    failed += 1
                    warnings.append(f"{group.name}: {exc}")
                    continue
                for art in articles:
                    # same URL, or the same headline syndicated elsewhere, counts once per factor
                    keys = {(group.factor, art.url),
                            (group.factor, " ".join(art.title.lower().split()))}
                    if art.source.lower() in self.settings.exclude_sources:
                        continue
                    if keys & seen or not group.matches(art.text):
                        continue
                    seen |= keys
                    picked.append((group, art))
        if attempted and failed == attempted:
            raise NewsAPIError("All NewsAPI requests failed. " + " | ".join(warnings[:3]))
        return picked

    def run(self, company: Company, lookback_days: int | None = None,
            now: datetime | None = None) -> AnalysisResult:
        now = now or datetime.now(timezone.utc)
        start = now - timedelta(days=lookback_days or self.settings.lookback_days)
        warnings: list[str] = []
        picked = self.collect(company, start, now, warnings)

        # Score each distinct text once, even if it appears under several factors.
        texts = list(dict.fromkeys(a.text for _, a in picked))
        sentiments = dict(zip(texts, self.scorer.score(texts)))

        factors = {k: FactorResult(k, label, None) for k, label in FACTORS.items()}
        for group, art in picked:
            factors[group.factor].articles.append(ScoredArticle(
                article=art, factor=group.factor, group=group.name,
                direction=group.direction, sentiment=sentiments[art.text],
                weight=recency_weight(art.published_at, now, self.settings.half_life_days),
            ))
        for f in factors.values():
            total = sum(a.weight for a in f.articles)
            if total > 0:
                f.score = sum(a.weight * a.signed for a in f.articles) / total
            f.articles.sort(key=lambda a: a.article.published_at, reverse=True)
        return AnalysisResult(company, start, now, factors, warnings)
