"""Command-line run of the analyzer (no Streamlit needed).

Examples:
  python run.py NVDA TATASTEEL.NS --days 7
  python run.py NVDA --scorer numpy --model-dir ./finbert   # no PyTorch needed
  python run.py --all --out results/

Writes <out>/<ticker>.json (scores) and <out>/<ticker>_articles.csv per ticker.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stock_analyzer import Analyzer, load_config
from stock_analyzer.analyzer import AnalysisResult
from stock_analyzer.news import NewsAPIClient, NewsAPIError

ROOT = Path(__file__).parent


def make_scorer(kind: str, model_dir: str | None):
    if kind == "numpy":
        if not model_dir:
            sys.exit("--scorer numpy needs --model-dir with config.json, vocab.txt, model.safetensors")
        from stock_analyzer.finbert_numpy import NumpyFinBERTScorer
        return NumpyFinBERTScorer(model_dir)
    from stock_analyzer.sentiment import FinBERTScorer
    return FinBERTScorer(model_dir or "ProsusAI/finbert")


def summary(result: AnalysisResult, weights, settings) -> dict:
    comp = result.composite(weights)
    return {
        "ticker": result.company.ticker,
        "name": result.company.name,
        "market": result.company.market,
        "window_utc": [result.start.isoformat(), result.end.isoformat()],
        "composite": comp,
        "verdict": AnalysisResult.verdict(comp, settings),
        "factors": {k: {"label": f.label, "score": f.score, "articles": f.n_articles}
                    for k, f in result.factors.items()},
        "warnings": result.warnings,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tickers", nargs="*")
    ap.add_argument("--all", action="store_true", help="analyse every company in the config")
    ap.add_argument("--days", type=int)
    ap.add_argument("--config", default=str(ROOT / "config" / "companies.yaml"))
    ap.add_argument("--scorer", choices=["finbert", "numpy"], default="finbert")
    ap.add_argument("--model-dir")
    ap.add_argument("--out", default=str(ROOT / "results"))
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    tickers = list(cfg.companies) if args.all or not args.tickers else args.tickers
    unknown = [t for t in tickers if t not in cfg.companies]
    if unknown:
        sys.exit(f"Not in config: {', '.join(unknown)}")

    try:
        client = NewsAPIClient()
    except NewsAPIError as exc:
        sys.exit(str(exc))
    analyzer = Analyzer(client, make_scorer(args.scorer, args.model_dir), cfg.settings)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    status = 0
    for t in tickers:
        try:
            result = analyzer.run(cfg.companies[t], args.days)
        except NewsAPIError as exc:
            print(f"{t}: {exc}", file=sys.stderr)
            status = 1
            continue
        s = summary(result, cfg.settings.weights, cfg.settings)
        safe = t.replace("/", "_")
        (out / f"{safe}.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
        result.articles_frame().to_csv(out / f"{safe}_articles.csv", index=False)
        fmt = lambda v: "  n/a" if v is None else f"{v:+.2f}"
        print(f"\n{result.company.label}: composite {fmt(s['composite'])} → {s['verdict']}")
        for f in result.factors.values():
            print(f"  {f.label:<30} {fmt(f.score)}  ({f.n_articles} articles)")
        for w in result.warnings:
            print(f"  warning: {w}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
