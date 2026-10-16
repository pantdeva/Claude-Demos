"""NewsAPI client (https://newsapi.org/docs/endpoints/everything) with a disk cache.

The free Developer plan allows 100 requests a day and only covers recent
articles, so responses are cached to avoid spending quota on reruns.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

NEWSAPI_URL = "https://newsapi.org/v2/everything"


class NewsAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class Article:
    title: str
    description: str
    url: str
    source: str
    published_at: datetime

    @property
    def text(self) -> str:
        parts = [self.title.strip(), (self.description or "").strip()]
        return ". ".join(p for p in parts if p)


def _parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_articles(payload: dict) -> list[Article]:
    if payload.get("status") != "ok":
        raise NewsAPIError(f"{payload.get('code', 'error')}: {payload.get('message', payload)}")
    out = []
    for a in payload.get("articles") or []:
        title, url = (a.get("title") or "").strip(), a.get("url") or ""
        if not title or not url or title == "[Removed]":
            continue
        try:
            published = _parse_time(a.get("publishedAt") or "")
        except ValueError:
            continue
        out.append(Article(
            title=title,
            description=(a.get("description") or "").strip(),
            url=url,
            source=((a.get("source") or {}).get("name") or "").strip(),
            published_at=published,
        ))
    return out


class NewsAPIClient:
    def __init__(self, api_key: str | None = None, cache_dir: str | Path | None = None,
                 cache_ttl_s: int = 3600, session: requests.Session | None = None):
        self.api_key = api_key or os.environ.get("NEWSAPI_KEY")
        if not self.api_key:
            raise NewsAPIError("No NewsAPI key: set NEWSAPI_KEY or pass api_key")
        self.cache_dir = Path(cache_dir or Path.home() / ".cache" / "nlp_stock_analyzer")
        self.cache_ttl_s = cache_ttl_s
        self.session = session or requests.Session()

    def search(self, query: str, language: str, start: datetime, end: datetime,
               page_size: int = 100) -> list[Article]:
        # Round to the hour so reruns within the hour hit the cache instead of the API.
        hour = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00:00")
        params = {
            "q": query,
            "language": language,
            "from": hour(start),
            "to": hour(end),
            "searchIn": "title,description",
            "sortBy": "publishedAt",
            "pageSize": max(1, min(100, page_size)),
        }
        return parse_articles(self._get(params))

    def _get(self, params: dict) -> dict:
        key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists() and time.time() - path.stat().st_mtime < self.cache_ttl_s:
            return json.loads(path.read_text(encoding="utf-8"))
        resp = self.session.get(NEWSAPI_URL, params=params,
                                headers={"X-Api-Key": self.api_key}, timeout=30)
        try:
            payload = resp.json()
        except ValueError as exc:
            raise NewsAPIError(f"HTTP {resp.status_code}: non-JSON response") from exc
        if resp.status_code != 200 or payload.get("status") != "ok":
            raise NewsAPIError(f"{payload.get('code', resp.status_code)}: "
                               f"{payload.get('message', 'request failed')}")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return payload
