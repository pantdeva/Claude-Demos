"""Investment routes for an Indian resident (config/routes.yaml; review the dates).

Order, from the plan:
  1. NSE/BSE listing → buy directly
  2. US exchange listing or ADR → LRS through a US broker or GIFT City Global Access
  3. Home market reachable from abroad → LRS through an international broker
     (China A-shares: Northbound Stock Connect via a Hong Kong broker; H-shares/ADRs)
  4. No practical direct route → country ETF (US-listed, under LRS), then sector ETF
  5. Not yet listed → IPO application (India: ASBA/UPI) or wait for listing;
     pre-IPO shares only with the SEBI and FEMA/ODI warnings
Never: NSE IFSC Receipts (closed to new buys).
"""

from __future__ import annotations

from ..config import load

US = {"NYSE", "NASDAQ"}


def _lrs_note() -> str:
    r = load("routes")["lrs"]
    return f"LRS limit USD {r['limit_usd_per_fy']:,} per financial year. {r['tcs']}. {r['tax']}"


def for_listed(listings: list[dict], home: dict, sector_group: str | None) -> list[dict]:
    """listings: [{symbol, venue, country, structure, share_type}] of one company."""
    cfg = load("routes")
    out = []
    india = [l for l in listings if l["venue"] in ("NSE", "BSE")]
    if india:
        best = next((l for l in india if l["venue"] == "NSE"), india[0])
        out.append({"route": "Buy directly on NSE/BSE", "symbol": best["symbol"], "ok": True,
                    "how": "any Indian broker; settled in rupees", "notes": "Indian listing: no LRS or TCS applies."})
    us = [l for l in listings if l["venue"] in US and l.get("share_type") != "preferred"]
    if us:
        l = next((x for x in us if x["structure"] in ("primary", "domestic secondary")), us[0])
        kind = {"primary": "US-listed shares", "ADR": "ADR", "foreign ordinary": "US-listed ordinary shares"}.get(
            l["structure"], l["structure"])
        out.append({"route": f"{kind} under LRS", "symbol": l["symbol"], "ok": True,
                    "how": cfg["lrs"]["brokers"], "notes": _lrs_note()})
    home_c = home["country"]
    dm = (cfg.get("direct_markets") or {}).get(home_c)
    if home_c != "IN" and home["venue"] not in US and dm:
        if home_c == "CN":
            board = "STAR/ChiNext" if home["symbol"].startswith(("688", "300", "301")) else "Main Board"
            hk = [l for l in listings if l["venue"] == "HKEX"]
            if hk:
                out.append({"route": "H-shares on HKEX under LRS", "symbol": hk[0]["symbol"], "ok": True,
                            "how": "Hong Kong or international broker", "notes": _lrs_note()})
            out.append({"route": "A-shares via Northbound Stock Connect", "symbol": home["symbol"],
                        "ok": board == "Main Board",
                        "how": "Hong Kong broker account under LRS",
                        "notes": f"{board} stock. " + ("Eligible for Northbound trading if in the Connect list."
                                                     if board == "Main Board" else
                                                     "STAR Market and ChiNext need professional-investor status.")})
        else:
            out.append({"route": "Home-market shares under LRS", "symbol": home["symbol"], "ok": dm["ok"] is True,
                        "how": dm["how"], "notes": _lrs_note() if dm["ok"] is True else "Access is limited; " + dm["how"]})
    otc = [l for l in listings if l["structure"] == "OTC ADR"]
    if otc and not us:
        out.append({"route": "US OTC ADR under LRS", "symbol": otc[0]["symbol"], "ok": True,
                    "how": "US broker", "notes": "Over-the-counter: thin trading and wide spreads. " + _lrs_note()})
    etfs = (cfg.get("country_etfs") or {}).get(home_c) or []
    if etfs and home_c != "IN":
        out.append({"route": "Country ETF under LRS", "symbol": ", ".join(etfs), "ok": True,
                    "how": "US broker", "notes": f"Broad exposure to {home_c}; check the fund is still trading."})
    sec = (cfg.get("sector_etfs") or {}).get(sector_group or "") or []
    if sec:
        out.append({"route": "Sector ETF under LRS", "symbol": ", ".join(sec), "ok": True, "how": "US broker",
                    "notes": "Theme exposure instead of the single stock."})
    if any(l["venue"] in US for l in listings) or home["venue"] in US:
        out.append({"route": "Avoid: NSE IFSC Receipts", "symbol": None, "ok": False, "how": None,
                    "notes": cfg["never"][0]["why"]})
    return out


def for_unlisted(name: str, stage: str, country_hint: str | None, sector_group: str | None) -> list[dict]:
    cfg = load("routes")
    w = cfg["warnings"]
    out = []
    if country_hint == "IN":
        out.append({"route": "Apply in the IPO", "symbol": None, "ok": True,
                    "how": "ASBA through your bank or UPI through an Indian broker when the issue opens",
                    "notes": "Check the red herring prospectus, price band and lot size; allotment is by lottery when "
                             "retail demand exceeds the quota."})
    else:
        out.append({"route": "Wait for the listing, then buy under LRS", "symbol": None, "ok": True,
                    "how": "international broker for the listing exchange (some US brokers offer IPO allocations)",
                    "notes": _lrs_note()})
    out.append({"route": "Pre-IPO / unlisted shares", "symbol": None, "ok": False, "how": None,
                "notes": w["unlisted_platforms"] + (" " + w["odi"] if country_hint not in (None, "IN") else "")})
    sec = (cfg.get("sector_etfs") or {}).get(sector_group or "") or []
    if sec:
        out.append({"route": "Sector ETF under LRS (theme exposure meanwhile)", "symbol": ", ".join(sec), "ok": True,
                    "how": "US broker", "notes": "Listed peers or a sector fund carry the same theme before the IPO."})
    return out


def best(routes: list[dict]) -> str:
    r = next((x for x in routes if x["ok"]), None)
    return f"{r['route']} ({r['symbol']})" if r and r.get("symbol") else (r["route"] if r else "No practical route")
