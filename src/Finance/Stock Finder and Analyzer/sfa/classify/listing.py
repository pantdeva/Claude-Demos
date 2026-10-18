"""Heading 2: geographic and listing structure.

For each company: which listing is home (primary), and what every other listing is:
  domestic secondary  another listing in the home country (NSE + BSE, GOOGL + GOOG)
  foreign ordinary    the same shares traded on a foreign exchange (Canadian interlisted
                      stocks on NYSE, LSE international lines, Xetra lines)
  ADR                 US-exchange depositary receipt (ratio = home shares per ADR)
  OTC ADR / OTC ord.  US over-the-counter receipts / ordinary lines
  GDR                 London International Order Book receipts
  CDR / SDR           Canadian (Cboe/TSX) and Singapore depositary receipts
  BDR                 Brazilian depositary receipts (B3)
Company-level label: "Depositary receipts" > "Cross-listed" > "Domestic".
"""

from __future__ import annotations

import re
import unicodedata

from ..config import load, venues

LEGAL = {"inc", "incorporated", "corp", "corporation", "co", "company", "companies", "ltd", "limited",
         "plc", "sa", "nv", "ag", "se", "spa", "asa", "ab", "oyj", "kk", "tbk", "bhd", "berhad", "pcl",
         "the", "cv", "sab", "lp", "llc", "ord", "adr", "ads", "sponsored", "class", "shares",
         "share", "common", "stock", "new", "kgaa", "co.,", "sociedad", "anonima", "societe",
         "anonyme", "aktiengesellschaft", "pjsc", "jsc", "group", "holdings", "holding",
         "bhd.", "tbk.", "n", "v", "s", "a", "b", "h", "de", "del", "y", "et", "cie", "sca",
         "reit", "trust", "units", "unit", "industries", "industry", "international", "intl"}
US_EXCH = {"NASDAQ", "NYSE"}


