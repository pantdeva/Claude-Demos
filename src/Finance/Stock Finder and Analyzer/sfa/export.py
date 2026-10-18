"""Write the Stage 0 classification to exports/: companies.csv, listings.csv,
classification.json and a summary.md of counts per heading."""

from __future__ import annotations

import csv
import json
from collections import Counter

from .config import EXPORT_DIR
from .db import now

COLUMNS = ["market_class", "market_class_ftse", "market_class_spdji", "home_exchange", "covered",
           "listing_structure", "domicile", "foreign_domiciled", "gics_sector", "sector_group",
           "market_cap_usd", "cap_band", "cap_band_sebi", "growth_value", "cyclical_defensive", "beta",
           "share_type", "has_preferred"]


def export(con, out_dir=EXPORT_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    comps = [dict(r) for r in con.execute("SELECT * FROM companies WHERE status='active' ORDER BY home_venue, name")]
    tags = {}
    for r in con.execute("SELECT company_id, tag, value, detail FROM stock_tags"):
        tags.setdefault(r["company_id"], {})[r["tag"]] = (r["value"], r["detail"])
    rows = []
    for c in comps:
        t = tags.get(c["id"], {})
        rows.append({"id": c["id"], "name": c["name"], "home_symbol": c["home_symbol"], "home_country": c["home_country"],
                     "yahoo_sector": c["sector"], "industry": c["industry"],
                     **{k: (t.get(k) or (None,))[0] for k in COLUMNS}})
    with open(out_dir / "companies.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["id"])
        w.writeheader()
        w.writerows(rows)
    lst = [dict(r) for r in con.execute(
        "SELECT l.symbol, c.name, l.venue, l.country, l.currency, l.is_home, l.structure, l.dr_ratio, "
        "l.structure_basis, l.share_type, l.share_class FROM listings l JOIN companies c ON c.id=l.company_id "
        "ORDER BY c.name, l.is_home DESC, l.symbol")]
    with open(out_dir / "listings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lst[0]) if lst else ["symbol"])
        w.writeheader()
        w.writerows(lst)
    full = []
    for c, r in zip(comps, rows):
        full.append({**r, "details": {k: json.loads(v[1] or "{}") for k, v in tags.get(c["id"], {}).items()}})
    (out_dir / "classification.json").write_text(json.dumps({"built": now(), "companies": full}, indent=1,
                                                            ensure_ascii=False, default=str), encoding="utf-8")
    (out_dir / "summary.md").write_text(summary(rows, lst), encoding="utf-8")
    return {"companies": len(rows), "listings": len(lst)}


def _table(title: str, counter: Counter) -> str:
    lines = [f"### {title}", "", "| Value | Companies |", "|---|---|"]
    lines += [f"| {k or '—'} | {v} |" for k, v in sorted(counter.items(), key=lambda x: -x[1])]
    return "\n".join(lines) + "\n"


def summary(rows: list[dict], listings: list[dict]) -> str:
    out = [f"# Stage 0 classification summary\n\nBuilt {now()}. {len(rows)} companies, {len(listings)} listings.\n"]
    out.append("## 1. Market development\n")
    out.append(_table("MSCI (primary)", Counter(r["market_class"] for r in rows)))
    dis = [r for r in rows if len({r["market_class"], r["market_class_ftse"], r["market_class_spdji"]}) > 1]
    out.append(f"Providers disagree for {len(dis)} companies (home markets: "
               f"{', '.join(sorted({r['home_country'] for r in dis})) or 'none'}).\n")
    out.append(_table("Home exchange", Counter(r["home_exchange"] for r in rows)))
    out.append("## 2. Listing structure\n")
    out.append(_table("Company level", Counter(r["listing_structure"] for r in rows)))
    out.append(_table("Non-home listings by type", Counter(l["structure"] for l in listings if not l["is_home"])))
    out.append(f"Foreign-domiciled (incorporated outside the home exchange's country): "
               f"{sum(r['foreign_domiciled'] == 'yes' for r in rows)}.\n")
    out.append("## 3. Industry\n")
    out.append(_table("Sector group", Counter(r["sector_group"] for r in rows)))
    out.append(_table("GICS sector", Counter(r["gics_sector"] for r in rows)))
    out.append("## 4. Stock level\n")
    out.append(_table("Cap band (USD)", Counter(r["cap_band"] for r in rows)))
    out.append(_table("Growth vs value", Counter(r["growth_value"] for r in rows)))
    out.append(_table("Cyclical vs defensive", Counter(r["cyclical_defensive"] for r in rows)))
    out.append(_table("Share type of home line", Counter(r["share_type"] for r in rows)))
    out.append(f"Companies that also have preferred lines: {sum(r['has_preferred'] == 'yes' for r in rows)}.\n")
    out.append("\n## Market class × sector group (companies)\n")
    groups = sorted({r["sector_group"] or "—" for r in rows})
    classes = ["Developed", "Emerging", "Frontier", "Standalone"]
    out.append("| Sector group | " + " | ".join(classes) + " |")
    out.append("|---|" + "---|" * len(classes))
    for g in groups:
        out.append(f"| {g} | " + " | ".join(str(sum(1 for r in rows if (r['sector_group'] or '—') == g
                                                     and r['market_class'] == c)) for c in classes) + " |")
    out.append("\nResearch output, not investment advice.\n")
    return "\n".join(out)
