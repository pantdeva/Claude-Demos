"""Heading 3: industry and sector (Yahoo sector → GICS sector → six app groups)."""

from __future__ import annotations

import re

from ..config import load


def norm_industry(industry: str | None) -> str | None:
    """Yahoo writes "Banks—Regional"; config files use "Banks - Regional"."""
    return re.sub(r"\s*[—–]\s*|\s+-\s+", " - ", industry).strip() if industry else industry


def map_sector(yahoo_sector: str | None, industry: str | None) -> dict:
    cfg = load("sectors")
    base = cfg["yahoo_sector"].get(yahoo_sector or "")
    if not base:
        return {"gics": None, "group": None, "group_name": "Unclassified", "super": None, "basis": "no sector"}
    out = {**base, "basis": "yahoo sector"}
    ov = (cfg.get("industry_override") or {}).get(norm_industry(industry) or "")
    if ov:
        out.update(ov)
        out["basis"] = "industry override"
    out["group_name"] = cfg["groups"][out["group"]]
    return out


def behaviour(super_sector: str | None, industry: str | None, beta: float | None) -> tuple[str, str]:
    """Cyclical vs defensive: (label, basis).

    Start from the Morningstar super-sector (Cyclical/Sensitive → cyclical, Defensive →
    defensive); industry lists override; then measured beta to the home index overrides
    when it disagrees strongly (beta < 0.6 → defensive, beta > 1.3 → cyclical).
    """
    beh = load("sectors").get("industry_behaviour") or {}
    industry = norm_industry(industry)
    if industry in beh.get("defensive", []):
        label, basis = "Defensive", "industry"
    elif industry in beh.get("cyclical", []):
        label, basis = "Cyclical", "industry"
    elif super_sector in ("Cyclical", "Sensitive"):
        label, basis = "Cyclical", f"super-sector {super_sector}"
    elif super_sector == "Defensive":
        label, basis = "Defensive", "super-sector Defensive"
    else:
        label, basis = None, "unknown"
    if beta is not None:
        if beta < 0.6 and label != "Defensive":
            label, basis = "Defensive", f"beta {beta:.2f} < 0.6"
        elif beta > 1.3 and label != "Cyclical":
            label, basis = "Cyclical", f"beta {beta:.2f} > 1.3"
        elif label is None:
            label, basis = ("Cyclical" if beta >= 1 else "Defensive"), f"beta {beta:.2f}"
    return label or "Unclassified", basis
