"""Stage 2: company analyzer (Module 13 integrated financial model and valuation)."""

from __future__ import annotations


def run(con, symbols: list[str] | None = None, log=print) -> dict:
    """Analyse the given symbols, or the top listed leads and new listings."""
    from ..config import EXPORT_DIR, load
    from . import report
    from .analyze import analyze
    cfg = load("analyzer")["run"]
    if not symbols:
        symbols = [r["symbol"] for r in con.execute(
            "SELECT symbol FROM finder_leads WHERE status='active' AND kind='listed' AND score IS NOT NULL "
            "ORDER BY score DESC LIMIT ?", (cfg["top_leads"],))]
        if cfg.get("include_new_listings"):
            symbols += [r["symbol"] for r in con.execute(
                "SELECT symbol FROM finder_leads WHERE status='active' AND kind='new_listing' AND symbol IS NOT NULL")]
    results = []
    for k, s in enumerate(symbols, 1):
        try:
            o = analyze(con, s)
        except Exception as e:  # noqa: BLE001 - one company must not stop the batch
            o = {"symbol": s, "error": f"{type(e).__name__}: {e}"}
        report.write(o)
        results.append(o)
        log(f"  analysed {k}/{len(symbols)} {s}: {o.get('verdict', o.get('error'))}")
    if results:
        report.summary_csv(results, EXPORT_DIR / "analysis_summary.csv")
    return {"analysed": len(results), "errors": sum(1 for o in results if o.get("error")),
            "verdicts": {v: sum(1 for o in results if o.get("verdict") == v) for v in
                         ("Undervalued", "Fairly valued", "Overvalued", "No verdict")}}
