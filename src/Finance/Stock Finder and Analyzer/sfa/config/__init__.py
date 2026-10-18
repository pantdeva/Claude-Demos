"""Load the YAML configuration files and build lookup tables over them."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).parent
ROOT = CONFIG_DIR.parent.parent           # "Stock Finder and Analyzer/"
DB_DIR = ROOT / "db"
EXPORT_DIR = ROOT / "exports"


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    return yaml.safe_load((CONFIG_DIR / f"{name}.yaml").read_text(encoding="utf-8")) or {}


class Venues:
    """Every venue the app knows about, with lookups by Yahoo exchange code and suffix.

    role = "covered"   one of the starting exchanges (home listings are modelled)
           "secondary" a venue for depositary receipts / secondary lines only
           "expansion" an exchange that may be added later; can be a company's home
    """

    def __init__(self):
        cfg = load("exchanges")
        self.by_id: dict[str, dict] = {}
        for role, key in (("covered", "exchanges"), ("secondary", "secondary_venues"),
                          ("expansion", "expansion_candidates")):
            for v in cfg.get(key) or []:
                if v["id"] in self.by_id:          # covered/secondary entry wins
                    continue
                self.by_id[v["id"]] = {**v, "role": role}
        self.by_code = {c: v for v in self.by_id.values() for c in v.get("yahoo_codes", [])}
        # suffix lookup only for venues we know well: Yahoo reuses suffixes
        # (".DU" is Düsseldorf, not Dubai), so expansion venues resolve by code only
        self.by_suffix = {}
        for role in ("covered", "secondary"):
            for v in self.by_id.values():
                if v["role"] == role and v.get("suffix") and v["suffix"] not in self.by_suffix:
                    self.by_suffix[v["suffix"]] = v

    def resolve(self, symbol: str, yahoo_code: str | None = None) -> dict | None:
        """Venue for a listing: Yahoo's exchange code first, ticker suffix second."""
        if yahoo_code and yahoo_code in self.by_code:
            return self.by_code[yahoo_code]
        if "." in symbol:
            suf = "." + symbol.rsplit(".", 1)[1]
            return self.by_suffix.get(suf)
        return None

    def covered(self) -> list[dict]:
        return [v for v in self.by_id.values() if v["role"] == "covered"]


@lru_cache(maxsize=None)
def venues() -> Venues:
    return Venues()


def seeds() -> list[tuple[str, str]]:
    """(group, ticker) pairs in file order, de-duplicated."""
    seen, out = set(), []
    for group, tickers in (load("universe_seeds").get("seeds") or {}).items():
        for t in tickers:
            if t not in seen:
                seen.add(t)
                out.append((group, t))
    return out
