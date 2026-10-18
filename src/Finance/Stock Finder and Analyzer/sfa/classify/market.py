"""Heading 1: market development (DM / EM / FM / Standalone), dated, by provider."""

from __future__ import annotations

from ..config import load

CLASSES = {"DM": "Developed", "EM": "Emerging", "FM": "Frontier", "SA": "Standalone"}
PROVIDERS = ("MSCI", "FTSE", "SPDJI")


def current_class(country: str, provider: str = "MSCI") -> str:
    cur = load("market_classification")["current"][provider]
    for cls in ("DM", "EM", "FM"):
        if country in cur.get(cls, []):
            return cls
    return "SA"          # not covered by the provider's DM/EM/FM indexes → standalone / unclassified


def class_on(country: str, date: str, provider: str = "MSCI") -> tuple[str, bool]:
    """(class in force on ISO date, assumed?) using the dated events.

    Walks the provider's events for the country backwards from today's label: an event
    after `date` means the label before it applied. `assumed` is True when the date is
    before every recorded event, i.e. the label is extrapolated.
    """
    evs = sorted((e for e in load("market_classification").get("events") or []
                  if e["provider"] == provider and e["country"] == country),
                 key=lambda e: str(e["date"]))
    cls = current_class(country, provider)
    for e in reversed(evs):
        if str(e["date"]) > date:
            cls = e["from"]
    return cls, not evs      # assumed: no recorded history, today's label extrapolated


def detail(country: str) -> dict:
    cfg = load("market_classification")
    out = {p: current_class(country, p) for p in PROVIDERS}
    for tier, cs in (cfg["current"]["FTSE"].get("detail") or {}).items():
        if country in cs:
            out["FTSE_tier"] = tier
    out["agree"] = len({out[p] for p in PROVIDERS}) == 1
    out["watch"] = [w["item"] for w in cfg.get("watch") or [] if w["country"] == country]
    return out


def seed_events(con):
    for e in load("market_classification").get("events") or []:
        con.execute("INSERT OR REPLACE INTO classification_events VALUES (?,?,?,?,?,?)",
                    (e["provider"], e["country"], str(e["date"]), e["from"], e["to"], e.get("note")))
