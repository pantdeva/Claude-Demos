"""Load and validate the YAML configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

FACTOR_KEYS = ("market_sentiment", "competition", "manufacturing", "customers")


@dataclass(frozen=True)
class Company:
    ticker: str
    name: str
    market: str = "US"
    language: str = "en"
    aliases: tuple[str, ...] = ()
    competitors: tuple[str, ...] = ()
    manufacturing: tuple[str, ...] = ()
    customers: tuple[str, ...] = ()
    # Extra words an article must also contain, per group: competitors / manufacturing / customers
    context: dict[str, tuple[str, ...]] = field(default_factory=dict, hash=False, compare=False)
    # Articles containing any of these are dropped from every factor
    exclude: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.ticker} · {self.name} ({self.market})"


@dataclass(frozen=True)
class Settings:
    lookback_days: int = 7
    half_life_days: float = 3.0
    max_articles_per_query: int = 100
    bullish: float = 0.15
    bearish: float = -0.15
    weights: dict[str, float] = field(default_factory=lambda: {k: 0.25 for k in FACTOR_KEYS})
    competitor_direction: int = -1
    release_keywords: tuple[str, ...] = ()
    exclude_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class AppConfig:
    settings: Settings
    companies: dict[str, Company]


def _strs(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v).strip() for v in value if str(v).strip())


def load_config(path: str | Path) -> AppConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    s = raw.get("settings") or {}
    thresholds = s.get("thresholds") or {}
    weights = {k: float((s.get("weights") or {}).get(k, 0.25)) for k in FACTOR_KEYS}
    direction = int(s.get("competitor_direction", -1))
    if direction not in (-1, 1):
        raise ValueError("competitor_direction must be 1 or -1")
    settings = Settings(
        lookback_days=int(s.get("lookback_days", 7)),
        half_life_days=float(s.get("half_life_days", 3)),
        max_articles_per_query=min(100, int(s.get("max_articles_per_query", 100))),
        bullish=float(thresholds.get("bullish", 0.15)),
        bearish=float(thresholds.get("bearish", -0.15)),
        weights=weights,
        competitor_direction=direction,
        release_keywords=_strs(s.get("release_keywords")),
        exclude_sources=tuple(x.lower() for x in _strs(s.get("exclude_sources"))),
    )

    companies: dict[str, Company] = {}
    for ticker, c in (raw.get("companies") or {}).items():
        c = c or {}
        name = str(c.get("name") or ticker)
        aliases = _strs(c.get("aliases")) or (name,)
        companies[str(ticker)] = Company(
            ticker=str(ticker),
            name=name,
            market=str(c.get("market", "US")),
            language=str(c.get("language", "en")),
            aliases=aliases,
            competitors=_strs(c.get("competitors")),
            manufacturing=_strs(c.get("manufacturing")),
            customers=_strs(c.get("customers")),
            context={k: _strs(v) for k, v in (c.get("context") or {}).items()
                     if k in ("competitors", "manufacturing", "customers")},
            exclude=_strs(c.get("exclude")),
        )
    if not companies:
        raise ValueError(f"No companies defined in {path}")
    return AppConfig(settings=settings, companies=companies)
