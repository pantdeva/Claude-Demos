"""FinBERT sentiment scoring (ProsusAI/finbert on Hugging Face).

Each text gets probabilities for positive / negative / neutral; the score is
P(positive) - P(negative), so it runs from -1 (very negative) to +1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

DEFAULT_MODEL = "ProsusAI/finbert"


@dataclass(frozen=True)
class Sentiment:
    positive: float
    negative: float
    neutral: float

    @property
    def score(self) -> float:
        return self.positive - self.negative

    @property
    def label(self) -> str:
        best = max(("positive", self.positive), ("negative", self.negative),
                   ("neutral", self.neutral), key=lambda kv: kv[1])
        return best[0]


class SentimentScorer(Protocol):
    def score(self, texts: Sequence[str]) -> list[Sentiment]: ...


class FinBERTScorer:
    """Loads the model once; downloads it on first use (~440 MB)."""

    def __init__(self, model_name: str = DEFAULT_MODEL, batch_size: int = 16,
                 device: int | str | None = None):
        from transformers import pipeline  # imported lazily: heavy dependency

        if device is None:
            try:
                import torch
                device = 0 if torch.cuda.is_available() else -1
            except ImportError:
                device = -1
        self.batch_size = batch_size
        self._pipe = pipeline("text-classification", model=model_name, tokenizer=model_name,
                              top_k=None, truncation=True, max_length=512, device=device)

    def score(self, texts: Sequence[str]) -> list[Sentiment]:
        if not texts:
            return []
        raw = self._pipe(list(texts), batch_size=self.batch_size)
        out = []
        for scores in raw:
            if isinstance(scores, dict):  # single-label output shape
                scores = [scores]
            probs = {s["label"].lower(): float(s["score"]) for s in scores}
            out.append(Sentiment(probs.get("positive", 0.0), probs.get("negative", 0.0),
                                 probs.get("neutral", 0.0)))
        return out
