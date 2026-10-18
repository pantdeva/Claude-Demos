"""Link news items to companies (rules A and B) and industries (rules C and D).

Company mentions come from three signals, strongest first:
  1. Yahoo's related-ticker tags (any listing symbol of the company)
  2. tickers written in the headline, e.g. "(TSM)" or "$NVDA"
  3. company aliases: the legal name without its legal form ("Infosys", "Toyota Motor"),
     a distinctive first word when no other company shares it ("Toyota", "Samsung"),
     and hand-made aliases in config/aliases.yaml ("TSMC", "Aramco")
Industry links: the supply-chain (rule C) and customer (rule D) terms for each
industry in config/industry_links.yaml.
"""

from __future__ import annotations

import re
from collections import defaultdict

from ..classify.sector import norm_industry
from ..config import load
from . import init

LEGAL_TAIL = re.compile(
    r"[\s,]+(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|p\.l\.c|s\.?a|n\.?v|ag|se|s\.?p\.?a|asa|ab|"
    r"oyj|holdings?|group|kgaa|& co|co\., ltd|co ltd|the)\.?$", re.I)
GENERIC_FIRST = set("""first china bank national general united american royal saudi japan korea taiwan hong new great
international global tokyo indian state hindustan bharat tata the sun power energy capital asian central eastern western
southern northern standard london banco industrial mitsubishi mitsui sumitomo hyundai lg sk adani bajaj mahindra
nippon shin shanghai shenzhen beijing guangdong ping air digital data semiconductor semiconductors solar electric steel
motor motors oil gas insurance technology technologies software systems industries pharma finance financial life
health healthcare medical resources mining metals chemical chemicals foods airlines airways telecom communications
networks media entertainment holdings investment trust realty properties construction engineering logistics shipping
marine paper cement glass textiles retail stores brands electronics microelectronics instruments devices labs
laboratories biotech therapeutics pharmaceuticals automotive auto infrastructure transport ports utilities water
renewable renewables green petroleum petrochemical coal gold silver copper aluminium aluminum iron credit securities
exchange markets payments cloud solutions services world universal premier prime advanced applied micro smart star
ever alpha delta bright sea ocean wind apollo atlas titan phoenix reliance victory liberty pioneer frontier summit
""".split())
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9&'’.\-]*")
TICK = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,9})\)|\$([A-Z]{1,5})\b")
MAX_N = 7


def short_names(name: str) -> list[str]:
    out, n = [], name.strip()
    for _ in range(3):
        m = LEGAL_TAIL.search(n)
        if not m:
            break
        n = n[:m.start()].strip(" ,.")
    if n and n != name:
        out.append(n)
    out.append(name.strip())
    return [x for x in dict.fromkeys(out) if len(x) >= 3]


