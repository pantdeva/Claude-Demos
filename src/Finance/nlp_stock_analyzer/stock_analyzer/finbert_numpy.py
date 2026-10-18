"""FinBERT in pure NumPy: same weights and outputs as the transformers model,
without PyTorch. Useful where PyTorch can't be installed.

Needs the model folder (config.json, vocab.txt, model.safetensors) from
https://huggingface.co/ProsusAI/finbert, and numpy (+ scipy for exact GELU).
"""

from __future__ import annotations

import json
import struct
import unicodedata
from pathlib import Path
from typing import Sequence

import numpy as np

from .sentiment import Sentiment

try:
    from scipy.special import erf as _erf
except ImportError:  # tanh approximation; differs from exact GELU by ~1e-3
    _erf = None

_DTYPES = {"F32": np.float32, "F16": np.float16, "BF16": None, "I64": np.int64}


def load_safetensors(path: str | Path) -> dict[str, np.ndarray]:
    data = Path(path).read_bytes()
    (n,) = struct.unpack("<Q", data[:8])
    header = json.loads(data[8:8 + n])
    base = 8 + n
    out = {}
    for name, meta in header.items():
        if name == "__metadata__":
            continue
        start, end = meta["data_offsets"]
        raw = data[base + start: base + end]
        if meta["dtype"] == "BF16":
            u16 = np.frombuffer(raw, dtype=np.uint16).astype(np.uint32) << 16
            arr = u16.view(np.float32)
        else:
            arr = np.frombuffer(raw, dtype=_DTYPES[meta["dtype"]])
        out[name] = arr.reshape(meta["shape"]).astype(np.float32)
    return out


# ---------------- Tokenizer (BERT uncased WordPiece) ----------------

def _is_punct(ch: str) -> bool:
    cp = ord(ch)
    if 33 <= cp <= 47 or 58 <= cp <= 64 or 91 <= cp <= 96 or 123 <= cp <= 126:
        return True
    return unicodedata.category(ch).startswith("P")


def _is_cjk(cp: int) -> bool:
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0x20000 <= cp <= 0x2A6DF
            or 0x2A700 <= cp <= 0x2B73F or 0x2B740 <= cp <= 0x2B81F or 0x2B820 <= cp <= 0x2CEAF
            or 0xF900 <= cp <= 0xFAFF or 0x2F800 <= cp <= 0x2FA1F)


class WordPieceTokenizer:
    def __init__(self, vocab_path: str | Path):
        tokens = Path(vocab_path).read_text(encoding="utf-8").splitlines()
        self.vocab = {t: i for i, t in enumerate(tokens)}
        self.cls, self.sep = self.vocab["[CLS]"], self.vocab["[SEP]"]
        self.pad, self.unk = self.vocab["[PAD]"], self.vocab["[UNK]"]

    def _basic(self, text: str) -> list[str]:
        cleaned = []
        for ch in text:
            cp = ord(ch)
            if cp == 0 or cp == 0xFFFD or (unicodedata.category(ch).startswith("C") and ch not in "\t\n\r"):
                continue
            if ch in "\t\n\r" or unicodedata.category(ch) == "Zs":
                cleaned.append(" ")
            elif _is_cjk(cp):
                cleaned.append(f" {ch} ")
            else:
                cleaned.append(ch)
        words = []
        for word in "".join(cleaned).lower().split():
            word = "".join(c for c in unicodedata.normalize("NFD", word)
                           if unicodedata.category(c) != "Mn")
            buf = ""
            for ch in word:
                if _is_punct(ch):
                    if buf:
                        words.append(buf)
                        buf = ""
                    words.append(ch)
                else:
                    buf += ch
            if buf:
                words.append(buf)
        return words

    def _wordpiece(self, word: str) -> list[int]:
        if len(word) > 100:
            return [self.unk]
        ids, start = [], 0
        while start < len(word):
            end, found = len(word), None
            while start < end:
                piece = word[start:end] if start == 0 else "##" + word[start:end]
                if piece in self.vocab:
                    found = self.vocab[piece]
                    break
                end -= 1
            if found is None:
                return [self.unk]
            ids.append(found)
            start = end
        return ids

    def encode(self, text: str, max_length: int = 512) -> list[int]:
        ids = [i for w in self._basic(text) for i in self._wordpiece(w)]
        return [self.cls] + ids[: max_length - 2] + [self.sep]


