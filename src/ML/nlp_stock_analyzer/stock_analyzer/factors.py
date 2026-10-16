"""Turn a company's config into NewsAPI queries, grouped by factor.

Four factors drive the analysis:

1. market_sentiment  - news that mentions the company itself
2. competition       - the company's own releases (+) and competitor news (flipped)
3. manufacturing     - the manufacturing industry and supply chain it depends on
4. customers         - the customers and end markets it sells to
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Company, Settings

FACTORS = {
    "market_sentiment": "Market sentiment",
    "competition": "Competition & news releases",
    "manufacturing": "Manufacturing industry",
    "customers": "Customers",
}

NEWSAPI_MAX_QUERY = 500  # NewsAPI limits q to 500 characters


def _quote(term: str) -> str:
    term = term.replace('"', "")
    return f'"{term}"' if " " in term or "-" in term else term


def _or(terms) -> str:
    return " OR ".join(_quote(t) for t in terms)


def _regex(terms, flags=0) -> re.Pattern | None:
    if not terms:
        return None
    alts = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(r"(?<!\w)(?:" + alts + r")(?!\w)", flags)


def term_matcher(terms):
    """Whole-word matcher. Terms with a capital letter are case-sensitive, so
    'Intel' won't match 'intel sharing' and 'SAIL' won't match 'sail';
    all-lowercase terms like 'iron ore' match in any case."""
    terms = [t for t in terms if t]
    exact = _regex([t for t in terms if t != t.lower()])
    loose = _regex([t for t in terms if t == t.lower()], re.IGNORECASE)

    def match(text: str) -> bool:
        return bool((exact and exact.search(text)) or (loose and loose.search(text)))

    return match if terms else None


@dataclass(frozen=True)
class FactorGroup:
    """One search within a factor, e.g. 'competitor news' inside competition."""

    factor: str
    name: str
    terms: tuple[str, ...]
    direction: int = 1
    required: tuple[str, ...] = ()   # article must also contain one of these
    exclude: tuple[str, ...] = ()    # article is dropped if it contains any of these

    def queries(self) -> list[str]:
        """NewsAPI q strings, split so each stays under the length limit."""
        suffix = f" AND ({_or(self.required)})" if self.required else ""
        budget = NEWSAPI_MAX_QUERY - len(suffix) - 2
        chunks, current = [], []
        for term in self.terms:
            trial = current + [term]
            if current and len(_or(trial)) > budget:
                chunks.append(current)
                current = [term]
            else:
                current = trial
        if current:
            chunks.append(current)
        return [f"({_or(c)}){suffix}" for c in chunks]

    def matches(self, text: str) -> bool:
        """Relevance filter: drop articles that don't really mention the terms."""
        main = term_matcher(self.terms)
        if main is None or not main(text):
            return False
        bad = term_matcher(self.exclude)
        if bad is not None and bad(text):
            return False
        req = term_matcher(self.required)
        return req is None or req(text)


def build_factor_groups(company: Company, settings: Settings) -> list[FactorGroup]:
    ctx, ex = company.context, company.exclude
    groups = [FactorGroup("market_sentiment", "Company coverage", company.aliases,
                          exclude=ex)]
    if settings.release_keywords:
        groups.append(FactorGroup("competition", "Company news releases", company.aliases,
                                  1, settings.release_keywords, ex))
    if company.competitors:
        # Stories naming the company too ("Nvidia, Broadcom stocks fall") are about the
        # company as well, so they stay in market sentiment instead of being flipped here.
        groups.append(FactorGroup("competition", "Competitor news", company.competitors,
                                  settings.competitor_direction, ctx.get("competitors", ()),
                                  ex + company.aliases))
    if company.manufacturing:
        groups.append(FactorGroup("manufacturing", "Manufacturing & supply chain",
                                  company.manufacturing, 1, ctx.get("manufacturing", ()), ex))
    if company.customers:
        groups.append(FactorGroup("customers", "Customers & end markets", company.customers,
                                  1, ctx.get("customers", ()), ex))
    return groups