class Linker:
    def __init__(self, con):
        init(con)
        self.alias: dict[str, int] = {}
        self.ticker: dict[str, int] = {}
        self.company = {}
        first_count = defaultdict(int)
        rows = con.execute("SELECT id, name, industry, sector FROM companies WHERE status='active'").fetchall()
        for r in rows:
            first = r["name"].split()[0].strip(",.").lower()
            first_count[first] += 1
        for r in rows:
            self.company[r["id"]] = dict(r)
            for a in short_names(r["name"]):
                self.alias.setdefault(a, r["id"])
            first = r["name"].split()[0].strip(",.")
            if first_count[first.lower()] == 1 and len(first) >= 4 and first.lower() not in GENERIC_FIRST \
                    and first[0].isupper():
                self.alias.setdefault(first, r["id"])
        for a in list(self.alias):                       # "NVIDIA" is written "Nvidia" in most headlines
            if a.isupper() and len(a) >= 4 and " " not in a:
                self.alias.setdefault(a.title(), self.alias[a])
        for r in con.execute("SELECT symbol, company_id FROM listings WHERE company_id IS NOT NULL"):
            self.ticker[r["symbol"]] = r["company_id"]
        sym_to_cid = self.ticker
        for k, v in (load("aliases").get("aliases") or {}).items():
            cid = sym_to_cid.get(k)
            if cid:
                for a in v:
                    self.alias[a] = cid
        self.alias_words = {a: a.split() for a in self.alias}
        self._ind = self._industry_terms()

    def _industry_terms(self):
        cfg = load("industry_links")
        out = {}
        for cid, c in self.company.items():
            ind = norm_industry(c["industry"])
            if ind in out:
                continue
            e = (cfg.get("industries") or {}).get(ind) or (cfg.get("sectors") or {}).get(c["sector"]) or {}
            out[ind] = {k: _matcher(v) for k, v in e.items() if v}
        return out

    def companies_in(self, text: str, tags: list[str] = ()) -> dict[int, str]:
        found = {}
        for t in tags:
            sym = t.split(":", 1)[1] if t.startswith("ticker:") else t
            if sym in self.ticker:
                found.setdefault(self.ticker[sym], "Yahoo related ticker")
        for m in TICK.finditer(text):
            sym = m.group(1) or m.group(2)
            if sym in self.ticker:
                found.setdefault(self.ticker[sym], f"ticker {sym}")
        words = [w.group(0).rstrip(".’'s").rstrip("’'") if w.group(0).endswith(("’s", "'s")) else w.group(0).rstrip(".")
                 for w in WORD.finditer(text)]
        i = 0
        while i < len(words):
            hit = None
            for n in range(min(MAX_N, len(words) - i), 0, -1):
                cand = " ".join(words[i:i + n])
                if cand in self.alias:
                    hit = (cand, n)
                    break
            if hit:
                cand, n = hit
                cid = self.alias[cand]
                if n == 1 and not self._single_ok(words, i, cid):
                    i += 1
                    continue
                found.setdefault(cid, f"name '{cand}'")
                i += n
            else:
                i += 1
        return found

    def _single_ok(self, words, i, cid) -> bool:
        """A one-word alias must not sit next to a generic corporate word that is not in
        the company's own name ("Reliance Steel", "First Solar", "Toyota Industries")."""
        name_words = {w.lower().strip(",.") for w in self.company[cid]["name"].split()}
        if words[i].lower() in GENERIC_FIRST:
            return False
        for k in (i - 1, i + 1):
            if 0 <= k < len(words):
                w = words[k].lower()
                if w in GENERIC_FIRST and w not in name_words:
                    return False
        return True

    def industries_in(self, text: str) -> list[tuple[str, str]]:
        """[(industry, rule)] for supply-chain (C) and customer (D) term matches."""
        out = []
        for ind, ms in self._ind.items():
            if "manufacturing" in ms and ms["manufacturing"](text):
                out.append((ind, "C"))
            if "customers" in ms and ms["customers"](text):
                out.append((ind, "D"))
        return out


def _matcher(terms):
    exact = [t for t in terms if t != t.lower()]
    loose = [t for t in terms if t == t.lower()]
    rx = []
    if exact:
        rx.append(re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t) for t in exact) + r")(?!\w)"))
    if loose:
        rx.append(re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t) for t in loose) + r")(?!\w)", re.I))
    return lambda s: any(r.search(s) for r in rx)


def link_pending(con, log=print) -> dict:
    """Add company and industry links for news items not yet linked."""
    init(con)
    lk = Linker(con)
    rows = con.execute("""SELECT n.id, n.title, n.summary FROM news_items n
                          WHERE NOT EXISTS (SELECT 1 FROM news_links k WHERE k.news_id=n.id AND k.rule IN ('A','C','D','none'))
                          """).fetchall()
    nc = ni = 0
    for r in rows:
        text = f"{r['title']}. {r['summary'] or ''}"
        tags = [t["target"] for t in con.execute("SELECT target FROM news_links WHERE news_id=? AND rule IN ('tag','query')",
                                                 (r["id"],))]
        tags_c = [t for t in tags if t.startswith("ticker:")]
        comps = lk.companies_in(text, tags_c)
        for t in tags:
            if t.startswith("company:"):
                comps.setdefault(int(t.split(":")[1]), "NewsAPI deep dive")
        for cid, basis in comps.items():
            con.execute("INSERT OR IGNORE INTO news_links VALUES (?,?,?,?,?)", (r["id"], f"company:{cid}", "A", 1, basis))
            nc += 1
        for ind, rule in lk.industries_in(text):
            con.execute("INSERT OR IGNORE INTO news_links VALUES (?,?,?,?,?)", (r["id"], f"industry:{ind}", rule, 1,
                                                                                "industry terms"))
            ni += 1
        if not comps:
            con.execute("INSERT OR IGNORE INTO news_links VALUES (?,?,?,?,?)", (r["id"], "none", "none", 0, "no company"))
    con.commit()
    return {"items": len(rows), "company_links": nc, "industry_links": ni}