# ---------------- Model ----------------

def _layer_norm(x, g, b, eps):
    mu = x.mean(-1, keepdims=True)
    var = ((x - mu) ** 2).mean(-1, keepdims=True)
    return (x - mu) / np.sqrt(var + eps) * g + b


def _gelu(x):
    if _erf is not None:
        return 0.5 * x * (1.0 + _erf(x / np.sqrt(2.0)))
    return 0.5 * x * (1.0 + np.tanh(np.sqrt(2 / np.pi) * (x + 0.044715 * x ** 3)))


class NumpyFinBERTScorer:
    """Drop-in replacement for FinBERTScorer that needs only NumPy."""

    def __init__(self, model_dir: str | Path, batch_size: int = 16, max_length: int = 128):
        model_dir = Path(model_dir)
        self.cfg = json.loads((model_dir / "config.json").read_text())
        self.tok = WordPieceTokenizer(model_dir / "vocab.txt")
        self.w = load_safetensors(model_dir / "model.safetensors")
        self.batch_size, self.max_length = batch_size, max_length
        id2label = {int(k): v.lower() for k, v in self.cfg["id2label"].items()}
        self.labels = [id2label[i] for i in range(len(id2label))]

    def _p(self, name):
        w = self.w
        for cand in (name, name.replace(".weight", ".gamma").replace(".bias", ".beta")):
            if cand in w:
                return w[cand]
        raise KeyError(name)

    def _lin(self, x, prefix):
        return x @ self._p(prefix + ".weight").T + self._p(prefix + ".bias")

    def _ln(self, x, prefix):
        return _layer_norm(x, self._p(prefix + ".weight"), self._p(prefix + ".bias"),
                           self.cfg.get("layer_norm_eps", 1e-12))

    def logits(self, texts: Sequence[str]) -> np.ndarray:
        enc = [self.tok.encode(t, self.max_length) for t in texts]
        L = max(len(e) for e in enc)
        ids = np.full((len(enc), L), self.tok.pad, dtype=np.int64)
        mask = np.zeros((len(enc), L), dtype=np.float32)
        for i, e in enumerate(enc):
            ids[i, :len(e)], mask[i, :len(e)] = e, 1.0

        e = "bert.embeddings."
        x = (self._p(e + "word_embeddings.weight")[ids]
             + self._p(e + "position_embeddings.weight")[:L][None]
             + self._p(e + "token_type_embeddings.weight")[0][None, None])
        x = self._ln(x, e + "LayerNorm")

        H = self.cfg["num_attention_heads"]
        B, _, D = x.shape
        d = D // H
        add_mask = (1.0 - mask)[:, None, None, :] * -1e9
        for i in range(self.cfg["num_hidden_layers"]):
            p = f"bert.encoder.layer.{i}."
            q = self._lin(x, p + "attention.self.query").reshape(B, L, H, d).transpose(0, 2, 1, 3)
            k = self._lin(x, p + "attention.self.key").reshape(B, L, H, d).transpose(0, 2, 1, 3)
            v = self._lin(x, p + "attention.self.value").reshape(B, L, H, d).transpose(0, 2, 1, 3)
            s = q @ k.transpose(0, 1, 3, 2) / np.sqrt(d) + add_mask
            s = np.exp(s - s.max(-1, keepdims=True))
            s /= s.sum(-1, keepdims=True)
            ctx = (s @ v).transpose(0, 2, 1, 3).reshape(B, L, D)
            x = self._ln(self._lin(ctx, p + "attention.output.dense") + x, p + "attention.output.LayerNorm")
            h = _gelu(self._lin(x, p + "intermediate.dense"))
            x = self._ln(self._lin(h, p + "output.dense") + x, p + "output.LayerNorm")

        pooled = np.tanh(self._lin(x[:, 0], "bert.pooler.dense"))
        return self._lin(pooled, "classifier")

    def score(self, texts: Sequence[str]) -> list[Sentiment]:
        out = []
        for i in range(0, len(texts), self.batch_size):
            z = self.logits(texts[i:i + self.batch_size])
            z = np.exp(z - z.max(-1, keepdims=True))
            probs = z / z.sum(-1, keepdims=True)
            for row in probs:
                p = dict(zip(self.labels, row.tolist()))
                out.append(Sentiment(p.get("positive", 0.0), p.get("negative", 0.0),
                                     p.get("neutral", 0.0)))
        return out
