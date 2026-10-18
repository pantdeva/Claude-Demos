"""FinBERT sentiment for news items, using the NumPy implementation from the earlier
analyzer (same weights as ProsusAI/finbert, no PyTorch needed). Score = P(positive) −
P(negative), from −1 to +1. Weights are looked up in $SFA_FINBERT_DIR, then
db/models/finbert, and downloaded from Hugging Face on first use (~440 MB)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

from ..config import ROOT, load
from ..db import now
from . import init

_QUANT = Path(__file__).resolve().parents[3] / "nlp_stock_analyzer"
if str(_QUANT) not in sys.path:
    sys.path.insert(0, str(_QUANT))

FILES = ("config.json", "vocab.txt", "model.safetensors")
_scorer = None


def model_dir() -> Path:
    cfg = load("finder")["news"]["finbert"]
    env = os.environ.get(cfg["dir_env"])
    d = Path(env) if env else ROOT / cfg["default_dir"]
    if all((d / f).exists() for f in FILES):
        return d
    d.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        if (d / f).exists():
            continue
        url = f"https://huggingface.co/{cfg['hf_repo']}/resolve/main/{f}"
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            tmp = d / (f + ".part")
            with open(tmp, "wb") as out:
                for chunk in r.iter_content(1 << 20):
                    out.write(chunk)
            tmp.rename(d / f)
    return d


def scorer():
    global _scorer
    if _scorer is None:
        from stock_analyzer.finbert_numpy import NumpyFinBERTScorer
        cfg = load("finder")["news"]["finbert"]
        _scorer = NumpyFinBERTScorer(model_dir(), batch_size=cfg["batch_size"], max_length=cfg["max_length"])
    return _scorer


def text_of(title: str, summary: str | None) -> str:
    t = (title or "").strip()
    s = (summary or "").strip()
    return f"{t}. {s[:300]}" if s and s.lower() != t.lower() else t


def score_pending(con, limit: int = 5000, log=print) -> dict:
    """Score unscored items published inside twice the news window (older ones are
    not used by the rules), shortest first so batches need little padding."""
    init(con)
    from datetime import datetime, timedelta, timezone
    days = load("finder")["news"]["lookback_days"] * 2
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = con.execute("""SELECT n.id, n.title, n.summary FROM news_items n
                          LEFT JOIN news_sentiment s ON s.news_id=n.id WHERE s.news_id IS NULL
                          AND (COALESCE(n.published, n.fetched) >= ?
                               OR EXISTS (SELECT 1 FROM ipo_events e WHERE e.news_id=n.id))
                          ORDER BY n.published DESC LIMIT ?""", (cut, limit)).fetchall()
    if not rows:
        return {"scored": 0}
    rows = sorted(rows, key=lambda r: len(text_of(r["title"], r["summary"])))
    sc = scorer()
    bs = load("finder")["news"]["finbert"]["batch_size"]
    for k in range(0, len(rows), bs):
        chunk = rows[k:k + bs]
        res = sc.score([text_of(r["title"], r["summary"]) for r in chunk])
        con.executemany("INSERT OR REPLACE INTO news_sentiment VALUES (?,?,?,?,?,?,?)",
                        [(r["id"], s.positive, s.negative, s.neutral, s.score, "finbert-numpy", now())
                         for r, s in zip(chunk, res)])
        if (k // bs) % 10 == 9:
            con.commit()
            log(f"  FinBERT {k + len(chunk)}/{len(rows)}")
    con.commit()
    return {"scored": len(rows)}
