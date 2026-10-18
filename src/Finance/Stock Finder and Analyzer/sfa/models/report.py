"""Export the Milestone 2 results to exports/: leaderboard.csv, model_choice.csv,
predictions.csv, portfolio_tests.csv and leaderboard.md."""

from __future__ import annotations

import csv
import json

from ..config import EXPORT_DIR, load
from ..db import now
from . import zoo


def _csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        if not rows:
            f.write("")
            return
        fields = list(dict.fromkeys(k for r in rows for k in r))
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _g(key) -> str:
    """Group key for a markdown cell ("|" would split the table)."""
    return str(key).replace(" | ", " × ")


def _pct(v, d=1):
    return "—" if v is None else f"{v * 100:+.{d}f}%"


def export(con, out_dir=EXPORT_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    names = {c["id"]: (c["name"], c["home_symbol"]) for c in con.execute("SELECT id, name, home_symbol FROM companies")}
    lb = [dict(r) for r in con.execute("SELECT * FROM leaderboard ORDER BY group_type, group_key, horizon, crps")]
    for r in lb:
        r["model_name"] = zoo.name(r["model"])
        if r["group_type"] == "company":
            r["group_name"] = "{} ({})".format(*names.get(int(r["group_key"]), ("?", "?")))
    _csv(out_dir / "leaderboard.csv", lb)
    ch = [dict(r) for r in con.execute("SELECT * FROM model_choice ORDER BY group_type, group_key, horizon")]
    for r in ch:
        r["selected_name"], r["baseline_name"] = zoo.name(r["selected"]), zoo.name(r["baseline"])
        if r["group_type"] == "company":
            r["group_name"] = "{} ({})".format(*names.get(int(r["group_key"]), ("?", "?")))
    _csv(out_dir / "model_choice.csv", ch)
    preds = []
    for c in con.execute("""SELECT c.id, c.name, c.home_symbol, c.home_venue,
            (SELECT value FROM stock_tags t WHERE t.company_id=c.id AND t.tag='market_class') mc,
            (SELECT value FROM stock_tags t WHERE t.company_id=c.id AND t.tag='sector_group') sg
            FROM companies c WHERE status='active' ORDER BY c.home_venue, c.name"""):
        row = {"name": c["name"], "symbol": c["home_symbol"], "exchange": c["home_venue"], "market_class": c["mc"],
               "sector_group": c["sg"]}
        for tag, lbl in (("growth_3m", "3m"), ("growth_1y", "1y")):
            t = con.execute("SELECT value, detail FROM stock_tags WHERE company_id=? AND tag=?", (c["id"], tag)).fetchone()
            if not t:
                continue
            d = json.loads(t["detail"])
            row.update({f"{lbl}_expected": t["value"], f"{lbl}_median": d.get("median_return"),
                        f"{lbl}_p05": d["range_5_95"][0], f"{lbl}_p95": d["range_5_95"][1],
                        f"{lbl}_p_beat_cash": d.get("p_beat_cash"), f"{lbl}_model": d.get("model"),
                        f"{lbl}_basis": d.get("basis"), f"{lbl}_all_models_median": d.get("all_models_median_expected")})
            row["as_of"], row["price"] = d.get("as_of"), d.get("price")
        preds.append(row)
    _csv(out_dir / "predictions.csv", preds)
    pt = [dict(r) for r in con.execute("SELECT * FROM portfolio_tests ORDER BY cell, strategy")] \
        if con.execute("SELECT name FROM sqlite_master WHERE name='portfolio_tests'").fetchone() else []
    _csv(out_dir / "portfolio_tests.csv", pt)
    (out_dir / "leaderboard.md").write_text(summary(con, ch, lb, pt), encoding="utf-8")
    return {"leaderboard_rows": len(lb), "choices": len(ch), "predictions": len(preds), "portfolio_rows": len(pt)}


def summary(con, ch, lb, pt) -> str:
    cfg = load("models")
    wf = cfg["walk_forward"]
    n = con.execute("SELECT COUNT(*), COUNT(DISTINCT company_id), COUNT(DISTINCT origin), MIN(origin), MAX(origin) "
                    "FROM forecast_scores WHERE crps IS NOT NULL").fetchone()
    out = [f"# Stage 0 model leaderboard\n\nBuilt {now()}. {n[0]:,} scored forecasts for {n[1]} companies on "
           f"{n[2]} forecast dates ({n[3]} to {n[4]}). Each model is fitted on the previous "
           f"{wf['window_days']} trading days only; forecast dates every ~{wf['step_days']} trading days.\n",
           "Loss: CRPS of the forecast distribution of the log return (lower is better). *Skill* = "
           "1 − CRPS ÷ CRPS of the group's baseline. A model replaces the baseline only with positive skill and "
           f"a Diebold–Mariano t at least the Bonferroni-corrected 5% level for the number of candidates "
           f"(≈ 2.73 for 8; Newey–West, small-sample corrected).\n"]
    for gt, title in (("all", "All companies"), ("market_class", "By market class"), ("cell", "By cell (market class × sector group)"),
                      ("sector_group", "By sector group"), ("exchange", "By exchange")):
        out.append(f"## {title}\n")
        out.append("| Group | Horizon | Baseline | Selected | Basis | Lowest CRPS | Dates | Stocks |")
        out.append("|---|---|---|---|---|---|---|---|")
        for r in ch:
            if r["group_type"] == gt:
                out.append(f"| {_g(r['group_key'])} | {r['horizon']} | {r['baseline_name']} | **{r['selected_name']}** | "
                           f"{r['basis']} | {zoo.name(r['best_raw'])} | {r['n_origins']} | {r['n_stocks']} |")
        out.append("")
    for hn in wf["horizons"]:
        out.append(f"## Model table, all companies, {hn}\n")
        out.append("| Model | Mean CRPS | Skill vs baseline | DM t | Direction hit | 90% coverage | Bias (log) |")
        out.append("|---|---|---|---|---|---|---|")
        for r in sorted((x for x in lb if x["group_type"] == "all" and x["horizon"] == hn), key=lambda x: x["crps"]):
            dm = "—" if r["dm_t"] is None else f"{r['dm_t']:.2f}"
            out.append(f"| {r['model_name']}{' (baseline)' if r['is_baseline'] else ''} | {r['crps']:.4f} | "
                       f"{_pct(r['skill'])} | {dm} | {r['hit']:.0%} | {r['cover90']:.0%} | {r['bias']:+.3f} |")
        out.append("")
    comp = [r for r in ch if r["group_type"] == "company"]
    if comp:
        out.append("## Companies\n")
        for hn in wf["horizons"]:
            c = [r for r in comp if r["horizon"] == hn]
            promo = [r for r in c if r["selected"] != r["baseline"]]
            counts = {}
            for r in promo:
                counts[r["selected_name"]] = counts.get(r["selected_name"], 0) + 1
            out.append(f"- {hn}: {len(promo)} of {len(c)} companies have a model that clearly beats their baseline "
                       f"({', '.join(f'{k} {v}' for k, v in sorted(counts.items(), key=lambda x: -x[1])) or 'none'}).")
        out.append("")
    if pt:
        out.append("## MPT vs 1/N inside each cell (quarterly rebalancing, US-dollar returns)\n")
        out.append("| Cell | Strategy | Quarters | Assets | Annual return | Volatility | Sharpe | Worst quarter | Sharpe-difference z |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for r in pt:
            z = "" if r["sharpe_diff_z"] is None else f"{r['sharpe_diff_z']:+.2f}"
            sh = "—" if r["sharpe"] is None else f"{r['sharpe']:.2f}"
            out.append(f"| {_g(r['cell'])} | {r['strategy']} | {r['quarters']} | {r['avg_assets']:.0f} | {_pct(r['cagr'])} | "
                       f"{r['vol']:.1%} | {sh} | {_pct(r['worst_quarter'])} | {z} |")
        out.append("\nz > 1.96 would mean MPT's Sharpe ratio is clearly higher than 1/N's; z < −1.96 clearly lower.\n")
    out.append("Caveats: the universe is today's largest companies (survivorship lifts every model's past results "
               "equally); forecasts extrapolate the last five years; research output, not investment advice.\n")
    return "\n".join(out)