def name_key(name: str | None) -> str:
    """Normalised company name: accents, punctuation and legal-form words removed."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ").replace("s.a.", " sa ").replace("n.v.", " nv ").replace("s.p.a.", " spa ")
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in LEGAL]
    return " ".join(toks)


def same_company(a: str | None, b: str | None) -> bool:
    """True when two listing names describe the same company.

    Equal keys match. A key that is a subset of the other matches only when they share
    at least two words and start with the same word ("enel" ≠ "enel chile"; "taiwan
    semiconductor manufacturing" = "taiwan semiconductor manufacturing co").
    """
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    ta, tb = ka.split(), kb.split()
    if ta[0] != tb[0]:
        return False
    sa, sb = set(ta), set(tb)
    small, big = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
    return len(small) >= 2 and small <= big and len(big - small) <= 1


# ---------------------------------------------------------------- share type
def share_type(symbol: str, name: str | None = None) -> tuple[str, str | None, str]:
    """(common|preferred, share class or None, rule used)."""
    ov = (load("overrides").get("share_type") or {}).get(symbol)
    if ov:
        return ov, None, "override"
    base, _, suf = symbol.partition(".")
    nm = (name or "").lower()
    if re.search(r"\b(pref|preferred|preference|vorzug|vz|prf|pfd)\b", nm):
        return "preferred", None, "name"
    if suf == "" and re.search(r"-P[A-Z]?$", base):                       # US: BAC-PL, C-PN
        return "preferred", base.split("-P")[-1] or None, "US -P suffix"
    if suf in ("KS", "KQ") and len(base) == 6:
        if base[-1] in "579" or base[-1] == "K":                       # 005935, 00088K
            return "preferred", None, "Korean code ending 5/7/9/K"
        return "common", None, "Korean code ending 0"
    if suf == "DE" and base.endswith("3") and not base[:-1].isdigit():  # VOW3, HEN3, PAH3
        return "preferred", None, "German Vorzugsaktie (…3)"
    if suf == "SA" and re.search(r"[A-Z]{4}(4|5|6|7|8)$", base):        # PETR4, ITUB4
        return "preferred", None, "Brazil PN class (4–8)"
    if suf == "MI" and base.endswith("R") and len(base) > 3:            # savings shares
        return "preferred", None, "Italian savings share (…R)"
    m = re.search(r"-([A-Z])$", base) or re.search(r"\b(?:class|cl)\s+([a-z])\b", nm)
    cls = m.group(1).upper() if m else None
    if base in ("GOOGL",):
        cls = "A"
    elif base in ("GOOG",):
        cls = "C"
    return "common", cls, "default"


# ---------------------------------------------------------------- home listing
def choose_home(listings: list[dict], statement_ccy: str | None, seed: str) -> tuple[dict, str]:
    """Pick the primary listing.

    Rules in order: override; drop preferred lines, secondary-only venues, LSE "0…"
    international lines; if any candidate is outside the US (other than Xetra-type lines),
    prefer it (US lines of foreign companies far outnumber foreign lines of US companies);
    then score: statement currency matches trading currency (+2), covered exchange (+0.5),
    is the seed (+1), earlier in Yahoo search (+0.5/(1+rank)).
    """
    from ..data.yahoo import normalise_ccy
    ov = load("overrides").get("home_listing") or {}
    syms = {l["symbol"] for l in listings}
    for s in syms:
        if s in ov and ov[s] in syms:
            return next(l for l in listings if l["symbol"] == ov[s]), "override"
    cand = [l for l in listings if l.get("venue") and l["venue_role"] != "secondary"
            and l.get("share_type") != "preferred"
            and not (l["venue"] == "LSE" and l["symbol"][:1].isdigit())]
    if not cand:
        cand = [l for l in listings if l["symbol"] == seed] or listings
        return cand[0], "seed (no home-capable venue)"
    us = [l for l in cand if l["venue"] in US_EXCH]
    non_us = [l for l in cand if l["venue"] not in US_EXCH]
    st = normalise_ccy(statement_ccy)[0]
    basis = "score"
    if us and non_us:
        # A foreign line is the home only with evidence: it reports in that line's
        # currency, it is the seed, or the US line is a known interlisted ordinary
        # (Canadian companies reporting in USD). Otherwise foreign lines of a US company
        # (Canadian CDRs, Xetra quotes) would win.
        interlisted = any(l["symbol"] in set(load("overrides").get("us_ordinary") or []) for l in us)
        strong = [l for l in non_us if (st and normalise_ccy(l.get("currency"))[0] == st)
                  or l["symbol"] == seed or (interlisted and l["country"] == "CA")]
        if strong:
            cand, basis = strong, "foreign company with US line"
        else:
            cand, basis = us, "US company with foreign lines"

    def score(l):
        s = 0.0
        if st and normalise_ccy(l.get("currency"))[0] == st:
            s += 2
        if l["venue_role"] == "covered":
            s += 0.5
        if l["symbol"] == seed:
            s += 1
        s += 0.5 / (1 + l.get("rank", 9))
        return s
    best = max(cand, key=score)
    return best, basis


# ---------------------------------------------------------------- structure
def nice_ratio(x: float) -> float:
    """Snap a measured price ratio to a typical depositary ratio (0.1, 0.5, 1, 2, 5, 10…)."""
    for r in (0.01, 0.02, 0.05, 0.1, 0.125, 0.2, 0.25, 1 / 3, 0.5, 1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 25,
              30, 40, 50, 100, 200, 250, 500, 1000):
        if abs(x / r - 1) < 0.08:
            return round(r, 4)
    return round(x, 3)


def listing_structure(l: dict, home: dict, home_price_usd: float | None,
                      price_usd: float | None) -> tuple[str, float | None, str]:
    """(structure, depositary ratio, basis) of one non-home listing."""
    ov_ord = set(load("overrides").get("us_ordinary") or [])
    sym, venue = l["symbol"], l.get("venue")
    if l["symbol"] == home["symbol"]:
        return "primary", None, "home listing"
    ratio = None
    if home_price_usd and price_usd:
        ratio = nice_ratio(price_usd / home_price_usd)
    if l.get("country") == home.get("country") and venue not in ("US_OTC",):
        return "domestic secondary", None, "same country as home"
    if venue == "US_OTC":
        base = sym.split(".")[0]
        if len(base) == 5 and base.endswith("Y"):
            return "OTC ADR", ratio, "OTC symbol ending Y"
        if len(base) == 5 and base.endswith("F"):
            return "OTC ordinary", None, "OTC symbol ending F"
        return ("OTC ADR", ratio, "OTC, price ratio ≠ 1") if ratio and ratio != 1 else \
               ("OTC ordinary", None, "OTC, price ratio ≈ 1")
    if venue == "LSE_IOB":
        if sym[:1].isdigit():
            return "foreign ordinary", None, "LSE international line (0…)"
        return "GDR", ratio, "London IOB receipt"
    if venue == "LSE" and sym[:1].isdigit():
        return "foreign ordinary", None, "LSE international line (0…)"
    if venue == "B3":
        return "BDR", ratio, "B3 depositary receipt"
    if venue == "SGX":
        return "SDR", ratio, "SGX depositary receipt"
    if venue in ("TSX", "TSXV") and home.get("country") == "US":
        if ratio is not None and ratio != 1:
            return "CDR", ratio, "Canadian depositary receipt of a US company (price ratio ≠ 1)"
        return "foreign ordinary", None, "TSX line of a US company"
    if venue in US_EXCH:
        if sym in ov_ord or home.get("country") == "CA":
            return "foreign ordinary", None, "interlisted ordinary shares (override/Canada)"
        if ratio is None:
            return "ADR", None, "US line of a foreign company (ratio not measured)"
        if ratio == 1:
            return "ADR", 1.0, "US line, price ratio 1:1 (could be ordinary)"
        return "ADR", ratio, "US line, price ratio ≠ 1"
    return "foreign ordinary", None, "listed on a foreign exchange"


def company_structure(structures: list[str]) -> str:
    s = set(structures)
    if s & {"ADR", "GDR", "SDR", "CDR"}:
        return "Depositary receipts (ADR/GDR/other DR)"
    if "foreign ordinary" in s:
        return "Cross-listed (foreign ordinary)"
    return "Domestic"
